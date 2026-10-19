"""Linha de comando: verificar, baixar, completar, classificar, aplicar."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

from triagem import aplicacao, dados, parsifal, planilha, regras, resumo_externo
from triagem.parsifal import Acesso, ClienteParsifal, ErroDeSessao

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DE_DADOS = RAIZ / "dados"
ESTUDOS = PASTA_DE_DADOS / "estudos.csv"
DECISOES = PASTA_DE_DADOS / "decisoes.xlsx"
CRITERIOS = PASTA_DE_DADOS / "criterios.json"
CONFIG_DE_REVISOES = RAIZ / "config" / "revisoes.json"

COLUNAS_DO_ESTUDO = (
    "id",
    "bibtex_key",
    "titulo",
    "resumo",
    "palavras_chave",
    "fonte",
    "paginas",
    "doi",
    "url",
    "ano",
    "idioma",
    "resumo_origem",
    "status",
)


def _cliente() -> ClienteParsifal:
    load_dotenv(RAIZ / ".env")
    cliente = ClienteParsifal(
        Acesso(
            url_da_revisao=os.getenv("PARSIFAL_REVIEW_URL", ""),
            usuario=os.getenv("PARSIFAL_USERNAME", ""),
            senha=os.getenv("PARSIFAL_PASSWORD", ""),
            sessionid=os.getenv("PARSIFAL_SESSIONID", ""),
            csrftoken=os.getenv("PARSIFAL_CSRFTOKEN", ""),
        )
    )
    cliente.autenticar()
    return cliente


def _revisao(sigla: str) -> regras.Revisao:
    if not CONFIG_DE_REVISOES.exists():
        raise SystemExit(
            f"{CONFIG_DE_REVISOES} não existe. Copie config/revisoes.exemplo.json para "
            "config/revisoes.json e cole nele a string da sua revisão."
        )
    revisoes = json.loads(CONFIG_DE_REVISOES.read_text(encoding="utf-8"))
    if sigla not in revisoes:
        raise SystemExit(f"revisão {sigla!r} não está em {CONFIG_DE_REVISOES}")

    try:
        return regras.Revisao.do_config(revisoes[sigla])
    except ValueError as erro:
        raise SystemExit(f"revisão {sigla!r} em {CONFIG_DE_REVISOES}: {erro}") from erro


def _avisar_criterio_fora_do_parsifal(revisao: regras.Revisao) -> None:
    """O `aplicar` recusa critério que não existe no Parsifal. Melhor saber agora que depois."""
    if not CRITERIOS.exists():
        return

    cadastrados = set(json.loads(CRITERIOS.read_text(encoding="utf-8")))
    for criterio in (revisao.criterio_de_aceite, revisao.criterio_de_rejeicao):
        if criterio not in cadastrados:
            print(f"aviso: critério não cadastrado no Parsifal, o `aplicar` vai recusar: {criterio}")


def comando_verificar(_argumentos) -> None:
    """Sonda a revisão antes de qualquer escrita, e diz o que encontrou."""
    cliente = _cliente()
    print(f"revisão:   {cliente.base}")
    print(f"review-id: {cliente.id_da_revisao}")

    artigos = cliente.listar_artigos()
    contagem = Counter(artigo["status"] for artigo in artigos)
    print(f"artigos:   {len(artigos)}")
    for status, quantidade in sorted(contagem.items()):
        print(f"  {parsifal.NOMES_DE_STATUS.get(status, status):<14} {quantidade:>5}")

    if not artigos:
        print("nenhum artigo importado: o resto da sondagem depende de ter ao menos um.")
        return

    criterios = cliente.listar_criterios(artigos[0]["id"])
    PASTA_DE_DADOS.mkdir(parents=True, exist_ok=True)
    CRITERIOS.write_text(json.dumps(sorted(criterios), ensure_ascii=False, indent=2), encoding="utf-8")

    por_etapa = Counter(texto.split(" - ")[0] for texto in criterios)
    print(f"\ncritérios de seleção: {len(criterios)}")
    for etapa, quantidade in sorted(por_etapa.items()):
        print(f"  {etapa:<14} {quantidade:>5}")
    for texto, identificador in sorted(criterios.items()):
        print(f"  [{identificador}] {texto}")

    if not criterios:
        print(
            "\nnenhum critério foi extraído da tela do artigo. Sem isso a marcação não consegue "
            "anexar o critério: conferir o HTML antes de aplicar."
        )


def comando_baixar(argumentos) -> None:
    """Copia para `dados/estudos.csv` os campos que a ETAPA 1 lê, um artigo por vez.

    A instância hospedada não tem export de resultados: a lista sai de `source_articles`, e resumo e
    palavras-chave só existem na tela de cada artigo. O arquivo local é o cache dessa varredura.
    """
    cliente = _cliente()
    artigos = cliente.listar_artigos()
    pendentes = [artigo for artigo in artigos if artigo["status"] == parsifal.NAO_CLASSIFICADO]

    if argumentos.limite:
        pendentes = pendentes[: argumentos.limite]

    print(f"{len(artigos)} artigos na revisão, {len(pendentes)} não classificados a baixar")

    linhas = []
    for numero, artigo in enumerate(pendentes, start=1):
        campos = cliente.campos_do_artigo(artigo["id"])
        linhas.append(
            {
                "id": artigo["id"],
                "bibtex_key": campos.get("bibtex-key", ""),
                "titulo": campos.get("title", ""),
                "resumo": campos.get("abstract", ""),
                "palavras_chave": " ".join(
                    filtro
                    for filtro in (campos.get("keywords", ""), campos.get("author_keywords", ""))
                    if filtro
                ),
                "fonte": campos.get("journal", "") or campos.get("note", ""),
                "paginas": campos.get("pages", ""),
                "doi": campos.get("doi", ""),
                "url": campos.get("url", ""),
                "ano": campos.get("year", ""),
                "idioma": campos.get("language", ""),
                "resumo_origem": "",
                "status": artigo["status"],
            }
        )
        if numero % 25 == 0 or numero == len(pendentes):
            print(f"  {numero}/{len(pendentes)}")
        time.sleep(argumentos.pausa)

    PASTA_DE_DADOS.mkdir(parents=True, exist_ok=True)
    with ESTUDOS.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_DO_ESTUDO)
        escritor.writeheader()
        escritor.writerows(linhas)

    com_resumo = sum(1 for linha in linhas if linha["resumo"].strip())
    com_keywords = sum(1 for linha in linhas if linha["palavras_chave"].strip())
    print(f"\n{len(linhas)} estudos em {ESTUDOS}")
    print(f"  com resumo:         {com_resumo}")
    print(f"  com palavras-chave: {com_keywords}")


def comando_completar(argumentos) -> None:
    """Busca na página do artigo o resumo que o Parsifal não tem.

    Ideia comum em automações de triagem. A diferença para elas é o que acontece quando falha: aqui o
    estudo apenas segue sem resumo para a ETAPA 2, em vez de ser rejeitado.
    """
    if not ESTUDOS.exists():
        raise SystemExit(f"{ESTUDOS} não existe. Rode `baixar` antes.")

    estudos = dados.carregar(ESTUDOS)
    sem_resumo = [estudo for estudo in estudos if not estudo.resumo.strip()]
    com_endereco = [
        estudo for estudo in sem_resumo if resumo_externo.enderecos_possiveis(estudo.url, estudo.doi)
    ]

    print(f"{len(estudos)} estudos, {len(sem_resumo)} sem resumo, {len(com_endereco)} com link ou DOI")
    if not com_endereco:
        print("nada a buscar.")
        return

    recuperados = 0
    with requests.Session() as sessao:
        for numero, estudo in enumerate(com_endereco, start=1):
            texto, origem = resumo_externo.buscar_resumo(estudo.url, estudo.doi, sessao)
            if texto:
                estudo.resumo = texto
                estudo.resumo_origem = origem
                recuperados += 1
            print(f"  {numero}/{len(com_endereco)} [{estudo.id}] {origem or 'não recuperado'}")
            time.sleep(argumentos.pausa)

    with ESTUDOS.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_DO_ESTUDO)
        escritor.writeheader()
        escritor.writerows(
            {coluna: getattr(estudo, coluna) for coluna in COLUNAS_DO_ESTUDO} for estudo in estudos
        )

    print(f"\n{recuperados} de {len(com_endereco)} resumos recuperados, gravados em {ESTUDOS}")
    print("Os que continuam sem resumo seguem para a ETAPA 2, como antes.")


def comando_classificar(argumentos) -> None:
    """Monta a planilha de trabalho com a decisão da string já preenchida.

    Se a planilha já existe, a linha em que você mudou a ação ou o critério fica como você deixou,
    e só o que continua como a automação preencheu é recalculado. Linha nova entra no fim.
    """
    revisao = _revisao(argumentos.revisao)
    entrada = Path(argumentos.entrada) if argumentos.entrada else ESTUDOS
    if not entrada.exists():
        raise SystemExit(f"{entrada} não existe. Rode `baixar` antes.")

    estudos = dados.carregar(entrada)
    anteriores = {linha["id"]: linha for linha in planilha.ler(DECISOES)} if DECISOES.exists() else {}
    preservadas = 0

    linhas = []
    for estudo in estudos:
        if estudo.ja_classificado:
            continue

        decisao = regras.triar(
            titulo=estudo.titulo,
            resumo=estudo.resumo,
            palavras_chave=estudo.palavras_chave,
            paginas=estudo.paginas,
            revisao=revisao,
            idioma_declarado=estudo.idioma,
        )
        acao, criterio = _preenchimento(decisao.acao, revisao)

        anterior = anteriores.get(estudo.id)
        if anterior:
            preenchido_antes = _preenchimento(anterior.get("automacao", ""), revisao)
            if planilha.foi_editada(anterior, preenchido_antes):
                acao, criterio = anterior.get("acao", ""), anterior.get("criterio", "")
                preservadas += 1

        linhas.append(
            {
                "id": estudo.id,
                "acao": acao,
                "criterio": criterio,
                "titulo": estudo.titulo[:250],
                "automacao": decisao.acao,
                "evidencia": decisao.evidencia,
                "notas_etapa_2": decisao.notas_em_texto,
                "doi": estudo.doi,
            }
        )

    criterios = json.loads(CRITERIOS.read_text(encoding="utf-8")) if CRITERIOS.exists() else []
    planilha.escrever(DECISOES, linhas, criterios)

    contagem = Counter(linha["automacao"] for linha in linhas)
    print(f"revisão {argumentos.revisao} ({revisao.nome}), {len(linhas)} estudos")
    print(f"  aceitar   {contagem[planilha.ACEITAR]:>5}  (atende à string)")
    print(f"  rejeitar  {contagem[planilha.REJEITAR]:>5}  (tem resumo e não atende à string)")
    print(f"  manual    {contagem[regras.MANUAL]:>5}  (sem resumo e não atende: confira à mão)")
    if preservadas:
        print(f"\n  {preservadas} linhas com decisão sua, preservadas como estavam")
    _avisar_criterio_fora_do_parsifal(revisao)

    print(f"\n{DECISOES}")
    print("Confira as colunas 'acao' e 'criterio', mude o que discordar, salve e rode `aplicar`.")


def _preenchimento(acao_da_automacao: str, revisao: regras.Revisao) -> tuple[str, str]:
    """O que a automação escreve em `acao` e `criterio`. Conferência manual fica em branco."""
    acao = "" if acao_da_automacao == regras.MANUAL else acao_da_automacao
    return acao, revisao.criterio_de(acao_da_automacao)


def comando_aplicar(argumentos) -> None:
    """Leva para o Parsifal o que está escrito na coluna `acao`.

    Compara com o status que está lá e só escreve o que estiver diferente, então rodar duas vezes
    seguidas não reescreve nada.
    """
    if not DECISOES.exists():
        raise SystemExit(f"{DECISOES} não existe. Rode `classificar` antes.")

    linhas = planilha.ler(DECISOES)
    cliente = _cliente()
    status_no_parsifal = {artigo["id"]: artigo["status"] for artigo in cliente.listar_artigos()}

    revisao = _revisao(argumentos.revisao)
    plano = aplicacao.planejar(linhas, status_no_parsifal, revisao.criterio_de_aceite)

    decididas = len(plano.a_aplicar) + len(plano.ja_iguais)
    print(f"{len(linhas)} linhas na planilha, {decididas} com ação preenchida")
    print(f"  a aplicar:      {len(plano.a_aplicar)}")
    print(f"  já iguais:      {len(plano.ja_iguais)}")
    print(f"  com problema:   {len(plano.problemas)}")

    for problema in plano.problemas:
        print(f"    {problema}")

    if not plano.a_aplicar:
        return

    if not argumentos.confirmar:
        print("\nDRY-RUN. Nada foi escrito. Amostra do que seria feito:\n")
        for marcacao in plano.a_aplicar[:15]:
            print(f"  {marcacao.acao:<9} [{marcacao.id}] {marcacao.criterio[:70]}")
        if len(plano.a_aplicar) > 15:
            print(f"  ... e mais {len(plano.a_aplicar) - 15}")
        print("\nRode de novo com --confirmar para gravar.")
        return

    criterios = cliente.listar_criterios(plano.a_aplicar[0].id)
    escritos, falhas = 0, []

    for marcacao in plano.a_aplicar:
        id_do_criterio = criterios.get(marcacao.criterio.strip())
        if not id_do_criterio:
            falhas.append((marcacao.id, f"critério não existe no Parsifal: {marcacao.criterio}"))
            continue
        try:
            cliente.marcar(marcacao.id, marcacao.status, id_do_criterio)
            escritos += 1
        except ErroDeSessao as erro:
            falhas.append((marcacao.id, f"{erro} (interrompido aqui)"))
            break
        except (ValueError, requests.HTTPError) as erro:
            falhas.append((marcacao.id, str(erro)))

    print(f"\n{escritos} de {len(plano.a_aplicar)} estudos marcados no Parsifal")
    for identificador, motivo in falhas:
        print(f"  falhou [{identificador}]: {motivo}")


def main() -> None:
    analisador = argparse.ArgumentParser(prog="triagem", description=__doc__)
    subcomandos = analisador.add_subparsers(dest="comando", required=True)

    subcomandos.add_parser("verificar", help="sonda a revisão sem escrever nada").set_defaults(
        funcao=comando_verificar
    )

    baixar = subcomandos.add_parser("baixar", help="copia os estudos não classificados para CSV")
    baixar.add_argument("--limite", type=int, help="baixa só os N primeiros, para testar")
    baixar.add_argument(
        "--pausa", type=float, default=0.3, help="segundos entre requisições (padrão: 0.3)"
    )
    baixar.set_defaults(funcao=comando_baixar)

    completar = subcomandos.add_parser(
        "completar", help="busca na página do artigo o resumo que o Parsifal não tem"
    )
    completar.add_argument(
        "--pausa", type=float, default=1.0, help="segundos entre requisições (padrão: 1.0)"
    )
    completar.set_defaults(funcao=comando_completar)

    classificar = subcomandos.add_parser("classificar", help="monta a planilha de trabalho")
    classificar.add_argument("--revisao", default="A", help="sigla da revisão em config/revisoes.json")
    classificar.add_argument("--entrada", help="caminho de um .csv ou .bib (padrão: dados/estudos.csv)")
    classificar.set_defaults(funcao=comando_classificar)

    aplicar = subcomandos.add_parser("aplicar", help="leva a coluna 'acao' da planilha para o Parsifal")
    aplicar.add_argument("--revisao", default="A", help="sigla da revisão em config/revisoes.json")
    aplicar.add_argument("--confirmar", action="store_true", help="grava de verdade")
    aplicar.set_defaults(funcao=comando_aplicar)

    argumentos = analisador.parse_args()
    argumentos.funcao(argumentos)
