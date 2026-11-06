import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("taskport.errors")


class AppError(Exception):
    """Erro de domínio com mapeamento direto para uma resposta HTTP."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidFileError(AppError):
    status_code = 422
    code = "invalid_file"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class TooManyFilesError(AppError):
    status_code = 413
    code = "too_many_files"


class TrelloNotConfiguredError(AppError):
    status_code = 503
    code = "trello_not_configured"


class TrelloError(AppError):
    """Falha ao comunicar com a API do Trello."""

    status_code = 502
    code = "trello_error"

    def __init__(self, message: str, *, upstream_status: int | None = None) -> None:
        super().__init__(message, details={"upstream_status": upstream_status} if upstream_status else None)
        self.upstream_status = upstream_status


class TrelloAuthError(TrelloError):
    code = "trello_auth_failed"


class TrelloNotFoundError(TrelloError):
    status_code = 404
    code = "trello_not_found"


class TrelloRateLimitError(TrelloError):
    status_code = 503
    code = "trello_rate_limited"


class TrelloUnavailableError(TrelloError):
    status_code = 504
    code = "trello_unavailable"


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "request_error",
            extra={"path": request.url.path, "error_code": exc.code, "status_code": exc.status_code},
        )
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(status_code=500, content=_error_body("internal_error", "Erro interno inesperado."))
