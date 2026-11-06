import hashlib
from collections.abc import Sequence

from app.parsers.markdown.builder import DocumentBuilder
from app.parsers.markdown.tokens import DEFAULT_RULES, LineRule, Tokenizer
from app.schemas.markdown import ParsedDocument


class MarkdownParser:
    """Converte o conteúdo de um arquivo Markdown em ``ParsedDocument``.

    Regras:
    - ``#``: projeto/contexto principal (o primeiro encontrado).
    - ``##``: lista do Trello.
    - ``###`` ou mais: contexto hierárquico, registrado na descrição do cartão.
    - ``- [ ]`` / ``- [x]``: cartão pendente/concluído.
    - checkboxes aninhados: itens de checklist.
    - texto sob a tarefa: descrição do cartão.
    - linha ``Etiquetas: a, b`` sob a tarefa: etiquetas do cartão.
    - tarefas sem ``##``: lista com o nome do arquivo.
    """

    def __init__(self, rules: Sequence[LineRule] = DEFAULT_RULES) -> None:
        self._tokenizer = Tokenizer(rules)

    def parse(self, content: str, filename: str) -> ParsedDocument:
        builder = DocumentBuilder(filename)
        for token in self._tokenizer.tokenize(content):
            builder.feed(token)
        builder.finish()

        return ParsedDocument(
            filename=filename,
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            project=builder.project,
            lists=builder.lists,
            unassigned_text=builder.unassigned_text,
            warnings=builder.warnings,
        )
