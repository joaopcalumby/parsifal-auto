"""Testes da string de busca como regra da ETAPA 1.

A string é a mesma colada nas bases. O que se testa é que ela casa nos três campos do jeito que uma
base casaria em TITLE-ABS-KEY: sem diferenciar maiúscula, com hífen e espaço equivalentes e com plural.
"""

import pytest

from triagem.string_de_busca import ErroNaString, StringDeBusca

STRING_PIBITI_V1 = """
("language model" OR "language models" OR "small language model" OR "small language models" OR LLM OR LLMs OR SLM OR SLMs)
AND
(serving OR "inference server" OR orchestration OR orchestrations OR orchestrator OR orchestrators OR orchestrate OR orchestrates OR orchestrated OR orchestrating OR microservice OR microservices OR API OR middleware OR offloading OR "request routing")
AND
("edge AI" OR "edge computing" OR "edge device" OR "edge devices" OR "edge server" OR "edge servers" OR "on-device" OR "on-premise" OR "on-premises" OR offline OR "resource-constrained" OR "resource-limited" OR mobile OR "consumer hardware" OR "air-gapped" OR "local inference" OR "local deployment" OR "locally hosted" OR "locally deployed" OR "locally run")
"""

STRING_HTR_V1 = """
("HDR" OR "HTR" OR "document transcription" OR "handwriting" OR "handwriting recognition" OR "handwritten" OR "handwritten document" OR "handwritten text" OR "handwritten text recognition" OR "intelligent character recognition" OR "manuscript recognition" OR "manuscript transcription")
AND
("entire page" OR "full page" OR "full-page" OR "page level" OR "page-level" OR "page-wise" OR "whole page")
"""


def _atende(string, titulo="", resumo="", palavras_chave=""):
    return StringDeBusca(string).avaliar(titulo, resumo, palavras_chave).atende


class TestTermo:
    def test_casa_palavra_inteira_e_nao_pedaco(self):
        assert _atende("API", resumo="A REST API for inference.")
        assert not _atende("API", resumo="A rapid prototype.")

    def test_nao_diferencia_maiuscula(self):
        assert _atende("LLM", titulo="llm serving")
        assert _atende('"edge AI"', titulo="Edge ai at scale")

    def test_frase_casa_a_sequencia_e_nao_as_palavras_soltas(self):
        assert _atende('"edge device"', resumo="runs on an edge device")
        assert not _atende('"edge device"', resumo="the device sits at the edge")

    def test_hifen_e_espaco_sao_equivalentes(self):
        assert _atende('"on-device"', resumo="on device inference")
        assert _atende('"full page"', resumo="full-page recognition")

    def test_hifen_tipografico_do_resumo_conta_como_hifen(self):
        """Export da Wiley e de PDFs traz U+2010 no lugar do hífen comum."""
        assert _atende('"on-device"', resumo="on\u2010device inference")

    @pytest.mark.parametrize(
        ("termo", "texto"),
        [("API", "three APIs"), ('"edge device"', "many edge devices"), ("process", "two processes")],
    )
    def test_casa_o_plural_como_as_bases(self, termo, texto):
        assert _atende(termo, resumo=texto)

    def test_curinga_casa_qualquer_continuacao(self):
        assert _atende("orchestrat*", resumo="model orchestration")
        assert _atende("orchestrat*", resumo="orchestrated services")
        assert not _atende("orchestrat*", resumo="an orchestra")

    def test_curinga_dentro_da_frase(self):
        assert _atende('"edge comput*"', resumo="edge computing nodes")

    def test_frase_nao_atravessa_campos(self):
        """Fim do título e começo do resumo não formam frase: em TITLE-ABS-KEY cada campo é um texto."""
        assert not _atende('"edge device"', titulo="Inference at the edge", resumo="Device placement")


