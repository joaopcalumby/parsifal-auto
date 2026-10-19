"""A string de busca como regra da ETAPA 1.

A mesma string colada nas bases é lida aqui e avaliada sobre título, resumo e palavras-chave juntos,
como o TITLE-ABS-KEY do Scopus e o Topic do Web of Science. A comparação imita o que as bases fazem
sozinhas: não diferencia maiúscula, trata hífen e espaço como iguais e casa o plural regular.

Gramática aceita: termos soltos, frases entre aspas, `*` como curinga, AND, OR, NOT (também como
AND NOT) e parênteses. AND tem precedência sobre OR, como nas bases. Código de campo e operador de
proximidade são recusados com erro, porque a regra sairia diferente da busca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

OPERADORES = {"AND", "OR", "NOT"}
PROXIMIDADE = re.compile(r"^(?:NEAR|W|PRE|ADJ)(?:/\d+)?$", re.IGNORECASE)
HIFENS_TIPOGRAFICOS = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014", "-"))
ASPAS_TIPOGRAFICAS = str.maketrans(dict.fromkeys("\u201c\u201d\u201e", '"'))
SEPARADOR_DE_CAMPOS = " | "


class ErroNaString(ValueError):
    """A string não pôde ser lida. A mensagem diz onde e por quê."""


@dataclass(frozen=True)
class Resultado:
    """Se o estudo atende à string, e a evidência por grupo para quem for conferir."""

    atende: bool
    evidencia: str


# -- árvore da expressão ------------------------------------------------------


class _No(Protocol):
    def casa(self, texto: str) -> bool: ...

    def termos_casados(self, texto: str) -> list[str]: ...


@dataclass(frozen=True)
class _Termo:
    texto: str
    padrao: re.Pattern

    def casa(self, texto: str) -> bool:
        return bool(self.padrao.search(texto))

    def termos_casados(self, texto: str) -> list[str]:
        return [self.texto] if self.casa(texto) else []


@dataclass(frozen=True)
class _E:
    partes: tuple[_No, ...]

    def casa(self, texto: str) -> bool:
        return all(parte.casa(texto) for parte in self.partes)

    def termos_casados(self, texto: str) -> list[str]:
        return [termo for parte in self.partes for termo in parte.termos_casados(texto)]


@dataclass(frozen=True)
class _Ou:
    partes: tuple[_No, ...]

    def casa(self, texto: str) -> bool:
        return any(parte.casa(texto) for parte in self.partes)

    def termos_casados(self, texto: str) -> list[str]:
        return [termo for parte in self.partes for termo in parte.termos_casados(texto)]


@dataclass(frozen=True)
class _Nao:
    parte: _No

    def casa(self, texto: str) -> bool:
        return not self.parte.casa(texto)

    def termos_casados(self, texto: str) -> list[str]:
        return self.parte.termos_casados(texto)


# -- leitura ------------------------------------------------------------------


def _padrao_do_termo(termo: str) -> re.Pattern:
    """Palavras separadas por hífen ou espaço, `*` como curinga e plural regular na última palavra."""
    palavras = [palavra for palavra in re.split(r"[\s\-]+", termo.lower()) if palavra]
    if not palavras:
        raise ErroNaString("termo vazio entre aspas")

    partes = [re.escape(palavra).replace(r"\*", r"\w*") for palavra in palavras]
    if "*" not in palavras[-1]:
        partes[-1] += "(?:s|es)?"

    return re.compile(r"(?<!\w)" + r"[\s\-]+".join(partes) + r"(?!\w)")


def _tokens(string: str) -> list[tuple[str, str]]:
    """Quebra a string em ('(' | ')' | 'op' | 'termo', valor)."""
    tokens: list[tuple[str, str]] = []
    posicao = 0

    while posicao < len(string):
        caractere = string[posicao]
        if caractere.isspace():
            posicao += 1
        elif caractere in "()":
            tokens.append((caractere, caractere))
            posicao += 1
        elif caractere == '"':
            fim = string.find('"', posicao + 1)
            if fim == -1:
                raise ErroNaString(f"aspas sem fechar a partir de: {string[posicao:posicao + 40]!r}")
            tokens.append(("termo", string[posicao + 1 : fim]))
            posicao = fim + 1
        else:
            fim = posicao
            while fim < len(string) and not string[fim].isspace() and string[fim] not in '()"':
                fim += 1
            palavra = string[posicao:fim]
            if palavra.upper() in OPERADORES:
                tokens.append(("op", palavra.upper()))
            elif PROXIMIDADE.match(palavra):
                raise ErroNaString(f"operador de proximidade não é aceito: {palavra}")
            elif fim < len(string) and string[fim] == "(":
                raise ErroNaString(
                    f"código de campo não é aceito: {palavra}(...). Cole a string sem ele."
                )
            else:
                tokens.append(("termo", palavra))
            posicao = fim

    return tokens


class _Leitor:
    """Descida recursiva sobre os tokens.

    expressao := e (OR e)*
    e         := fator ((AND | NOT) fator)*
    fator     := NOT fator | "(" expressao ")" | termo
    """

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.posicao = 0

    def _proximo(self) -> tuple[str, str] | None:
        return self.tokens[self.posicao] if self.posicao < len(self.tokens) else None

    def _consumir(self) -> tuple[str, str]:
        token = self.tokens[self.posicao]
        self.posicao += 1
        return token

    def ler(self) -> _No:
        arvore = self._expressao()
        sobra = self._proximo()
        if sobra == (")", ")"):
            raise ErroNaString("parêntese fechando sem abrir")
        if sobra is not None:
            anterior = self.tokens[self.posicao - 1][1]
            raise ErroNaString(f"falta operador entre {anterior!r} e {sobra[1]!r}")
        return arvore

    def _expressao(self) -> _No:
        partes = [self._e()]
        while self._proximo() == ("op", "OR"):
            self._consumir()
            partes.append(self._e())
        return partes[0] if len(partes) == 1 else _Ou(tuple(partes))

    def _e(self) -> _No:
        partes = [self._fator()]
        while self._proximo() in (("op", "AND"), ("op", "NOT")):
            _, operador = self._consumir()
            partes.append(_Nao(self._fator()) if operador == "NOT" else self._fator())
        return partes[0] if len(partes) == 1 else _E(tuple(partes))

    def _fator(self) -> _No:
        token = self._proximo()
        if token is None:
            anterior = self.tokens[self.posicao - 1][1] if self.posicao else ""
            raise ErroNaString(f"falta um termo depois de {anterior!r}")

        tipo, valor = self._consumir()
        if (tipo, valor) == ("op", "NOT"):
            return _Nao(self._fator())
        if tipo == "(":
            dentro = self._expressao()
            if self._proximo() != (")", ")"):
                raise ErroNaString("parêntese sem fechar")
            self._consumir()
            return dentro
        if tipo == "termo":
            return _Termo(valor, _padrao_do_termo(valor))

        raise ErroNaString(f"esperava um termo e encontrou {valor!r}")


# -- avaliação ----------------------------------------------------------------


def _normalizar(campo: str | None) -> str:
    return re.sub(r"\s+", " ", (campo or "").translate(HIFENS_TIPOGRAFICOS)).lower()


def _sem_repetir(termos: list[str]) -> list[str]:
    return list(dict.fromkeys(termos))


class StringDeBusca:
    """Uma string de busca lida e pronta para avaliar estudos.

    `grupos` são as partes ligadas por AND no nível mais alto, que é como a string costuma ser
    montada: um grupo de sinônimos por conceito.
    """

    def __init__(self, string: str) -> None:
        texto = (string or "").translate(ASPAS_TIPOGRAFICAS).strip()
        if not texto:
            raise ErroNaString("string vazia")

        arvore = _Leitor(_tokens(texto)).ler()
        self.grupos: tuple[_No, ...] = arvore.partes if isinstance(arvore, _E) else (arvore,)

    def avaliar(self, titulo: str, resumo: str, palavras_chave: str) -> Resultado:
        campos = (titulo, resumo, palavras_chave)
        texto = SEPARADOR_DE_CAMPOS.join(_normalizar(campo) for campo in campos)
        atende = all(grupo.casa(texto) for grupo in self.grupos)
        evidencia = " | ".join(
            f"G{numero}: {self._descrever(grupo, texto)}"
            for numero, grupo in enumerate(self.grupos, start=1)
        )
        return Resultado(atende=atende, evidencia=evidencia)

    @staticmethod
    def _descrever(grupo: _No, texto: str) -> str:
        casados = ", ".join(_sem_repetir(grupo.termos_casados(texto)))
        if grupo.casa(texto):
            return casados or "ok"
        return f"não atende ({casados})" if casados else "nenhum termo"
