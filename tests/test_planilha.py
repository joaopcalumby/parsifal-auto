"""Testes da planilha de trabalho: o que é escrito tem que voltar igual na leitura."""

from triagem import planilha

LINHAS = [
    {
        "id": "55403348",
        "acao": "aceitar",
        "criterio": "ETAPA 1 - Estudo trata de aprendizado federado",
        "titulo": "Federated learning on edge devices",
        "sugestao": "MANTER",
        "sinais": "",
        "notas_etapa_2": "Short-paper: metadado indica 3 páginas",
        "recorte_em": "título, resumo (2x)",
        "doi": "10.1000/exemplo",
    },
    {
        "id": "55403335",
        "acao": "",
        "criterio": "",
        "titulo": "An FL controller for IoT irrigation",
        "sugestao": "SINALIZAR",
        "sinais": "Estudo fora do domínio da revisão: fuzzy, membership function",
        "notas_etapa_2": "",
        "recorte_em": "ausente",
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
            {**linha, "sinais": "recalculado", "acao": "", "criterio": ""} for linha in LINHAS
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
        assert lidas["55403348"]["sinais"] == "recalculado"
