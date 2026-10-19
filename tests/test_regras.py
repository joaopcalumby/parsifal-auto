"""Testes das regras da ETAPA 1.

A decisão vem da string de busca, a mesma colada nas bases, e, quando a revisão configura, do número
de páginas do metadado. O idioma é calculado à parte e vira nota para a ETAPA 2, sem pesar na decisão.

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

SHORT_PAPER = {
    "minimo_de_paginas": 4,
    "criterio_de_short_paper": "ETAPA 1 - Short-paper, com menos de 4 páginas",
}
REVISAO_COM_SHORT_PAPER = regras.Revisao.do_config({**BLOCO, **SHORT_PAPER})

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
            ("1-2", 2),
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

    @pytest.mark.parametrize("intervalo", ["1-1", "45-45", "1--1"])
    def test_pagina_unica_nao_e_contada(self, intervalo):
        """O IEEE exporta `1-1` para artigo de periódico em early access, ainda sem paginação."""
        assert regras.contar_paginas(intervalo) is None


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
    def test_idioma_vira_nota(self):
        notas = regras.levantar_notas_da_etapa_2(
            "Verteiltes Lernen auf mobilen Geraeten", RESUMO_EM_ALEMAO
        )
        assert [nota.criterio for nota in notas] == [regras.CRITERIO_IDIOMA]

    def test_estudo_sem_ressalva_nao_gera_nota(self):
        assert regras.levantar_notas_da_etapa_2("Federated learning", RESUMO_TIPICO) == []

    def test_idioma_declarado_vence_a_deteccao_pelo_resumo(self):
        """Artigo em russo com resumo em inglês: a detecção diria inglês, o metadado não."""
        notas = regras.levantar_notas_da_etapa_2(
            "Distributed learning on mobile devices", RESUMO_TIPICO, idioma_declarado="Russian"
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
        assert REVISAO.preenchimento(regras.ATENDE) == (planilha.ACEITAR, BLOCO["criterio_de_aceite"])
        assert REVISAO.preenchimento(regras.NAO_ATENDE) == (
            planilha.REJEITAR,
            BLOCO["criterio_de_rejeicao"],
        )
        assert REVISAO.preenchimento(regras.MANUAL) == ("", "")

    def test_short_paper_e_rejeicao_com_o_criterio_proprio(self):
        assert REVISAO_COM_SHORT_PAPER.preenchimento(regras.SHORT_PAPER) == (
            planilha.REJEITAR,
            SHORT_PAPER["criterio_de_short_paper"],
        )

    def test_sem_short_paper_configurado_nao_ha_limite(self):
        assert REVISAO.minimo_de_paginas is None

    @pytest.mark.parametrize("chave", ["minimo_de_paginas", "criterio_de_short_paper"])
    def test_short_paper_exige_as_duas_chaves(self, chave):
        bloco = {**BLOCO, **{nome: valor for nome, valor in SHORT_PAPER.items() if nome != chave}}
        with pytest.raises(ValueError, match="minimo_de_paginas e criterio_de_short_paper"):
            regras.Revisao.do_config(bloco)

    @pytest.mark.parametrize("minimo", [0, -1, "4", 4.5, True])
    def test_minimo_de_paginas_precisa_ser_inteiro_positivo(self, minimo):
        with pytest.raises(ValueError, match="minimo_de_paginas"):
            regras.Revisao.do_config({**BLOCO, **SHORT_PAPER, "minimo_de_paginas": minimo})

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
    def _triar(self, titulo, resumo, palavras_chave="", paginas="100-112", idioma="", revisao=REVISAO):
        return regras.triar(titulo, resumo, palavras_chave, paginas, revisao, idioma)

    def test_estudo_que_atende_a_string_e_aceito_com_a_evidencia(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO)
        assert decisao.desfecho == regras.ATENDE
        assert decisao.evidencia == "G1: federated learning | G2: edge device"

    def test_estudo_com_resumo_que_nao_atende_e_rejeitado(self):
        decisao = self._triar("Federated learning in the cloud", "We train on data center servers.")
        assert decisao.desfecho == regras.NAO_ATENDE
        assert decisao.evidencia == "G1: federated learning | G2: nenhum termo"

    def test_sem_resumo_e_sem_atender_vai_para_conferencia_manual(self):
        """Sem resumo, "não atende" mediria a lacuna do registro, não o artigo."""
        assert self._triar("Federated learning in the cloud", "").desfecho == regras.MANUAL

    def test_sem_resumo_mas_atendendo_pelo_titulo_e_aceito(self):
        assert self._triar("Federated learning on IoT", "").desfecho == regras.ATENDE

    def test_palavras_chave_contam_como_titulo_e_resumo(self):
        decisao = self._triar(
            "Privacy-preserving training", RESUMO_EM_ALEMAO, palavras_chave="FedAvg; IoT"
        )
        assert decisao.desfecho == regras.ATENDE

    def test_sem_short_paper_configurado_paginas_nao_decidem(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO, paginas="10-12")
        assert decisao.desfecho == regras.ATENDE
        assert decisao.notas == []

    def test_short_paper_vem_antes_da_string(self):
        decisao = self._triar(
            "Federated learning on edge devices",
            RESUMO_TIPICO,
            paginas="10-12",
            revisao=REVISAO_COM_SHORT_PAPER,
        )
        assert decisao.desfecho == regras.SHORT_PAPER
        assert decisao.evidencia == "3 páginas pelo metadado | G1: federated learning | G2: edge device"

    def test_short_paper_tambem_decide_quem_iria_para_conferencia_manual(self):
        decisao = self._triar(
            "Guest editorial", "", paginas="1827-1829", revisao=REVISAO_COM_SHORT_PAPER
        )
        assert decisao.desfecho == regras.SHORT_PAPER

    def test_no_limite_de_paginas_nao_e_short_paper(self):
        decisao = self._triar(
            "Federated learning on edge devices",
            RESUMO_TIPICO,
            paginas="10-13",
            revisao=REVISAO_COM_SHORT_PAPER,
        )
        assert decisao.desfecho == regras.ATENDE

    @pytest.mark.parametrize("paginas", ["", "e12345", "7"])
    def test_sem_numero_de_paginas_quem_decide_e_a_string(self, paginas):
        """Campo vazio ou número de artigo não indica tamanho nenhum: não há o que conferir."""
        decisao = self._triar(
            "Federated learning on edge devices",
            RESUMO_TIPICO,
            paginas=paginas,
            revisao=REVISAO_COM_SHORT_PAPER,
        )
        assert decisao.desfecho == regras.ATENDE

    @pytest.mark.parametrize(
        ("titulo", "resumo", "esperado"),
        [
            ("Federated learning on edge devices", RESUMO_TIPICO, regras.ATENDE),
            ("Federated learning in the cloud", "We train on data center servers.", regras.NAO_ATENDE),
        ],
    )
    @pytest.mark.parametrize("paginas", ["1-1", "45-45"])
    def test_pagina_unica_fica_com_a_string(self, titulo, resumo, esperado, paginas):
        """O IEEE exporta `1-1` para artigo completo em early access, e nada no registro os separa."""
        decisao = self._triar(titulo, resumo, paginas=paginas, revisao=REVISAO_COM_SHORT_PAPER)
        assert decisao.desfecho == esperado
        assert decisao.evidencia.startswith("G1:")

    def test_idioma_declarado_vira_nota(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO, idioma="Russian")
        assert [nota.criterio for nota in decisao.notas] == [regras.CRITERIO_IDIOMA]
