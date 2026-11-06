from pathlib import Path

import pytest

from app.clients.trello import TrelloClient
from app.core.errors import TrelloNotConfiguredError, TrelloNotFoundError
from app.parsers.markdown import MarkdownParser
from app.schemas.imports import (
    CardAction,
    CardStatus,
    ExistingCardPolicy,
    ImportOptions,
    ImportStatus,
    ListAction,
)
from app.services.dedup import extract_fingerprint
from app.services.import_service import CHECKLIST_NAME, ImportService
from app.services.uploads import MarkdownFile
from tests.fake_trello import BOARD_ID, FakeTrello

pytestmark = pytest.mark.anyio

EXAMPLE = MarkdownFile(
    "jobs-control.md", (Path(__file__).parent.parent / "examples" / "jobs-control.md").read_text(encoding="utf-8")
)


@pytest.fixture
def service(trello_client: TrelloClient) -> ImportService:
    return ImportService(MarkdownParser(), trello_client)


async def test_import_creates_lists_cards_and_checklists(service: ImportService, fake_trello: FakeTrello) -> None:
    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.SUCCESS
    s = report.summary
    assert (s.files_processed, s.lists_created, s.cards_created) == (1, 3, 5)
    assert (s.checklists_created, s.checklist_items_created, s.cards_archived) == (1, 3, 0)
    assert report.errors == []

    assert sorted(lst["name"] for lst in fake_trello.lists.values()) == ["Backlog", "Concluído", "Em andamento"]
    auth_card = fake_trello.cards_named("Criar API de autenticação")[0]
    assert "Implementar autenticação utilizando JWT." in auth_card["desc"]
    assert extract_fingerprint(auth_card["desc"])
    checklist = fake_trello.checklist_of(auth_card["id"])
    assert checklist["name"] == CHECKLIST_NAME
    assert [(i["name"], i["state"]) for i in checklist["checkItems"]] == [
        ("Criar endpoint de login", "incomplete"),
        ("Criar endpoint de refresh token", "incomplete"),
        ("Criar schemas", "complete"),
    ]


async def test_existing_lists_are_reused(service: ImportService, fake_trello: FakeTrello) -> None:
    backlog_id = fake_trello.add_list("backlog")

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.summary.lists_reused == 1
    assert report.summary.lists_created == 2
    assert fake_trello.cards_named("Configurar integração AWS")[0]["idList"] == backlog_id


async def test_archive_completed_cards(service: ImportService, fake_trello: FakeTrello) -> None:
    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions(archive_completed=True))

    assert report.summary.cards_archived == 2
    archived = sorted(c["name"] for c in fake_trello.cards.values() if c["closed"])
    assert archived == ["Configurar estrutura do projeto", "Criar repositórios"]


async def test_reimport_does_not_duplicate(service: ImportService, fake_trello: FakeTrello) -> None:
    await service.run_import([EXAMPLE], BOARD_ID, ImportOptions(archive_completed=True))
    writes_before = len(fake_trello.writes)

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions(archive_completed=True))

    assert report.status == ImportStatus.SUCCESS
    assert report.summary.cards_created == 0
    assert report.summary.cards_skipped == 5  # inclusive os arquivados
    assert report.summary.lists_reused == 3
    assert len(fake_trello.writes) == writes_before
    assert len(fake_trello.cards) == 5


async def test_same_task_in_two_files_of_same_request_is_created_once(
    service: ImportService, fake_trello: FakeTrello
) -> None:
    content = "## Backlog\n- [ ] Tarefa compartilhada\n"
    files = [MarkdownFile("a.md", content), MarkdownFile("b.md", content)]

    report = await service.run_import(files, BOARD_ID, ImportOptions())

    assert report.summary.cards_created == 1
    assert report.summary.cards_skipped == 1
    assert len(fake_trello.cards_named("Tarefa compartilhada")) == 1


