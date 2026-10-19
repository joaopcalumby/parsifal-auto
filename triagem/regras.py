"""Regras da ETAPA 1: a string de busca decide, o revisor confere.

A ETAPA 1 lê **título, palavras-chave e resumo**, os mesmos três campos em que a busca rodou nas
bases. A regra é uma só: o estudo que atende à string nesses campos é aceito, o que tem resumo e não
atende é rejeitado, e o que não tem resumo nem atende vai para conferência manual, porque ali "não
atende" mediria a lacuna do registro, não o artigo.

Idioma e páginas são calculados, mas viram **nota para a ETAPA 2**, fora da decisão desta etapa:
os dois só se confirmam com o arquivo aberto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

from triagem.planilha import ACEITAR, REJEITAR
from triagem.string_de_busca import ErroNaString, StringDeBusca

# langdetect é probabilístico e varia entre execuções sem semente fixa.
DetectorFactory.seed = 0

MANUAL = "manual"

CRITERIO_IDIOMA = "ETAPA 2 - Estudo em idioma distinto do inglês"
CRITERIO_SHORT_PAPER = "ETAPA 2 - Short-paper: estudo com menos de 5 páginas"

MINIMO_DE_PAGINAS = 5
CONFIANCA_MINIMA_DE_IDIOMA = 0.90
CARACTERES_MINIMOS_PARA_DETECTAR_IDIOMA = 80

CHAVES_OBRIGATORIAS = ("string", "criterio_de_aceite", "criterio_de_rejeicao")


@dataclass(frozen=True)
class Revisao:
    """Um bloco do `config/revisoes.json`: a string e o critério anexado a cada decisão."""

    nome: str
    string: StringDeBusca
    criterio_de_aceite: str
    criterio_de_rejeicao: str

    @classmethod
    def do_config(cls, bloco: dict) -> Revisao:
        faltando = [chave for chave in CHAVES_OBRIGATORIAS if not str(bloco.get(chave) or "").strip()]
        if faltando:
            raise ValueError(f"falta no bloco da revisão: {', '.join(faltando)}")

        try:
            string = StringDeBusca(bloco["string"])
        except ErroNaString as erro:
            raise ValueError(f"string: {erro}") from erro

        return cls(
            nome=str(bloco.get("nome", "")),
            string=string,
            criterio_de_aceite=bloco["criterio_de_aceite"].strip(),
            criterio_de_rejeicao=bloco["criterio_de_rejeicao"].strip(),
        )

    def criterio_de(self, acao: str) -> str:
        """O critério que vai junto da decisão da automação. Conferência manual não tem critério."""
        return {ACEITAR: self.criterio_de_aceite, REJEITAR: self.criterio_de_rejeicao}.get(acao, "")


@dataclass(frozen=True)
class Sinal:
    """Algo que a automação já sabe sobre o estudo e que só se decide na ETAPA 2."""

    criterio: str
    evidencia: str


@dataclass
class Decisao:
    """Resultado da ETAPA 1 para um estudo: a ação, a evidência da string e as notas da ETAPA 2."""

    acao: str
    evidencia: str
    notas: list[Sinal] = field(default_factory=list)

    @property
    def notas_em_texto(self) -> str:
        return " | ".join(f"{nota.criterio.split(' - ')[-1]}: {nota.evidencia}" for nota in self.notas)


def contar_paginas(intervalo: str | None) -> int | None:
    """Conta páginas a partir do campo `pages` do BibTeX.

    Devolve None quando o campo não permite contagem confiável - página única sem intervalo,
    número de artigo eletrônico, campo vazio ou formato inesperado. None nunca exclui: vira sinal.
    """
    if not intervalo:
        return None

    texto = str(intervalo).strip().replace("--", "-").replace("–", "-").replace("—", "-")
    if not texto:
        return None

    partes = [parte.strip() for parte in texto.split("-") if parte.strip()]
    numeros = [parte for parte in partes if parte.isdigit()]
    if len(numeros) != 2 or len(partes) != 2:
        return None

    inicio, fim = int(numeros[0]), int(numeros[1])
    if fim < inicio:
        return None

    return fim - inicio + 1


def sinal_de_paginas(intervalo: str | None) -> Sinal | None:
    """Aponta suspeita de short-paper a partir do metadado, sem decidir.

    O metadado erra e nem sempre existe, e a contagem de verdade sai do arquivo aberto pelo DOI.
    Só vira sinal quando o intervalo é legível e curto: campo ausente não diz nada e viraria ruído.
    """
    paginas = contar_paginas(intervalo)
    if paginas is None or paginas >= MINIMO_DE_PAGINAS:
        return None

    return Sinal(CRITERIO_SHORT_PAPER, f"metadado indica {paginas} páginas")


def sinal_de_idioma(titulo: str, resumo: str = "") -> Sinal | None:
    """Aponta suspeita de idioma diferente de inglês, sem decidir.

    Texto curto ou detecção ambígua não vira sinal: em vez de mandar o revisor conferir centenas de
    registros, aponta só o que a detecção afirma com confiança.
    """
    texto = f"{titulo or ''} {resumo or ''}".strip()
    if len(texto) < CARACTERES_MINIMOS_PARA_DETECTAR_IDIOMA:
        return None

    try:
        candidatos = detect_langs(texto)
    except LangDetectException:
        return None

    provavel = candidatos[0]
    if provavel.lang == "en" or provavel.prob < CONFIANCA_MINIMA_DE_IDIOMA:
        return None

    return Sinal(CRITERIO_IDIOMA, f"detectado {provavel.lang} (p={provavel.prob:.2f})")


def sinal_de_idioma_declarado(idioma: str) -> Sinal | None:
    """Usa o campo `language` do registro, quando ele existe.

    Vale mais que a detecção: um artigo em russo costuma trazer resumo em inglês, e a detecção sobre
    o resumo diria inglês. Foi o que aconteceu num lote real.
    """
    declarado = (idioma or "").strip()
    if not declarado or declarado.lower() in ("english", "en", "eng", "inglês", "ingles"):
        return None

    return Sinal(CRITERIO_IDIOMA, f"registro declara idioma {declarado}")


def levantar_notas_da_etapa_2(
    titulo: str,
    resumo: str,
    paginas: str | None,
    idioma_declarado: str = "",
) -> list[Sinal]:
    """O que a automação já sabe e não decide agora: idioma e contagem de páginas.

    Vai junto na planilha, em coluna própria, para poupar a conferência quando o estudo chegar na
    ETAPA 2 com o PDF aberto. O idioma declarado tem precedência sobre a detecção.
    """
    idioma = sinal_de_idioma_declarado(idioma_declarado) or sinal_de_idioma(titulo, resumo)
    return [nota for nota in (idioma, sinal_de_paginas(paginas)) if nota]


def triar(
    titulo: str,
    resumo: str,
    palavras_chave: str,
    paginas: str | None,
    revisao: Revisao,
    idioma_declarado: str = "",
) -> Decisao:
    """Aplica a ETAPA 1 a um estudo: a string decide, as notas vão junto."""
    resultado = revisao.string.avaliar(titulo, resumo, palavras_chave)
    notas = levantar_notas_da_etapa_2(titulo, resumo, paginas, idioma_declarado)

    if resultado.atende:
        acao = ACEITAR
    elif (resumo or "").strip():
        acao = REJEITAR
    else:
        acao = MANUAL

    return Decisao(acao=acao, evidencia=resultado.evidencia, notas=notas)
