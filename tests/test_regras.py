"""Testes das regras da ETAPA 1.

A decisão vem só da string de busca, a mesma colada nas bases. Idioma e páginas são calculados à
parte e viram nota para a ETAPA 2, sem pesar na decisão.

O tema dos exemplos é o mesmo do `config/revisoes.exemplo.json`: aprendizado federado em
dispositivos de borda.
"""

import json
from pathlib import Path

import pytest

from triagem import planilha, regras

RAIZ = Path(__file__).resolve().parent.parent

BLOCO = {
    "nome": "Aprendizado federado em dispositivos de borda",
    "string": '("federated learning" OR "federated training" OR FedAvg) AND ("edge device" OR IoT)',
    "criterio_de_aceite": "ETAPA 1 - Atende à string de busca em título, resumo ou palavras-chave",
    "criterio_de_rejeicao": "ETAPA 1 - Não atende à string de busca em título, resumo ou palavras-chave",
}
REVISAO = regras.Revisao.do_config(BLOCO)

RESUMO_TIPICO = (
    "This paper presents a federated learning framework for training models on edge devices "
    "without sharing raw data. We evaluate the approach on non-IID benchmarks and report accuracy "
    "and communication cost against strong baselines."
)

RESUMO_EM_ALEMAO = (
    "Diese Arbeit beschreibt ein Verfahren zum verteilten Lernen auf mobilen Geraeten ohne "
    "Austausch der Rohdaten und vergleicht es mit bestehenden Ansaetzen aus der Literatur."
)


class TestContarPaginas:
    @pytest.mark.parametrize(
        "intervalo, esperado",
        [
            ("123-127", 5),
            ("123--127", 5),
            ("1234-1240", 7),
            ("10 - 14", 5),
            ("100–104", 5),
            ("1-1", 1),
        ],
    )
    def test_conta_intervalos_legiveis(self, intervalo, esperado):
        assert regras.contar_paginas(intervalo) == esperado

    @pytest.mark.parametrize(
        "intervalo",
        ["", None, "e12345", "7", "artigo 42", "127-123", "1-2-3", "xii-xx"],
    )
    def test_devolve_none_quando_nao_da_para_contar(self, intervalo):
        assert regras.contar_paginas(intervalo) is None


class TestSinalDePaginas:
    def test_sinaliza_intervalo_curto(self):
        sinal = regras.sinal_de_paginas("100-103")
        assert sinal is not None
        assert sinal.criterio == regras.CRITERIO_SHORT_PAPER

    def test_nao_sinaliza_no_limite_de_cinco_paginas(self):
        assert regras.sinal_de_paginas("100-104") is None

    @pytest.mark.parametrize("intervalo", ["", None, "e12345"])
    def test_metadado_ilegivel_nao_vira_ruido(self, intervalo):
        assert regras.sinal_de_paginas(intervalo) is None


class TestSinalDeIdioma:
    def test_ingles_nao_gera_sinal(self):
        assert regras.sinal_de_idioma("Federated learning on edge devices", RESUMO_TIPICO) is None

    def test_outro_idioma_com_texto_longo_gera_sinal(self):
        sinal = regras.sinal_de_idioma("Verteiltes Lernen auf mobilen Geraeten", RESUMO_EM_ALEMAO)
        assert sinal is not None
        assert sinal.criterio == regras.CRITERIO_IDIOMA

    def test_texto_curto_nao_gera_sinal(self):
        assert regras.sinal_de_idioma("FL baseline", "") is None



