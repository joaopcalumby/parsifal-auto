"""Testes das regras da ETAPA 1.

O teste que sustenta o desenho é o negativo: nenhum caminho de `triar` exclui. A automação aponta,
o revisor decide.

O tema dos exemplos é o mesmo do `config/revisoes.exemplo.json`: aprendizado federado em
dispositivos de borda, com a sigla FL colidindo com fuzzy logic.
"""

import pytest

from triagem import regras

VOCABULARIO = regras.Vocabulario(
    dominio=("federated learning", "federated training", "fedavg"),
    siglas_ambiguas=("fl",),
    colisao=("fuzzy", "membership function"),
    recorte=("edge device", "edge devices", "device level", "iot"),
)

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


class TestVocabulario:
    def test_le_as_chaves_da_revisao_em_minusculas(self):
        vocabulario = regras.Vocabulario.da_revisao(
            {
                "termos_dominio": ["Federated Learning"],
                "siglas_ambiguas": ["FL"],
                "termos_colisao": ["Fuzzy"],
                "termos_recorte": ["IoT"],
            }
        )
        assert vocabulario == regras.Vocabulario(
            dominio=("federated learning",), siglas_ambiguas=("fl",), colisao=("fuzzy",), recorte=("iot",)
        )

    def test_chave_ausente_vira_lista_vazia(self):
        assert regras.Vocabulario.da_revisao({"nome": "só o nome"}) == regras.Vocabulario()


class TestSinaisDaEtapa1:
    def _sinais(self, titulo, resumo="", palavras_chave="", fonte="", vocabulario=VOCABULARIO):
        return {
            sinal.criterio
            for sinal in regras.levantar_sinais(titulo, resumo, palavras_chave, fonte, vocabulario)
        }

    def test_survey_e_sinalizado_como_estudo_secundario(self):
        assert regras.CRITERIO_SECUNDARIO in self._sinais(
            "A survey of federated learning on edge devices", RESUMO_TIPICO
        )

    def test_preprint_e_sinalizado_como_literatura_cinza(self):
        assert regras.CRITERIO_CINZA in self._sinais(
            "Federated learning on edge devices", RESUMO_TIPICO, fonte="arXiv preprint"
        )

    def test_vocabulario_da_colisao_e_sinalizado_como_fora_de_dominio(self):
        assert regras.CRITERIO_DOMINIO in self._sinais(
            "An FL controller for IoT irrigation",
            "We tune the fuzzy rules and the membership function of the controller on IoT sensors.",
        )

    def test_termo_inequivoco_vence_a_colisao(self):
        assert regras.CRITERIO_DOMINIO not in self._sinais(
            "Fuzzy client selection for federated learning on IoT",
            "We select clients with fuzzy rules before each federated training round.",
        )

    def test_sigla_sozinha_sem_colisao_nao_sinaliza(self):
        """A sigla conta como termo do domínio; só não prova o domínio diante da colisão."""
        assert self._sinais(
            "FL on edge devices", "We study FL with heterogeneous clients on edge devices."
        ) == set()

    def test_sem_termo_do_dominio_e_sinalizado(self):
        sinais = regras.levantar_sinais(
            "Centralized training on edge devices",
            "We train a single model in the cloud and deploy it to edge devices.",
            "",
            "",
            VOCABULARIO,
        )
        assert [sinal.criterio for sinal in sinais] == [regras.CRITERIO_DOMINIO]
        assert "nenhum termo do domínio" in sinais[0].evidencia

    def test_estudo_tipico_da_revisao_nao_gera_sinal(self):
        assert self._sinais("Federated learning on edge devices", RESUMO_TIPICO) == set()

    def test_ausencia_do_termo_do_recorte_e_sinalizada(self):
        assert regras.CRITERIO_RECORTE in self._sinais(
            "Federated learning for image classification",
            "We train models across many clients with federated averaging on CIFAR-10.",
        )

    def test_termo_do_recorte_so_nas_palavras_chave_e_suficiente(self):
        """A busca costuma casar em TITLE-ABS-KEY, então keyword vale tanto quanto título e resumo."""
        assert regras.CRITERIO_RECORTE not in self._sinais(
            "Communication-efficient federated learning",
            "We compress model updates sent by clients during federated training.",
            palavras_chave="federated learning; IoT; compression",
        )

    def test_termo_do_dominio_so_nas_palavras_chave_e_suficiente(self):
        assert regras.CRITERIO_DOMINIO not in self._sinais(
            "Privacy-preserving model training on edge devices",
            "Clients keep their data locally and only share model updates.",
            palavras_chave="federated learning",
        )

    def test_vocabulario_vazio_desliga_dominio_e_recorte(self):
        assert self._sinais(
            "Any study at all", "An abstract without any configured term.", vocabulario=regras.Vocabulario()
        ) == set()


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


