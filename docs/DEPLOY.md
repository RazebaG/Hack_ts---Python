# Guia de Deploy e Containerização — ACME Normas Backend

Este documento descreve os procedimentos de containerização e deploy do backend FastAPI do **Assistente do Arquivo Central de Normas** (HACKA/TS 2026 · Team 5 Clankers).

---

## 1. Execução Local via Container

### Pré-requisitos
- Docker Engine 20.10+ ou Docker Desktop
- Docker Compose v2+ (opcional, para orquestração simplificada)

### 1.1 Usando Docker Compose (Recomendado)
Para subir o backend em container com as variáveis padronizadas:

```bash
# Constrói a imagem e inicia o container em segundo plano
docker compose up --build -d

# Visualizar logs em tempo real
docker compose logs -f backend

# Verificar o healthcheck da API
curl -s http://localhost:8000/api/saude | jq .

# Parar o serviço
docker compose down
```

> [!NOTE]
> **Bedrock no container local:** o compose repassa `AWS_PROFILE` (padrão `hackats`), mas o container não enxerga o `~/.aws` da máquina. Com `LLM_PROVIDER=nenhum` (padrão) nada muda. Para usar `LLM_PROVIDER=bedrock` localmente, monte o perfil só para leitura, por exemplo num `docker-compose.override.yml` (não commitado):
> ```yaml
> services:
>   backend:
>     volumes:
>       - ~/.aws:/home/appuser/.aws:ro
> ```

### 1.2 Usando Docker CLI e Makefile
```bash
# Construir a imagem localmente
make docker-build
# ou: docker build -t acme-normas-backend:latest .

# Executar o container na porta 8000
make docker-run
# ou: docker run -d --name acme-normas-backend -p 8000:8000 --env-file .env acme-normas-backend:latest
```

---

## 2. Deploy na AWS via Amazon ECS Express Gateway

O Amazon ECS Express Gateway simplifica o provisionamento de serviços web conteinerizados gerenciando automaticamente o Application Load Balancer (ALB), Target Groups, Security Groups e políticas de auto-scaling.

### 2.1 Sintaxe Homologada da CLI AWS
A sintaxe do comando foi verificada e validada localmente via `aws ecs create-express-gateway-service help` (AWS CLI v2).

> [!IMPORTANT]
> **Limite Conhecido de Lotes em Memória (Obrigatoriedade de 1 Tarefa):**  
> No MVP atual (ondas 0 e 1), o estado de lotes e documentos dinâmicos enviados via upload/digitalização (`/api/lotes`) é mantido em memória no runtime (`AcervoRepository`).  
> **Recomendação arquitetural:** O serviço DEVE ser configurado com exatamente **1 tarefa** (`minTaskCount: 1, maxTaskCount: 1`), assegurando que todas as requisições acessem o mesmo estado consistente sem necessidade de banco de dados distribuído nesta fase. A persistência externa em PostgreSQL faz parte do plano de evolução de 6 meses (Mês 1).

