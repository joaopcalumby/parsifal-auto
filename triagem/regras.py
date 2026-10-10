"""Regras da ETAPA 1: a automação sinaliza, o revisor decide.

A ETAPA 1 lê **título, palavras-chave e resumo**. É o campo lido que define a etapa, não quem
decide: por isso sobraram aqui só as três exclusões que se reconhecem pelo próprio vocabulário do
texto (estudo secundário, literatura cinza, fora do domínio).

Estudo secundário e literatura cinza valem para qualquer tema e moram aqui. O vocabulário do
domínio e do recorte é de cada revisão e vem do `config/revisoes.json`, como um `Vocabulario`.

Idioma e páginas são calculados, mas viram **nota para a ETAPA 2**, fora da decisão desta etapa:
os dois só se confirmam com o arquivo aberto.

Nenhuma regra aqui exclui estudo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

# langdetect é probabilístico e varia entre execuções sem semente fixa.
DetectorFactory.seed = 0

SINALIZAR = "SINALIZAR"
MANTER = "MANTER"
SEM_RESUMO = "SEM_RESUMO"

CRITERIO_IDIOMA = "ETAPA 2 - Estudo em idioma distinto do inglês"
CRITERIO_SHORT_PAPER = "ETAPA 2 - Short-paper: estudo com menos de 5 páginas"
CRITERIO_SECUNDARIO = "ETAPA 1 - Estudo secundário (revisão, survey ou mapeamento sistemático)"
CRITERIO_CINZA = (
    "ETAPA 1 - Literatura cinza (preprint não publicado, relatório técnico, tese não indexada)"
)
CRITERIO_DOMINIO = "ETAPA 1 - Estudo fora do domínio da revisão"
CRITERIO_RECORTE = "ETAPA 1 - Título, resumo ou palavras-chave indicam o recorte da revisão"

MINIMO_DE_PAGINAS = 5
CONFIANCA_MINIMA_DE_IDIOMA = 0.90
CARACTERES_MINIMOS_PARA_DETECTAR_IDIOMA = 80

TERMOS_ESTUDO_SECUNDARIO = (
    "systematic review",
    "systematic literature review",
    "systematic mapping",
    "mapping study",
    "literature review",
    "state of the art",
    "state-of-the-art review",
    "a survey",
    "survey of",
    "survey on",
    "review of the literature",
)

TERMOS_LITERATURA_CINZA = (
    "arxiv",
    "preprint",
    "technical report",
    "tech report",
    "working paper",
    "master's thesis",
    "phd thesis",
    "dissertation",
    "biorxiv",
)

@dataclass(frozen=True)
class Vocabulario:
    """O vocabulário de uma revisão, lido do `config/revisoes.json`.

    `dominio` são os termos que, sozinhos, provam que o estudo é do tema. `siglas_ambiguas` são
    siglas do tema que também nomeiam outra coisa: contam como termo do tema, mas não como prova,
    porque é justamente quando a sigla é a única marca do tema que o estudo precisa ser olhado.
    `colisao` é o vocabulário da outra área com que a sigla colide. `recorte` são os termos que
    delimitam a revisão dentro do tema.

    Lista vazia desliga o sinal correspondente.
    """

    dominio: tuple[str, ...] = ()
    siglas_ambiguas: tuple[str, ...] = ()
    colisao: tuple[str, ...] = ()
    recorte: tuple[str, ...] = ()

    @classmethod
    def da_revisao(cls, revisao: dict) -> Vocabulario:
        def termos(chave: str) -> tuple[str, ...]:
            return tuple(termo.lower() for termo in revisao.get(chave, ()))

        return cls(
            dominio=termos("termos_dominio"),
            siglas_ambiguas=termos("siglas_ambiguas"),
            colisao=termos("termos_colisao"),
            recorte=termos("termos_recorte"),
        )


@dataclass(frozen=True)
class Sinal:
    """Motivo pelo qual um estudo merece olhar humano, sem decidir por ele."""

    criterio: str
    evidencia: str


@dataclass
class Decisao:
    """Resultado da ETAPA 1 para um estudo.

    `sinais` é o que se decide nesta etapa. `notas` é o que já se sabe e só será decidido na ETAPA 2,
    separado para não competir com a leitura de agora.
    """

    acao: str
    criterio: str = ""
    motivo: str = ""
    sinais: list[Sinal] = field(default_factory=list)
    notas: list[Sinal] = field(default_factory=list)
    recorte_em: str = ""

    @property
    def sinais_em_texto(self) -> str:
        return _em_texto(self.sinais)

    @property
    def notas_em_texto(self) -> str:
        return _em_texto(self.notas)


def _em_texto(sinais: list[Sinal]) -> str:
    return " | ".join(f"{sinal.criterio.split(' - ')[-1]}: {sinal.evidencia}" for sinal in sinais)


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


def _encontrar(termos: tuple[str, ...], texto: str) -> list[str]:
    """Casa termo inteiro, não pedaço de palavra: uma sigla não pode casar dentro de outra palavra."""
    return [termo for termo in termos if re.search(rf"\b{re.escape(termo)}\b", texto)]


def _normalizar(*campos: str | None) -> str:
    return re.sub(r"\s+", " ", " ".join(campo or "" for campo in campos)).lower()


def levantar_sinais(
    titulo: str,
    resumo: str,
    palavras_chave: str,
    fonte: str,
    vocabulario: Vocabulario,
) -> list[Sinal]:
    """As três exclusões e as duas inclusões que a ETAPA 1 decide, sobre os três campos dela.

    Palavras-chave entram na leitura porque a busca costuma rodar em `TITLE-ABS-KEY`: sem elas a
    automação enxergaria menos que a própria busca enxergou, e "termo ausente" mediria a pobreza do
    export.
    """
    texto = _normalizar(titulo, resumo, palavras_chave)
    texto_com_fonte = _normalizar(titulo, resumo, palavras_chave, fonte)
    sinais: list[Sinal] = []

    secundarios = _encontrar(TERMOS_ESTUDO_SECUNDARIO, texto)
    if secundarios:
        sinais.append(Sinal(CRITERIO_SECUNDARIO, ", ".join(secundarios)))

    cinza = _encontrar(TERMOS_LITERATURA_CINZA, texto_com_fonte)
    if cinza:
        sinais.append(Sinal(CRITERIO_CINZA, ", ".join(cinza)))

    prova_do_dominio = _encontrar(vocabulario.dominio, texto)
    colisao = _encontrar(vocabulario.colisao, texto)
    if colisao and not prova_do_dominio:
        sinais.append(Sinal(CRITERIO_DOMINIO, ", ".join(colisao)))

    termos_do_dominio = vocabulario.dominio + vocabulario.siglas_ambiguas
    if termos_do_dominio and not _encontrar(termos_do_dominio, texto):
        sinais.append(Sinal(CRITERIO_DOMINIO, "nenhum termo do domínio nos três campos"))

    if vocabulario.recorte and not _encontrar(vocabulario.recorte, texto):
        sinais.append(Sinal(CRITERIO_RECORTE, "nenhum termo do recorte nos três campos"))

    return sinais


def sinal_de_idioma_declarado(idioma: str) -> Sinal | None:
    """Usa o campo `language` do registro, quando ele existe.

    Vale mais que a detecção: um artigo em russo costuma trazer resumo em inglês, e a detecção sobre
    o resumo diria inglês. Foi o que aconteceu num lote real.
    """
    declarado = (idioma or "").strip()
    if not declarado or declarado.lower() in ("english", "en", "eng", "inglês", "ingles"):
        return None

    return Sinal(CRITERIO_IDIOMA, f"registro declara idioma {declarado}")


def _contar_mencoes(termos: tuple[str, ...], texto: str) -> int:
    """Conta menções, não casamentos de termo.

    Sinônimos do mesmo recorte se sobrepõem: "edge device level" casa com `edge device` e com
    `device level`, e é uma menção só. Contar duas inflaria justamente o número que separa menção de
    foco.
    """
    trechos = sorted(
        (achado.span() for termo in termos for achado in re.finditer(rf"\b{re.escape(termo)}\b", texto)),
    )

    mencoes, fim_anterior = 0, -1
    for inicio, fim in trechos:
        if inicio >= fim_anterior:
            mencoes += 1
        fim_anterior = max(fim_anterior, fim)

    return mencoes


def localizacao_do_recorte(
    titulo: str,
    resumo: str,
    palavras_chave: str,
    termos_recorte: tuple[str, ...] | list[str],
) -> str:
    """Onde o termo do recorte aparece, e quantas vezes no resumo.

    Não decide nada: é ordenação para a ETAPA 2, onde costuma pesar "o recorte é o foco declarado
    ou só mencionado". Recorte no título é indício forte de foco; uma aparição solta no resumo é
    indício de menção.
    """
    termos = tuple(termos_recorte)
    onde = []

    if _encontrar(termos, _normalizar(titulo)):
        onde.append("título")
    if _encontrar(termos, _normalizar(palavras_chave)):
        onde.append("palavras-chave")

    ocorrencias = _contar_mencoes(termos, _normalizar(resumo))
    if ocorrencias:
        onde.append(f"resumo ({ocorrencias}x)")

    return ", ".join(onde) if onde else "ausente"


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
    fonte: str,
    paginas: str | None,
    vocabulario: Vocabulario,
    idioma_declarado: str = "",
) -> Decisao:
    """Aplica a ETAPA 1 a um estudo.

    Três resultados possíveis, e nenhum deles exclui: passa limpo, volta com sinais para o revisor olhar,
    ou não é decidível aqui por não ter resumo.
    """
    notas = levantar_notas_da_etapa_2(titulo, resumo, paginas, idioma_declarado)
    recorte_em = localizacao_do_recorte(titulo, resumo, palavras_chave, vocabulario.recorte)

    if not (resumo or "").strip():
        return Decisao(
            acao=SEM_RESUMO,
            motivo="registro sem resumo: a ETAPA 1 não decide, segue para a ETAPA 2",
            notas=notas,
            recorte_em=recorte_em,
        )

    sinais = levantar_sinais(titulo, resumo, palavras_chave, fonte, vocabulario)
    if sinais:
        return Decisao(
            acao=SINALIZAR,
            motivo="requer decisão humana",
            sinais=sinais,
            notas=notas,
            recorte_em=recorte_em,
        )

    return Decisao(
        acao=MANTER, motivo="passa na ETAPA 1 sem ressalva", notas=notas, recorte_em=recorte_em
    )
