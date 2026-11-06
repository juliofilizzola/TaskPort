"""Regras de negócio da pré-visualização e da importação para o Trello."""

import logging
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.clients.trello import TrelloClient
from app.core.errors import TrelloAuthError, TrelloError, TrelloNotConfiguredError
from app.parsers.markdown import MarkdownParser
from app.schemas.imports import (
    CardAction,
    CardPreview,
    CardResult,
    CardStatus,
    ExistingCardPolicy,
    FilePreview,
    FileResult,
    ImportOptions,
    ImportResponse,
    ImportStatus,
    ImportSummary,
    ListAction,
    ListPreview,
    OperationError,
    PreviewResponse,
    PreviewSummary,
)
from app.schemas.markdown import ParsedCard, ParsedDocument
from app.schemas.trello import TrelloCard, TrelloChecklist
from app.services.dedup import assign_fingerprints, extract_fingerprint, with_marker
from app.services.uploads import MarkdownFile

logger = logging.getLogger("taskport.import")

CHECKLIST_NAME = "Subtarefas"

# Cores das etiquetas criadas automaticamente (nome normalizado, sem acento).
LABEL_COLORS = {
    "critica": "red",
    "critico": "red",
    "alta": "orange",
    "alto": "orange",
    "media": "yellow",
    "medio": "yellow",
    "baixa": "green",
    "baixo": "green",
    "informativo": "blue",
    "info": "blue",
}
DEFAULT_LABEL_COLOR = "sky"


