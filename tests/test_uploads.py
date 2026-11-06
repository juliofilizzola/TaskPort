import io

import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import FileTooLargeError, InvalidFileError, TooManyFilesError
from app.services.uploads import read_markdown_files, validate_markdown

pytestmark = pytest.mark.anyio


def upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=name)


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("tarefas.txt", b"- [ ] a", "extens"),
        ("tarefas", b"- [ ] a", "extens"),
        ("vazio.md", b"   \n\n", "vazio"),
        ("binario.md", b"- [ ] a\x00\x01", "bin"),
        ("latin1.md", "- [ ] ação".encode("latin-1"), "UTF-8"),
        ("", b"- [ ] a", "sem nome"),
    ],
)
def test_invalid_files_are_rejected(filename: str, data: bytes, message: str) -> None:
    with pytest.raises(InvalidFileError, match=message):
        validate_markdown(filename, data, max_bytes=1024)


def test_accepts_markdown_with_bom() -> None:
    result = validate_markdown("a.MARKDOWN", "\ufeff- [ ] ação".encode(), max_bytes=1024)
    assert result.content == "- [ ] ação"


def test_rejects_file_above_limit() -> None:
    with pytest.raises(FileTooLargeError):
        validate_markdown("a.md", b"x" * 11, max_bytes=10)


async def test_reads_multiple_files_and_strips_paths(settings: Settings) -> None:
    files = [upload("../../etc/a.md", b"- [ ] a"), upload("C:\\docs\\b.md", b"- [ ] b")]

    result = await read_markdown_files(files, settings)

    assert [f.filename for f in result] == ["a.md", "b.md"]


async def test_reports_every_invalid_file(settings: Settings) -> None:
    files = [upload("ok.md", b"- [ ] a"), upload("x.txt", b"a"), upload("vazio.md", b"")]

    with pytest.raises(InvalidFileError) as exc_info:
        await read_markdown_files(files, settings)
    assert len(exc_info.value.details) == 2


async def test_too_large_upload_returns_413_error(settings: Settings) -> None:
    with pytest.raises(FileTooLargeError):
        await read_markdown_files([upload("big.md", b"x" * (settings.max_upload_bytes + 1))], settings)


async def test_too_many_files(settings: Settings) -> None:
    files = [upload(f"{i}.md", b"- [ ] a") for i in range(settings.max_files_per_request + 1)]
    with pytest.raises(TooManyFilesError):
        await read_markdown_files(files, settings)


async def test_duplicate_filenames_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidFileError):
        await read_markdown_files([upload("a.md", b"- [ ] a"), upload("A.md", b"- [ ] b")], settings)


async def test_no_files(settings: Settings) -> None:
    with pytest.raises(InvalidFileError):
        await read_markdown_files([], settings)
