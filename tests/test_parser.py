from pathlib import Path

from app.parsers.markdown import DEFAULT_RULES, MarkdownParser
from app.parsers.markdown.builder import COMPLETED_NOTE
from app.parsers.markdown.tokens import Line, TaskToken, Token

EXAMPLE = (Path(__file__).parent.parent / "examples" / "jobs-control.md").read_text(encoding="utf-8")

parser = MarkdownParser()


def test_parses_reference_example() -> None:
    doc = parser.parse(EXAMPLE, "jobs-control.md")

    assert doc.project == "Projeto Jobs Control"
    assert [lst.name for lst in doc.lists] == ["Backlog", "Em andamento", "Concluído"]
    assert [len(lst.cards) for lst in doc.lists] == [2, 2, 1]
    assert doc.warnings == []
    assert doc.unassigned_text == []
    assert len(doc.content_sha256) == 64


def test_pending_and_completed_tasks() -> None:
    doc = parser.parse(EXAMPLE, "jobs-control.md")
    in_progress = doc.lists[1].cards

    assert in_progress[0].title == "Implementar logs"
    assert in_progress[0].completed is False
    assert in_progress[1].title == "Configurar estrutura do projeto"
    assert in_progress[1].completed is True
    assert COMPLETED_NOTE in in_progress[1].description


def test_nested_subtasks_become_checklist_and_text_becomes_description() -> None:
    card = parser.parse(EXAMPLE, "jobs-control.md").lists[0].cards[0]

    assert card.title == "Criar API de autenticação"
    assert card.description.startswith("Implementar autenticação utilizando JWT.")
    assert "**Projeto:** Projeto Jobs Control" in card.description
    assert [(i.name, i.checked) for i in card.checklist] == [
        ("Criar endpoint de login", False),
        ("Criar endpoint de refresh token", False),
        ("Criar schemas", True),
    ]


def test_deeply_nested_subtasks_keep_hierarchy_prefix() -> None:
    content = "- [ ] Pai\n  - [ ] Filho\n    - [x] Neto\n  - [ ] Outro filho\n"
    card = parser.parse(content, "a.md").lists[0].cards[0]

    assert [i.name for i in card.checklist] == ["Filho", "↳ Neto", "Outro filho"]
    assert card.checklist[1].checked is True


def test_file_without_headings_uses_filename_as_list() -> None:
    doc = parser.parse("- [ ] Tarefa A\n- [x] Tarefa B\n", "docs/sprint-12.md")

    assert doc.project is None
    assert len(doc.lists) == 1
    assert doc.lists[0].name == "sprint-12"
    assert doc.lists[0].from_filename is True
    assert [c.title for c in doc.lists[0].cards] == ["Tarefa A", "Tarefa B"]


def test_project_heading_without_list_heading_uses_filename() -> None:
    doc = parser.parse("# Projeto X\n\n- [ ] Tarefa\n", "ideias.md")

    assert doc.project == "Projeto X"
    assert doc.lists[0].name == "ideias"


def test_level_three_headings_are_kept_as_context() -> None:
    content = "## Backlog\n### Backend\n#### Auth\n- [ ] Login\n### Frontend\n- [ ] Tela\n"
    cards = parser.parse(content, "a.md").lists[0].cards

    assert cards[0].context == ["Backend", "Auth"]
    assert "**Seção:** Backend › Auth" in cards[0].description
    assert cards[1].context == ["Frontend"]


def test_alternative_checkbox_markers() -> None:
    content = "* [X] Estrela\n+ [ ] Mais\n1. [ ] Numerada\n2) [x] Parêntese\n"
    cards = parser.parse(content, "a.md").lists[0].cards

    assert [(c.title, c.completed) for c in cards] == [
        ("Estrela", True),
        ("Mais", False),
        ("Numerada", False),
        ("Parêntese", True),
    ]


def test_tab_indentation_is_supported() -> None:
    cards = parser.parse("- [ ] Pai\n\t- [x] Filho\n", "a.md").lists[0].cards

    assert len(cards) == 1
    assert cards[0].checklist[0].name == "Filho"


def test_unrecognized_content_is_preserved_in_description() -> None:
    content = (
        "## Backlog\n"
        "- [ ] Tarefa\n"
        "  Texto da descrição.\n"
        "  - item comum sem checkbox\n"
        "  ```python\n"
        "  - [ ] isto é código, não tarefa\n"
        "  ```\n"
        "Parágrafo não indentado após a tarefa.\n"
    )
    cards = parser.parse(content, "a.md").lists[0].cards

    assert len(cards) == 1
    description = cards[0].description
    assert "Texto da descrição." in description
    assert "- item comum sem checkbox" in description
    assert "- [ ] isto é código, não tarefa" in description
    assert "Parágrafo não indentado após a tarefa." in description
    assert cards[0].checklist == []


def test_text_under_subtask_is_preserved_with_reference() -> None:
    content = "- [ ] Pai\n  - [ ] Filho\n    detalhe do filho\n"
    card = parser.parse(content, "a.md").lists[0].cards[0]

    assert "*Filho*: detalhe do filho" in card.description


def test_intro_text_before_first_task_goes_to_next_card() -> None:
    content = "## Backlog\nContexto da lista.\n\n- [ ] Tarefa\n"
    card = parser.parse(content, "a.md").lists[0].cards[0]

    assert card.description.startswith("Contexto da lista.")


def test_text_without_any_task_is_reported_not_discarded() -> None:
    content = "# Projeto\n\nIntrodução geral.\n\n## Backlog\n- [ ] Tarefa\n"
    doc = parser.parse(content, "a.md")

    assert doc.unassigned_text == ["Introdução geral."]
    assert any("sem tarefa associada" in w for w in doc.warnings)


def test_document_without_tasks_produces_warning() -> None:
    doc = parser.parse("# Só um título\n\nTexto qualquer.\n", "a.md")

    assert all(not lst.cards for lst in doc.lists)
    assert any("Nenhuma tarefa" in w for w in doc.warnings)


def test_repeated_list_heading_is_merged() -> None:
    doc = parser.parse("## Backlog\n- [ ] A\n## Outra\n- [ ] B\n## backlog\n- [ ] C\n", "a.md")

    assert [lst.name for lst in doc.lists] == ["Backlog", "Outra"]
    assert [c.title for c in doc.lists[0].cards] == ["A", "C"]


def test_labels_line_becomes_card_labels() -> None:
    content = (
        "- [ ] Com etiquetas\n"
        "  Descrição.\n"
        "  **Etiquetas:** Crítica, Rede\n"
        "  - [ ] Sub\n"
        "  Labels: rede, Segurança\n"
        "- [ ] Sem etiquetas\n"
    )
    cards = parser.parse(content, "a.md").lists[0].cards

    assert cards[0].labels == ["Crítica", "Rede", "Segurança"]
    assert "Etiquetas" not in cards[0].description
    assert "Labels" not in cards[0].description
    assert cards[0].description.startswith("Descrição.")
    assert cards[1].labels == []


def test_parser_accepts_custom_rules() -> None:
    class TodoRule:
        """Convenção extra: linhas 'TODO: ...' viram tarefas."""

        def match(self, line: Line) -> Token | None:
            if line.text.startswith("TODO:"):
                return TaskToken(line.number, line.indent, False, line.text.removeprefix("TODO:").strip())
            return None

    custom = MarkdownParser(rules=(*DEFAULT_RULES, TodoRule()))
    cards = custom.parse("TODO: revisar contrato\n- [x] feito\n", "a.md").lists[0].cards

    assert [(c.title, c.completed) for c in cards] == [("revisar contrato", False), ("feito", True)]
