"""Monta a estrutura de projeto/listas/cartões a partir dos tokens."""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.parsers.markdown.tokens import BlankToken, HeadingToken, TaskToken, TextToken, Token
from app.schemas.markdown import ChecklistItem, ParsedCard, ParsedList

COMPLETED_NOTE = "✅ Tarefa marcada como concluída no arquivo de origem."
SUBTASK_PREFIX = "↳ "
CONTENT_OFFSET = 2  # largura de "- " após a indentação do marcador
# Linha de metadados no corpo do cartão: "Etiquetas: a, b" (também "**Etiquetas:**" e "Labels:").
LABELS_LINE = re.compile(r"^\*{0,2}(?:etiquetas|labels)\s*:\s*\*{0,2}\s*(.+)$", re.IGNORECASE)


@dataclass
class _CardDraft:
    title: str
    completed: bool
    line: int
    indent: int
    context: list[str]
    intro: list[str]
    project: str | None = None
    body: list[str] = field(default_factory=list)
    checklist: list[ChecklistItem] = field(default_factory=list)
    item_indents: list[int] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def add_item(self, token: TaskToken) -> None:
        while self.item_indents and self.item_indents[-1] >= token.indent:
            self.item_indents.pop()
        depth = len(self.item_indents)
        self.item_indents.append(token.indent)
        self.checklist.append(ChecklistItem(name=SUBTASK_PREFIX * depth + token.text, checked=token.checked))

    def add_text(self, token: TextToken) -> None:
        if self.checklist and self.item_indents and token.indent > self.item_indents[-1]:
            # Texto indentado sob uma subtarefa: preservado na descrição, referenciando a subtarefa.
            item = self.checklist[-1].name.removeprefix(SUBTASK_PREFIX * (len(self.item_indents) - 1))
            self.body.append(f"- *{item}*: {token.raw.strip()}")
            return
        if match := LABELS_LINE.match(token.raw.strip()):
            for label in match.group(1).split(","):
                label = label.strip().strip("*").strip()
                if label and label.casefold() not in {existing.casefold() for existing in self.labels}:
                    self.labels.append(label)
            return
        offset = self.indent + CONTENT_OFFSET
        raw = token.raw
        self.body.append(raw[offset:] if raw[:offset].strip() == "" else raw.lstrip())

    def add_blank(self) -> None:
        if self.body and self.body[-1] != "":
            self.body.append("")

    def build(self) -> ParsedCard:
        parts = [_join(self.intro), _join(self.body)]
        if self.completed:
            parts.append(COMPLETED_NOTE)
        origin = []
        if self.project:
            origin.append(f"**Projeto:** {self.project}")
        if self.context:
            origin.append(f"**Seção:** {' › '.join(self.context)}")
        if origin:
            parts.append("\n".join(origin))
        return ParsedCard(
            title=self.title,
            description="\n\n".join(p for p in parts if p),
            completed=self.completed,
            checklist=self.checklist,
            labels=self.labels,
            context=self.context,
            line=self.line,
        )


def _join(lines: list[str]) -> str:
    return "\n".join(lines).strip("\n")


class DocumentBuilder:
    def __init__(self, filename: str) -> None:
        self.default_list_name = PurePosixPath(filename).stem or filename
        self.project: str | None = None
        self.lists: list[ParsedList] = []
        self.unassigned_text: list[str] = []
        self.warnings: list[str] = []

        self._list: ParsedList | None = None
        self._context: list[tuple[int, str]] = []
        self._card: _CardDraft | None = None
        self._pending: list[str] = []  # texto antes da primeira tarefa da seção
        self._pending_line: int | None = None

    def feed(self, token: Token) -> None:
        match token:
            case HeadingToken():
                self._on_heading(token)
            case TaskToken():
                self._on_task(token)
            case TextToken():
                self._on_text(token)
            case BlankToken():
                self._on_blank()

    def finish(self) -> None:
        self._finish_card()
        self._flush_pending()
        if not any(lst.cards for lst in self.lists):
            self.warnings.append("Nenhuma tarefa (- [ ] / - [x]) encontrada no arquivo.")

    # --- handlers -------------------------------------------------------------------------

    def _on_heading(self, token: HeadingToken) -> None:
        self._finish_card()
        self._flush_pending()

        if token.level == 1:
            if self.project is None:
                self.project = token.text
                return
            self.warnings.append(
                f"Linha {token.line}: heading '# {token.text}' adicional tratado como seção contextual."
            )
            self._context = [(2, token.text)]
            return

        if token.level == 2:
            self._list = self._get_or_create_list(token.text, from_filename=False)
            self._context = []
            return

        self._context = [(lvl, text) for lvl, text in self._context if lvl < token.level]
        self._context.append((token.level, token.text))

    def _on_task(self, token: TaskToken) -> None:
        if self._card is not None and token.indent > self._card.indent:
            self._card.add_item(token)
            return

        self._finish_card()
        if self._list is None:
            self._list = self._get_or_create_list(self.default_list_name, from_filename=True)
        self._card = _CardDraft(
            title=token.text,
            completed=token.checked,
            line=token.line,
            indent=token.indent,
            context=[text for _, text in self._context],
            intro=self._pending,
            project=self.project,
        )
        self._pending = []
        self._pending_line = None

    def _on_text(self, token: TextToken) -> None:
        if self._card is not None:
            self._card.add_text(token)
            return
        if not self._pending:
            self._pending_line = token.line
        self._pending.append(token.raw)

    def _on_blank(self) -> None:
        if self._card is not None:
            self._card.add_blank()
        elif self._pending and self._pending[-1] != "":
            self._pending.append("")

    # --- auxiliares -----------------------------------------------------------------------

    def _finish_card(self) -> None:
        if self._card is None:
            return
        assert self._list is not None
        self._list.cards.append(self._card.build())
        self._card = None

    def _flush_pending(self) -> None:
        text = _join(self._pending)
        if text:
            self.unassigned_text.append(text)
            self.warnings.append(
                f"Linha {self._pending_line}: texto sem tarefa associada não será enviado ao Trello."
            )
        self._pending = []
        self._pending_line = None

    def _get_or_create_list(self, name: str, *, from_filename: bool) -> ParsedList:
        for existing in self.lists:
            if existing.name.casefold() == name.casefold():
                return existing
        created = ParsedList(name=name, from_filename=from_filename)
        self.lists.append(created)
        return created
