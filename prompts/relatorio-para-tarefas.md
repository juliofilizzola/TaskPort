# Prompt: relatório de achados → tarefas Markdown para o TaskPort

Use o prompt abaixo em qualquer IA (ChatGPT, Claude, etc.), anexando o relatório (PDF ou HTML). A resposta é um arquivo `.md` pronto para `POST /preview` e `POST /imports`.

**Dica:** a partir da segunda versão do relatório, anexe também o `.md` gerado na importação anterior. Assim a IA reaproveita os mesmos títulos e o TaskPort **atualiza** os cartões em vez de criar duplicados (use `on_existing=update`).

---

````text
Você é um analista que transforma relatórios técnicos de auditoria de infraestrutura em tarefas
para o Trello. Vou anexar um relatório (PDF ou HTML) que contém uma tabela de "Achados e
Recomendações" com as colunas: #, Achado, Severidade, Status e Recomendação. Ele também pode
ter uma seção de "Revalidação" (ações realizadas, com data/hora e responsável), uma "Ordem
sugerida de correção" e seções técnicas de inventário.

Sua tarefa: gerar UM arquivo Markdown que será importado automaticamente por um parser estrito.
Siga TODAS as regras abaixo à risca. Qualquer desvio quebra a importação ou cria cartões duplicados.

## 1. Estrutura obrigatória

```
# <Cliente> – <Tema do relatório>

## TODO

- [ ] #NN · <título da tarefa>
  <descrição, várias linhas, sempre indentadas com 2 espaços>
  **Etiquetas:** <severidade>

  - [x] <subtarefa concluída>
  - [ ] <subtarefa pendente>

- [ ] #NN · <próxima tarefa>
...
```

- Linha 1: exatamente um heading `#` com cliente e tema, SEM data, versão ou número de revisão
  (ex.: `# BP Tech – Rede e Conectividade`). Esse nome precisa ser idêntico em todas as versões
  do relatório.
- Não escreva NADA entre o `#` e o primeiro `##` (nenhum parágrafo, resumo ou nota).
- Use UMA única lista: `## TODO` (exatamente esta grafia). Todos os cartões ficam nela,
  inclusive os resolvidos. A severidade NÃO vira lista: ela vai na linha `**Etiquetas:**`
  (regra 4).
- NÃO use `###` nem headings mais profundos.
- Não use tabelas, blocos de código, HTML nem linhas com `---`.

## 2. Uma tarefa por achado

- Cada linha da tabela de achados vira exatamente UM cartão: `- [ ] #NN · <título>` ou
  `- [x] #NN · <título>`, começando na coluna 0 (sem indentação).
- `NN` é o número do achado com 2 dígitos (`#01`, `#08`, `#23`).
- Não crie cartões para inventário, diagramas, metodologia ou referências. Não crie cartões
  separados para os itens da "Ordem sugerida de correção": eles viram subtarefas do achado
  relacionado (regra 5).
- Se um mesmo achado aparecer em mais de um lugar, junte tudo no mesmo cartão.

## 3. Título (CRÍTICO para evitar duplicidade)

O título identifica o cartão entre versões do relatório. Se mudar uma letra, o Trello recebe um
cartão novo. Por isso:

- Formato: `#NN · <recurso principal>: <ação principal no infinitivo>`, com no máximo 80 caracteres.
  Exemplos: `#08 · payment-gateway: fechar portas abertas no SG launch-wizard-2`,
  `#21 · S3: ativar Block Public Access no nível da conta`.
- O título descreve o PROBLEMA/AÇÃO, nunca o estado atual. NÃO inclua status, datas, nomes de
  pessoas, porcentagens nem quantidades que mudam entre versões (escreva "Sites estáticos S3",
  não "30 buckets").
- Não use os caracteres `[`, `]` nem `#` no título, exceto o `#NN` inicial.
- **Se eu anexar o Markdown da importação anterior:** para todo achado com o mesmo número,
  copie o título EXATAMENTE como está lá, mesmo que você escreveria diferente. Só crie títulos
  novos para achados novos.

## 4. Etiqueta (severidade)

- Cada cartão tem exatamente uma linha `  **Etiquetas:** <severidade>` dentro da descrição
  (indentada com 2 espaços, logo após a linha `**Severidade:**`). Ela vira a etiqueta do cartão
  no Trello e não aparece no texto da descrição.
- Use somente um destes valores, com esta grafia exata: `Crítica`, `Alta`, `Média`, `Baixa`,
  `Informativo`.
- Para valores compostos, use a MAIOR severidade: `Média/Alta` → `Alta`; `Baixa/Média` →
  `Média`; `Baixa (custo)` → `Baixa`. Para achados resolvidos, use a severidade original.
- Ordene os cartões dentro de `## TODO` por severidade (Crítica, Alta, Média, Baixa,
  Informativo) e, dentro da mesma severidade, pelo número do achado.

## 5. Subtarefas (checklist)

- Ficam ABAIXO da descrição, indentadas com exatamente 2 espaços: `  - [ ] texto` ou
  `  - [x] texto`. Separe-as da descrição com uma linha em branco.
