import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import extract_bearer_token
from app.core.config import API_TOKEN_MIN_LENGTH, Settings
from app.main import create_app
from tests.conftest import TEST_API_TOKEN
from tests.fake_trello import BOARD_ID

PROTECTED = [("GET", "/boards"), ("POST", "/preview")]


@pytest.fixture
def anon(settings: Settings) -> TestClient:
    """Cliente sem cabeçalho de autenticação, com o token configurado."""
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_route_without_token_returns_401(anon: TestClient, method: str, path: str) -> None:
    response = anon.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_token_returns_401(anon: TestClient) -> None:
    response = anon.get("/boards", headers={"Authorization": "Bearer nao-e-o-token-correto-1234567890"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Token inválido."


@pytest.mark.parametrize(
    "header",
    [
        "Basic " + TEST_API_TOKEN,  # esquema errado
        "Bearer",  # sem token
        f"Bearer {TEST_API_TOKEN} extra",  # partes a mais
        TEST_API_TOKEN,  # sem esquema
    ],
)
def test_malformed_authorization_returns_401(anon: TestClient, header: str) -> None:
    response = anon.get("/boards", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Token ausente ou mal formatado."


def test_valid_token_is_accepted_with_case_insensitive_scheme(anon: TestClient) -> None:
    response = anon.get("/health", headers={"Authorization": f"bearer {TEST_API_TOKEN}"})
    assert response.status_code == 200

    response = anon.get("/boards", headers={"Authorization": f"bearer {TEST_API_TOKEN}"})
    # Sem Trello configurado nesta app de teste, o erro vem da camada de negócio, não da autenticação.
    assert response.status_code != 401


def test_upload_is_rejected_before_reading_body(anon: TestClient) -> None:
    response = anon.post("/preview", files=[("files", ("a.md", b"# A\n", "text/markdown"))])
    assert response.status_code == 401


def test_health_and_docs_are_public(anon: TestClient) -> None:
    assert anon.get("/health").status_code == 200
    assert anon.get("/openapi.json").status_code == 200
    assert anon.get("/docs").status_code == 200


def test_fails_closed_when_token_not_configured() -> None:
    app = create_app(Settings(_env_file=None, trello_api_key=None, trello_token=None))  # type: ignore[call-arg]
    with TestClient(app) as client:
        response = client.get("/boards", headers={"Authorization": f"Bearer {TEST_API_TOKEN}"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "auth_not_configured"
        # Health continua público para diagnóstico do próprio servidor.
        assert client.get("/health").status_code == 200


def test_token_is_redacted_from_logs(settings: Settings) -> None:
    assert TEST_API_TOKEN in settings.secret_values()


def test_import_still_works_with_token(api: TestClient) -> None:
    assert api.get("/boards").json()[0]["id"] == BOARD_ID


@pytest.mark.parametrize(
    "value",
    [
        "x" * (API_TOKEN_MIN_LENGTH - 1),  # curto demais
        "tem espaco no meio do token com tamanho suficiente",
    ],
)
def test_settings_reject_weak_or_malformed_token(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_token=value)  # type: ignore[call-arg]


def test_empty_token_means_not_configured() -> None:
    assert Settings(_env_file=None, api_token="").api_token is None  # type: ignore[call-arg]
    assert Settings(_env_file=None, api_token="   ").api_token is None  # type: ignore[call-arg]


def test_token_is_stripped() -> None:
    settings = Settings(_env_file=None, api_token=f"  {TEST_API_TOKEN}\n")  # type: ignore[call-arg]
    assert settings.api_token is not None
    assert settings.api_token.get_secret_value() == TEST_API_TOKEN


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("  Bearer abc  ", "abc"),
        ("Bearer", None),
        ("Bearer  abc", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer_token(header: str | None, expected: str | None) -> None:
    assert extract_bearer_token(header) == expected