async def test_update_policy_syncs_description_and_checklist(service: ImportService, fake_trello: FakeTrello) -> None:
    await service.run_import([MarkdownFile("a.md", "- [ ] Pai\n  - [ ] Sub A\n")], BOARD_ID, ImportOptions())
    updated = MarkdownFile("a.md", "- [ ] Pai\n  Nova descrição.\n  - [x] Sub A\n  - [ ] Sub B\n")

    report = await service.run_import(
        [updated], BOARD_ID, ImportOptions(on_existing=ExistingCardPolicy.UPDATE)
    )

    assert report.summary.cards_updated == 1
    assert report.summary.checklist_items_updated == 1
    assert report.summary.checklist_items_created == 1
    assert report.summary.checklists_created == 0
    card = fake_trello.cards_named("Pai")[0]
    assert "Nova descrição." in card["desc"]
    states = {i["name"]: i["state"] for i in fake_trello.checklist_of(card["id"])["checkItems"]}
    assert states == {"Sub A": "complete", "Sub B": "incomplete"}
    assert len(fake_trello.cards) == 1


async def test_partial_failure_continues_and_reports(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/cards$", 400, times=1)  # falha só no primeiro cartão

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.PARTIAL
    assert report.aborted is False
    assert report.summary.cards_failed == 1
    assert report.summary.cards_created == 4
    assert report.summary.errors == 1
    assert report.errors[0].operation == "create_card"
    assert report.errors[0].card == "Criar API de autenticação"
    assert report.errors[0].upstream_status == 400

    # Uma nova importação completa apenas o que faltou, sem duplicar.
    retry = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())
    assert retry.summary.cards_created == 1
    assert retry.summary.cards_skipped == 4
    assert len(fake_trello.cards) == 5


async def test_checklist_item_failure_marks_card_as_partial(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/checkItems$", 400, times=1)

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.PARTIAL
    assert report.summary.checklist_items_created == 2
    assert [e.operation for e in report.errors] == ["add_checklist_item"]
    assert report.errors[0].card == "Criar API de autenticação › Criar endpoint de login"
    statuses = {c.title: c.status for c in report.cards}
    assert statuses["Criar API de autenticação"] == CardStatus.PARTIAL

    # Com a política update, a reimportação completa o item que faltou.
    retry = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions(on_existing=ExistingCardPolicy.UPDATE))
    assert retry.summary.checklist_items_created == 1
    card = fake_trello.cards_named("Criar API de autenticação")[0]
    assert len(fake_trello.checklist_of(card["id"])["checkItems"]) == 3


LABELED = MarkdownFile(
    "labels.md",
    "# Projeto\n## TODO\n"
    "- [ ] Tarefa crítica\n  **Etiquetas:** Crítica\n"
    "- [ ] Tarefa média\n  **Etiquetas:** Média, Rede\n"
    "- [ ] Outra crítica\n  **Etiquetas:** crítica\n",
)


