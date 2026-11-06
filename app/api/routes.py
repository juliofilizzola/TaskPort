from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app import __version__
from app.api.deps import ImportServiceDep, SettingsDep, TrelloClientDep
from app.schemas.imports import (
    BOARD_ID_PATTERN,
    ExistingCardPolicy,
    ImportOptions,
    ImportResponse,
    PreviewResponse,
)
from app.schemas.trello import BoardOut
from app.services.uploads import read_markdown_files

router = APIRouter()

FilesField = Annotated[list[UploadFile], File(description="Um ou mais arquivos .md / .markdown (UTF-8).")]
OnExistingField = Annotated[
    ExistingCardPolicy,
    Form(description="O que fazer com tarefas já importadas: `skip` (padrão) ou `update` (sincroniza descrição e checklist)."),
]

_ERRORS = {
    413: {"description": "Arquivo(s) acima do limite ou excesso de arquivos."},
    422: {"description": "Arquivo inválido (extensão, codificação, vazio ou binário)."},
    502: {"description": "Erro retornado pelo Trello (ex.: credenciais inválidas)."},
    503: {"description": "Trello não configurado ou limite de requisições excedido."},
    504: {"description": "Trello indisponível ou tempo limite excedido."},
}


@router.get("/health", tags=["health"], summary="Verifica a disponibilidade da aplicação")
async def health(settings: SettingsDep) -> dict[str, object]:
    return {"status": "ok", "version": __version__, "trello_configured": settings.trello_configured}


@router.get(
    "/boards",
    tags=["trello"],
    response_model=list[BoardOut],
    summary="Lista os quadros abertos da conta Trello autenticada",
    responses={k: v for k, v in _ERRORS.items() if k >= 500},
)
async def list_boards(client: TrelloClientDep) -> list[BoardOut]:
    boards = await client.get_boards()
    return [BoardOut(id=b.id, name=b.name, url=b.url) for b in boards]


@router.post(
    "/preview",
    tags=["import"],
    response_model=PreviewResponse,
    summary="Pré-visualiza a importação sem alterar o Trello",
    description=(
        "Interpreta os arquivos e devolve a estrutura que seria criada. Nenhuma escrita é feita no Trello. "
        "Se `board_id` for informado, o quadro é **lido** para indicar quais listas serão reutilizadas e "
        "quais tarefas já foram importadas (`action`)."
    ),
    responses=_ERRORS,
)
async def preview_import(
    files: FilesField,
    settings: SettingsDep,
    service: ImportServiceDep,
    board_id: Annotated[str | None, Form(pattern=BOARD_ID_PATTERN, description="Quadro de destino (opcional).")] = None,
    on_existing: OnExistingField = ExistingCardPolicy.SKIP,
) -> PreviewResponse:
    markdown_files = await read_markdown_files(files, settings)
    return await service.preview(markdown_files, board_id, on_existing)


@router.post(
    "/imports",
    tags=["import"],
    response_model=ImportResponse,
    summary="Importa as tarefas para o Trello",
    description=(
        "Cria listas, cartões e checklists no quadro informado. Falhas parciais não interrompem a importação: "
        "o relatório indica o que foi concluído e o que falhou. Reenviar os mesmos arquivos não duplica cartões."
    ),
    responses={404: {"description": "Quadro não encontrado."}, **_ERRORS},
)
async def create_import(
    files: FilesField,
    board_id: Annotated[str, Form(pattern=BOARD_ID_PATTERN, description="ID do quadro de destino.")],
    settings: SettingsDep,
    service: ImportServiceDep,
    archive_completed: Annotated[bool, Form(description="Arquivar cartões de tarefas concluídas (`- [x]`).")] = False,
    on_existing: OnExistingField = ExistingCardPolicy.SKIP,
) -> ImportResponse:
    markdown_files = await read_markdown_files(files, settings)
    options = ImportOptions(archive_completed=archive_completed, on_existing=on_existing)
    return await service.run_import(markdown_files, board_id, options)
