# BP Tech – Rede e Conectividade

## TODO

- [ ] #08 · payment-gateway: fechar portas abertas no SG launch-wizard-2
  **Achado:** Instância payment-gateway: o SG launch-wizard-2 ainda libera para 0.0.0.0/0 o Redis (6379/tcp), o Beats/Logstash (5044 tcp/udp) e as portas 80, 443, 3001, 3030, 3031, 3099 e 8080. Desde 05/11, o SSH (22) não está mais aberto para a internet: está liberado só para as VPCs internas, a VPN e as prefix lists com os IPs do WAF.
  **Severidade:** Crítica
  **Etiquetas:** Crítica
  **Status:** 🟡 Parcial (SSH corrigido em 05/11; as demais portas seguem abertas)
  **Recomendação:** Remover as regras abertas uma a uma, manter o SSH como está e, por fim, desassociar o launch-wizard-2 da instância.
  **Histórico:** 05/11 15:02 a 16:20 – SSH (22) para a internet removido do launch-wizard-2 e liberado só para as VPCs internas, a VPN e as 3 prefix lists (viviane.coelho); 05/11 15:48 a 16:17 – criadas as managed prefix lists bp_ips, IPsConfiaveis_1 e IPsConfiaveis_2 com os IPs dos IP sets do WAF (viviane.coelho)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Restringir SSH (22) às VPCs internas, VPN e prefix lists do WAF
  - [ ] Remover regra 6379/tcp de 0.0.0.0/0 (Redis da aplicação é o ElastiCache lannister-redis)
  - [ ] Enviar logs para localhost ou IP privado e remover regras 5044 tcp/udp
  - [ ] Confirmar acesso só pelo ALB alb-payment-gateway-ec2 e remover 80, 443, 3001, 3030, 3031, 3099 e 8080
  - [ ] Desassociar o SG launch-wizard-2 da instância

- [x] #12 · RDS lipsync: remover acesso público e regra 0.0.0.0/0
  **Achado:** RDS lipsync (Postgres) com PubliclyAccessible = true e SG liberando todo protocolo/porta para 0.0.0.0/0.
  **Severidade:** Crítica
  **Etiquetas:** Crítica
  **Status:** ✅ Resolvido (desde 2026-10-13)
  **Recomendação:** Já corrigido.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Desativar PubliclyAccessible e remover a regra 0.0.0.0/0 do SG

- [ ] #22 · S3 template-backend-dev-logs: remover gravação anônima
  **Achado:** Bucket template-backend-dev-logs com política AllowPublicPut: s3:PutObject liberado para Principal: *, sem condição.
  **Severidade:** Crítica
  **Etiquetas:** Crítica
  **Status:** ✅ Resolvido (Block Public Access completo desde 03/11)
  **Recomendação:** Remover o statement AllowPublicPut que ficou na política, sem efeito hoje, para não voltar a valer caso o Block Public Access seja desligado.
  **Histórico:** 03/11 13:27 – Block Public Access completo no bucket template-backend-dev-logs (julio.stanik)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Ativar Block Public Access completo no bucket
  - [ ] Remover o statement AllowPublicPut da política do bucket

- [ ] #01 · EKS eks-bptech: restringir SG do cluster aberto a 0.0.0.0/0
  **Achado:** SG sg-06cecdabf15118ebb (eks-bptech) libera todo tráfego de 0.0.0.0/0 em todas as portas.
  **Severidade:** Alta
  **Etiquetas:** Alta
  **Status:** Persiste
  **Recomendação:** Restringir a origens conhecidas (VPN/bastion) e portas necessárias.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Restringir o sg-06cecdabf15118ebb a origens conhecidas (VPN/bastion) e portas necessárias

- [ ] #02 · EKS: restringir endpoint público do control plane
  **Achado:** Endpoint público do control plane aberto a 0.0.0.0/0.
  **Severidade:** Média/Alta
  **Etiquetas:** Alta
  **Status:** 🟡 Parcial (cluster Fenix removido; persiste no eks-bptech)
  **Recomendação:** Restringir publicAccessCidrs a faixas de IP corporativas ou desabilitar acesso público, mantendo apenas o privado.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Remover o cluster Fenix
  - [ ] Restringir publicAccessCidrs do eks-bptech ou desabilitar o acesso público

