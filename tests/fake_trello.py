"""Implementação em memória da API do Trello para testes (sem conta real)."""

import itertools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

BOARD_ID = "5f1a2b3c4d5e6f7a8b9c0d1e"

Handler = Callable[[re.Match[str], dict[str, Any]], httpx.Response]


@dataclass
class _Failure:
    method: str
    pattern: re.Pattern[str]
    status: int
    remaining: int
    headers: dict[str, str] = field(default_factory=dict)
    exception: Exception | None = None


class FakeTrello:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.boards: dict[str, dict[str, Any]] = {
            BOARD_ID: {"id": BOARD_ID, "name": "Jobs", "url": "https://trello.com/b/x", "closed": False}
        }
        self.lists: dict[str, dict[str, Any]] = {}
        self.cards: dict[str, dict[str, Any]] = {}
        self.checklists: dict[str, dict[str, Any]] = {}
        self.labels: dict[str, dict[str, Any]] = {}
        self.requests: list[httpx.Request] = []
        self._failures: list[_Failure] = []
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = [
            ("GET", re.compile(r"^/1/members/me/boards$"), self._get_boards),
            ("GET", re.compile(r"^/1/boards/(?P<id>\w+)$"), self._get_board),
            ("GET", re.compile(r"^/1/boards/(?P<id>\w+)/lists$"), self._get_lists),
            ("GET", re.compile(r"^/1/boards/(?P<id>\w+)/cards/all$"), self._get_cards),
            ("GET", re.compile(r"^/1/boards/(?P<id>\w+)/labels$"), self._get_labels),
            ("POST", re.compile(r"^/1/labels$"), self._create_label),
            ("POST", re.compile(r"^/1/cards/(?P<id>\w+)/idLabels$"), self._add_card_label),
            ("POST", re.compile(r"^/1/lists$"), self._create_list),
            ("POST", re.compile(r"^/1/cards$"), self._create_card),
            ("PUT", re.compile(r"^/1/cards/(?P<id>\w+)$"), self._update_card),
            ("GET", re.compile(r"^/1/cards/(?P<id>\w+)/checklists$"), self._get_checklists),
            ("POST", re.compile(r"^/1/checklists$"), self._create_checklist),
            ("POST", re.compile(r"^/1/checklists/(?P<id>\w+)/checkItems$"), self._add_item),
            ("PUT", re.compile(r"^/1/cards/(?P<card>\w+)/checkItem/(?P<item>\w+)$"), self._update_item),
        ]

    # --- configuração dos testes ----------------------------------------------------------

    def fail(
        self,
        method: str,
        path_regex: str,
        status: int = 500,
        *,
        times: int = 1,
        headers: dict[str, str] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self._failures.append(_Failure(method, re.compile(path_regex), status, times, headers or {}, exception))

    def add_list(self, name: str) -> str:
        list_id = self._new_id()
        self.lists[list_id] = {"id": list_id, "name": name, "closed": False, "idBoard": BOARD_ID}
        return list_id

    def add_label(self, name: str, color: str | None = None) -> str:
        label_id = self._new_id()
        self.labels[label_id] = {"id": label_id, "name": name, "color": color, "idBoard": BOARD_ID}
        return label_id

    def label_names(self, card: dict[str, Any]) -> list[str]:
        return [self.labels[label_id]["name"] for label_id in card["idLabels"]]

    @property
    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    def cards_named(self, name: str) -> list[dict[str, Any]]:
        return [c for c in self.cards.values() if c["name"] == name]

    def checklist_of(self, card_id: str) -> dict[str, Any]:
        return next(c for c in self.checklists.values() if c["idCard"] == card_id)

    # --- transporte -----------------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        for failure in self._failures:
            if failure.remaining > 0 and failure.method == request.method and failure.pattern.search(path):
                failure.remaining -= 1
                if failure.exception is not None:
                    raise failure.exception
                return httpx.Response(failure.status, headers=failure.headers, text="simulated failure")
        body = json.loads(request.content) if request.content else {}
        for method, pattern, route in self._routes:
            if method == request.method and (match := pattern.match(path)):
                return route(match, body)
        return httpx.Response(404, text="route not found")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    # --- rotas ----------------------------------------------------------------------------

    def _new_id(self) -> str:
        return f"{next(self._ids):024x}"

    def _get_boards(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json=list(self.boards.values()))

    def _get_board(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        board = self.boards.get(match["id"])
        return httpx.Response(200, json=board) if board else httpx.Response(404, text="board not found")

    def _get_lists(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json=[lst for lst in self.lists.values() if not lst["closed"]])

    def _get_cards(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json=list(self.cards.values()))

    def _get_labels(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json=list(self.labels.values()))

    def _create_label(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        label_id = self.add_label(body["name"], body.get("color"))
        return httpx.Response(200, json=self.labels[label_id])

    def _add_card_label(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        card = self.cards[match["id"]]
        if body["value"] in card["idLabels"]:
            return httpx.Response(400, text="that label is already on the card")
        card["idLabels"].append(body["value"])
        return httpx.Response(200, json=card["idLabels"])

    def _create_list(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        list_id = self.add_list(body["name"])
        return httpx.Response(200, json=self.lists[list_id])

    def _create_card(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        card_id = self._new_id()
        self.cards[card_id] = {
            "id": card_id,
            "name": body["name"],
            "desc": body.get("desc", ""),
            "idList": body["idList"],
            "idLabels": [i for i in body.get("idLabels", "").split(",") if i],
            "closed": False,
            "url": f"https://trello.com/c/{card_id}",
        }
        return httpx.Response(200, json=self.cards[card_id])

    def _update_card(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        card = self.cards[match["id"]]
        card.update(body)
        return httpx.Response(200, json=card)

    def _get_checklists(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json=[c for c in self.checklists.values() if c["idCard"] == match["id"]])

    def _create_checklist(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        checklist_id = self._new_id()
        self.checklists[checklist_id] = {"id": checklist_id, "idCard": body["idCard"], "name": body["name"], "checkItems": []}
        return httpx.Response(200, json=self.checklists[checklist_id])

    def _add_item(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        item = {"id": self._new_id(), "name": body["name"], "state": "complete" if body.get("checked") else "incomplete"}
        self.checklists[match["id"]]["checkItems"].append(item)
        return httpx.Response(200, json=item)

    def _update_item(self, match: re.Match[str], body: dict[str, Any]) -> httpx.Response:
        for checklist in self.checklists.values():
            for item in checklist["checkItems"]:
                if item["id"] == match["item"]:
                    item["state"] = body["state"]
                    return httpx.Response(200, json=item)
        return httpx.Response(404)
