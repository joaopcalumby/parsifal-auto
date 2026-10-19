"""Testes da planilha de trabalho: o que é escrito tem que voltar igual na leitura."""

from triagem import planilha

ACEITE = "ETAPA 1 - Atende à string de busca em título, resumo ou palavras-chave"
REJEICAO = "ETAPA 1 - Não atende à string de busca em título, resumo ou palavras-chave"

LINHAS = [
    {
        "id": "55403348",
        "acao": "aceitar",
        "criterio": ACEITE,
        "titulo": "Federated learning on edge devices",
        "automacao": "aceitar",
        "evidencia": "G1: federated learning | G2: edge device",
        "notas_etapa_2": "Short-paper: metadado indica 3 páginas",
        "doi": "10.1000/exemplo",
    },
    {
        "id": "55403335",
        "acao": "",
        "criterio": "",
        "titulo": "Federated learning in the cloud",
        "automacao": "manual",
        "evidencia": "G1: federated learning | G2: nenhum termo",
        "notas_etapa_2": "",
        "doi": "",
    },
]


class TestIdaEVolta:
    def test_o_que_foi_escrito_volta_igual(self, tmp_path):
        caminho = tmp_path / "decisoes.xlsx"
        planilha.escrever(caminho, LINHAS)
        assert planilha.ler(caminho) == LINHAS

    def test_planilha_vazia_nao_quebra(self, tmp_path):
        caminho = tmp_path / "vazia.xlsx"
        planilha.escrever(caminho, [])
        assert planilha.ler(caminho) == []

    def test_linha_sem_id_e_descartada_na_leitura(self, tmp_path):
        """Linha em branco no fim da planilha é acidente de edição, não estudo."""
        caminho = tmp_path / "decisoes.xlsx"
        planilha.escrever(caminho, [*LINHAS, {"id": "", "acao": "aceitar"}])
        assert [linha["id"] for linha in planilha.ler(caminho)] == ["55403348", "55403335"]

    def test_aba_de_criterios_nao_atrapalha_a_leitura(self, tmp_path):
        caminho = tmp_path / "decisoes.xlsx"
        planilha.escrever(caminho, LINHAS, criterios=["ETAPA 1 - Um", "ETAPA 2 - Dois"])
        assert len(planilha.ler(caminho)) == 2

    def test_decisao_escrita_a_mao_sobrevive_a_regravacao(self, tmp_path):
        """É o caso que quebrou antes: reescrever a planilha não pode perder a coluna dele."""
        caminho = tmp_path / "decisoes.xlsx"
        planilha.escrever(caminho, LINHAS)

        anteriores = {linha["id"]: linha for linha in planilha.ler(caminho)}
        recalculadas = [
            {**linha, "evidencia": "recalculado", "acao": "", "criterio": ""} for linha in LINHAS
        ]
        preservadas = [
            {
                **linha,
                "acao": anteriores[linha["id"]]["acao"],
                "criterio": anteriores[linha["id"]]["criterio"],
            }
            for linha in recalculadas
        ]
        planilha.escrever(caminho, preservadas)

        lidas = {linha["id"]: linha for linha in planilha.ler(caminho)}
        assert lidas["55403348"]["acao"] == "aceitar"
        assert lidas["55403348"]["evidencia"] == "recalculado"


class TestFoiEditada:
    """A automação preenche a ação. Só o que o revisor mudou sobrevive a um novo `classificar`."""

    def test_linha_como_a_automacao_deixou_nao_foi_editada(self):
        anterior = {"acao": "rejeitar", "criterio": REJEICAO, "automacao": "rejeitar"}
        assert not planilha.foi_editada(anterior, ("rejeitar", REJEICAO))

    def test_acao_trocada_pelo_revisor_foi_editada(self):
        anterior = {"acao": "aceitar", "criterio": REJEICAO, "automacao": "rejeitar"}
        assert planilha.foi_editada(anterior, ("rejeitar", REJEICAO))

    def test_criterio_trocado_pelo_revisor_foi_editada(self):
        anterior = {"acao": "rejeitar", "criterio": "ETAPA 1 - Preprint", "automacao": "rejeitar"}
        assert planilha.foi_editada(anterior, ("rejeitar", REJEICAO))

    def test_conferencia_manual_preenchida_pelo_revisor_foi_editada(self):
        anterior = {"acao": "aceitar", "criterio": ACEITE, "automacao": "manual"}
        assert planilha.foi_editada(anterior, ("", ""))

    def test_espaco_sobrando_nao_conta_como_edicao(self):
        anterior = {"acao": " rejeitar ", "criterio": REJEICAO + " ", "automacao": "rejeitar"}
        assert not planilha.foi_editada(anterior, ("rejeitar", REJEICAO))
