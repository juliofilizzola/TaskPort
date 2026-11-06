"""Tokenização linha a linha do Markdown.

Cada convenção reconhecida é uma ``LineRule``. Para suportar uma nova convenção basta
criar uma regra que devolva um token existente (ou um novo, tratado no builder) e
incluí-la na lista de regras passada ao ``MarkdownParser``.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Line:
    number: int
    raw: str  # linha sem espaços à direita e com tabs convertidos em espaços
    indent: int
    text: str  # conteúdo sem indentação


@dataclass(frozen=True, slots=True)
class HeadingToken:
    line: int
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class TaskToken:
    line: int
    indent: int
    checked: bool
    text: str


@dataclass(frozen=True, slots=True)
class TextToken:
    line: int
    indent: int
    raw: str


@dataclass(frozen=True, slots=True)
class BlankToken:
    line: int


Token = HeadingToken | TaskToken | TextToken | BlankToken


class LineRule(Protocol):
    def match(self, line: Line) -> Token | None: ...


class HeadingRule:
    """ATX headings: ``#`` a ``######``."""

    _pattern = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")

    def match(self, line: Line) -> Token | None:
        if line.indent > 3:
            return None
        match = self._pattern.match(line.text)
        if not match or not match.group(2).strip():
            return None
        return HeadingToken(line.number, len(match.group(1)), match.group(2).strip())


class TaskRule:
    """Checkboxes GFM: ``- [ ]``, ``* [x]``, ``+ [X]``, ``1. [ ]``."""

    _pattern = re.compile(r"^(?:[-*+]|\d+[.)])\s+\[([ xX])\]\s+(.+)$")

    def match(self, line: Line) -> Token | None:
        match = self._pattern.match(line.text)
        if not match:
            return None
        return TaskToken(line.number, line.indent, match.group(1) in "xX", match.group(2).strip())


DEFAULT_RULES: tuple[LineRule, ...] = (HeadingRule(), TaskRule())

_FENCE = re.compile(r"^(`{3,}|~{3,})")


class Tokenizer:
    def __init__(self, rules: Sequence[LineRule]) -> None:
        self._rules = tuple(rules)

    def tokenize(self, content: str) -> list[Token]:
        tokens: list[Token] = []
        fence: str | None = None

        for number, original in enumerate(content.splitlines(), start=1):
            expanded = original.expandtabs(4).rstrip()
            text = expanded.lstrip(" ")
            line = Line(number, expanded, len(expanded) - len(text), text)

            # Conteúdo de blocos de código é sempre texto literal.
            if fence is not None:
                tokens.append(TextToken(number, line.indent, line.raw))
                if text.startswith(fence):
                    fence = None
                continue
            if fence_match := _FENCE.match(text):
                fence = fence_match.group(1)
                tokens.append(TextToken(number, line.indent, line.raw))
                continue

            if not text:
                tokens.append(BlankToken(number))
                continue

            tokens.append(self._match(line))
        return tokens

    def _match(self, line: Line) -> Token:
        for rule in self._rules:
            if (token := rule.match(line)) is not None:
                return token
        # Nada reconhecido: preservado como texto.
        return TextToken(line.number, line.indent, line.raw)
