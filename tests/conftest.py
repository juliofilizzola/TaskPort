from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_optional_trello_client
from app.clients.trello import TrelloClient
from app.core.config import Settings
from app.main import create_app
from tests.fake_trello import FakeTrello

TEST_KEY = "test-api-key-123"
TEST_TOKEN = "test-token-456"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_trello() -> FakeTrello:
    return FakeTrello()


@pytest.fixture
def sleeps() -> list[float]:
    return []


def build_client(fake: FakeTrello, sleeps: list[float], **kwargs: object) -> TrelloClient:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    options: dict[str, object] = {"max_retries": 2, "backoff": 0.5}
    options.update(kwargs)
    return TrelloClient(TEST_KEY, TEST_TOKEN, transport=fake.transport(), sleep=fake_sleep, **options)  # type: ignore[arg-type]


@pytest.fixture
async def trello_client(fake_trello: FakeTrello, sleeps: list[float]) -> AsyncIterator[TrelloClient]:
    client = build_client(fake_trello, sleeps)
    yield client
    await client.aclose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        trello_api_key=TEST_KEY,
        trello_token=TEST_TOKEN,
        max_upload_bytes=2048,
        max_files_per_request=3,
    )


@pytest.fixture
def api(settings: Settings, fake_trello: FakeTrello, sleeps: list[float]) -> Iterator[TestClient]:
    app = create_app(settings)
    client = build_client(fake_trello, sleeps)
    app.dependency_overrides[get_optional_trello_client] = lambda: client
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_without_trello() -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, trello_api_key=None, trello_token=None))  # type: ignore[call-arg]
    with TestClient(app) as test_client:
        yield test_client
