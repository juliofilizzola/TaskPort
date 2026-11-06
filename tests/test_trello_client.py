import httpx
import pytest

from app.clients.trello import TrelloClient
from app.core.errors import (
    TrelloAuthError,
    TrelloError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloUnavailableError,
)
from tests.conftest import TEST_KEY, TEST_TOKEN
from tests.fake_trello import BOARD_ID, FakeTrello

pytestmark = pytest.mark.anyio


async def test_credentials_are_sent_only_in_header(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    await trello_client.get_boards()

    request = fake_trello.requests[0]
    assert TEST_KEY not in str(request.url)
    assert TEST_TOKEN not in str(request.url)
    assert request.headers["Authorization"] == f'OAuth oauth_consumer_key="{TEST_KEY}", oauth_token="{TEST_TOKEN}"'


async def test_rate_limit_is_retried_honoring_retry_after(
    trello_client: TrelloClient, fake_trello: FakeTrello, sleeps: list[float]
) -> None:
    fake_trello.fail("POST", r"/1/cards$", 429, times=2, headers={"Retry-After": "3"})
    list_id = fake_trello.add_list("Backlog")

    card = await trello_client.create_card(list_id, "Tarefa", "")

    assert card.name == "Tarefa"
    assert sleeps == [3.0, 3.0]
    assert len(fake_trello.cards) == 1


async def test_rate_limit_uses_exponential_backoff_without_header(
    trello_client: TrelloClient, fake_trello: FakeTrello, sleeps: list[float]
) -> None:
    fake_trello.fail("GET", r"/boards$", 429, times=2)

    await trello_client.get_boards()

    assert sleeps == [0.5, 1.0]


async def test_rate_limit_exhausted_raises(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", 429, times=10)

    with pytest.raises(TrelloRateLimitError):
        await trello_client.get_boards()
    assert len(fake_trello.requests) == 3  # 1 tentativa + 2 retries


async def test_server_error_is_retried_for_get(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", 503, times=1)

    boards = await trello_client.get_boards()

    assert [b.id for b in boards] == [BOARD_ID]


async def test_server_error_is_not_retried_for_post(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/lists$", 500, times=1)

    with pytest.raises(TrelloUnavailableError):
        await trello_client.create_list(BOARD_ID, "Backlog")
    assert len(fake_trello.requests) == 1  # evita criar a lista em duplicidade


async def test_timeout_on_post_is_not_retried(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("POST", r"/1/lists$", exception=httpx.ReadTimeout("timeout"))

    with pytest.raises(TrelloUnavailableError, match="Tempo limite"):
        await trello_client.create_list(BOARD_ID, "Backlog")
    assert len(fake_trello.requests) == 1


async def test_timeout_on_get_is_retried(trello_client: TrelloClient, fake_trello: FakeTrello) -> None:
    fake_trello.fail("GET", r"/boards$", exception=httpx.ConnectTimeout("timeout"))

    assert len(await trello_client.get_boards()) == 1


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, TrelloAuthError), (403, TrelloAuthError), (404, TrelloNotFoundError), (400, TrelloError)],
)
async def test_http_errors_are_mapped(
    trello_client: TrelloClient, fake_trello: FakeTrello, status: int, error: type[Exception]
) -> None:
    fake_trello.fail("GET", r"/boards$", status)

    with pytest.raises(error) as exc_info:
        await trello_client.get_boards()
    assert exc_info.value.upstream_status == status  # type: ignore[attr-defined]


async def test_connection_error_raises_unavailable(fake_trello: FakeTrello, sleeps: list[float]) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async def no_sleep(_: float) -> None:
        sleeps.append(_)

    client = TrelloClient(TEST_KEY, TEST_TOKEN, transport=httpx.MockTransport(broken), max_retries=1, sleep=no_sleep)
    with pytest.raises(TrelloUnavailableError):
        await client.get_boards()
    assert sleeps == [1.0]
    await client.aclose()