class TestLocalizacaoDoRecorte:
    """Ordenação para a ETAPA 2: recorte no título é indício de foco, no resumo pode ser menção."""

    def _onde(self, titulo, resumo="", palavras_chave=""):
        return regras.localizacao_do_recorte(titulo, resumo, palavras_chave, VOCABULARIO.recorte)

    def test_recorte_no_titulo(self):
        assert self._onde("Federated learning on edge devices") == "título"

    def test_recorte_nas_palavras_chave(self):
        assert self._onde("Federated learning", palavras_chave="IoT; FL") == "palavras-chave"

    def test_conta_ocorrencias_no_resumo(self):
        assert self._onde("Federated learning", resumo=RESUMO_TIPICO) == "resumo (1x)"

    def test_sinonimos_sobrepostos_contam_como_uma_mencao(self):
        """'edge device level' casa com `edge device` e `device level`, e é uma menção só."""
        assert self._onde("Federated learning", resumo="Work at the edge device level here.") == (
            "resumo (1x)"
        )

    def test_duas_mencoes_separadas_contam_duas(self):
        assert self._onde(
            "Federated learning", resumo="Clients run on edge devices. Each IoT node trains locally."
        ) == "resumo (2x)"

    def test_soma_os_tres_campos(self):
        onde = self._onde("Federated learning on IoT", RESUMO_TIPICO, palavras_chave="edge devices")
        assert onde == "título, palavras-chave, resumo (1x)"

    def test_ausente_quando_nenhum_campo_traz_o_recorte(self):
        assert self._onde("Federated learning in the cloud", "We train on servers.") == "ausente"


class TestTriar:
    def _triar(self, titulo, resumo, palavras_chave="", fonte="", paginas="100-112"):
        return regras.triar(titulo, resumo, palavras_chave, fonte, paginas, VOCABULARIO)

    def test_estudo_alvo_passa_limpo(self):
        assert self._triar("Federated learning on edge devices", RESUMO_TIPICO).acao == regras.MANTER

    @pytest.mark.parametrize(
        "titulo, resumo, paginas",
        [
            ("An FL controller for IoT irrigation", "Fuzzy rules tuned on IoT sensors.", "45-60"),
            ("Federated learning on edge devices", RESUMO_TIPICO, "10-13"),
            ("Verteiltes Lernen auf mobilen Geraeten", RESUMO_EM_ALEMAO, "200-215"),
            ("A survey of federated learning on edge devices", RESUMO_TIPICO, "100-140"),
        ],
    )
    def test_nenhum_caminho_exclui(self, titulo, resumo, paginas):
        assert self._triar(titulo, resumo, paginas=paginas).acao in (
            regras.MANTER,
            regras.SINALIZAR,
            regras.SEM_RESUMO,
        )

    def test_short_paper_nao_interrompe_a_etapa_1(self):
        decisao = self._triar("Federated learning on edge devices", RESUMO_TIPICO, paginas="10-13")
        assert decisao.acao == regras.MANTER
        assert any(nota.criterio == regras.CRITERIO_SHORT_PAPER for nota in decisao.notas)

    def test_idioma_nao_interrompe_a_etapa_1(self):
        decisao = self._triar("Verteiltes Lernen auf mobilen Geraeten", RESUMO_EM_ALEMAO)
        assert any(nota.criterio == regras.CRITERIO_IDIOMA for nota in decisao.notas)

    def test_registro_sem_resumo_nao_e_decidido_na_etapa_1(self):
        decisao = self._triar("Federated learning on edge devices", "")
        assert decisao.acao == regras.SEM_RESUMO
        assert decisao.sinais == []

    def test_registro_sem_resumo_nao_sinaliza_termo_ausente(self):
        """Sem resumo, 'nenhum termo do recorte' mediria a lacuna do metadado, não o artigo."""
        decisao = self._triar("Untitled record", "", paginas="")
        assert decisao.acao == regras.SEM_RESUMO
        assert decisao.sinais == []
