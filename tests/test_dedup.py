from app.parsers.markdown import MarkdownParser
from app.services.dedup import (
    MAX_DESCRIPTION_LENGTH,
    assign_fingerprints,
    extract_fingerprint,
    task_fingerprint,
    with_marker,
)

parser = MarkdownParser()


def fingerprints(content: str, filename: str = "a.md") -> list[str]:
    doc = parser.parse(content, filename)
    assign_fingerprints(doc)
    return [card.fingerprint for _, card in doc.iter_cards()]


def test_fingerprint_ignores_description_and_completion() -> None:
    before = fingerprints("## Backlog\n- [ ] Tarefa\n")
    after = fingerprints("## Backlog\n- [x] Tarefa\n  descrição nova\n  - [ ] sub\n")
    assert before == after


def test_fingerprint_ignores_case_and_spacing() -> None:
    assert fingerprints("## Backlog\n- [ ] Criar  API\n") == fingerprints("## backlog\n- [ ] criar api\n")


def test_fingerprint_depends_on_project_and_section_but_not_list() -> None:
    base = fingerprints("# P\n## Backlog\n- [ ] Tarefa\n")
    assert base == fingerprints("# P\n## Outra\n- [ ] Tarefa\n")
    assert base != fingerprints("# Q\n## Backlog\n- [ ] Tarefa\n")
    assert base != fingerprints("# P\n## Backlog\n### Sec\n- [ ] Tarefa\n")


def test_homonymous_tasks_get_distinct_fingerprints() -> None:
    first, second = fingerprints("- [ ] Revisar\n- [ ] Revisar\n")
    assert first != second


def test_marker_roundtrip() -> None:
    fp = task_fingerprint(None, [], "Tarefa", 1)
    description = with_marker("Descrição", fp)

    assert description.startswith("Descrição")
    assert extract_fingerprint(description) == fp
    assert extract_fingerprint("sem marcador") is None
    assert with_marker("", fp) == f"---\n`taskport:{fp}`"


def test_long_description_is_truncated_keeping_marker() -> None:
    fp = task_fingerprint(None, [], "T", 1)
    description = with_marker("x" * 20_000, fp)

    assert len(description) <= MAX_DESCRIPTION_LENGTH
    assert extract_fingerprint(description) == fp
    assert "truncada" in description
