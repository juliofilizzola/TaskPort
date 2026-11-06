# Plataforma de Pagamentos

Notas gerais do projeto (não associadas a nenhuma tarefa).

## Sprint 14

### Backend

- [ ] Implementar webhook de estorno
  Validar assinatura HMAC antes de processar.

  ```json
  { "event": "refund.created" }
  ```
  - [ ] Criar endpoint
    Usar fila para processamento assíncrono.
  - [ ] Testes de integração
    - [ ] Cenário de assinatura inválida

### Frontend

- [x] Tela de histórico de transações
