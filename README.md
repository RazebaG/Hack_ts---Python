# ACME - Assistente do Arquivo Central de Normas

Transforma contratos, normas e políticas em decisões fundamentadas com citação auditável (`código · versão · seção · camada`), aponta contradições em radar determinístico, simula cenários "E se?" e integra-se à interface web React, Slack e Teams.

Backend de inteligência sobre o acervo normativo da ACME para o **HACKA/TS 2026** (Desafio 2 · Team 5 Clankers).

---

## Execução Local em 5 Passos

### Passo 1: Clonar os Repositórios
```bash
# Repositório do Backend (Python)
git clone https://github.com/RazebaG/Hack_ts---Python.git
cd Hack_ts---Python

# Repositório do Frontend (React / TypeScript)
git clone https://github.com/RazebaG/Hacka_ts-React.git
```

### Passo 2: Configurar as Variáveis de Ambiente
Copie o modelo `.env.example` para `.env` no backend. **Atenção:** nunca insira credenciais, chaves de acesso ou IDs de conta. O ambiente do evento utiliza perfil local seguro.

**Backend (`Hack_ts---Python/.env`):**
- `API_KEY`: Chave de autenticação da API (quando definida, exige o cabeçalho `X-API-Key` com comparação em tempo constante; se vazia, autenticação fica desligada; `/api/saude` e preflight `OPTIONS` permanecem abertos)
- `RATE_LIMIT_POR_MINUTO`: Limite de requisições por minuto por IP com janela deslizante (ex: `60`; responde `429 Too Many Requests` com cabeçalho `Retry-After`; se vazia ou 0, fica desligado)
- `CORS_ORIGINS`: Lista de origens permitidas para CORS separadas por vírgula (padrão: `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000`)
- `LLM_PROVIDER`: Provedor do modelo de linguagem (`nenhum` para extração direta determinística; `bedrock` para Amazon Bedrock)
- `AWS_PROFILE`: Nome do perfil de autenticação local da AWS (padrão: `hackats`)
- `AWS_REGION`: Região da AWS (padrão: `us-east-1`)
- `BEDROCK_MODEL_ID`: Modelo de texto principal (padrão: `amazon.nova-pro-v1:0`)
- `BEDROCK_FALLBACK_MODEL_ID`: Modelo de fallback rápido (padrão: `amazon.nova-lite-v1:0`)
- `BEDROCK_EMBED_MODEL_ID`: Modelo de embeddings (padrão: `us.cohere.embed-v4:0`)

**Frontend (`Hacka_ts-React/.env`):**
- `VITE_API_URL`: URL base do backend (ex: `http://localhost:8000`)

### Passo 3: Instalar as Dependências
```bash
# Backend (Python 3.10+)
cd Hack_ts---Python
pip install -r requirements.txt

# Frontend (Node.js 18+)
cd ../Hacka_ts-React
npm install
```

### Passo 4: Inicializar os Serviços
Em terminais separados:

```bash
# Terminal 1: Iniciar API FastAPI do Backend (porta 8000)
cd Hack_ts---Python
make run
# ou: uvicorn app.main:app --reload --port 8000

# Terminal 2: Iniciar Servidor de Desenvolvimento do Frontend (porta 5173)
cd Hacka_ts-React
npm run dev
```

Acesse a interface web em: `http://localhost:5173`
A documentação interativa da API estará disponível em: `http://localhost:8000/docs`

### Passo 5: Executar Testes e Smoke Integrado
```bash
# No diretório do Backend (Hack_ts---Python):
make test    # Executa a suíte de testes com pytest (343 testes)
make smoke   # Executa o smoke test ponta a ponta com acervo real, 10 casos-chave (incluindo Ficha de CTR_2026-012, NG_111 e Triagem C25) e CORS
make eval    # Executa a avaliação de perguntas e respostas (/api/perguntar)
python -m eval.sinais   # Sinais do mapa de posição (F-02, #42): % de seções marcadas e recall contra data/curadoria
                        # (--prototipo mostra as regras antigas, para comparar)

# No diretório do Frontend (Hacka_ts-React):
npm test -- --run   # Executa os testes unitários e de integração do frontend
```

---

## Canais (Slack) · issue #9

