"""Leitura dos estudos: a cópia local baixada do Parsifal, ou um BibTeX das bases."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

COLUNAS_EQUIVALENTES = {
    "id": ("id", "article_id", "article-id"),
    "bibtex_key": ("bibtex_key", "bibtex-key", "bibtexkey", "ID"),
    "titulo": ("title", "titulo", "Title"),
    "resumo": ("abstract", "resumo", "Abstract"),
    # A busca roda em TITLE-ABS-KEY: sem as palavras-chave a triagem lê menos que a busca leu.
    "palavras_chave": (
        "author_keywords",
        "keywords",
        "Author Keywords",
        "Keywords",
        "palavras_chave",
    ),
    "fonte": ("source", "journal", "booktitle", "fonte"),
    "paginas": ("pages", "paginas", "Pages"),
    "doi": ("doi", "DOI"),
    "url": ("url", "URL", "link"),
    "ano": ("year", "ano", "Year"),
    "idioma": ("idioma", "language", "Language"),
    # Vazio quando o resumo veio do próprio Parsifal; "url" ou "doi" quando foi buscado fora.
    "resumo_origem": ("resumo_origem",),
    "status": ("status", "Status"),
}


@dataclass
class Estudo:
    id: str = ""
    bibtex_key: str = ""
    titulo: str = ""
    resumo: str = ""
    palavras_chave: str = ""
    fonte: str = ""
    paginas: str = ""
    doi: str = ""
    url: str = ""
    ano: str = ""
    idioma: str = ""
    resumo_origem: str = ""
    status: str = ""

    @property
    def ja_classificado(self) -> bool:
        """Estudo já aceito, rejeitado ou marcado como duplicado não volta para a triagem."""
        return self.status.strip().upper() not in ("", "U", "UNCLASSIFIED", "NAN")


def _primeira_coluna_presente(linha: dict, nomes: tuple[str, ...]) -> str:
    for nome in nomes:
        if nome in linha and pd.notna(linha[nome]):
            return str(linha[nome]).strip()
    return ""


def _linha_para_estudo(linha: dict) -> Estudo:
    return Estudo(
        **{
            campo: _primeira_coluna_presente(linha, nomes)
            for campo, nomes in COLUNAS_EQUIVALENTES.items()
        }
    )


def carregar_csv(caminho: Path) -> list[Estudo]:
    """Lê o `estudos.csv` que o comando `baixar` monta a partir da tela de cada artigo.

    O parsif.al hospedado não tem export de resultados, então este arquivo é a cópia local dos
    campos que a ETAPA 1 precisa ler.
    """
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return [_linha_para_estudo(linha) for linha in csv.DictReader(arquivo)]


def carregar_export(caminho: Path) -> list[Estudo]:
    """Lê uma planilha de artigos, caso alguma instância do Parsifal ainda exporte uma."""
    quadro = pd.read_excel(caminho)
    return [_linha_para_estudo(linha) for linha in quadro.to_dict(orient="records")]


def carregar_bibtex(caminho: Path) -> list[Estudo]:
    """Lê um .bib exportado direto da base, que costuma trazer resumo mais completo."""
    import bibtexparser

    with caminho.open(encoding="utf-8") as arquivo:
        base = bibtexparser.load(arquivo)
    return [_linha_para_estudo(entrada) for entrada in base.entries]


def carregar(caminho: Path) -> list[Estudo]:
    sufixo = caminho.suffix.lower()
    if sufixo == ".bib":
        return carregar_bibtex(caminho)
    if sufixo == ".csv":
        return carregar_csv(caminho)
    return carregar_export(caminho)
