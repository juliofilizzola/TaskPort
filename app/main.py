import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app import __version__
from app.api.routes import router
from app.clients.trello import TrelloClient
from app.core.auth import TokenAuthMiddleware
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger("taskport")

DESCRIPTION = """
Importa tarefas de arquivos Markdown para quadros do Trello.

Fluxo recomendado: `GET /boards` → `POST /preview` (revisão, sem escrita) → `POST /imports`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, secrets=settings.secret_values())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = TrelloClient.from_settings(settings) if settings.trello_configured else None
        if client is None:
            logger.warning("trello_not_configured")
        app.state.trello_client = client
        try:
            yield
        finally:
            if client is not None:
                await client.aclose()

    app = FastAPI(title="TaskPort", version=__version__, description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    register_exception_handlers(app)

    if not settings.api_token_configured:
        logger.warning("api_token_not_configured", extra={"hint": "defina API_TOKEN (rotas protegidas: 503)"})
    app.add_middleware(
        TokenAuthMiddleware,
        token=settings.api_token.get_secret_value() if settings.api_token else None,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,  # sem query string
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    app.include_router(router)
    return app


app = create_app()