A camada comum fica em `app/canais/`. `cartao.py` monta o cartão neutro a partir da resposta da API: conclusão, até 3 citações com selo `SIGLA · Grupo`, avisos, próxima ação, link do painel e botões Útil/Não útil. `slack.py` só traduz esse cartão para Block Kit. O bot consome apenas a API (`API_URL`).

1. Crie o app no workspace de teste a partir de `app/canais/slack_manifest.yaml` (Socket Mode, comando `/acervo`).
2. Gere um App-Level Token com `connections:write` e instale o app no workspace.
3. No `.env`, preencha `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `API_URL` e `PAINEL_URL`. O `.env` não vai para o repositório.
4. Suba a API (`uvicorn app.main:app`) e o bot (`python -m app.canais.slack`).

Uso: `/acervo <pergunta>` ou `/acervo radar [perspectiva]`. Se a perspectiva não existir, o bot mostra a mensagem de erro da API.

## Agente do Teams (Microsoft 365 Agents SDK) · issue #14

O agente fica em `app/canais/teams.py`. Ele só cuida da apresentação. Cada mensagem é enviada a
`POST /api/perguntar`, a resposta vira o **cartão neutro** de `app/canais/cartao.py` (o mesmo do Slack)
e esse cartão é traduzido para **Adaptive Card**. Se a API recusar a pergunta (4xx), o agente pede para
reformular; se a API estiver fora (5xx ou sem conexão), avisa e manda o link do painel. Um corpo que não é
atividade válida em `/api/messages` recebe **400**. Os botões **Útil** / **Não útil** gravam em `POST /api/avaliacoes` com
`canal: teams`. O agente confirma na hora com "Consultando o acervo…" e manda o cartão na mensagem seguinte.

Mensagens aceitas (mensagem direta ao agente):

| Mensagem | O que faz |
|---|---|
| `acervo <pergunta>` ou só a pergunta | Responde com o cartão de `/api/perguntar` |
| `acervo radar [tema]` | Lista até 3 itens de `GET /api/radar` (título, explicação, fontes, link "Ver lado a lado") filtrados pelo tema, sem diferenciar acentos (`férias` = `ferias`). Sem itens, mostra um texto de estado |
| `acervo ajuda` | Mostra os comandos |

### Configuração

Tudo vem de variáveis de ambiente. Os nomes estão em [`.env.example`](.env.example):

| Variável | Padrão | Uso |
|---|---|---|
| `API_URL` | `http://localhost:8000` | API FastAPI do acervo |
| `PAINEL_URL` | `http://localhost:5173` | Links "Abrir no painel" e das citações |
| `TEAMS_PORTA` | `3978` | Porta do agente |
| `TEAMS_PERFIL` | vazio (geral) | Perfil enviado a `/api/perguntar` |
| `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` | vazios | Credenciais do Azure Bot. **Vazias no Playground** (modo anônimo). A publicação no tenant fica para o plano de 6 meses |

Sem `CLIENT_ID`, o agente aceita requisições anônimas, que é o que o Playground usa.

### Rodar localmente e testar no Microsoft 365 Agents Playground

Pré-requisitos: Python 3.10+ e Node.js 18+.

1. **API** (terminal 1):
   ```bash
   uvicorn app.main:app --port 8000
   ```
2. **Agente** (terminal 2):
   ```bash
   set -a; [ -f .env ] && source .env; set +a   # opcional
   python -m app.canais.teams
   # Agente Teams em http://localhost:3978/api/messages · modo anônimo (Agents Playground)
   ```
3. **Playground** (terminal 3). Pacote npm `@microsoft/m365agentsplayground`, conferido em 12/11/2026, versão 0.2.30.
   Antes de instalar, confira o nome atual na
   documentação da Microsoft (Microsoft 365 Agents SDK → "Agents Playground") ou em
   <https://www.npmjs.com/package/@microsoft/m365agentsplayground>:
   ```bash
   npm install -g @microsoft/m365agentsplayground
   agentsplayground -e http://localhost:3978/api/messages -c msteams
   ```
   O Playground abre no navegador. Envie, por exemplo:
   `acervo Até quando peço férias que começam em 05/05/2027?`. Deve chegar "Consultando o acervo…"
   e, logo depois, o cartão com a conclusão, as citações (`NG_111 · v3.0.0 · Anexo C`, camada curta),
   os avisos, a próxima ação e os botões. Clicar em **Útil** registra a avaliação, e
   `GET /api/avaliacoes/resumo` passa a contar `teams`.