- Fonte das subtarefas, nesta ordem:
  1. Passos numerados da coluna Recomendação (cada passo vira uma subtarefa).
  2. Itens da "Ordem sugerida de correção" ligados ao achado.
  3. Recursos individuais citados no achado quando a correção é por recurso
     (ex.: um bucket por subtarefa).
  4. Se não houver nada disso, uma única subtarefa com a recomendação.
- Marque `[x]` SOMENTE o que o relatório afirma explicitamente que já foi feito (status, coluna
  "Ação realizada" da revalidação ou texto "corrigido/removido/restringido em DD/MM"). Na dúvida,
  `[ ]`.
- Texto da subtarefa: ação curta no infinitivo, sem datas e sem status
  (ex.: `Remover regra 6379/tcp de 0.0.0.0/0`). Use o mesmo texto em todas as versões: a
  checklist é sincronizada pelo texto do item.
- Nunca escreva texto abaixo de uma subtarefa e nunca aninhe subtarefas em 2 níveis.

## 6. Cartão concluído

- `- [x]` apenas quando o status é "Resolvido" E não sobra nenhuma ação na coluna Recomendação
  (ex.: "Já corrigido", "Instância descomissionada").
- Se o status é "Resolvido" mas a recomendação ainda pede algo (ex.: remover um resíduo), use
  `- [ ]`, com a parte resolvida como subtarefa `[x]` e o resíduo como `[ ]`.
- "Parcial", "Persiste", "Ampliado" e "Novo" são sempre `- [ ]`.

## 7. Descrição

Logo abaixo da linha do cartão, indentada com 2 espaços, nesta ordem e uma informação por linha:

```
  **Achado:** <texto completo da coluna Achado, sem resumir IDs, portas, CIDRs e nomes>
  **Severidade:** <valor original da coluna, ex.: Média/Alta>
  **Etiquetas:** <severidade normalizada da regra 4, ex.: Alta>
  **Status:** <emoji + status + detalhe, como no relatório>
  **Recomendação:** <texto da coluna Recomendação; se forem passos numerados, resuma aqui
  em 1 linha, porque os passos viram subtarefas>
  **Histórico:** <ações da revalidação ligadas a este achado, no formato
  "DD/MM HH:MM – ação (responsável)", separadas por "; ". Omita a linha se não houver>
  **Fonte:** <nome do relatório>, v<versão>, <data> – seção <número da seção>
```

- Copie identificadores técnicos (sg-…, vpc-…, nomes de buckets, portas, CIDRs, IPs) exatamente
  como no relatório.
- A descrição pode mudar entre versões (ela é atualizada no Trello), mas o título não.
- Não comece nenhuma linha da descrição com `#`, `- [ ]`, `- [x]`, `* [`, `+ [` ou `1. [`.
- Não deixe linhas de descrição com 4 ou mais espaços de indentação.

## 8. Ordem e saída

- Siga a ordem de cartões da regra 4.
- Inclua TODOS os achados da tabela, inclusive os resolvidos.
- Responda APENAS com o conteúdo do arquivo, dentro de um único bloco ```markdown, sem
  comentários antes ou depois.
- Antes de responder, confira: quantidade de cartões = quantidade de linhas da tabela de
  achados; nenhum título repetido; nenhuma linha fora das regras acima.
````

---

## Por que essas regras

| Regra | Motivo no TaskPort |
|---|---|
| `#` estável, sem data/versão | O projeto entra na identificação do cartão: mudar o nome duplica tudo |
| Tudo em `## TODO` | Cartões novos entram na coluna TODO. Mover o cartão para outra coluna no Trello não gera duplicata: a reimportação atualiza o cartão onde ele estiver e não o move de volta |
| Severidade em `**Etiquetas:**` | A API cria a etiqueta no quadro (Crítica vermelha, Alta laranja, Média amarela, Baixa verde, Informativo azul) e a aplica ao cartão. Na reimportação, só adiciona etiquetas que faltam e mantém as colocadas manualmente |
| Título estável com `#NN` | O título identifica o cartão. Com `on_existing=update`, a reimportação atualiza descrição e checklist |
| Nada entre `#` e o primeiro `##` | Esse texto não é associado a nenhum cartão (vira aviso no preview) |
| Sem `###` | `###` entra na identificação do cartão e na descrição como "Seção" |
| Descrição antes das subtarefas, indentada com 2 espaços | Texto indentado abaixo de uma subtarefa é tratado como nota da subtarefa; 4 ou mais espaços viram bloco de código no Trello |

## Como importar

1. Salve a resposta da IA como `.md` (ex.: `bptech-rede-conectividade.md`).
2. Revise antes de importar:

```bash
curl -F "files=@bptech-rede-conectividade.md" -F "board_id=SEU_BOARD_ID" -F "on_existing=update" http://localhost:8000/preview
```

Confira em `summary` os campos `cards_to_create`, `cards_to_update`, `cards_to_skip` e `labels_to_create`, e veja se `warnings` está vazio.

3. Importe:

```bash
curl -F "files=@bptech-rede-conectividade.md" -F "board_id=SEU_BOARD_ID" -F "on_existing=update" -F "archive_completed=true" http://localhost:8000/imports
```

Na versão seguinte do relatório, gere o `.md` de novo anexando o anterior e importe com os mesmos parâmetros. Os achados que avançaram têm a checklist e a descrição atualizadas, mesmo que você já os tenha movido para outra coluna. Os resolvidos são arquivados e os novos são criados em TODO.