def label_color(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().strip().casefold()
    return LABEL_COLORS.get(plain, DEFAULT_LABEL_COLOR)


@dataclass
class BoardState:
    """Estado conhecido do quadro: listas abertas por nome e cartões já importados por fingerprint.

    Durante a importação é atualizado com o que foi criado, de modo que tarefas repetidas
    entre arquivos da mesma requisição também não sejam duplicadas.
    """

    lists: dict[str, str | None] = field(default_factory=dict)  # nome normalizado -> id (None = planejada)
    cards: dict[str, TrelloCard | None] = field(default_factory=dict)  # fingerprint -> cartão (None = planejado)
    labels: dict[str, str | None] = field(default_factory=dict)  # nome normalizado -> id (None = planejada)

    @staticmethod
    def key(name: str) -> str:
        return " ".join(name.split()).casefold()

    @classmethod
    async def load(cls, client: TrelloClient, board_id: str) -> "BoardState":
        await client.get_board(board_id)  # valida acesso ao quadro antes de qualquer escrita
        state = cls()
        for trello_list in await client.get_lists(board_id):
            state.lists.setdefault(cls.key(trello_list.name), trello_list.id)
        for card in await client.get_cards(board_id):
            if fingerprint := extract_fingerprint(card.desc):
                state.cards.setdefault(fingerprint, card)
        for label in await client.get_labels(board_id):
            if label.name.strip():
                state.labels.setdefault(cls.key(label.name), label.id)
        return state


class ImportService:
    def __init__(self, parser: MarkdownParser, client: TrelloClient | None = None) -> None:
        self._parser = parser
        self._client = client

    def parse(self, files: Sequence[MarkdownFile]) -> list[ParsedDocument]:
        documents = [self._parser.parse(f.content, f.filename) for f in files]
        for document in documents:
            assign_fingerprints(document)
        return documents

    # --- Pré-visualização (somente leitura) ------------------------------------------------

    async def preview(
        self,
        files: Sequence[MarkdownFile],
        board_id: str | None = None,
        on_existing: ExistingCardPolicy = ExistingCardPolicy.SKIP,
    ) -> PreviewResponse:
        documents = self.parse(files)
        state = await BoardState.load(self._require_client(), board_id) if board_id else None

        previews = [self._preview_document(doc, state, on_existing) for doc in documents]
        cards = [card for f in previews for lst in f.lists for card in lst.cards]
        summary = PreviewSummary(
            files=len(previews),
            lists=sum(len(f.lists) for f in previews),
            cards=len(cards),
            completed_cards=sum(c.completed for c in cards),
            checklist_items=sum(len(c.checklist) for c in cards),
            labels=len({BoardState.key(label) for c in cards for label in c.labels}),
        )
        if state is not None:
            summary.lists_to_create = sum(lst.action == ListAction.CREATE for f in previews for lst in f.lists)
            summary.cards_to_create = sum(c.action == CardAction.CREATE for c in cards)
            summary.cards_to_update = sum(c.action == CardAction.UPDATE for c in cards)
            summary.cards_to_skip = sum(c.action == CardAction.SKIP for c in cards)
            summary.labels_to_create = len(
                {BoardState.key(label) for c in cards for label in c.labels} - set(state.labels)
            )
        return PreviewResponse(board_id=board_id, summary=summary, files=previews)

    @staticmethod
    def _preview_document(
        document: ParsedDocument, state: BoardState | None, on_existing: ExistingCardPolicy
    ) -> FilePreview:
        preview = FilePreview.model_validate(document.model_dump())
        if state is None:
            return preview
        for lst in preview.lists:
            key = BoardState.key(lst.name)
            if key in state.lists:
                lst.action, lst.existing_list_id = ListAction.REUSE, state.lists[key]
            else:
                lst.action = ListAction.CREATE
                state.lists[key] = None
            for card in lst.cards:
                _plan_card(card, state, on_existing)
        return preview

    # --- Importação ------------------------------------------------------------------------

    async def run_import(self, files: Sequence[MarkdownFile], board_id: str, options: ImportOptions) -> ImportResponse:
        client = self._require_client()
        documents = self.parse(files)
        # Falhas aqui (credencial inválida, quadro inexistente) abortam antes de qualquer escrita.
        state = await BoardState.load(client, board_id)

        run = _ImportRun(client, board_id, state, options)
        logger.info("import_started", extra={"board_id": board_id, "files": len(documents)})
        await run.execute(documents)
        response = run.response(documents)
        logger.info(
            "import_finished",
            extra={"board_id": board_id, "status": response.status, **response.summary.model_dump()},
        )
        return response

    def _require_client(self) -> TrelloClient:
        if self._client is None:
            raise TrelloNotConfiguredError("Credenciais do Trello não configuradas (TRELLO_API_KEY/TRELLO_TOKEN).")
        return self._client


def _plan_card(card: CardPreview, state: BoardState, on_existing: ExistingCardPolicy) -> None:
    if card.fingerprint in state.cards:
        existing = state.cards[card.fingerprint]
        card.existing_card_id = existing.id if existing else None
        update = on_existing == ExistingCardPolicy.UPDATE and existing is not None
        card.action = CardAction.UPDATE if update else CardAction.SKIP
    else:
        card.action = CardAction.CREATE
        state.cards[card.fingerprint] = None


class _Aborted(Exception):
    """Interrompe a importação (ex.: credenciais revogadas no meio do processo)."""


class _ImportRun:
    """Executa a importação acumulando resultados e erros parciais.

    Não há rollback automático: o relatório indica exatamente o que foi criado e o que
    falhou, e uma nova importação dos mesmos arquivos completa apenas o que falta.
    """

    def __init__(self, client: TrelloClient, board_id: str, state: BoardState, options: ImportOptions) -> None:
        self.client = client
        self.board_id = board_id
        self.state = state
        self.options = options
        self.summary = ImportSummary()
        self.cards: list[CardResult] = []
        self.errors: list[OperationError] = []
        self.aborted = False

    async def execute(self, documents: list[ParsedDocument]) -> None:
        try:
            for document in documents:
                await self._import_document(document)
                self.summary.files_processed += 1
        except _Aborted:
            self.aborted = True

    def response(self, documents: list[ParsedDocument]) -> ImportResponse:
        self.summary.errors = len(self.errors)
        self.summary.cards_failed = sum(c.status == CardStatus.FAILED for c in self.cards)
        succeeded = any(c.status != CardStatus.FAILED for c in self.cards) or self.summary.lists_created > 0
        if not self.errors:
            status = ImportStatus.SUCCESS
        elif succeeded:
            status = ImportStatus.PARTIAL
        else:
            status = ImportStatus.FAILED
        return ImportResponse(
            board_id=self.board_id,
            status=status,
            aborted=self.aborted,
            summary=self.summary,
            files=[
                FileResult(filename=d.filename, content_sha256=d.content_sha256, cards=len(d.iter_cards()))
                for d in documents
            ],
            cards=self.cards,
            errors=self.errors,
        )

    # --- etapas ----------------------------------------------------------------------------

    async def _import_document(self, document: ParsedDocument) -> None:
        for lst in document.lists:
            try:
                list_id = await self._ensure_list(lst.name)
            except TrelloError as exc:
                self._record(exc, document.filename, "create_list", lst.name)
                for card in lst.cards:
                    self.cards.append(self._result(document.filename, lst.name, card, CardStatus.FAILED))
                continue
            for card in lst.cards:
                await self._import_card(document.filename, lst.name, list_id, card)

    async def _ensure_list(self, name: str) -> str:
        key = BoardState.key(name)
        if list_id := self.state.lists.get(key):
            self.summary.lists_reused += 1
            return list_id
        created = await self.client.create_list(self.board_id, name)
        self.state.lists[key] = created.id
        self.summary.lists_created += 1
        return created.id

    async def _import_card(self, filename: str, list_name: str, list_id: str, card: ParsedCard) -> None:
        if card.fingerprint in self.state.cards:
            existing = self.state.cards[card.fingerprint]
            if self.options.on_existing == ExistingCardPolicy.UPDATE and existing is not None:
                await self._update_card(filename, list_name, card, existing)
            else:
                self.summary.cards_skipped += 1
                self.cards.append(self._result(filename, list_name, card, CardStatus.SKIPPED, existing))
            return
        await self._create_card(filename, list_name, list_id, card)

    async def _create_card(self, filename: str, list_name: str, list_id: str, card: ParsedCard) -> None:
        result = self._result(filename, list_name, card, CardStatus.CREATED)
        self.cards.append(result)
        label_ids = await self._ensure_labels(card, result)
        try:
            created = await self.client.create_card(
                list_id, card.title, with_marker(card.description, card.fingerprint), label_ids
            )
        except TrelloError as exc:
            result.status = CardStatus.FAILED
            self._record(exc, filename, "create_card", list_name, card.title)
            return

        self.summary.cards_created += 1
        self.summary.card_labels_added += len(label_ids)
        self.state.cards[card.fingerprint] = created
        result.card_id, result.url = created.id, created.url

        await self._sync_checklist(created.id, card, result, existing=[])
        if card.completed and self.options.archive_completed:
            await self._archive(created.id, card, result)

    async def _update_card(self, filename: str, list_name: str, card: ParsedCard, existing: TrelloCard) -> None:
        result = self._result(filename, list_name, card, CardStatus.UPDATED, existing)
        self.cards.append(result)

        changes: dict[str, str] = {}
        description = with_marker(card.description, card.fingerprint)
        if existing.name != card.title:
            changes["name"] = card.title
        if existing.desc != description:
            changes["desc"] = description
        try:
            if changes:
                await self.client.update_card(existing.id, **changes)
            checklists = await self.client.get_card_checklists(existing.id) if card.checklist else []
        except TrelloError as exc:
            result.status = CardStatus.FAILED
            self._record(exc, filename, "update_card", list_name, card.title)
            return

        self.summary.cards_updated += 1
        await self._add_missing_labels(existing, card, result)
        await self._sync_checklist(existing.id, card, result, existing=checklists)
        if card.completed and self.options.archive_completed and not existing.closed:
            await self._archive(existing.id, card, result)

    async def _sync_checklist(
        self, card_id: str, card: ParsedCard, result: CardResult, existing: list[TrelloChecklist]
    ) -> None:
        """Cria a checklist e seus itens, ou sincroniza o estado dos itens já existentes.
        Itens presentes apenas no Trello nunca são removidos."""
        if not card.checklist:
            return
        checklist = next((c for c in existing if c.name == CHECKLIST_NAME), None)
        if checklist is None:
            try:
                checklist = await self.client.create_checklist(card_id, CHECKLIST_NAME)
            except TrelloError as exc:
                result.status = CardStatus.PARTIAL
                self._record(exc, result.file, "create_checklist", result.list_name, card.title)
                return
            self.summary.checklists_created += 1

        current = {item.name: item for item in checklist.check_items}
        for item in card.checklist:
            found = current.get(item.name)
            try:
                if found is None:
                    await self.client.add_checklist_item(checklist.id, item.name, item.checked)
                    self.summary.checklist_items_created += 1
                elif found.complete != item.checked:
                    await self.client.set_checklist_item_state(card_id, found.id, item.checked)
                    self.summary.checklist_items_updated += 1
            except TrelloError as exc:
                result.status = CardStatus.PARTIAL
                operation = "add_checklist_item" if found is None else "update_checklist_item"
                self._record(exc, result.file, operation, result.list_name, f"{card.title} › {item.name}")

    async def _ensure_labels(self, card: ParsedCard, result: CardResult) -> list[str]:
        """IDs das etiquetas do cartão, criando no quadro as que ainda não existem."""
        ids: list[str] = []
        for name in card.labels:
            key = BoardState.key(name)
            label_id = self.state.labels.get(key)
            if label_id is None:
                try:
                    created = await self.client.create_label(self.board_id, name, label_color(name))
                except TrelloError as exc:
                    result.status = CardStatus.PARTIAL
                    self._record(exc, result.file, "create_label", result.list_name, f"{card.title} › {name}")
                    continue
                label_id = created.id
                self.state.labels[key] = label_id
                self.summary.labels_created += 1
            ids.append(label_id)
        return ids

    async def _add_missing_labels(self, existing: TrelloCard, card: ParsedCard, result: CardResult) -> None:
        """Adiciona as etiquetas que faltam; etiquetas colocadas manualmente no Trello são mantidas."""
        for label_id in await self._ensure_labels(card, result):
            if label_id in existing.id_labels:
                continue
            try:
                await self.client.add_label_to_card(existing.id, label_id)
            except TrelloError as exc:
                result.status = CardStatus.PARTIAL
                self._record(exc, result.file, "add_label", result.list_name, card.title)
                continue
            existing.id_labels.append(label_id)
            self.summary.card_labels_added += 1

    async def _archive(self, card_id: str, card: ParsedCard, result: CardResult) -> None:
        try:
            await self.client.archive_card(card_id)
        except TrelloError as exc:
            result.status = CardStatus.PARTIAL
            self._record(exc, result.file, "archive_card", result.list_name, card.title)
            return
        result.archived = True
        self.summary.cards_archived += 1

    # --- auxiliares ------------------------------------------------------------------------

    @staticmethod
    def _result(
        filename: str, list_name: str, card: ParsedCard, status: CardStatus, trello_card: TrelloCard | None = None
    ) -> CardResult:
        return CardResult(
            file=filename,
            list_name=list_name,
            title=card.title,
            fingerprint=card.fingerprint,
            status=status,
            card_id=trello_card.id if trello_card else None,
            url=trello_card.url if trello_card else None,
        )

    def _record(
        self, exc: TrelloError, filename: str, operation: str, list_name: str | None = None, card: str | None = None
    ) -> None:
        self.errors.append(
            OperationError(
                file=filename,
                list_name=list_name,
                card=card,
                operation=operation,
                message=exc.message,
                upstream_status=exc.upstream_status,
            )
        )
        logger.warning(
            "import_operation_failed",
            extra={"board_id": self.board_id, "operation": operation, "file": filename, "error_code": exc.code},
        )
        if isinstance(exc, TrelloAuthError):
            # Sem credenciais válidas nenhuma operação seguinte terá sucesso.
            raise _Aborted from exc