**Plano B (sem Playground):** `pytest tests/test_teams.py -v` faz uma atividade real passar pelo
`CloudAdapter`/`AgentApplication` do SDK com `deliveryMode: expectReplies`, que devolve as respostas no
corpo HTTP. O teste roda sem rede e sem credenciais, e confere o Adaptive Card gerado. Para ver o JSON com o
agente no ar, use:

```bash
curl -s localhost:3978/api/messages -H 'Content-Type: application/json' -d '{
  "type":"message","id":"1","channelId":"msteams","serviceUrl":"http://localhost",
  "deliveryMode":"expectReplies","text":"acervo Qual a antecedência mínima para pedir férias?",
  "from":{"id":"u"},"recipient":{"id":"agente"},"conversation":{"id":"c"}}'
```

---

## Segurança e Proteção da API

A camada de segurança implementa controles essenciais para proteção de runtime e resiliência:

1. **Autenticação por API Key (`X-API-Key`):**
   - Comparação segura em tempo constante (`secrets.compare_digest`) para prevenir ataques de temporização (timing attacks).
   - Ativação dinâmica: se `API_KEY` não for configurada no ambiente, a autenticação opera desligada (compatibilidade de desenvolvimento e testes locais).
   - Exceções seguras: requisições `OPTIONS` (preflight do CORS) e o endpoint de monitoramento `/api/saude` permanecem abertos.
   - Resposta padronizada `401 Unauthorized` com detalhe claro caso a chave seja ausente ou inválida (com cabeçalhos CORS, para o navegador conseguir ler o erro).
   - Os canais Slack e Teams enviam `X-API-Key` automaticamente quando `API_KEY` está definida no ambiente deles. **O frontend web ainda não envia o cabeçalho:** ligar `API_KEY` hoje bloqueia a interface web. Uma chave embutida no bundle do navegador é pública, então para a web ela serve como barreira contra uso casual, não como segredo.

2. **Limite de Taxa de Requisições (`RATE_LIMIT_POR_MINUTO`):**
   - Rate limiting por IP utilizando janela deslizante de 60 segundos.
   - O IP é o `request.client.host`; o `X-Forwarded-For` enviado pelo cliente não é confiado (trocar o valor não zera a cota). Atrás do ALB do ECS, defina `FORWARDED_ALLOW_IPS` com a faixa da VPC para o uvicorn usar o IP real repassado pelo balanceador; sem isso, todo o tráfego conta como o IP do ALB.
   - Desligado quando a variável não está definida (ou `<= 0`), garantindo zero impacto nos testes unitários e de integração.
   - Ao ultrapassar a cota, responde com `429 Too Many Requests` e cabeçalho `Retry-After` indicando os segundos até a liberação.

