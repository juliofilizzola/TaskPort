"""Cliente HTTP da API oficial do Trello (https://developer.atlassian.com/cloud/trello/rest/)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import (
    TrelloAuthError,
    TrelloError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloUnavailableError,
)
from app.schemas.trello import TrelloBoard, TrelloCard, TrelloChecklist, TrelloCheckItem, TrelloLabel, TrelloList

logger = logging.getLogger("taskport.trello")

# Métodos que podem ser repetidos com segurança após timeout/5xx sem risco de duplicar recursos.
_IDEMPOTENT_METHODS = frozenset({"GET", "PUT"})
_MAX_RETRY_DELAY = 30.0

Sleep = Callable[[float], Awaitable[None]]


class TrelloClient:
    def __init__(
        self,
        api_key: str,
        token: str,
        *,
        base_url: str = "https://api.trello.com/1",
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep
        # Credenciais no cabeçalho (e não na query string) para não vazarem em URLs e logs.
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f'OAuth oauth_consumer_key="{api_key}", oauth_token="{token}"',
                "Accept": "application/json",
            },
        )

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> "TrelloClient":
        assert settings.trello_api_key and settings.trello_token
        return cls(
            settings.trello_api_key.get_secret_value(),
            settings.trello_token.get_secret_value(),
            base_url=settings.trello_base_url,
            timeout=settings.trello_timeout_seconds,
            max_retries=settings.trello_max_retries,
            backoff=settings.trello_backoff_seconds,
            **kwargs,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- Quadros e listas -------------------------------------------------------------------

    async def get_boards(self) -> list[TrelloBoard]:
        data = await self._request("GET", "/members/me/boards", params={"filter": "open", "fields": "name,url,closed"})
        return [TrelloBoard.model_validate(item) for item in data]

    async def get_board(self, board_id: str) -> TrelloBoard:
        data = await self._request("GET", f"/boards/{board_id}", params={"fields": "name,url,closed"})
        return TrelloBoard.model_validate(data)

    async def get_lists(self, board_id: str) -> list[TrelloList]:
        data = await self._request("GET", f"/boards/{board_id}/lists", params={"filter": "open", "fields": "name,closed"})
        return [TrelloList.model_validate(item) for item in data]

    async def create_list(self, board_id: str, name: str) -> TrelloList:
        data = await self._request("POST", "/lists", json={"idBoard": board_id, "name": name, "pos": "bottom"})
        return TrelloList.model_validate(data)

    # --- Cartões ----------------------------------------------------------------------------

    async def get_cards(self, board_id: str) -> list[TrelloCard]:
        """Todos os cartões do quadro, inclusive arquivados (necessário para detectar duplicidade)."""
        data = await self._request(
            "GET", f"/boards/{board_id}/cards/all", params={"fields": "name,desc,closed,idList,idLabels,url"}
        )
        return [TrelloCard.model_validate(item) for item in data]

    async def create_card(
        self, list_id: str, name: str, desc: str, label_ids: list[str] | None = None
    ) -> TrelloCard:
        payload: dict[str, Any] = {"idList": list_id, "name": name, "desc": desc, "pos": "bottom"}
        if label_ids:
            payload["idLabels"] = ",".join(label_ids)
        data = await self._request("POST", "/cards", json=payload)
        return TrelloCard.model_validate(data)

    async def add_label_to_card(self, card_id: str, label_id: str) -> None:
        await self._request("POST", f"/cards/{card_id}/idLabels", json={"value": label_id})

    async def update_card(self, card_id: str, **fields: Any) -> TrelloCard:
        data = await self._request("PUT", f"/cards/{card_id}", json=fields)
        return TrelloCard.model_validate(data)

    async def archive_card(self, card_id: str) -> TrelloCard:
        return await self.update_card(card_id, closed=True)

    # --- Etiquetas --------------------------------------------------------------------------

    async def get_labels(self, board_id: str) -> list[TrelloLabel]:
        data = await self._request("GET", f"/boards/{board_id}/labels", params={"fields": "name,color", "limit": 1000})
        return [TrelloLabel.model_validate(item) for item in data]

    async def create_label(self, board_id: str, name: str, color: str | None) -> TrelloLabel:
        data = await self._request("POST", "/labels", json={"idBoard": board_id, "name": name, "color": color})
        return TrelloLabel.model_validate(data)

    # --- Checklists -------------------------------------------------------------------------

    async def get_card_checklists(self, card_id: str) -> list[TrelloChecklist]:
        data = await self._request("GET", f"/cards/{card_id}/checklists")
        return [TrelloChecklist.model_validate(item) for item in data]

    async def create_checklist(self, card_id: str, name: str) -> TrelloChecklist:
        data = await self._request("POST", "/checklists", json={"idCard": card_id, "name": name})
        return TrelloChecklist.model_validate(data)

    async def add_checklist_item(self, checklist_id: str, name: str, checked: bool) -> TrelloCheckItem:
        data = await self._request(
            "POST", f"/checklists/{checklist_id}/checkItems", json={"name": name, "checked": checked, "pos": "bottom"}
        )
        return TrelloCheckItem.model_validate(data)

    async def set_checklist_item_state(self, card_id: str, item_id: str, checked: bool) -> TrelloCheckItem:
        data = await self._request(
            "PUT", f"/cards/{card_id}/checkItem/{item_id}", json={"state": "complete" if checked else "incomplete"}
        )
        return TrelloCheckItem.model_validate(data)

    # --- Infraestrutura HTTP ----------------------------------------------------------------

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any:
        retryable = method in _IDEMPOTENT_METHODS
        attempt = 0
        while True:
            try:
                response = await self._http.request(method, path, params=params, json=json)
            except httpx.TimeoutException as exc:
                if retryable and attempt < self._max_retries:
                    await self._wait(attempt, method, path, reason="timeout")
                    attempt += 1
                    continue
                raise TrelloUnavailableError("Tempo limite excedido ao comunicar com o Trello.") from exc
            except httpx.TransportError as exc:
                if retryable and attempt < self._max_retries:
                    await self._wait(attempt, method, path, reason="transport_error")
                    attempt += 1
                    continue
                raise TrelloUnavailableError("Não foi possível conectar ao Trello.") from exc

            # 429: a requisição foi rejeitada sem efeito, então é seguro repetir qualquer método.
            if response.status_code == 429:
                if attempt < self._max_retries:
                    await self._wait(attempt, method, path, reason="rate_limited", retry_after=_retry_after(response))
                    attempt += 1
                    continue
                raise TrelloRateLimitError("Limite de requisições do Trello excedido.", upstream_status=429)

            if response.status_code >= 500 and retryable and attempt < self._max_retries:
                await self._wait(attempt, method, path, reason=f"http_{response.status_code}")
                attempt += 1
                continue

            return _parse_response(response)

    async def _wait(self, attempt: int, method: str, path: str, *, reason: str, retry_after: float | None = None) -> None:
        delay = retry_after if retry_after is not None else self._backoff * (2**attempt)
        delay = min(delay, _MAX_RETRY_DELAY)
        logger.warning(
            "trello_retry",
            extra={"method": method, "path": path, "reason": reason, "attempt": attempt + 1, "delay_seconds": delay},
        )
        await self._sleep(delay)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return max(float(value), 0.0) if value is not None else None
    except ValueError:
        return None


def _parse_response(response: httpx.Response) -> Any:
    status = response.status_code
    if status < 400:
        return response.json() if response.content else None

    # Mensagem do Trello truncada; nunca inclui credenciais (enviadas apenas no cabeçalho).
    detail = response.text.strip()[:200]
    if status in (401, 403):
        raise TrelloAuthError("Credenciais do Trello inválidas ou sem permissão para o recurso.", upstream_status=status)
    if status == 404:
        raise TrelloNotFoundError("Recurso não encontrado no Trello.", upstream_status=status)
    if status >= 500:
        raise TrelloUnavailableError("O Trello está indisponível no momento.", upstream_status=status)
    raise TrelloError(f"O Trello rejeitou a requisição: {detail or 'sem detalhes'}", upstream_status=status)
