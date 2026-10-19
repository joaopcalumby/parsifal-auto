"""Regras da ETAPA 1: a string de busca decide, o revisor confere.

A ETAPA 1 lê **título, palavras-chave e resumo**, os mesmos três campos em que a busca rodou nas
bases, e o número de páginas do metadado. Quando a revisão configura um mínimo de páginas, o estudo
abaixo dele sai como short-paper. Os demais seguem a string: quem atende é aceito, quem tem resumo e
não atende é rejeitado, e quem não tem resumo nem atende vai para conferência manual, porque ali "não
atende" mediria a lacuna do registro, não o artigo.

O idioma é calculado, mas vira **nota para a ETAPA 2**, fora da decisão desta etapa: ele só se
confirma com o arquivo aberto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

from triagem.planilha import ACEITAR, REJEITAR
from triagem.string_de_busca import ErroNaString, StringDeBusca

# langdetect é probabilístico e varia entre execuções sem semente fixa.
DetectorFactory.seed = 0

# Desfechos da ETAPA 1. Os dois primeiros têm o mesmo texto da ação na planilha.
ATENDE = ACEITAR
NAO_ATENDE = REJEITAR
SHORT_PAPER = "short-paper"
MANUAL = "manual"

CRITERIO_IDIOMA = "ETAPA 2 - Estudo em idioma distinto do inglês"

CONFIANCA_MINIMA_DE_IDIOMA = 0.90
CARACTERES_MINIMOS_PARA_DETECTAR_IDIOMA = 80

CHAVES_OBRIGATORIAS = ("string", "criterio_de_aceite", "criterio_de_rejeicao")
CHAVES_DE_SHORT_PAPER = ("minimo_de_paginas", "criterio_de_short_paper")


@dataclass(frozen=True)
class Revisao:
    """Um bloco do `config/revisoes.json`: a string e o critério anexado a cada decisão.

    `minimo_de_paginas` é None quando a revisão não exclui short-paper na ETAPA 1.
    """

    nome: str
    string: StringDeBusca
    criterio_de_aceite: str
    criterio_de_rejeicao: str
    minimo_de_paginas: int | None = None
    criterio_de_short_paper: str = ""

    @classmethod
    def do_config(cls, bloco: dict) -> Revisao:
        faltando = [chave for chave in CHAVES_OBRIGATORIAS if not str(bloco.get(chave) or "").strip()]
        if faltando:
            raise ValueError(f"falta no bloco da revisão: {', '.join(faltando)}")

        try:
            string = StringDeBusca(bloco["string"])
        except ErroNaString as erro:
            raise ValueError(f"string: {erro}") from erro

        minimo_de_paginas, criterio_de_short_paper = _short_paper(bloco)
        return cls(
            nome=str(bloco.get("nome", "")),
            string=string,
            criterio_de_aceite=bloco["criterio_de_aceite"].strip(),
            criterio_de_rejeicao=bloco["criterio_de_rejeicao"].strip(),
            minimo_de_paginas=minimo_de_paginas,
            criterio_de_short_paper=criterio_de_short_paper,
        )

    def preenchimento(self, desfecho: str) -> tuple[str, str]:
        """A ação e o critério que a automação escreve na planilha.

        Conferência manual fica em branco.
        """
        return {
            ATENDE: (ACEITAR, self.criterio_de_aceite),
            NAO_ATENDE: (REJEITAR, self.criterio_de_rejeicao),
            SHORT_PAPER: (REJEITAR, self.criterio_de_short_paper),
        }.get(desfecho, ("", ""))


def _short_paper(bloco: dict) -> tuple[int | None, str]:
    """Lê o par opcional `minimo_de_paginas` e `criterio_de_short_paper`: os dois, ou nenhum."""
    presentes = [chave for chave in CHAVES_DE_SHORT_PAPER if bloco.get(chave) not in (None, "")]
    if not presentes:
        return None, ""
    if len(presentes) != len(CHAVES_DE_SHORT_PAPER):
        raise ValueError(
            "short-paper exige as duas chaves juntas: minimo_de_paginas e criterio_de_short_paper"
        )

    minimo = bloco["minimo_de_paginas"]
    if isinstance(minimo, bool) or not isinstance(minimo, int) or minimo < 1:
        raise ValueError(f"minimo_de_paginas deve ser um inteiro positivo, recebido: {minimo!r}")

    return minimo, str(bloco["criterio_de_short_paper"]).strip()


@dataclass(frozen=True)
class Sinal:
    """Algo que a automação já sabe sobre o estudo e que só se decide na ETAPA 2."""

    criterio: str
    evidencia: str


@dataclass
class Decisao:
    """Resultado da ETAPA 1 para um estudo: o desfecho, a evidência e as notas da ETAPA 2."""

    desfecho: str
    evidencia: str
    notas: list[Sinal] = field(default_factory=list)

    @property
    def notas_em_texto(self) -> str:
        return " | ".join(f"{nota.criterio.split(' - ')[-1]}: {nota.evidencia}" for nota in self.notas)


def _limites(intervalo: str | None) -> tuple[int, int] | None:
    """Primeira e última página do campo `pages` do BibTeX, ou None se ele não for um intervalo."""
    texto = str(intervalo or "").strip().replace("--", "-").replace("–", "-").replace("—", "-")
    partes = [parte.strip() for parte in texto.split("-") if parte.strip()]
    if len(partes) != 2 or not all(parte.isdigit() for parte in partes):
        return None

    return int(partes[0]), int(partes[1])


def contar_paginas(intervalo: str | None) -> int | None:
    """Conta páginas a partir do campo `pages` do BibTeX.

    Devolve None quando o campo não permite contagem confiável: página solta, intervalo de página
    única, número de artigo eletrônico, campo vazio ou formato inesperado. None nunca exclui.
    """
    limites = _limites(intervalo)
    if limites is None or limites[1] <= limites[0]:
        return None

    inicio, fim = limites
    return fim - inicio + 1


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


def levantar_notas_da_etapa_2(titulo: str, resumo: str, idioma_declarado: str = "") -> list[Sinal]:
    """O que a automação já sabe e não decide agora: o idioma.

    Vai junto na planilha, em coluna própria, para poupar a conferência quando o estudo chegar na
    ETAPA 2 com o PDF aberto. O idioma declarado tem precedência sobre a detecção.
    """
    idioma = sinal_de_idioma_declarado(idioma_declarado) or sinal_de_idioma(titulo, resumo)
    return [idioma] if idioma else []


def triar(
    titulo: str,
    resumo: str,
    palavras_chave: str,
    paginas: str | None,
    revisao: Revisao,
    idioma_declarado: str = "",
) -> Decisao:
    """Aplica a ETAPA 1 a um estudo: páginas primeiro, depois a string; as notas vão junto."""
    resultado = revisao.string.avaliar(titulo, resumo, palavras_chave)
    notas = levantar_notas_da_etapa_2(titulo, resumo, idioma_declarado)

    if revisao.minimo_de_paginas:
        contagem = contar_paginas(paginas)
        if contagem is not None and contagem < revisao.minimo_de_paginas:
            evidencia = f"{contagem} páginas pelo metadado | {resultado.evidencia}"
            return Decisao(desfecho=SHORT_PAPER, evidencia=evidencia, notas=notas)

    if resultado.atende:
        desfecho = ATENDE
    elif (resumo or "").strip():
        desfecho = NAO_ATENDE
    else:
        desfecho = MANUAL

    return Decisao(desfecho=desfecho, evidencia=resultado.evidencia, notas=notas)