class TestOperadores:
    def test_or_basta_um(self):
        assert _atende("LLM OR SLM", resumo="an SLM")

    def test_and_exige_os_dois(self):
        assert _atende("LLM AND mobile", resumo="LLM on mobile")
        assert not _atende("LLM AND mobile", resumo="LLM on servers")

    def test_and_tem_precedencia_sobre_or(self):
        assert _atende("LLM OR SLM AND mobile", resumo="an LLM")
        assert not _atende("LLM OR SLM AND mobile", resumo="an SLM")

    def test_parenteses_mudam_a_precedencia(self):
        assert not _atende("(LLM OR SLM) AND mobile", resumo="an LLM")

    def test_and_not_exclui(self):
        assert not _atende("LLM AND NOT cloud", resumo="LLM in the cloud")
        assert _atende("LLM AND NOT cloud", resumo="LLM on device")

    def test_not_binario_como_no_web_of_science(self):
        assert not _atende("LLM NOT cloud", resumo="LLM in the cloud")

    def test_operador_em_minuscula_tambem_vale(self):
        assert not _atende("LLM and mobile", resumo="LLM on servers")

    def test_aspas_tipograficas_coladas_de_documento(self):
        assert _atende("\u201cedge device\u201d", resumo="an edge device")

    def test_os_tres_campos_contam_juntos_como_em_title_abs_key(self):
        assert _atende(
            "LLM AND serving AND mobile",
            titulo="LLM serving",
            resumo="We study latency.",
            palavras_chave="mobile",
        )


class TestStringsReais:
    def test_string_do_pibiti_v1(self):
        busca = StringDeBusca(STRING_PIBITI_V1)
        assert len(busca.grupos) == 3
        assert busca.avaliar("Serving LLMs on edge devices", "", "").atende

    def test_string_do_htr_v1(self):
        busca = StringDeBusca(STRING_HTR_V1)
        assert len(busca.grupos) == 2
        assert busca.avaliar("Full-page handwritten text recognition", "", "").atende


class TestEvidencia:
    def test_mostra_os_termos_que_casaram_em_cada_grupo(self):
        resultado = StringDeBusca(STRING_PIBITI_V1).avaliar("Serving LLMs on mobile", "", "")
        assert resultado.evidencia == "G1: LLM, LLMs | G2: serving | G3: mobile"

    def test_aponta_o_grupo_que_faltou(self):
        resultado = StringDeBusca(STRING_PIBITI_V1).avaliar("LLM on mobile", "", "")
        assert not resultado.atende
        assert resultado.evidencia == "G1: LLM | G2: nenhum termo | G3: mobile"

    def test_grupo_com_not_violado_mostra_o_termo(self):
        resultado = StringDeBusca("LLM AND NOT cloud").avaliar("LLM in the cloud", "", "")
        assert resultado.evidencia == "G1: LLM | G2: não atende (cloud)"

    def test_grupo_com_not_satisfeito(self):
        resultado = StringDeBusca("LLM AND NOT cloud").avaliar("LLM on device", "", "")
        assert resultado.evidencia == "G1: LLM | G2: ok"


class TestErros:
    """String mal colada vira erro com o motivo, nunca uma regra diferente da busca."""

    @pytest.mark.parametrize(
        ("string", "motivo"),
        [
            ("", "vazia"),
            ("(LLM OR SLM", "parêntese"),
            ("LLM OR SLM)", "parêntese"),
            ('"edge device', "aspas"),
            ("LLM mobile", "operador"),
            ("LLM AND", "termo"),
            ("OR LLM", "termo"),
            ('LLM OR ""', "vazio"),
            ("TITLE-ABS-KEY(LLM)", "código de campo"),
            ("LLM W/3 mobile", "proximidade"),
            ("LLM NEAR/2 mobile", "proximidade"),
        ],
    )
    def test_recusa_com_o_motivo(self, string, motivo):
        with pytest.raises(ErroNaString, match=motivo):
            StringDeBusca(string)
