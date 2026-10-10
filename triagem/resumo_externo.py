"""Busca o resumo na página do artigo quando o Parsifal não tem.

A ideia é comum em automações de triagem: abrir o link externo do registro e usar o texto da página
como resumo. Aqui a extração é por metadado da página (`citation_abstract`, `og:description` e
parentes) antes de cair para o texto solto: publicador sério declara o resumo em meta tag, e isso
evita trazer menu e rodapé junto.

O que **não** foi adotado: rejeitar o estudo quando a busca falha. Registro sem resumo continua
indo para a ETAPA 2, porque ausência de metadado não é propriedade do trabalho.
"""

from __future__ import annotations

import random
import re

import requests
from bs4 import BeautifulSoup

TEMPO_LIMITE = (5, 15)
TAMANHO_MINIMO = 150

NAVEGADORES = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
)

META_DE_RESUMO = (
    {"name": "citation_abstract"},
    {"name": "dc.description"},
    {"name": "DC.Description"},
    {"name": "dcterms.abstract"},
    {"property": "og:description"},
    {"name": "description"},
)

SEM_RESUMO = ""


def _limpar(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    return re.sub(r"^(abstract|resumo)[:\s.-]*", "", texto, flags=re.IGNORECASE).strip()


def extrair_resumo(html: str) -> str:
    """Tira o resumo de uma página de artigo, preferindo o que o publicador declara em meta tag."""
    sopa = BeautifulSoup(html, "html.parser")

    for atributos in META_DE_RESUMO:
        etiqueta = sopa.find("meta", attrs=atributos)
        if etiqueta and (conteudo := _limpar(etiqueta.get("content", ""))):
            if len(conteudo) >= TAMANHO_MINIMO:
                return conteudo

    for seletor in ("#abstract", ".abstract", "section.abstract", "div.abstractSection"):
        bloco = sopa.select_one(seletor)
        if bloco and (texto := _limpar(bloco.get_text(" "))):
            if len(texto) >= TAMANHO_MINIMO:
                return texto

    return SEM_RESUMO


def enderecos_possiveis(url: str = "", doi: str = "") -> list[tuple[str, str]]:
    """Por onde tentar, em ordem, com o rótulo que vai para a coluna de origem."""
    enderecos = []
    if url.strip():
        enderecos.append((url.strip(), "url"))
    if doi.strip():
        limpo = doi.strip().replace("\\_", "_")
        enderecos.append((f"https://doi.org/{limpo}", "doi"))
    return enderecos


def buscar_resumo(url: str = "", doi: str = "", sessao: requests.Session | None = None) -> tuple[str, str]:
    """Devolve `(resumo, origem)`. Origem vazia quando não deu para recuperar.

    Falha de rede aqui é resultado esperado, não erro: publicador bloqueia robô, e o estudo apenas
    segue sem resumo para a ETAPA 2.
    """
    cliente = sessao or requests
    for endereco, origem in enderecos_possiveis(url, doi):
        try:
            resposta = cliente.get(
                endereco,
                headers={"User-Agent": random.choice(NAVEGADORES)},
                allow_redirects=True,
                timeout=TEMPO_LIMITE,
            )
            if resposta.status_code != 200:
                continue
            if resumo := extrair_resumo(resposta.text):
                return resumo, origem
        except requests.RequestException:
            continue

    return SEM_RESUMO, ""
