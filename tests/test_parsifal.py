"""Testes do que o cliente extrai do HTML do Parsifal, sem tocar na rede.

A marcação depende de duas leituras: os campos do formulário do artigo (que precisam voltar
inteiros no POST, senão o metadado é apagado) e o mapa de critério para id.
"""

import pytest

from triagem.parsifal import (
    ACEITO,
    Acesso,
    ErroDeSessao,
    artigos_do_html,
    campos_do_formulario,
    criterios_do_html,
    id_da_revisao_do_html,
)

HTML_DO_ARTIGO = """
<form id="article-details-form">
  <input type="hidden" name="csrfmiddlewaretoken" value="token-falso-de-teste">
  <input type="hidden" name="article-id" value="4321">
  <input type="hidden" name="review-id" value="99">
  <input type="text" name="title" value="Federated learning on edge devices">
  <input type="text" name="author" value="Silva, A. and Costa, B.">
  <input type="text" name="year" value="2024">
  <input type="text" name="pages" value="101-118">
  <input type="text" name="doi" value="10.1000/exemplo">
  <textarea name="abstract">This paper presents an end-to-end approach.</textarea>
  <textarea name="comments"></textarea>
  <select name="status">
    <option value="U">Unclassified</option>
    <option value="A" selected>Accepted</option>
    <option value="R">Rejected</option>
  </select>
  <select name="selection_criteria">
    <option value="">---</option>
    <option value="11">ETAPA 1 - Estudo trata de aprendizado federado</option>
    <option value="12" selected>ETAPA 1 - Estudo secundário (revisão, survey ou mapeamento sistemático)</option>
  </select>
  <input type="submit" name="salvar" value="Save">
</form>
"""


class TestCamposDoFormulario:
    @pytest.fixture
    def campos(self):
        return campos_do_formulario(HTML_DO_ARTIGO)

    def test_recolhe_os_campos_de_texto(self, campos):
        assert campos["title"] == "Federated learning on edge devices"
        assert campos["pages"] == "101-118"
        assert campos["doi"] == "10.1000/exemplo"

    def test_recolhe_os_ocultos_que_o_post_exige(self, campos):
        assert campos["article-id"] == "4321"
        assert campos["review-id"] == "99"

    def test_recolhe_textarea_inclusive_vazia(self, campos):
        assert campos["abstract"] == "This paper presents an end-to-end approach."
        assert campos["comments"] == ""

    def test_recolhe_a_opcao_selecionada_do_select(self, campos):
        assert campos["status"] == ACEITO
        assert campos["selection_criteria"] == "12"

    def test_mantem_o_token_csrf_que_o_formulario_traz(self, campos):
        """O POST de save exige o token do próprio formulário, como o navegador faz."""
        assert campos["csrfmiddlewaretoken"] == "token-falso-de-teste"

    def test_descarta_botao_de_envio(self, campos):
        assert "salvar" not in campos

    def test_html_sem_formulario_devolve_vazio(self):
        assert campos_do_formulario("<div>nada aqui</div>") == {}


class TestCriteriosDoHtml:
    def test_mapeia_texto_do_criterio_para_id(self):
        criterios = criterios_do_html(HTML_DO_ARTIGO)
        assert criterios["ETAPA 1 - Estudo secundário (revisão, survey ou mapeamento sistemático)"] == "12"
        assert (
            criterios["ETAPA 1 - Estudo trata de aprendizado federado"]
            == "11"
        )

    def test_ignora_opcao_sem_valor_numerico(self):
        assert "---" not in criterios_do_html(HTML_DO_ARTIGO)

    def test_normaliza_espaco_sobrando_no_texto_do_criterio(self):
        """Pelo menos um critério cadastrado tem espaço na frente, e o texto é a chave do mapa."""
        html = '<select><option value="451198">  ETAPA 2 - Estudo  sem validação </option></select>'
        assert criterios_do_html(html) == {"ETAPA 2 - Estudo sem validação": "451198"}


HTML_DA_TABELA = """
<table csrf-token="token-falso-de-teste">
  <tbody>
    <tr oid="55403348" article-status="D">
      <td><input type="checkbox" value="55403348"></td><td></td>
      <td>A benchmark dataset for federated learning</td><td>Autor, A.</td>
      <td>None</td><td>2021</td><td>Revisor</td><td>01 Sep 2026</td>
      <td><span class="label">Duplicated</span></td>
    </tr>
    <tr oid="55403335" article-status="U">
      <td><input type="checkbox" value="55403335"></td><td></td>
      <td>Client selection for federated training</td><td>Autor, B.</td>
      <td>None</td><td>2023</td><td>Revisor</td><td>01 Sep 2026</td>
      <td><span class="label">Unclassified</span></td>
    </tr>
  </tbody>
</table>
"""


class TestIdDaRevisao:
    def test_le_o_review_id_que_vem_como_atributo_id(self):
        """Na página de estudos o campo tem `id`, não `name`, então não é campo de formulário."""
        html = '<input type="hidden" id="review-id" value="79691">'
        assert id_da_revisao_do_html(html) == "79691"

    def test_devolve_vazio_quando_nao_ha_review_id(self):
        assert id_da_revisao_do_html("<div>página errada</div>") == ""


class TestArtigosDoHtml:
    def test_le_id_e_status_de_cada_linha(self):
        artigos = artigos_do_html(HTML_DA_TABELA)
        assert [artigo["id"] for artigo in artigos] == ["55403348", "55403335"]
        assert [artigo["status"] for artigo in artigos] == ["D", "U"]

    def test_le_titulo_e_ano(self):
        primeiro = artigos_do_html(HTML_DA_TABELA)[0]
        assert primeiro["titulo"] == "A benchmark dataset for federated learning"
        assert primeiro["ano"] == "2021"

    def test_tabela_vazia_devolve_lista_vazia(self):
        assert artigos_do_html("<table><tbody></tbody></table>") == []


class TestAcesso:
    def test_exige_url_da_revisao(self):
        with pytest.raises(ErroDeSessao, match="PARSIFAL_REVIEW_URL"):
            Acesso(url_da_revisao="").validar()

    def test_exige_credencial_de_algum_tipo(self):
        with pytest.raises(ErroDeSessao, match="credencial"):
            Acesso(url_da_revisao="https://parsif.al/usuario/revisao").validar()

    def test_aceita_usuario_e_senha(self):
        Acesso(url_da_revisao="https://parsif.al/usuario/revisao", usuario="usuario", senha="x").validar()

    def test_aceita_cookie_de_sessao(self):
        Acesso(url_da_revisao="https://parsif.al/usuario/revisao", sessionid="abc").validar()
