"""Testes da comparação entre a planilha e o Parsifal.

A regra que sustenta o desenho: só se escreve o que está diferente. Rodar `aplicar` duas vezes
seguidas não pode reescrever nada.
"""

import pytest

from triagem import parsifal, planilha
from triagem.aplicacao import planejar

CRITERIO_DE_ACEITE = "ETAPA 1 - Estudo trata de aprendizado federado"
CRITERIO_DE_RECUSA = "ETAPA 1 - Estudo secundário (revisão, survey ou mapeamento sistemático)"


def linha(identificador, acao="", criterio=""):
    return {"id": identificador, "acao": acao, "criterio": criterio}


class TestNormalizarAcao:
    @pytest.mark.parametrize("escrito", ["aceitar", "Aceitar", " ACEITAR ", "aceito", "aceita"])
    def test_variacoes_de_aceitar(self, escrito):
        assert planilha.normalizar_acao(escrito) == planilha.ACEITAR

    @pytest.mark.parametrize("escrito", ["rejeitar", "Rejeitado", "REJEITAR"])
    def test_variacoes_de_rejeitar(self, escrito):
        assert planilha.normalizar_acao(escrito) == planilha.REJEITAR

    @pytest.mark.parametrize("vazio", ["", "   ", None])
    def test_celula_vazia_nao_e_decisao(self, vazio):
        assert planilha.normalizar_acao(vazio) == planilha.SEM_ACAO

    def test_palavra_desconhecida_e_erro_e_nao_silencio(self):
        with pytest.raises(ValueError, match="não reconhecida"):
            planilha.normalizar_acao("manter")


class TestPlanejar:
    def test_aceita_o_que_esta_nao_classificado(self):
        plano = planejar([linha("1", "aceitar")], {"1": parsifal.NAO_CLASSIFICADO}, CRITERIO_DE_ACEITE)
        assert [(m.id, m.status, m.criterio) for m in plano.a_aplicar] == [
            ("1", parsifal.ACEITO, CRITERIO_DE_ACEITE)
        ]

    def test_rejeita_com_o_criterio_escrito_na_planilha(self):
        plano = planejar([linha("1", "rejeitar", CRITERIO_DE_RECUSA)], {"1": "U"}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar[0].status == parsifal.REJEITADO
        assert plano.a_aplicar[0].criterio == CRITERIO_DE_RECUSA

    def test_nao_reescreve_o_que_ja_esta_igual(self):
        plano = planejar([linha("1", "aceitar")], {"1": parsifal.ACEITO}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert plano.ja_iguais == ["1"]

    def test_reescreve_quando_a_planilha_discorda_do_parsifal(self):
        """Ele mudou de ideia: estava aceito lá, virou rejeitar aqui."""
        plano = planejar(
            [linha("1", "rejeitar", CRITERIO_DE_RECUSA)], {"1": parsifal.ACEITO}, CRITERIO_DE_ACEITE
        )
        assert plano.a_aplicar[0].status == parsifal.REJEITADO

    def test_linha_sem_acao_e_ignorada_em_silencio(self):
        plano = planejar([linha("1"), linha("2", "  ")], {"1": "U", "2": "U"}, CRITERIO_DE_ACEITE)
        assert (plano.a_aplicar, plano.ja_iguais, plano.problemas) == ([], [], [])

    def test_duplicado_no_parsifal_nao_e_tocado(self):
        plano = planejar([linha("1", "aceitar")], {"1": parsifal.DUPLICADO}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert "duplicado" in plano.problemas[0]

    def test_rejeicao_sem_criterio_e_problema(self):
        """Rejeição sem critério não registra em que etapa o estudo saiu, e o PRISMA depende disso."""
        plano = planejar([linha("1", "rejeitar")], {"1": "U"}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert "sem critério" in plano.problemas[0]

    def test_aceite_sem_criterio_usa_o_padrao_da_revisao(self):
        plano = planejar([linha("1", "aceitar")], {"1": "U"}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar[0].criterio == CRITERIO_DE_ACEITE

    def test_artigo_que_sumiu_da_revisao_e_problema(self):
        plano = planejar([linha("999", "aceitar")], {"1": "U"}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert "não está mais na revisão" in plano.problemas[0]

    def test_palavra_invalida_aponta_a_linha(self):
        plano = planejar([linha("1", "talvez")], {"1": "U"}, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert "[1]" in plano.problemas[0]

    def test_rodar_de_novo_depois_de_aplicar_nao_faz_nada(self):
        linhas = [linha("1", "aceitar"), linha("2", "rejeitar", CRITERIO_DE_RECUSA)]
        depois = {"1": parsifal.ACEITO, "2": parsifal.REJEITADO}
        plano = planejar(linhas, depois, CRITERIO_DE_ACEITE)
        assert plano.a_aplicar == []
        assert sorted(plano.ja_iguais) == ["1", "2"]
