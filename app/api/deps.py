from typing import Annotated

from fastapi import Depends, Request

from app.clients.trello import TrelloClient
from app.core.config import Settings
from app.core.errors import TrelloNotConfiguredError
from app.parsers.markdown import MarkdownParser
from app.services.import_service import ImportService

_parser = MarkdownParser()


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_optional_trello_client(request: Request) -> TrelloClient | None:
    return getattr(request.app.state, "trello_client", None)


def get_trello_client(client: Annotated[TrelloClient | None, Depends(get_optional_trello_client)]) -> TrelloClient:
    if client is None:
        raise TrelloNotConfiguredError("Credenciais do Trello não configuradas (TRELLO_API_KEY/TRELLO_TOKEN).")
    return client


def get_import_service(
    client: Annotated[TrelloClient | None, Depends(get_optional_trello_client)],
) -> ImportService:
    return ImportService(_parser, client)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
TrelloClientDep = Annotated[TrelloClient, Depends(get_trello_client)]
ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