- [ ] #09 · robos: fechar portas abertas no SG robos-sg
  **Achado:** Instância robos: o SG robos-sg, criado em 05/11 com as regras do antigo ubuntu, libera para 0.0.0.0/0 e ::/0 o Postgres (5432/tcp) e as portas 80, 443, 3021, 3022, 3030, 3031, 3035, 3084, 3085 e 8080. Desde 05/11, o SSH (22) não está mais aberto para a internet: está liberado só para as VPCs internas.
  **Severidade:** Alta
  **Etiquetas:** Alta
  **Status:** 🟡 Parcial (SSH corrigido e SG ubuntu desassociado em 05/11; as demais portas seguem abertas no robos-sg)
  **Recomendação:** Restringir Postgres e portas de aplicação às origens internas, remover regras IPv6 desnecessárias e excluir o SG ubuntu.
  **Histórico:** 05/11 16:36 – SSH (22) no launch-wizard-1 restrito às VPCs internas (viviane.coelho); 05/11 17:01 a 17:09 – criado o SG robos-sg com as regras do ubuntu, exceto SSH, e o SG ubuntu desassociado da instância (viviane.coelho)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Restringir SSH (22) às VPCs internas
  - [x] Desassociar o SG ubuntu da instância
  - [ ] Restringir o Postgres (5432) às origens que usam o banco
  - [ ] Mapear portas de aplicação com acesso externo e restringir as demais às VPCs internas e à VPN
  - [ ] Remover as regras ::/0 (IPv6) desnecessárias
  - [ ] Excluir o SG ubuntu, que ainda libera 22/tcp para 0.0.0.0/0

