"""Autenticação por token estático (sem login).

Todas as rotas exigem `Authorization: Bearer <API_TOKEN>`, exceto as listadas em `PUBLIC_PATHS`.
Se `API_TOKEN` não estiver configurado, as rotas protegidas são recusadas (falha fechada).
"""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})

_SCHEME = "bearer"


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extrai o token de `Authorization: Bearer <token>`. Retorna None se o formato for inválido."""
    if not authorization:
        return None
    parts = authorization.strip().split(" ")
    if len(parts) != 2 or parts[0].casefold() != _SCHEME or not parts[1]:
        return None
    return parts[1]


class TokenAuthMiddleware:
    """Middleware ASGI que valida o token de acesso antes de chegar às rotas.

    Implementado em ASGI puro para não consumir o corpo das requisições (uploads).
    """

    def __init__(self, app: ASGIApp, *, token: str | None, public_paths: frozenset[str] = PUBLIC_PATHS) -> None:
        self.app = app
        self._token = token.encode() if token else None
        self._public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self._public_paths or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if self._token is None:
            await _reject(scope, receive, send, 503, "auth_not_configured", "API_TOKEN não configurado no servidor.")
            return

        provided = extract_bearer_token(_header(scope, b"authorization"))
        if provided is None:
            await _reject(scope, receive, send, 401, "unauthorized", "Token ausente ou mal formatado.")
            return
        if not hmac.compare_digest(provided.encode(), self._token):
            await _reject(scope, receive, send, 401, "unauthorized", "Token inválido.")
            return

        await self.app(scope, receive, send)


async def _reject(scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str) -> None:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    body = {"error": {"code": code, "message": message}}
    await JSONResponse(body, status_code=status, headers=headers)(scope, receive, send)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return None
