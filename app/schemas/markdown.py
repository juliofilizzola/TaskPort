"""Estrutura intermediária produzida pelo parser de Markdown."""

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    name: str
    checked: bool = False


class ParsedCard(BaseModel):
    title: str
    description: str = ""
    completed: bool = False
    checklist: list[ChecklistItem] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list, description="Etiquetas do cartão (linha `Etiquetas: ...`).")
    context: list[str] = Field(default_factory=list, description="Hierarquia de headings ### (ou mais) acima da tarefa.")
    line: int = Field(description="Linha da tarefa no arquivo de origem.")
    fingerprint: str = Field(default="", description="Identificador estável da tarefa, usado contra duplicidade.")


class ParsedList(BaseModel):
    name: str
    from_filename: bool = Field(default=False, description="True quando o nome veio do arquivo (sem heading ##).")
    cards: list[ParsedCard] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    filename: str
    content_sha256: str
    project: str | None = None
    lists: list[ParsedList] = Field(default_factory=list)
    unassigned_text: list[str] = Field(
        default_factory=list,
        description="Trechos que não puderam ser associados a nenhuma tarefa (não serão enviados ao Trello).",
    )
    warnings: list[str] = Field(default_factory=list)

    def iter_cards(self) -> "list[tuple[ParsedList, ParsedCard]]":
        return [(lst, card) for lst in self.lists for card in lst.cards]