async def test_labels_are_created_once_and_applied(service: ImportService, fake_trello: FakeTrello) -> None:
    existing = fake_trello.add_label("Rede", "purple")

    report = await service.run_import([LABELED], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.SUCCESS
    assert report.summary.labels_created == 2
    assert report.summary.card_labels_added == 4
    colors = {label["name"]: label["color"] for label in fake_trello.labels.values()}
    assert colors == {"Rede": "purple", "Crítica": "red", "Média": "yellow"}
    assert fake_trello.label_names(fake_trello.cards_named("Tarefa média")[0]) == ["Média", "Rede"]
    assert fake_trello.cards_named("Outra crítica")[0]["idLabels"] == fake_trello.cards_named("Tarefa crítica")[0]["idLabels"]
    assert existing in fake_trello.cards_named("Tarefa média")[0]["idLabels"]


async def test_update_adds_missing_labels_and_keeps_manual_ones(service: ImportService, fake_trello: FakeTrello) -> None:
    await service.run_import([MarkdownFile("a.md", "## TODO\n- [ ] Tarefa\n")], BOARD_ID, ImportOptions())
    card = fake_trello.cards_named("Tarefa")[0]
    manual = fake_trello.add_label("Manual")
    card["idLabels"].append(manual)

    labeled = MarkdownFile("a.md", "## TODO\n- [ ] Tarefa\n  Etiquetas: Alta\n")
    report = await service.run_import([labeled], BOARD_ID, ImportOptions(on_existing=ExistingCardPolicy.UPDATE))
    again = await service.run_import([labeled], BOARD_ID, ImportOptions(on_existing=ExistingCardPolicy.UPDATE))

    assert report.summary.card_labels_added == 1
    assert again.summary.card_labels_added == 0
    assert again.errors == []
    assert sorted(fake_trello.label_names(card)) == ["Alta", "Manual"]


async def test_label_creation_failure_is_partial(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/labels$", 400, times=1)

    report = await service.run_import([LABELED], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.PARTIAL
    assert [e.operation for e in report.errors] == ["create_label"]
    assert report.summary.cards_created == 3
    assert fake_trello.cards_named("Tarefa crítica")[0]["idLabels"] == []


async def test_moving_task_to_another_list_does_not_duplicate(service: ImportService, fake_trello: FakeTrello) -> None:
    await service.run_import([MarkdownFile("a.md", "## Alta\n- [ ] Tarefa\n")], BOARD_ID, ImportOptions())

    report = await service.run_import([MarkdownFile("a.md", "## TODO\n- [ ] Tarefa\n")], BOARD_ID, ImportOptions())

    assert report.summary.cards_created == 0
    assert report.summary.cards_skipped == 1
    assert len(fake_trello.cards) == 1


async def test_preview_counts_labels_to_create(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.add_label("Rede")

    preview = await service.preview([LABELED], BOARD_ID)

    assert preview.summary.labels == 3
    assert preview.summary.labels_to_create == 2
    assert preview.files[0].lists[0].cards[1].labels == ["Média", "Rede"]
    assert fake_trello.writes == []


async def test_list_creation_failure_marks_its_cards_as_failed(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/lists$", 400, times=1)

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.PARTIAL
    failed = [c.title for c in report.cards if c.status == CardStatus.FAILED]
    assert failed == ["Criar API de autenticação", "Configurar integração AWS"]
    assert report.summary.cards_created == 3


async def test_auth_failure_mid_import_aborts(service: ImportService, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/cards$", 401, times=99)

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.aborted is True
    assert report.status == ImportStatus.PARTIAL  # a primeira lista foi criada
    assert len(report.errors) == 1
    assert report.summary.files_processed == 0


async def test_rate_limit_during_import_is_retried(
    service: ImportService, fake_trello: FakeTrello, sleeps: list[float]
) -> None:
    fake_trello.fail("POST", r"/1/cards$", 429, times=2)

    report = await service.run_import([EXAMPLE], BOARD_ID, ImportOptions())

    assert report.status == ImportStatus.SUCCESS
    assert len(sleeps) == 2


async def test_unknown_board_fails_before_any_write(service: ImportService, fake_trello: FakeTrello) -> None:
    with pytest.raises(TrelloNotFoundError):
        await service.run_import([EXAMPLE], "aaaaaaaaaaaaaaaaaaaaaaaa", ImportOptions())
    assert fake_trello.writes == []


async def test_preview_without_board_does_not_call_trello(fake_trello: FakeTrello) -> None:
    preview = await ImportService(MarkdownParser(), None).preview([EXAMPLE])

    assert preview.summary.cards == 5
    assert preview.summary.completed_cards == 2
    assert preview.summary.checklist_items == 3
    assert preview.summary.cards_to_create is None
    assert fake_trello.requests == []


async def test_preview_with_board_plans_actions_without_writing(
    service: ImportService, fake_trello: FakeTrello
) -> None:
    await service.run_import([MarkdownFile("x.md", "## Backlog\n- [ ] Criar API de autenticação\n")], BOARD_ID, ImportOptions())
    writes_before = len(fake_trello.writes)

    preview = await service.preview([EXAMPLE], BOARD_ID)

    assert len(fake_trello.writes) == writes_before
    backlog = preview.files[0].lists[0]
    assert backlog.action == ListAction.REUSE
    assert preview.files[0].lists[1].action == ListAction.CREATE
    # A tarefa importada por x.md tem outro projeto (None), logo outro fingerprint.
    assert backlog.cards[0].action == CardAction.CREATE
    assert preview.summary.cards_to_create == 5

    preview_again = await service.preview([MarkdownFile("x.md", "## Backlog\n- [ ] Criar API de autenticação\n")], BOARD_ID)
    assert preview_again.files[0].lists[0].cards[0].action == CardAction.SKIP
    assert preview_again.summary.cards_to_skip == 1


async def test_import_requires_configured_client() -> None:
    with pytest.raises(TrelloNotConfiguredError):
        await ImportService(MarkdownParser(), None).run_import([EXAMPLE], BOARD_ID, ImportOptions())