3. **Validação Estrita de Uploads e Digitalização:**
   - Prevenção contra Directory Traversal (nomes com `/`, `\`, byte nulo, ou iguais a `.`/`..` rejeitados com `400 Bad Request`). O nome mostrado no lote é o original (acentos e espaços preservados); o nome gravado em disco é saneado.
   - Limite rígido de 10 MB por arquivo e 50 MB por lote (`413 Payload Too Large`).
   - Validação de formato real via magic bytes (PDF `%PDF`, PNG `\x89PNG`, JPEG `\xff\xd8\xff`, Markdown UTF-8 sem bytes nulos; rejeição com `415 Unsupported Media Type`).

4. **Integridade de Avaliações e Escapamento de Canais:**
   - Validação obrigatória de `resposta_id` não-vazio antes de registrar e responder `201 Created` em `/api/avaliacoes` (rejeição com `400`/`422`).
   - Sanitização com `_esc()` nos textos de fallback e notificações do Slack para evitar quebras de marcação `mrkdwn`.

---

## Endpoints da API e Conformidade com o Frontend

Todos os endpoints operam em JSON UTF-8 com suporte a CORS para `http://localhost:5173`.

| Método | Endpoint | Descrição | Consumido no Frontend | Status |
|---|---|---|---|---|
| `GET` | `/api/saude` | Status da API, total de documentos, status de IA, contagem de fichas e autenticação | `fetchSaude()` | ✓ Conforme |
| `GET` | `/api/documentos` | Catálogo completo (vigentes e substituídos), com filtro `?serie=` | `fetchDocumentos()` | ✓ Conforme |
| `GET` | `/api/documentos/{codigo}` | Detalhes e seções estruturadas (suporta `?versao=`) | `fetchDocumentoDetalhe()` | ✓ Conforme |
| `GET` | `/api/documentos/{codigo}/ficha` | Ficha estruturada por regra (C22, F-07): identidade, mesa, semáforo, BLUF, ações, mapa de calor e alertas | `fetchFicha()` | ✓ Conforme |
| `GET` | `/api/ficha/triagem` | Fila e lista de atenção para triagem (C25, F-18): chips, semáforo, próximo prazo, sinais e urgência | `fetchTriagem()` | ✓ Conforme |
| `POST` | `/api/perguntar` | Respostas ancoradas com perfil, citações, avisos e camada | `postPerguntar()` | ✓ Conforme |
| `GET` | `/api/codigo/{codigo}` | Decodificador de código taxonômico conforme catálogo | `fetchCodigo()` | ✓ Conforme |
| `GET` | `/api/perspectivas` | Lista das 4 perspectivas analíticas homologadas | `fetchPerspectivas()` | ✓ Conforme |
| `GET` | `/api/perspectivas/{id}` | Painel analítico com destaques, valores, prazos e riscos | `fetchPerspectivaDetalhe()` | ✓ Conforme |
| `GET` | `/api/grafo` | Grafo de interligação de normas com nós ausentes sinalizados | `fetchGrafo()` | ✓ Conforme |
| `GET` | `/api/comparar` | Comparador estruturado seção a seção entre versões | `fetchComparar()` | ✓ Conforme |
| `GET` | `/api/relatorio` | Relatório executivo consolidado por perspectiva ou documento | `fetchRelatorio()` | ✓ Conforme |
| `GET` | `/api/radar` | Radar determinístico de divergências e referências ausentes | `fetchRadar()` | ✓ Conforme |
| `GET` | `/api/regras` | Catálogo de regras paramétricas para simulação | `fetchRegras()` | ✓ Conforme |
| `POST` | `/api/simular` | Simulador de cenários "E se?" com marcos e impactos | `postSimular()` | ✓ Conforme |
| `POST` | `/api/avaliacoes` | Registro de feedback útil/não-útil por canal | `avaliacoesApi` | ✓ Conforme |
| `GET` | `/api/avaliacoes/resumo` | Métricas consolidadas de avaliações por canal | `avaliacoesApi` | ✓ Conforme |

---

## Roteiro das 5 Cenas do Pitch

1. **Cena 1 (Pessoas · Armadilha de Versão):** Pergunta sobre antecedência mínima de férias retorna 45 dias da versão vigente `NG_111 v3.0.0` com aviso explícito de que a `v2.0.0` (30 dias) foi substituída.
2. **Cena 2 (Financeiro · Multa do Coworking):** Painel financeiro destaca o valor global de R$ 18.250,00 e a multa de R$ 912,50 no Apêndice B do `CTR_2026-012`, além do alerta de que a `NG_012` é citada mas não consta no acervo.
3. **Cena 3 (O Que Mudou · Linha do Tempo):** Comparação entre `NG_111` v2.0.0 e v3.0.0 exibindo a alteração na seção 4.3.1 (30 para 45 dias) e o reflexo no formulário `FM_1111-001`.
4. **Cena 4 (Perguntar · Abstenção e Citações):** Consulta sobre acumulação de funções retorna abstenção segura (`consta: false`, `citacoes: []`); pergunta com resposta retorna citações com metadados de camada (`sigla`, `tipo_nome`, `grupo`).
5. **Cena 5 (Relatório Executivo e Radar):** Geração de relatório consolidado com fontes auditáveis e radar apontando divergências e lacunas sem uso de IA (100% determinístico).
