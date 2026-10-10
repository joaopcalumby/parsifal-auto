"""Compara a planilha com o Parsifal e decide o que precisa ser escrito.

Sem rede e sem arquivo: recebe as linhas e o status de cada artigo, devolve o que aplicar. É aqui
que mora a regra de só mexer no que está diferente - rodar duas vezes seguidas não reescreve nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from triagem import parsifal, planilha

STATUS_DESEJADO = {planilha.ACEITAR: parsifal.ACEITO, planilha.REJEITAR: parsifal.REJEITADO}


@dataclass(frozen=True)
class Marcacao:
    """Uma escrita a fazer no Parsifal."""

    id: str
    acao: str
    status: str
    criterio: str


@dataclass
class Plano:
    a_aplicar: list[Marcacao]
    ja_iguais: list[str]
    problemas: list[str]


def planejar(
    linhas: list[dict[str, str]],
    status_no_parsifal: dict[str, str],
    criterio_de_aceite: str = "",
) -> Plano:
    """Decide, linha a linha, o que escrever.

    Linha sem ação é ignorada em silêncio: é o estado normal de quem ainda não foi revisado.
    Ação escrita errada vira problema, não silêncio.
    """
    plano = Plano(a_aplicar=[], ja_iguais=[], problemas=[])

    for linha in linhas:
        identificador = linha.get("id", "").strip()
        try:
            acao = planilha.normalizar_acao(linha.get("acao"))
        except ValueError as erro:
            plano.problemas.append(f"[{identificador}] {erro}")
            continue

        if not acao:
            continue

        status_atual = status_no_parsifal.get(identificador)
        if status_atual is None:
            plano.problemas.append(f"[{identificador}] não está mais na revisão do Parsifal")
            continue

        if status_atual == parsifal.DUPLICADO:
            plano.problemas.append(
                f"[{identificador}] está marcado como duplicado no Parsifal: a automação não mexe"
            )
            continue

        if status_atual == STATUS_DESEJADO[acao]:
            plano.ja_iguais.append(identificador)
            continue

        criterio = linha.get("criterio", "").strip()
        if not criterio and acao == planilha.ACEITAR:
            criterio = criterio_de_aceite
        if not criterio:
            plano.problemas.append(
                f"[{identificador}] {acao} sem critério. "
                "Rejeição precisa dizer por qual critério o estudo saiu."
            )
            continue

        plano.a_aplicar.append(
            Marcacao(id=identificador, acao=acao, status=STATUS_DESEJADO[acao], criterio=criterio)
        )

    return plano
