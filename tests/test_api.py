import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, redact
from tests.conftest import TEST_KEY, TEST_TOKEN
from tests.fake_trello import BOARD_ID, FakeTrello

EXAMPLE = b"# Projeto\n## Backlog\n- [ ] Tarefa A\n  - [x] Sub\n## Feito\n- [x] Tarefa B\n"


def md(name: str, content: bytes = EXAMPLE) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, content, "text/markdown"))


def test_health(api: TestClient) -> None:
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["trello_configured"] is True


def test_health_without_credentials(api_without_trello: TestClient) -> None:
    assert api_without_trello.get("/health").json()["trello_configured"] is False


def test_list_boards(api: TestClient) -> None:
    response = api.get("/boards")
    assert response.status_code == 200
    assert response.json() == [{"id": BOARD_ID, "name": "Jobs", "url": "https://trello.com/b/x"}]


def test_boards_without_credentials_returns_503(api_without_trello: TestClient) -> None:
    response = api_without_trello.get("/boards")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "trello_not_configured"


def test_boards_with_invalid_credentials_returns_502(api: TestClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", 401)
    response = api.get("/boards")
    assert response.status_code == 502
    body = response.text
    assert response.json()["error"]["code"] == "trello_auth_failed"
    assert TEST_KEY not in body and TEST_TOKEN not in body


def test_preview_multiple_files_without_trello(api_without_trello: TestClient) -> None:
    response = api_without_trello.post("/preview", files=[md("a.md"), md("b.md", b"- [ ] Solta\n")])

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["files"] == 2
    assert data["summary"]["cards"] == 3
    assert data["files"][1]["lists"][0]["name"] == "b"
    assert data["files"][0]["lists"][0]["cards"][0]["checklist"] == [{"name": "Sub", "checked": True}]


def test_preview_with_board_does_not_write(api: TestClient, fake_trello: FakeTrello) -> None:
    response = api.post("/preview", files=[md("a.md")], data={"board_id": BOARD_ID})

    assert response.status_code == 200
    assert response.json()["summary"]["cards_to_create"] == 2
    assert fake_trello.writes == []


def test_import_end_to_end(api: TestClient, fake_trello: FakeTrello) -> None:
    response = api.post(
        "/imports",
        files=[md("a.md")],
        data={"board_id": BOARD_ID, "archive_completed": "true"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["summary"]["lists_created"] == 2
    assert data["summary"]["cards_created"] == 2
    assert data["summary"]["checklists_created"] == 1
    assert data["summary"]["checklist_items_created"] == 1
    assert data["summary"]["cards_archived"] == 1
    assert data["files"][0]["filename"] == "a.md"

    again = api.post("/imports", files=[md("a.md")], data={"board_id": BOARD_ID}).json()
    assert again["summary"]["cards_skipped"] == 2
    assert len(fake_trello.cards) == 2


def test_import_requires_board_id(api: TestClient) -> None:
    assert api.post("/imports", files=[md("a.md")]).status_code == 422


def test_import_rejects_malformed_board_id(api: TestClient) -> None:
    response = api.post("/imports", files=[md("a.md")], data={"board_id": "../members/me"})
    assert response.status_code == 422


def test_import_unknown_board_returns_404(api: TestClient) -> None:
    response = api.post("/imports", files=[md("a.md")], data={"board_id": "a" * 24})
    assert response.status_code == 404


def test_invalid_file_returns_422(api: TestClient, fake_trello: FakeTrello) -> None:
    response = api.post("/imports", files=[md("a.md"), md("b.txt")], data={"board_id": BOARD_ID})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file"
    assert fake_trello.requests == []


def test_empty_file_returns_422(api: TestClient) -> None:
    assert api.post("/preview", files=[md("a.md", b"")]).status_code == 422


def test_large_file_returns_413(api: TestClient) -> None:
    response = api.post("/preview", files=[md("a.md", b"- [ ] x\n" * 1000)])
    assert response.status_code == 413


def test_too_many_files_returns_413(api: TestClient) -> None:
    response = api.post("/preview", files=[md(f"{i}.md") for i in range(4)])
    assert response.status_code == 413


def test_trello_unavailable_returns_504(api: TestClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", 503, times=10)
    assert api.get("/boards").status_code == 504


def test_trello_rate_limit_returns_503(api: TestClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", 429, times=10)
    response = api.get("/boards")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "trello_rate_limited"


def test_openapi_documents_endpoints(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]
    assert {"/health", "/boards", "/preview", "/imports"} <= set(paths)


def test_logs_never_contain_credentials() -> None:
    formatter = JsonFormatter(secrets=[TEST_KEY, TEST_TOKEN])
    record = logging.LogRecord("t", logging.INFO, "", 0, f"url?key={TEST_KEY}&token={TEST_TOKEN}", None, None)
    record.header = f'OAuth oauth_consumer_key="{TEST_KEY}", oauth_token="{TEST_TOKEN}"'

    output = formatter.format(record)

    assert TEST_KEY not in output and TEST_TOKEN not in output
    assert json.loads(output)["message"] == "url?key=***&token=***"
    assert "oauth_token=***" in redact('oauth_token="abc"')
