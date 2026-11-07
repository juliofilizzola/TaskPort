"""Contratos de entrada e saída dos endpoints de pré-visualização e importação."""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.markdown import ParsedCard, ParsedDocument, ParsedList

# IDs do Trello: 24 caracteres hexadecimais ou shortLink de 8 caracteres.
BOARD_ID_PATTERN = r"^[A-Za-z0-9]{8,24}$"


class ExistingCardPolicy(StrEnum):
    SKIP = "skip"
    UPDATE = "update"


class ListAction(StrEnum):
    CREATE = "create"
    REUSE = "reuse"


class CardAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"


class ImportOptions(BaseModel):
    archive_completed: bool = False
    on_existing: ExistingCardPolicy = ExistingCardPolicy.SKIP
    completed_list: str | None = None


# --- Pré-visualização ------------------------------------------------------------------------


class CardPreview(ParsedCard):
    action: CardAction | None = Field(default=None, description="Preenchido somente quando board_id é informado.")
    existing_card_id: str | None = None
    move_to_completed: bool | None = Field(
        default=None, description="True se o cartão concluído irá para a lista `completed_list`."
    )


class ListPreview(ParsedList):
    cards: list[CardPreview] = Field(default_factory=list)  # type: ignore[assignment]
    action: ListAction | None = None
    existing_list_id: str | None = None


class FilePreview(ParsedDocument):
    lists: list[ListPreview] = Field(default_factory=list)  # type: ignore[assignment]


class PreviewSummary(BaseModel):
    files: int
    lists: int
    cards: int
    completed_cards: int
    checklist_items: int
    labels: int = 0
    lists_to_create: int | None = None
    labels_to_create: int | None = None
    cards_to_create: int | None = None
    cards_to_update: int | None = None
    cards_to_skip: int | None = None
    cards_to_move_to_completed: int | None = None


class PreviewResponse(BaseModel):
    board_id: str | None
    summary: PreviewSummary
    files: list[FilePreview]


# --- Importação ------------------------------------------------------------------------------


class CardStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


class ImportStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class OperationError(BaseModel):
    file: str
    list_name: str | None = None
    card: str | None = None
    operation: str
    message: str
    upstream_status: int | None = None


class CardResult(BaseModel):
    file: str
    list_name: str
    title: str
    fingerprint: str
    status: CardStatus
    card_id: str | None = None
    url: str | None = None
    archived: bool = False
    moved_to_completed: bool = False


class FileResult(BaseModel):
    filename: str
    content_sha256: str
    cards: int


class ImportSummary(BaseModel):
    files_processed: int = 0
    lists_created: int = 0
    lists_reused: int = 0
    cards_created: int = 0
    cards_updated: int = 0
    cards_skipped: int = 0
    cards_failed: int = 0
    checklists_created: int = 0
    checklist_items_created: int = 0
    checklist_items_updated: int = 0
    labels_created: int = 0
    card_labels_added: int = 0
    cards_moved_to_completed: int = 0
    cards_archived: int = 0
    errors: int = 0


class ImportResponse(BaseModel):
    board_id: str
    status: ImportStatus
    aborted: bool = Field(default=False, description="True se a importação foi interrompida antes do fim.")
    summary: ImportSummary
    files: list[FileResult]
    cards: list[CardResult]
    errors: list[OperationError]
