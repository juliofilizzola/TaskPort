# TaskPort

API em **Python + FastAPI** que importa tarefas de arquivos Markdown (`.md`) para quadros do **Trello**, criando listas, cartões e checklists automaticamente, usando exclusivamente a [API REST oficial do Trello](https://developer.atlassian.com/cloud/trello/rest/).

Fluxo: configurar credenciais → escolher o quadro (`GET /boards`) → enviar os arquivos para **pré-visualização** (`POST /preview`, sem nenhuma escrita) → confirmar a **importação** (`POST /imports`) → receber o relatório.

## Requisitos

- Python 3.12+ **ou** Docker
- Uma API key e um token do Trello

## Configuração das credenciais

1. Acesse <https://trello.com/power-ups/admin>, crie (ou abra) uma integração e copie a **API key**.
2. Na mesma página, gere um **token** com permissão de leitura e escrita.
3. Copie `.env.example` para `.env` e preencha:

```env
TRELLO_API_KEY=sua-api-key
TRELLO_TOKEN=seu-token
```

As credenciais são lidas apenas de variáveis de ambiente (ou do `.env`), enviadas ao Trello somente no cabeçalho `Authorization` (nunca na URL) e removidas de qualquer log. Nenhum endpoint as retorna.

Variáveis opcionais:

| Variável | Padrão | Descrição |
|---|---|---|
| `TRELLO_TIMEOUT_SECONDS` | `10` | Timeout de cada requisição ao Trello |
| `TRELLO_MAX_RETRIES` | `3` | Novas tentativas em rate limit (429) e falhas transitórias |
| `TRELLO_BACKOFF_SECONDS` | `1` | Base do backoff exponencial (1s, 2s, 4s…) |
| `MAX_UPLOAD_BYTES` | `1048576` | Tamanho máximo por arquivo |
| `MAX_FILES_PER_REQUEST` | `20` | Arquivos por requisição |
| `LOG_LEVEL` | `INFO` | Nível dos logs (JSON) |

## Instalação e execução local

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements-dev.txt
```

```bash
uvicorn app.main:app --reload
```

A documentação interativa (Swagger) fica em <http://localhost:8000/docs> e o OpenAPI em `/openapi.json`.

### Testes

```bash
pytest
```

Os testes não usam uma conta real: o Trello é simulado em memória (`tests/fake_trello.py`) via `httpx.MockTransport`, exercitando o cliente HTTP real, inclusive retries e rate limit.

## Execução via Docker Compose (recomendado)

Com o `.env` preenchido:

```bash
docker compose up -d --build
```

A API fica em <http://localhost:8000/docs>. Para usar outra porta, defina `TASKPORT_PORT` (no `.env` ou no shell, por exemplo `TASKPORT_PORT=9000`). Comandos úteis:

```bash
docker compose logs -f
```

```bash
docker compose down
```

O serviço reinicia automaticamente (`unless-stopped`), roda com sistema de arquivos somente leitura e `no-new-privileges`, e tem healthcheck em `/health`.

## Execução via Docker

```bash
docker build -t taskport .
```

```bash
docker run --rm -p 8000:8000 --env-file .env taskport
```

A imagem roda com usuário sem privilégios e possui `HEALTHCHECK` em `/health`.

## Interpretação do Markdown

| Markdown | Resultado no Trello |
|---|---|
| `# Título` | Projeto (o primeiro `#`). Registrado na descrição dos cartões |
| `## Título` | Lista. Reutiliza uma lista aberta de mesmo nome (sem diferenciar maiúsculas) |
| `###`, `####`… | Contexto hierárquico, registrado na descrição (`Seção: Backend › Auth`) |
| `- [ ] tarefa` | Cartão pendente |
| `- [x] tarefa` | Cartão concluído (nota na descrição; arquivado se `archive_completed=true` ou levado para a lista `completed_list`) |
| Checkbox aninhado | Item da checklist **Subtarefas** (marcado ou não). Níveis mais profundos recebem o prefixo `↳` |
| Texto sob a tarefa | Descrição do cartão (parágrafos, listas comuns, blocos de código) |
| `Etiquetas: a, b` sob a tarefa | Etiquetas do cartão (aceita também `**Etiquetas:**` e `Labels:`). A linha não entra na descrição. Etiquetas inexistentes são criadas no quadro: Crítica vermelha, Alta laranja, Média amarela, Baixa verde, Informativo azul e as demais em azul-claro |
| Texto sob uma subtarefa | Descrição do cartão, como `- *Subtarefa*: texto` |
| Texto antes da primeira tarefa de uma seção | Início da descrição do próximo cartão da seção |
| Tarefas sem `##` | Lista com o nome do arquivo (`sprint-12.md` → `sprint-12`) |

Também são aceitos `* [ ]`, `+ [ ]`, `1. [ ]`, `[X]` maiúsculo e indentação com tabs. Conteúdo dentro de blocos de código nunca é interpretado como tarefa.

Nada é descartado em silêncio: texto que não pode ser associado a nenhuma tarefa (por exemplo, um parágrafo entre `#` e o primeiro `##`) aparece em `unassigned_text` e em `warnings` na pré-visualização.

**Extensível:** cada convenção é uma `LineRule` (`app/parsers/markdown/tokens.py`). Para adicionar uma nova basta passar regras extras ao `MarkdownParser(rules=(*DEFAULT_RULES, MinhaRegra()))`. Veja `test_parser_accepts_custom_rules`.

### Exemplo

`examples/jobs-control.md`:

```markdown
# Projeto Jobs Control

## Backlog

- [ ] Criar API de autenticação
  Implementar autenticação utilizando JWT.
  - [ ] Criar endpoint de login
  - [ ] Criar endpoint de refresh token
  - [x] Criar schemas

- [ ] Configurar integração AWS

## Em andamento

- [ ] Implementar logs
- [x] Configurar estrutura do projeto

## Concluído

- [x] Criar repositórios
```

Gera 3 listas e 5 cartões; o cartão "Criar API de autenticação" recebe a descrição e uma checklist com 3 itens (1 marcado). Outros exemplos: `examples/sem-headings.md` e `examples/com-secoes.md`.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Disponibilidade e se o Trello está configurado |
| `GET` | `/boards` | Quadros abertos da conta autenticada |
| `POST` | `/preview` | Interpreta arquivos e mostra o que será criado. **Não escreve no Trello** |
| `POST` | `/imports` | Executa a importação e retorna o relatório |

Campos de formulário (`multipart/form-data`) de `/preview` e `/imports`:

| Campo | Obrigatório | Descrição |
|---|---|---|
| `files` | sim | Um ou mais arquivos `.md`/`.markdown` (UTF-8) |
| `board_id` | em `/imports` | ID (24 caracteres) ou shortLink (8) do quadro. Em `/preview`, opcional: se informado, o quadro é apenas **lido** para indicar o que será criado, reutilizado ou ignorado |
| `archive_completed` | não (`false`) | Arquiva os cartões de tarefas `- [x]` (só em `/imports`) |
| `completed_list` | não | Nome de uma lista **existente** (ex.: `Concluido`; maiúsculas e acentos são ignorados) para onde vão as tarefas `- [x]`. Cartões novos já nascem nela; com `on_existing=update`, cartões existentes são movidos de qualquer coluna (EM ANDAMENTO, STAND BY etc.). Tarefas pendentes nunca são movidas. Não pode ser combinado com `archive_completed`. Em `/preview`, mostra `move_to_completed` por cartão e `cards_to_move_to_completed` no resumo |
| `on_existing` | não (`skip`) | Tarefas já importadas: `skip` ignora; `update` sincroniza a descrição e o estado/itens da checklist |

### Postman

A coleção [`postman/TaskPort.postman_collection.json`](postman/TaskPort.postman_collection.json) tem todas as requisições, com testes:

1. No Postman, clique em **Import** e selecione o arquivo.
2. Em **Settings → General → Working directory**, selecione a pasta do projeto, para que os campos `files` encontrem `examples/*.md`. Outra opção é selecionar os arquivos manualmente em cada requisição.
3. Ajuste as variáveis da coleção se necessário: `baseUrl` (padrão `http://localhost:8000`) e `boardId`. *Listar quadros* preenche o `boardId` com o primeiro quadro quando ele está vazio.
4. As requisições da pasta **Importar** escrevem no Trello. As demais apenas leem.

Para rodar pela linha de comando (somente as pastas de leitura):

```bash
npx newman run postman/TaskPort.postman_collection.json --folder "Health" --folder "Listar quadros" --folder "Pré-visualizar" --folder "Erros"
```

### Exemplos de requisições

```bash
curl http://localhost:8000/boards
```

```bash
curl -F "files=@examples/jobs-control.md" -F "board_id=5f1a2b3c4d5e6f7a8b9c0d1e" http://localhost:8000/preview
```

```bash
curl -F "files=@examples/jobs-control.md" -F "files=@examples/sem-headings.md" -F "board_id=5f1a2b3c4d5e6f7a8b9c0d1e" -F "archive_completed=true" http://localhost:8000/imports
```

### Exemplos de respostas

`GET /boards`

```json
[{ "id": "5f1a2b3c4d5e6f7a8b9c0d1e", "name": "Jobs", "url": "https://trello.com/b/AbCd1234/jobs" }]
```

`POST /preview` (resumido)

```json
{
  "board_id": "5f1a2b3c4d5e6f7a8b9c0d1e",
  "summary": {
    "files": 1, "lists": 3, "cards": 5, "completed_cards": 2, "checklist_items": 3,
    "lists_to_create": 2, "cards_to_create": 4, "cards_to_update": 0, "cards_to_skip": 1
  },
  "files": [{
    "filename": "jobs-control.md",
    "content_sha256": "a052222d…",
    "project": "Projeto Jobs Control",
    "lists": [{
      "name": "Backlog", "from_filename": false, "action": "reuse", "existing_list_id": "6650…",
      "cards": [{
        "title": "Criar API de autenticação",
        "description": "Implementar autenticação utilizando JWT.\n\n**Projeto:** Projeto Jobs Control",
        "completed": false,
        "checklist": [
          { "name": "Criar endpoint de login", "checked": false },
          { "name": "Criar endpoint de refresh token", "checked": false },
          { "name": "Criar schemas", "checked": true }
        ],
        "context": [], "line": 5, "fingerprint": "3f9c0a1b2c3d4e5f",
        "action": "create", "existing_card_id": null
      }]
    }],
    "unassigned_text": [],
    "warnings": []
  }]
}
```

`POST /imports` com falha parcial (resumido)

```json
{
  "board_id": "5f1a2b3c4d5e6f7a8b9c0d1e",
  "status": "partial",
  "aborted": false,
  "summary": {
    "files_processed": 1, "lists_created": 3, "lists_reused": 0,
    "cards_created": 4, "cards_updated": 0, "cards_skipped": 0, "cards_failed": 1,
    "checklists_created": 0, "checklist_items_created": 0, "checklist_items_updated": 0,
    "labels_created": 0, "card_labels_added": 0, "cards_moved_to_completed": 0, "cards_archived": 0, "errors": 1
  },
  "files": [{ "filename": "jobs-control.md", "content_sha256": "a052222d…", "cards": 5 }],
  "cards": [
    { "file": "jobs-control.md", "list_name": "Backlog", "title": "Criar API de autenticação",
      "fingerprint": "3f9c0a1b2c3d4e5f", "status": "failed", "card_id": null, "url": null, "archived": false }
  ],
  "errors": [
    { "file": "jobs-control.md", "list_name": "Backlog", "card": "Criar API de autenticação",
      "operation": "create_card", "message": "O Trello rejeitou a requisição: …", "upstream_status": 400 }
  ]
}
```

`status` é `success` (sem erros), `partial` (algo foi criado e algo falhou) ou `failed`. Cada cartão tem `status` `created`, `updated`, `skipped`, `partial` (cartão criado, mas checklist/arquivamento falhou) ou `failed`.

### Erros

Formato: `{"error": {"code": "...", "message": "...", "details": ...}}`.

| HTTP | `code` | Quando |
|---|---|---|
| 404 | `trello_not_found` | Quadro inexistente ou inacessível |
| 413 | `file_too_large`, `too_many_files` | Limites de upload excedidos |
| 422 | `invalid_file` | Extensão inválida, arquivo vazio, binário ou não UTF-8 (lista todos os problemas em `details`) |
| 422 | `invalid_options` | `completed_list` não existe no quadro (as listas disponíveis vêm em `details`) ou foi combinada com `archive_completed` |
| 502 | `trello_auth_failed`, `trello_error` | Credenciais inválidas ou requisição rejeitada pelo Trello |
| 503 | `trello_not_configured`, `trello_rate_limited` | Credenciais ausentes ou rate limit persistente |
| 504 | `trello_unavailable` | Timeout, falha de conexão ou 5xx do Trello |

## Decisões de arquitetura

### Prevenção de duplicidade sem banco de dados

Cada cartão criado recebe ao final da descrição um marcador `taskport:<fingerprint>`. O fingerprint é um hash de **projeto + seção + título** (normalizados) + ocorrência, então editar a descrição, marcar a tarefa como concluída ou mudá-la de lista **não** gera um novo cartão. A lista não faz parte da identificação: se você mover o cartão de TODO para outra coluna no Trello, a reimportação o atualiza onde ele estiver, sem trazê-lo de volta.

Antes de importar (e na pré-visualização com `board_id`), a API lê todos os cartões do quadro, **inclusive arquivados**, e extrai os marcadores. Tarefas já presentes são ignoradas (`skip`) ou sincronizadas (`update`). Tarefas repetidas entre arquivos da mesma requisição também são criadas uma única vez.

**Por que não usar banco de dados:** o próprio quadro já é a fonte de verdade do que foi importado. Um histórico local ficaria inconsistente sempre que alguém excluísse ou movesse cartões no Trello, exigiria volume persistente no container e não funcionaria entre várias instâncias. O `content_sha256` de cada arquivo é retornado nos relatórios para auditoria; um histórico persistente só se justificaria para trilha de auditoria ou para importações assíncronas/agendadas.

### Falhas parciais sem rollback

Cada operação (lista, cartão, checklist, item, arquivamento) é tratada isoladamente e registrada no relatório. Não há rollback automático: excluir cartões já criados poderia apagar dados editados nesse meio-tempo. Como a importação é idempotente, **basta reenviar os mesmos arquivos** para completar o que faltou (com `on_existing=update` também são completados itens de checklist que falharam). Credenciais inválidas ou quadro inexistente são detectados **antes** de qualquer escrita; se as credenciais forem revogadas no meio do processo, a importação é interrompida (`aborted: true`).

### Rate limit e retries

O Trello limita requisições por token e por key (retornando 429). O cliente respeita `Retry-After` ou aplica backoff exponencial. Requisições `GET`/`PUT` também são repetidas após timeout e 5xx. `POST` **não** é repetido nesses casos, porque o Trello pode ter criado o recurso antes da falha e a repetição o duplicaria; o 429 é sempre seguro, pois a requisição foi rejeitada.

### Estrutura

```
app/
  api/        rotas e dependências (injeção do cliente/serviço)
  schemas/    contratos Pydantic (Markdown interpretado, Trello, preview/importação)
  services/   regras de negócio: validação de uploads, duplicidade, importação
  parsers/    tokenização por regras + montagem da estrutura
  clients/    cliente HTTP do Trello (auth, timeout, retries, mapeamento de erros)
  core/       configuração, logs JSON com redação de segredos, erros
tests/        parser, uploads, duplicidade, cliente, serviço e API (98 testes)
examples/     arquivos Markdown de exemplo
```

## Limitações conhecidas

- **Checklist única:** todas as subtarefas vão para a checklist "Subtarefas". O Trello não tem checklists aninhadas: a hierarquia é indicada pelo prefixo `↳`.
- **Renomear uma tarefa cria outro cartão:** alterar o título, a seção (`###`) ou o projeto (`#`) produz outro fingerprint, e o cartão antigo permanece no quadro. Mudar a lista (`##`) não.
- **Lista só na criação:** a lista do Markdown é usada apenas ao criar o cartão. O modo `update` não move cartões entre listas, exceto tarefas concluídas quando `completed_list` é informado. Reabrir uma tarefa (`[x]` → `[ ]`) não tira o cartão da lista de concluídos.
- **Etiquetas só são adicionadas:** o modo `update` adiciona as etiquetas que faltam, mas não remove etiquetas do cartão.
- **Sem remoção:** o modo `update` não remove cartões nem itens de checklist que deixaram de existir no Markdown, e não desarquiva cartões.
- **Marcador visível:** o marcador `taskport:…` fica visível no fim da descrição. Removê-lo manualmente faz a tarefa ser importada de novo.
- **Conclusão:** cartões concluídos e não arquivados recebem apenas uma nota na descrição. A API não aplica etiquetas nem datas de entrega.
- **Importação síncrona e sequencial:** arquivos muito grandes podem levar alguns segundos por causa dos limites do Trello. Não há fila nem processamento em segundo plano.
- **Texto antes da primeira tarefa do arquivo** (entre `#` e o primeiro `##`) não é enviado ao Trello. Ele é sinalizado em `warnings`/`unassigned_text`.
- Apenas headings ATX (`#`) são reconhecidos. Headings sublinhados (`===`/`---`) e front matter YAML são tratados como texto.
- A descrição é truncada no limite de 16.384 caracteres do Trello, preservando o marcador.
