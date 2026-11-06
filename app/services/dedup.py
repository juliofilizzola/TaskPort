"""Identificação estável de tarefas para prevenção de duplicidade.

Cada cartão criado recebe na descrição um marcador ``taskport:<fingerprint>``. Antes de
importar, os cartões do quadro (inclusive arquivados) são lidos e os marcadores
existentes indicam quais tarefas já foram importadas. Assim o próprio Trello é a fonte
de verdade do histórico, sem necessidade de banco de dados.
"""

import hashlib
import re
from collections import Counter

from app.schemas.markdown import ParsedDocument

MARKER_PREFIX = "taskport:"
MARKER_PATTERN = re.compile(r"taskport:([0-9a-f]{16})\b")
MAX_DESCRIPTION_LENGTH = 16_384  # limite da API do Trello
_TRUNCATION_NOTE = "\n\n… (descrição truncada)"


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def task_fingerprint(project: str | None, context: list[str], title: str, occurrence: int) -> str:
    """Hash da identidade da tarefa (projeto, seção, título).

    Não usa a lista, o hash do arquivo nem a descrição: mudar a tarefa de lista (no Markdown
    ou movendo o cartão no Trello), editar o texto ou concluí-la não gera um novo cartão.
    ``occurrence`` diferencia tarefas homônimas.
    """
    parts = [_normalize(project or ""), *map(_normalize, context), _normalize(title), str(occurrence)]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def assign_fingerprints(document: ParsedDocument) -> None:
    occurrences: Counter[tuple[str, ...]] = Counter()
    for _, card in document.iter_cards():
        key = (*map(_normalize, card.context), _normalize(card.title))
        occurrences[key] += 1
        card.fingerprint = task_fingerprint(document.project, card.context, card.title, occurrences[key])


def with_marker(description: str, fingerprint: str) -> str:
    marker = f"\n\n---\n`{MARKER_PREFIX}{fingerprint}`"
    limit = MAX_DESCRIPTION_LENGTH - len(marker)
    if len(description) > limit:
        description = description[: limit - len(_TRUNCATION_NOTE)] + _TRUNCATION_NOTE
    return f"{description}{marker}".lstrip("\n")


def extract_fingerprint(description: str) -> str | None:
    match = MARKER_PATTERN.search(description or "")
    return match.group(1) if match else None
