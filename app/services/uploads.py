"""Validação dos arquivos Markdown recebidos."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import FileTooLargeError, InvalidFileError, TooManyFilesError

ALLOWED_EXTENSIONS = frozenset({".md", ".markdown"})


@dataclass(frozen=True, slots=True)
class MarkdownFile:
    filename: str
    content: str


def _safe_filename(raw: str | None) -> str:
    return PurePosixPath((raw or "").replace("\\", "/")).name.strip()


def validate_markdown(filename: str, data: bytes, max_bytes: int) -> MarkdownFile:
    if not filename:
        raise InvalidFileError("Arquivo enviado sem nome.")
    if PurePosixPath(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidFileError(f"'{filename}': extensão não suportada (use .md ou .markdown).")
    if len(data) > max_bytes:
        raise FileTooLargeError(f"'{filename}': excede o limite de {max_bytes} bytes.")
    if b"\x00" in data:
        raise InvalidFileError(f"'{filename}': conteúdo binário não é permitido.")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidFileError(f"'{filename}': o arquivo deve estar codificado em UTF-8.") from exc
    if not content.strip():
        raise InvalidFileError(f"'{filename}': arquivo vazio.")
    return MarkdownFile(filename=filename, content=content)


async def read_markdown_files(files: list[UploadFile], settings: Settings) -> list[MarkdownFile]:
    if not files:
        raise InvalidFileError("Envie ao menos um arquivo Markdown.")
    if len(files) > settings.max_files_per_request:
        raise TooManyFilesError(f"Máximo de {settings.max_files_per_request} arquivos por requisição.")

    result: list[MarkdownFile] = []
    problems: list[str] = []
    too_large = False
    seen: set[str] = set()
    for upload in files:
        filename = _safe_filename(upload.filename)
        data = await upload.read(settings.max_upload_bytes + 1)
        try:
            markdown = validate_markdown(filename, data, settings.max_upload_bytes)
        except FileTooLargeError as exc:
            too_large = True
            problems.append(exc.message)
            continue
        except InvalidFileError as exc:
            problems.append(exc.message)
            continue
        if filename.casefold() in seen:
            problems.append(f"'{filename}': arquivo enviado mais de uma vez na mesma requisição.")
            continue
        seen.add(filename.casefold())
        result.append(markdown)

    if problems:
        error_cls = FileTooLargeError if too_large and len(problems) == 1 else InvalidFileError
        raise error_cls("Um ou mais arquivos são inválidos.", details=problems)  # type: ignore[call-arg]
    return result
