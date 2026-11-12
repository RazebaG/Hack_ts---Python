# Hack_ts---Python
O back-end da aplicação.

## Rodar a API

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q
```

## Agente do Teams (Microsoft 365 Agents SDK)

O agente fica em `app/canais/teams.py`. Ele só cuida da apresentação. Cada mensagem é enviada a
`POST /api/perguntar`, e a resposta (texto, citações, avisos, próxima ação) vira um
**Adaptive Card**. Os botões **Útil** / **Não útil** gravam em `POST /api/avaliacoes` com
`canal: teams`. O agente confirma na hora com "Consultando o acervo…" e manda o cartão na mensagem seguinte.

Mensagens aceitas (mensagem direta ao agente):

| Mensagem | O que faz |
|---|---|
| `acervo <pergunta>` ou só a pergunta | Responde com o cartão de `/api/perguntar` |
| `acervo radar [tema]` | Lista os itens de `/api/radar` filtrados pelo tema. Enquanto o endpoint não existir, manda o link do radar no painel |
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
