"""Cliente do Parsifal: faz por HTTP exatamente o que você faz clicando.

Quando você abre um artigo, escolhe o critério e salva, a página manda um POST para
`save_article_details/` com o formulário inteiro serializado. É esse mesmo POST que este módulo
monta: abre o artigo, lê os campos que já estão lá, troca só o status e o critério, e devolve.

**As rotas foram levantadas da instância hospedada (parsif.al v2.2.1) em 01/09/2026**, não do código
do GitHub - as duas divergem. Na hospedada os endpoints são absolutos, sob `/reviews/conducting/`, e
**não existe export de resultados**: a lista de artigos sai de `source_articles/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TEMPO_LIMITE = 60

# Uma varredura faz uma requisição por artigo, e uma queda isolada de conexão não pode derrubá-la.
# Só o GET é repetido: o POST grava, e repeti-lo sem saber se o primeiro chegou é escrever às cegas.
REPETICOES = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    raise_on_status=False,
)
RAIZ_PADRAO = "https://parsif.al"

ACEITO = "A"
REJEITADO = "R"
NAO_CLASSIFICADO = "U"
DUPLICADO = "D"

NOMES_DE_STATUS = {
    ACEITO: "Accepted",
    REJEITADO: "Rejected",
    NAO_CLASSIFICADO: "Unclassified",
    DUPLICADO: "Duplicated",
}

TODAS_AS_FONTES = "None"


class ErroDeSessao(RuntimeError):
    """A sessão do Parsifal não está válida, ou o login falhou."""


@dataclass
class Acesso:
    """Como entrar no Parsifal.

    Dois caminhos: usuário e senha (a automação loga sozinha), ou o cookie de uma sessão já aberta
    no navegador. Os dois moram no `.env`, que está no `.gitignore` e não sai da máquina.
    """

    url_da_revisao: str
    usuario: str = ""
    senha: str = ""
    sessionid: str = ""
    csrftoken: str = ""

    def validar(self) -> None:
        if not self.url_da_revisao:
            raise ErroDeSessao("falta PARSIFAL_REVIEW_URL no .env")
        if not (self.usuario and self.senha) and not self.sessionid:
            raise ErroDeSessao(
                "falta credencial no .env: preencha PARSIFAL_USERNAME e PARSIFAL_PASSWORD, "
                "ou PARSIFAL_SESSIONID com o cookie do navegador"
            )


# -- leitura de HTML, sem rede ----------------------------------------------


def campos_do_formulario(html: str) -> dict[str, str]:
    """Extrai os campos preenchidos de um formulário HTML, o token CSRF incluído.

    É o que permite trocar status e critério sem apagar o resto: `save_article_details` reescreve o
    artigo inteiro, então tudo que já estava lá precisa voltar junto.
    """
    sopa = BeautifulSoup(html, "html.parser")
    campos: dict[str, str] = {}

    for entrada in sopa.find_all("input"):
        nome = entrada.get("name")
        tipo = (entrada.get("type") or "text").lower()
        if not nome or tipo in ("submit", "button", "file"):
            continue
        if tipo in ("checkbox", "radio"):
            if entrada.has_attr("checked"):
                campos[nome] = entrada.get("value", "on")
            continue
        campos[nome] = entrada.get("value", "")

    for area in sopa.find_all("textarea"):
        if nome := area.get("name"):
            campos[nome] = area.get_text()

    for selecao in sopa.find_all("select"):
        nome = selecao.get("name")
        if not nome:
            continue
        escolhida = selecao.find("option", selected=True)
        campos[nome] = escolhida.get("value", "") if escolhida else ""

    return campos


def id_da_revisao_do_html(html: str) -> str:
    """O `review-id` da página de estudos. Vem como `id`, não como `name`, então não é campo."""
    achado = re.search(r'id="review-id"[^>]*value="(\d+)"', html)
    return achado.group(1) if achado else ""


def artigos_do_html(html: str) -> list[dict[str, str]]:
    """Lê a tabela de artigos devolvida por `source_articles/`.

    Cada linha traz id e status, que é o que basta para decidir quem entra na triagem. Resumo e
    palavras-chave não vêm aqui: eles moram na tela do artigo.
    """
    sopa = BeautifulSoup(html, "html.parser")
    artigos = []

    for linha in sopa.find_all("tr", attrs={"oid": True}):
        celulas = [celula.get_text(strip=True) for celula in linha.find_all("td")]
        artigos.append(
            {
                "id": linha["oid"],
                "status": linha.get("article-status", ""),
                "titulo": celulas[2] if len(celulas) > 2 else "",
                "ano": celulas[5] if len(celulas) > 5 else "",
            }
        )

    return artigos


def criterios_do_html(html: str) -> dict[str, str]:
    """Mapeia o texto de cada critério de seleção para o id que o Parsifal usa.

    O critério é gravado por chave primária, não por texto. O texto é normalizado porque pelo menos
    um critério cadastrado tem espaço sobrando na frente.
    """
    sopa = BeautifulSoup(html, "html.parser")
    criterios: dict[str, str] = {}

    for opcao in sopa.find_all("option"):
        valor = opcao.get("value", "")
        texto = re.sub(r"\s+", " ", opcao.get_text()).strip()
        if valor.isdigit() and texto:
            criterios[texto] = valor

    return criterios


# -- cliente ----------------------------------------------------------------


class ClienteParsifal:
    def __init__(self, acesso: Acesso) -> None:
        acesso.validar()
        self.acesso = acesso
        self.base = acesso.url_da_revisao.rstrip("/")
        partes = urlparse(self.base)
        self.raiz = f"{partes.scheme}://{partes.netloc}" if partes.netloc else RAIZ_PADRAO
        self.sessao = requests.Session()
        self.sessao.mount("https://", HTTPAdapter(max_retries=REPETICOES))
        self.sessao.mount("http://", HTTPAdapter(max_retries=REPETICOES))
        self._id_da_revisao = ""

        if acesso.sessionid:
            self.sessao.cookies.update({"sessionid": acesso.sessionid})
            if acesso.csrftoken:
                self.sessao.cookies.update({"csrftoken": acesso.csrftoken})

    def autenticar(self) -> None:
        """Loga com usuário e senha, se houver. Com cookie no .env, não faz nada."""
        if not (self.acesso.usuario and self.acesso.senha):
            return

        url_de_login = f"{self.raiz}/login/"
        self.sessao.get(url_de_login, timeout=TEMPO_LIMITE)
        resposta = self.sessao.post(
            url_de_login,
            data={
                "username": self.acesso.usuario,
                "password": self.acesso.senha,
                "csrfmiddlewaretoken": self.sessao.cookies.get("csrftoken", ""),
                "next": "/",
            },
            headers={"Referer": url_de_login},
            timeout=TEMPO_LIMITE,
        )

        if not self.sessao.cookies.get("sessionid"):
            raise ErroDeSessao(
                f"login recusado pelo Parsifal (HTTP {resposta.status_code}). "
                "Confira PARSIFAL_USERNAME e PARSIFAL_PASSWORD no .env."
            )

    def _endpoint(self, nome: str) -> str:
        return f"{self.raiz}/reviews/conducting/{nome}/"

    def _conferir(self, resposta: requests.Response) -> requests.Response:
        if "/login" in resposta.url or resposta.status_code in (401, 403):
            raise ErroDeSessao("o Parsifal devolveu a tela de login: a sessão caiu")
        resposta.raise_for_status()
        return resposta

    @property
    def id_da_revisao(self) -> str:
        if not self._id_da_revisao:
            pagina = self._conferir(
                self.sessao.get(f"{self.base}/conducting/studies/", timeout=TEMPO_LIMITE)
            )
            self._id_da_revisao = id_da_revisao_do_html(pagina.text)
            if not self._id_da_revisao:
                raise ErroDeSessao(
                    "não achei o review-id na página de estudos. "
                    f"Confira se PARSIFAL_REVIEW_URL aponta para a revisão certa: {self.base}"
                )
        return self._id_da_revisao

    def listar_artigos(self, id_da_fonte: str = TODAS_AS_FONTES) -> list[dict[str, str]]:
        """Todos os artigos da revisão, com id e status. Não traz resumo."""
        resposta = self._conferir(
            self.sessao.get(
                self._endpoint("source_articles"),
                params={"review-id": self.id_da_revisao, "source-id": id_da_fonte},
                timeout=TEMPO_LIMITE,
            )
        )
        return artigos_do_html(resposta.text)

    def html_do_artigo(self, id_do_artigo: str) -> str:
        """O mesmo HTML que aparece quando você clica no artigo."""
        resposta = self._conferir(
            self.sessao.get(
                self._endpoint("article_details"),
                params={"review-id": self.id_da_revisao, "article-id": id_do_artigo},
                timeout=TEMPO_LIMITE,
            )
        )
        return resposta.text

    def campos_do_artigo(self, id_do_artigo: str) -> dict[str, str]:
        return campos_do_formulario(self.html_do_artigo(id_do_artigo))

    def listar_criterios(self, id_de_um_artigo: str) -> dict[str, str]:
        """Os critérios de seleção com seus ids, lidos da tela de um artigo qualquer."""
        criterios = criterios_do_html(self.html_do_artigo(id_de_um_artigo))
        return {
            texto: identificador
            for texto, identificador in criterios.items()
            if texto not in NOMES_DE_STATUS.values()
        }

    def marcar(self, id_do_artigo: str, status: str, id_do_criterio: str) -> requests.Response:
        """Aceita ou rejeita um artigo com o critério anexado, como o botão Save da tela faz.

        Lê os campos atuais, troca dois deles e devolve o formulário inteiro. Mandar só o status
        apagaria título, resumo e o resto do metadado.
        """
        if status not in NOMES_DE_STATUS:
            raise ValueError(f"status inválido: {status!r}")

        campos = self.campos_do_artigo(id_do_artigo)
        if not campos.get("article-id"):
            raise ErroDeSessao(f"a tela do artigo {id_do_artigo} não trouxe o formulário esperado")

        campos["status"] = status
        campos["selection_criteria"] = id_do_criterio

        return self._conferir(
            self.sessao.post(
                self._endpoint("save_article_details"),
                data=campos,
                headers={"Referer": f"{self.base}/conducting/studies/"},
                timeout=TEMPO_LIMITE,
            )
        )