class TestNotasDaEtapa2:
    def test_short_paper_vira_nota_e_nao_sinal(self):
        notas = regras.levantar_notas_da_etapa_2("Federated learning", RESUMO_TIPICO, "10-13")
        assert [nota.criterio for nota in notas] == [regras.CRITERIO_SHORT_PAPER]

    def test_idioma_vira_nota_e_nao_sinal(self):
        notas = regras.levantar_notas_da_etapa_2(
            "Verteiltes Lernen auf mobilen Geraeten", RESUMO_EM_ALEMAO, "200-215"
        )
        assert [nota.criterio for nota in notas] == [regras.CRITERIO_IDIOMA]

    def test_estudo_sem_ressalva_nao_gera_nota(self):
        assert regras.levantar_notas_da_etapa_2("Federated learning", RESUMO_TIPICO, "100-112") == []

    def test_idioma_declarado_vence_a_deteccao_pelo_resumo(self):
        """Artigo em russo com resumo em inglês: a detecção diria inglês, o metadado não."""
        notas = regras.levantar_notas_da_etapa_2(
            "Distributed learning on mobile devices",
            RESUMO_TIPICO,
            "160-172",
            idioma_declarado="Russian",
        )
        assert [nota.criterio for nota in notas] == [regras.CRITERIO_IDIOMA]
        assert "Russian" in notas[0].evidencia

    @pytest.mark.parametrize("declarado", ["English", "english", "en", "", "  "])
    def test_idioma_declarado_ingles_ou_ausente_nao_gera_nota(self, declarado):
        assert regras.sinal_de_idioma_declarado(declarado) is None




class TestRevisao:
    def test_le_a_string_e_os_dois_criterios(self):
        assert REVISAO.nome == BLOCO["nome"]
        assert len(REVISAO.string.grupos) == 2
        assert REVISAO.criterio_de(planilha.ACEITAR) == BLOCO["criterio_de_aceite"]
        assert REVISAO.criterio_de(planilha.REJEITAR) == BLOCO["criterio_de_rejeicao"]
        assert REVISAO.criterio_de(regras.MANUAL) == ""

    @pytest.mark.parametrize("chave", ["string", "criterio_de_aceite", "criterio_de_rejeicao"])
    def test_chave_obrigatoria_ausente_e_recusada_pelo_nome(self, chave):
        bloco = {nome: valor for nome, valor in BLOCO.items() if nome != chave}
        with pytest.raises(ValueError, match=chave):
            regras.Revisao.do_config(bloco)

    def test_string_invalida_e_recusada_com_o_motivo(self):
        with pytest.raises(ValueError, match="string: parêntese sem fechar"):
            regras.Revisao.do_config({**BLOCO, "string": "(LLM OR SLM"})

    def test_o_exemplo_publicado_carrega(self):
        exemplo = json.loads((RAIZ / "config" / "revisoes.exemplo.json").read_text(encoding="utf-8"))
        for bloco in exemplo.values():
            regras.Revisao.do_config(bloco)


class TestTriar:
    def _triar(self, titulo, resumo, palavras_chave="", paginas="100-112", idioma=""):
        return regras.triar(titulo, resumo, palavras_chave, paginas, REVISAO, idioma)

    def test_estudo_que_atende_a_string_e_aceito_com_a_evidencia(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO)
        assert decisao.acao == planilha.ACEITAR
        assert decisao.evidencia == "G1: federated learning | G2: edge device"

    def test_estudo_com_resumo_que_nao_atende_e_rejeitado(self):
        decisao = self._triar("Federated learning in the cloud", "We train on data center servers.")
        assert decisao.acao == planilha.REJEITAR
        assert decisao.evidencia == "G1: federated learning | G2: nenhum termo"

    def test_sem_resumo_e_sem_atender_vai_para_conferencia_manual(self):
        """Sem resumo, "não atende" mediria a lacuna do registro, não o artigo."""
        assert self._triar("Federated learning in the cloud", "").acao == regras.MANUAL

    def test_sem_resumo_mas_atendendo_pelo_titulo_e_aceito(self):
        assert self._triar("Federated learning on IoT", "").acao == planilha.ACEITAR

    def test_palavras_chave_contam_como_titulo_e_resumo(self):
        decisao = self._triar("Privacy-preserving training", RESUMO_EM_ALEMAO, palavras_chave="FedAvg; IoT")
        assert decisao.acao == planilha.ACEITAR

    def test_notas_da_etapa_2_nao_mudam_a_decisao(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO, paginas="10-13")
        assert decisao.acao == planilha.ACEITAR
        assert [nota.criterio for nota in decisao.notas] == [regras.CRITERIO_SHORT_PAPER]

    def test_idioma_declarado_vira_nota(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO, idioma="Russian")
        assert [nota.criterio for nota in decisao.notas] == [regras.CRITERIO_IDIOMA]
