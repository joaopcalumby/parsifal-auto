"""Testes da recuperação de resumo fora do Parsifal, sem tocar na rede."""

import pytest

from triagem.resumo_externo import enderecos_possiveis, extrair_resumo

RESUMO_LONGO = (
    "This paper presents a federated learning framework for training models on edge devices, "
    "evaluated on non-IID benchmarks with accuracy and communication cost reported against baselines."
)


class TestExtrairResumo:
    def test_prefere_a_meta_tag_do_publicador(self):
        html = f"""
        <html><head>
          <meta name="citation_abstract" content="{RESUMO_LONGO}">
          <meta property="og:description" content="Página do periódico, menu e rodapé.">
        </head><body><p>lixo de navegação</p></body></html>
        """
        assert extrair_resumo(html) == RESUMO_LONGO

    def test_cai_para_og_description_quando_nao_ha_citation_abstract(self):
        html = f'<html><head><meta property="og:description" content="{RESUMO_LONGO}"></head></html>'
        assert extrair_resumo(html) == RESUMO_LONGO

    def test_cai_para_bloco_de_abstract_na_pagina(self):
        html = f'<html><body><div class="abstract"><h2>Abstract</h2><p>{RESUMO_LONGO}</p></div></body></html>'
        assert extrair_resumo(html) == RESUMO_LONGO

    def test_descarta_texto_curto_demais_para_ser_resumo(self):
        html = '<html><head><meta name="description" content="Springer Nature"></head></html>'
        assert extrair_resumo(html) == ""

    def test_pagina_sem_resumo_devolve_vazio(self):
        assert extrair_resumo("<html><body><p>Access denied</p></body></html>") == ""

    def test_remove_o_rotulo_abstract_do_inicio(self):
        html = f'<html><body><div id="abstract">Abstract: {RESUMO_LONGO}</div></body></html>'
        assert extrair_resumo(html) == RESUMO_LONGO


class TestEnderecosPossiveis:
    def test_tenta_url_antes_do_doi(self):
        assert enderecos_possiveis("https://ieee.org/artigo", "10.1000/x") == [
            ("https://ieee.org/artigo", "url"),
            ("https://doi.org/10.1000/x", "doi"),
        ]

    def test_desfaz_o_escape_de_underscore_que_vem_do_bibtex(self):
        """O Parsifal guarda o DOI como veio do BibTeX, com `\\_` no lugar de `_`."""
        assert enderecos_possiveis(doi=r"10.1007/978-3-030-86337-1\_14") == [
            ("https://doi.org/10.1007/978-3-030-86337-1_14", "doi")
        ]

    @pytest.mark.parametrize("url, doi", [("", ""), ("   ", "  ")])
    def test_sem_endereco_nao_ha_o_que_tentar(self, url, doi):
        assert enderecos_possiveis(url, doi) == []
