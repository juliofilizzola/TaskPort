"""Opção `completed_list`: tarefas concluídas vão para uma lista (ex.: Concluido) em vez de arquivadas."""

import pytest
from fastapi.testclient import TestClient

from app.clients.trello import TrelloClient
from app.core.errors import InvalidOptionsError
from app.parsers.markdown import MarkdownParser
from app.schemas.imports import CardAction, ExistingCardPolicy, ImportOptions, ImportStatus
from app.services.import_service import ImportService
from app.services.uploads import MarkdownFile
from tests.fake_trello import BOARD_ID, FakeTrello

pytestmark = pytest.mark.anyio

UPDATE_TO_DONE = ImportOptions(on_existing=ExistingCardPolicy.UPDATE, completed_list="Concluido")


def md(tasks: str) -> MarkdownFile:
    return MarkdownFile("relatorio.md", f"# Projeto\n## TODO\n{tasks}")


@pytest.fixture
def board(fake_trello: FakeTrello) -> dict[str, str]:
    """Quadro com as colunas de status do usuário."""
    return {name: fake_trello.add_list(name) for name in ("TODO", "EM ANDAMENTO", "Concluido", "STAND BY", "CANCELADOS")}


@pytest.fixture
def service(trello_client: TrelloClient) -> ImportService:
    return ImportService(MarkdownParser(), trello_client)


async def test_new_completed_cards_are_created_in_completed_list(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    report = await service.run_import([md("- [ ] Pendente\n- [x] Feita\n")], BOARD_ID, UPDATE_TO_DONE)

    assert report.status == ImportStatus.SUCCESS
    assert fake_trello.cards_named("Pendente")[0]["idList"] == board["TODO"]
    assert fake_trello.cards_named("Feita")[0]["idList"] == board["Concluido"]
    assert fake_trello.cards_named("Feita")[0]["closed"] is False
    assert report.summary.cards_moved_to_completed == 1
    assert report.summary.lists_created == 0
    done = next(c for c in report.cards if c.title == "Feita")
    assert done.moved_to_completed is True
    assert done.list_name == "Concluido"


async def test_completed_cards_are_moved_from_any_column(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    tasks = "- [ ] A\n- [ ] B\n- [ ] C\n- [ ] D\n"
    await service.run_import([md(tasks)], BOARD_ID, UPDATE_TO_DONE)
    # O usuário organiza o quadro manualmente.
    fake_trello.cards_named("A")[0]["idList"] = board["EM ANDAMENTO"]
    fake_trello.cards_named("B")[0]["idList"] = board["STAND BY"]
    fake_trello.cards_named("C")[0]["idList"] = board["CANCELADOS"]

    # Nova versão do relatório: A e B concluídas, C e D seguem pendentes.
    report = await service.run_import(
        [md("- [x] A\n- [x] B\n- [ ] C\n- [ ] D\n")], BOARD_ID, UPDATE_TO_DONE
    )

    assert report.status == ImportStatus.SUCCESS
    assert report.summary.cards_moved_to_completed == 2
    assert report.summary.cards_created == 0
    assert fake_trello.cards_named("A")[0]["idList"] == board["Concluido"]
    assert fake_trello.cards_named("B")[0]["idList"] == board["Concluido"]
    assert fake_trello.cards_named("C")[0]["idList"] == board["CANCELADOS"]  # pendente: não é movido
    assert fake_trello.cards_named("D")[0]["idList"] == board["TODO"]
    assert len(fake_trello.cards) == 4


async def test_reimport_does_not_move_again_or_reopen(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    await service.run_import([md("- [x] Feita\n- [x] Arquivada\n")], BOARD_ID, UPDATE_TO_DONE)
    fake_trello.cards_named("Arquivada")[0]["closed"] = True
    writes_before = len(fake_trello.writes)

    report = await service.run_import([md("- [x] Feita\n- [x] Arquivada\n")], BOARD_ID, UPDATE_TO_DONE)

    assert report.summary.cards_moved_to_completed == 0
    assert len(fake_trello.writes) == writes_before
    assert fake_trello.cards_named("Arquivada")[0]["closed"] is True


async def test_list_name_ignores_case_and_accents(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    options = ImportOptions(completed_list="concluído")

    await service.run_import([md("- [x] Feita\n")], BOARD_ID, options)

    assert fake_trello.cards_named("Feita")[0]["idList"] == board["Concluido"]


async def test_unknown_completed_list_fails_before_any_write(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    with pytest.raises(InvalidOptionsError) as exc_info:
        await service.run_import([md("- [x] Feita\n")], BOARD_ID, ImportOptions(completed_list="Done"))

    assert "Done" in exc_info.value.message
    assert "Concluido" in exc_info.value.details["available_lists"]
    assert fake_trello.writes == []


async def test_completed_list_and_archive_are_mutually_exclusive(
    service: ImportService, fake_trello: FakeTrello, board: dict[str, str]
) -> None:
    options = ImportOptions(completed_list="Concluido", archive_completed=True)

    with pytest.raises(InvalidOptionsError):
        await service.run_import([md("- [x] Feita\n")], BOARD_ID, options)
    assert fake_trello.writes == []


async def test_preview_shows_cards_to_move(service: ImportService, fake_trello: FakeTrello, board: dict[str, str]) -> None:
    await service.run_import([md("- [ ] A\n- [ ] B\n")], BOARD_ID, UPDATE_TO_DONE)
    writes_before = len(fake_trello.writes)

    preview = await service.preview(
        [md("- [x] A\n- [ ] B\n- [x] Nova\n")], BOARD_ID, ExistingCardPolicy.UPDATE, completed_list="Concluido"
    )

    cards = {c.title: c for c in preview.files[0].lists[0].cards}
    assert cards["A"].action == CardAction.UPDATE and cards["A"].move_to_completed is True
    assert cards["B"].move_to_completed is None
    assert cards["Nova"].action == CardAction.CREATE and cards["Nova"].move_to_completed is True
    assert preview.summary.cards_to_move_to_completed == 2
    assert len(fake_trello.writes) == writes_before


def test_api_accepts_completed_list(api: TestClient, fake_trello: FakeTrello) -> None:
    done_id = fake_trello.add_list("Concluido")
    files = [("files", ("a.md", b"## TODO\n- [x] Feita\n- [ ] Pendente\n", "text/markdown"))]

    response = api.post("/imports", files=files, data={"board_id": BOARD_ID, "completed_list": "Concluido"})

    assert response.status_code == 200
    assert response.json()["summary"]["cards_moved_to_completed"] == 1
    assert fake_trello.cards_named("Feita")[0]["idList"] == done_id


def test_api_rejects_invalid_completed_list(api: TestClient, fake_trello: FakeTrello) -> None:
    files = [("files", ("a.md", b"- [x] Feita\n", "text/markdown"))]

    missing = api.post("/imports", files=files, data={"board_id": BOARD_ID, "completed_list": "Concluido"})
    fake_trello.add_list("Concluido")
    both = api.post(
        "/imports",
        files=files,
        data={"board_id": BOARD_ID, "completed_list": "Concluido", "archive_completed": "true"},
    )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "invalid_options"
    assert both.status_code == 422
    assert fake_trello.writes == []