> [!WARNING]
> **Avaliações também são efêmeras:** `/api/avaliacoes` grava em `data/avaliacoes.jsonl` dentro do container. Em Fargate esse arquivo some a cada novo deploy ou troca de tarefa.
>
> **CORS:** nesta versão as origens permitidas são fixas (`localhost`/`127.0.0.1`, portas 5173 e 3000). Um frontend publicado em outro domínio só consegue chamar a API depois da configuração de origens por ambiente (`CORS_ORIGINS`, PR #41).

### 2.2 Pré-requisitos na AWS
1. **Repositório no Amazon ECR:**
   ```bash
   # Autenticar no ECR da conta
   aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com

   # Taguear e enviar a imagem construída
   docker tag acme-normas-backend:latest <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/acme-normas-backend:latest
   docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/acme-normas-backend:latest
   ```
2. **Roles IAM Necessárias:**
   - **Infrastructure Role (`--infrastructure-role-arn`):** Permite ao ECS criar e gerenciar ALB, Target Groups e Security Groups.
   - **Execution Role (`--execution-role-arn`):** Permite ao ECS Agent puxar imagens do ECR e registrar logs no Amazon CloudWatch.
   - **Task Role (`--task-role-arn`):** Concede à aplicação as permissões de acesso ao Amazon Bedrock (`bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`).

### 2.3 Comando de Criação do Serviço ECS Express Gateway
Execute o comando abaixo substituindo os identificadores `<ACCOUNT_ID>` e `<REGION>`. O cluster `acme-cluster` precisa existir; sem `--cluster`, o ECS usa o cluster `default`.

```bash
aws ecs create-express-gateway-service \
  --service-name acme-normas-backend \
  --cluster acme-cluster \
  --infrastructure-role-arn arn:aws:iam::<ACCOUNT_ID>:role/ecsInfrastructureRole \
  --execution-role-arn arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole \
  --task-role-arn arn:aws:iam::<ACCOUNT_ID>:role/acmeBedrockTaskRole \
  --health-check-path "/api/saude" \
  --cpu "512" \
  --memory "1024" \
  --primary-container '{
    "image": "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/acme-normas-backend:latest",
    "containerPort": 8000,
    "environment": [
      {"name": "PORT", "value": "8000"},
      {"name": "LLM_PROVIDER", "value": "bedrock"},
      {"name": "AWS_REGION", "value": "<REGION>"},
      {"name": "BEDROCK_MODEL_ID", "value": "amazon.nova-pro-v1:0"},
      {"name": "BEDROCK_FALLBACK_MODEL_ID", "value": "amazon.nova-lite-v1:0"},
      {"name": "BEDROCK_EMBED_MODEL_ID", "value": "us.cohere.embed-v4:0"}
    ]
  }' \
  --scaling-target '{
    "minTaskCount": 1,
    "maxTaskCount": 1,
    "autoScalingMetric": "AVERAGE_CPU",
    "autoScalingTargetValue": 70
  }'
```

### 2.4 Alternativa via Console Web AWS
Caso o ambiente do evento restrinja permissões de criação via CLI ou utilize a interface visual:
1. Acesse o **Amazon ECS** no AWS Management Console (`us-east-1`).
2. Navegue até o Cluster de destino (`acme-cluster`).
3. Clique em **Create Service** e selecione o tipo de lançamento **Fargate / Express Gateway**.
4. Configure:
   - **Service Name:** `acme-normas-backend`
   - **Container Image URI:** `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/acme-normas-backend:latest`
   - **Port:** `8000`
   - **Health Check Path:** `/api/saude`
   - **Tasks:** Min `1`, Max `1` (arquitetura mono-tarefa para acervo/lotes em memória)
   - **Task Role:** Role com política gerenciada para Amazon Bedrock.
5. Conclua o assistente para provisionar o endpoint público gerenciado.

---

## 3. Verificação Pós-Deploy

Após a conclusão da inicialização do serviço:

```bash
# 1. Testar endpoint de saúde público retornado pelo ALB / Express Gateway
curl -s https://<ENDPOINT_SERVICO>/api/saude | jq .

# 2. Executar smoke test apontando para o ambiente publicado
API_URL=https://<ENDPOINT_SERVICO> bash scripts/smoke.sh
```

---

## 4. Segurança e Boas Práticas

- **Usuário Não-Root:** O `Dockerfile` executa a aplicação com o usuário `appuser` (UID 1000).
- **Sem Credenciais em Arquivo:** Nenhuma credencial estática, token ou segredo deve ser colocado no `Dockerfile`, `docker-compose.yml`, `.env` commitado ou nos parâmetros do CLI. Em produção na AWS, a autenticação utiliza IAM Roles concedidas via `TaskRoleArn`.
- **CORS Homologado:** A API mantém o suporte CORS para o frontend React local (`http://localhost:5173`) e endereços homologados.