- [ ] #21 · S3: ativar Block Public Access no nível da conta
  **Achado:** Block Public Access do S3 não configurado no nível da conta.
  **Severidade:** Alta
  **Etiquetas:** Alta
  **Status:** Persiste
  **Recomendação:** Ativar na conta depois que os sites estáticos estiverem atrás do CloudFront com OAC (seção 10.6, etapa 5).
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seções 10.6 e 11

  - [ ] Concluir a migração dos sites estáticos para CloudFront com OAC (achado #24)
  - [ ] Ativar o Block Public Access no nível da conta

- [ ] #23 · S3: remover listagem pública de buckets com dados internos
  **Achado:** Buckets com nomes de dados internos e listagem pública: relatorio-diario-bp e stg-bucket-doc (ACL AllUsers: READ) e codepipeline-us-east-1-847031318752 (ACL AuthenticatedUsers: READ).
  **Severidade:** Alta
  **Etiquetas:** Alta
  **Status:** 🟡 Parcial (codepipeline-us-east-1-847031318752 protegido em 03/11; relatorio-diario-bp e stg-bucket-doc seguem com ACL pública)
  **Recomendação:** Remover as concessões de ACL, desabilitar ACLs (Bucket owner enforced) e ativar o Block Public Access completo.
  **Histórico:** 03/11 13:30 – Block Public Access completo no bucket codepipeline-us-east-1-847031318752; a concessão de ACL para AuthenticatedUsers não existe mais (julio.stanik)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seções 10.6 e 11

  - [x] Proteger o bucket codepipeline-us-east-1-847031318752
  - [ ] Proteger o bucket relatorio-diario-bp (remover ACL, Bucket owner enforced, Block Public Access)
  - [ ] Proteger o bucket stg-bucket-doc (remover ACL, Bucket owner enforced, Block Public Access)

- [x] #03 · VPCs: eliminar CIDR 10.0.0.0/16 duplicado
  **Achado:** CIDR 10.0.0.0/16 duplicado entre Fenix-vpc e eks-vpc.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** ✅ Resolvido
  **Recomendação:** Fenix-vpc removida; não há mais sobreposição de CIDR entre as VPCs da conta.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Remover a Fenix-vpc

- [ ] #04 · eks-vpc: criar um NAT Gateway por AZ
  **Achado:** NAT único em eks-vpc (sem redundância entre AZs).
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Criar um NAT Gateway por AZ.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Criar um NAT Gateway por AZ na eks-vpc

- [ ] #05 · Rede: avaliar migração do peering para Transit Gateway
  **Achado:** Ausência de Transit Gateway; topologia depende de peering ponto a ponto.
  **Severidade:** Baixa/Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Avaliar migração para Transit Gateway se o número de VPCs crescer (com o fim do conflito de CIDR, a migração ficou viável).
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Avaliar migração para Transit Gateway

- [ ] #10 · VPC default: tirar IP público direto das instâncias standalone
  **Achado:** Todas as instâncias standalone da VPC default recebem IP público direto, sem NAT/bastion na frente.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Avaliar mover essas instâncias para subnets privadas atrás de NAT, com acesso administrativo apenas via VPN.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Avaliar mover as instâncias para subnets privadas atrás de NAT, com acesso administrativo via VPN

- [ ] #11 · VPN-PritUNL: restringir acesso ao console web
  **Achado:** Console web do concentrador VPN-PritUNL (80/443) aberto para 0.0.0.0/0.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Restringir o acesso ao painel administrativo a faixas de IP conhecidas.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Restringir as portas 80/443 do painel a faixas de IP conhecidas

- [ ] #13 · RDS db-bkp-18-06-5-55: remover regra ampla do SG
  **Achado:** RDS db-bkp-18-06-5-55 com regra de SG -1/0.0.0.0/0, apesar de não ser publicamente acessível.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Remover a regra ampla e manter apenas o acesso restrito já existente.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Remover a regra -1/0.0.0.0/0 do SG

- [ ] #16 · api-pdf: restringir porta 80 no SG api-pdf-sg
  **Achado:** Instância api-pdf: SG api-pdf-sg libera a porta 80/tcp para 0.0.0.0/0.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Restringir a porta 80 às mesmas origens da regra de 443, ou redirecionar para HTTPS e remover a regra aberta.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Restringir a porta 80 às origens da regra 443 ou redirecionar para HTTPS e remover a regra

- [ ] #19 · VPC default: remover SG default aberto dos endpoints do ElastiCache
  **Achado:** SG default da VPC default (sg-2ee7c968) libera todo tráfego de 0.0.0.0/0 e está anexado aos 3 VPC Endpoints do ElastiCache Serverless (9 interfaces de rede).
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Os endpoints não têm IP público, mas aceitam conexões de qualquer origem das VPCs com peering e da VPN. Remover o SG default dos endpoints (já usam também o sg-00d006c6c8a45ad0b) e retirar a regra 0.0.0.0/0 do SG default.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Remover o SG default (sg-2ee7c968) dos 3 VPC Endpoints do ElastiCache Serverless
  - [ ] Retirar a regra 0.0.0.0/0 do SG default

- [ ] #20 · EKS eks-bptech: restringir porta 9200 no SG dos nós
  **Achado:** SG dos nós do eks-bptech (sg-0bd505e766527688c) libera 9200/tcp para 0.0.0.0/0, sem descrição.
  **Severidade:** Baixa/Média
  **Etiquetas:** Média
  **Status:** Persiste
  **Recomendação:** Identificar o serviço que usa a porta 9200 (porta padrão do Elasticsearch/OpenSearch) e restringir a origem às redes que realmente precisam, ou remover a regra se não for mais usada.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Identificar o serviço que usa a porta 9200
  - [ ] Restringir a origem da regra 9200/tcp ou removê-la

- [ ] #24 · Sites estáticos S3: servir via CloudFront com OAC e fechar acesso direto
  **Achado:** 30 buckets de site/conteúdo estático com acesso público direto (28 via política s3:GetObject e 2 só via ACL), 24 deles com listagem pública via ACL.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** 🟡 Parcial (de 30 para 25 buckets: 4 protegidos e 1 excluído; admin.bbone.com.br e front-web-vistoria-prod em transição para CloudFront)
  **Recomendação:** Confirmar quais estão em uso, servir por CloudFront com OAC, remover ACLs READ/READ_ACP e remover os que não são mais usados. Ativar o Block Public Access em um bucket de site sem antes colocar o CloudFront com OAC na frente deixa o site fora do ar.
  **Histórico:** 03/11 13:34 e 13:46 – Block Public Access completo nos buckets bbone-test-deploy e bbone-web-teste-wkauf3fa-dev (julio.stanik); 03/11 13:44 – bucket hookord-bp excluído (julio.stanik); 03/11 13:50 – dev.bbonebrasil.com.br servido só pelo CloudFront (julio.stanik); 03/11 14:43 a 14:45 – bp-seguros-corp com ACL pública removida, política só para o CloudFront e Block Public Access (julio.stanik); 03/11 18:09 e 05/11 14:59 – admin.bbone.com.br e front-web-vistoria-prod-bucket-367265287622 com permissão para o CloudFront, mas leitura pública mantida (julio.stanik)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seções 10.6 e 11

  - [x] Proteger os buckets bbone-test-deploy e bbone-web-teste-wkauf3fa-dev
  - [x] Excluir o bucket hookord-bp
  - [x] Migrar dev.bbonebrasil.com.br para CloudFront com OAC
  - [x] Migrar bp-seguros-corp para CloudFront com OAC
  - [ ] Concluir a migração de admin.bbone.com.br (remover statement público e ACLs, ativar Block Public Access)
  - [ ] Concluir a migração de front-web-vistoria-prod-bucket-367265287622 (remover statement público e ACLs, ativar Block Public Access)
  - [ ] Confirmar quais dos demais sites estáticos estão em uso
  - [ ] Servir os sites em uso pelo CloudFront com OAC e fechar o acesso direto
  - [ ] Remover os buckets de sites que não estão em uso
  - [ ] Limpar as políticas residuais dos 3 buckets citados na seção 10.4

- [ ] #25 · S3: ativar Block Public Access nos buckets sem proteção
  **Achado:** 7 buckets sem Block Public Access, embora hoje não sejam públicos.
  **Severidade:** Média
  **Etiquetas:** Média
  **Status:** 🟡 Parcial (6 de 7 protegidos em 03/11; resta checkout.bpseguradora.com.br)
  **Recomendação:** Ativar o Block Public Access completo no checkout.bpseguradora.com.br (sem impacto, pois hoje ele não é público).
  **Histórico:** 03/11 13:32 a 13:42 – Block Public Access completo em aliveplan, simplesbucket, vetmark, buonavita-btx, staging.digital-opening.bbonebrasil.com.br e boonbrasil (julio.stanik)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seções 10.6 e 11

  - [x] Proteger aliveplan, simplesbucket, vetmark, buonavita-btx, staging.digital-opening.bbonebrasil.com.br e boonbrasil
  - [ ] Ativar o Block Public Access completo no checkout.bpseguradora.com.br

- [ ] #06 · EKS eks-bptech: habilitar todos os logs do control plane
  **Achado:** Logging do control plane incompleto em eks-bptech.
  **Severidade:** Baixa
  **Etiquetas:** Baixa
  **Status:** 🟡 Parcial (authenticator habilitado; controllerManager/scheduler seguem desabilitados)
  **Recomendação:** Habilitar os 5 tipos de log.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Habilitar o log authenticator
  - [ ] Habilitar os logs controllerManager e scheduler

- [ ] #14 · Lambdas bbone-jobs-dev: criar SG dedicado em vez dos SGs do EKS
  **Achado:** Lambda bbone-jobs-dev-message-processor usa Security Groups criados para o cluster EKS.
  **Severidade:** Baixa
  **Etiquetas:** Baixa
  **Status:** ⚠️ Ampliado (desde 03/11 a bbone-jobs-dev-message-queue também usa esses SGs)
  **Recomendação:** Criar um SG dedicado para as 2 funções.
  **Histórico:** 03/11 15:44 – Lambda bbone-jobs-dev-message-queue associada à eks-vpc com os mesmos 3 SGs do EKS (caio.resende)
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Criar um SG dedicado para as Lambdas bbone-jobs-dev-message-processor e bbone-jobs-dev-message-queue

- [x] #18 · Elastic IPs: liberar EIPs sem associação da antiga Fenix-vpc
  **Achado:** 3 Elastic IPs da antiga Fenix-vpc (3.216.210.139, 52.203.35.140, 54.87.29.94) alocados e sem associação.
  **Severidade:** Baixa (custo)
  **Etiquetas:** Baixa
  **Status:** ✅ Resolvido
  **Recomendação:** EIPs liberados; a conta não tem mais EIPs sem associação.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Liberar os 3 Elastic IPs sem associação

- [ ] #07 · VPC 172.30.0.0/16: confirmar uso ou remover
  **Achado:** VPCs sem peering, sem conectividade com o restante do ambiente.
  **Severidade:** Informativo
  **Etiquetas:** Informativo
  **Status:** 🟡 Parcial (Fenix-vpc removida; resta a VPC 172.30.0.0/16)
  **Recomendação:** Confirmar se a VPC 172.30.0.0/16 ainda é usada; se não, removê-la.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Remover a Fenix-vpc
  - [ ] Confirmar se a VPC 172.30.0.0/16 ainda é usada e removê-la se não for

- [ ] #15 · RDS bpqa2 e tools-prod: confirmar uso dos bancos sem regras de entrada
  **Achado:** RDS bpqa2 e tools-prod sem nenhuma regra de entrada no SG.
  **Severidade:** Informativo
  **Etiquetas:** Informativo
  **Status:** Persiste
  **Recomendação:** Confirmar se os bancos estão em desuso; caso contrário, adicionar as regras necessárias.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [ ] Confirmar se bpqa2 e tools-prod estão em desuso ou adicionar as regras necessárias

- [x] #17 · RDS payment-gateway-old1: descomissionar cópia antiga
  **Achado:** RDS payment-gateway-old1 (cópia do banco anterior ao upgrade).
  **Severidade:** Informativo
  **Etiquetas:** Informativo
  **Status:** ✅ Resolvido
  **Recomendação:** Instância descomissionada.
  **Fonte:** Relatório de Rede e Conectividade - BPTech, v5.0, 06/11/2026 – seção 11

  - [x] Descomissionar a instância payment-gateway-old1
