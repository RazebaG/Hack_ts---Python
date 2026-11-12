# Hack_ts---Python
O back-end da aplicação.

## Canais (Slack) — issue #9

Camada comum em `app/canais/`: `cartao.py` monta o cartão neutro (conclusão, até 3 citações com selo `SIGLA · Grupo`, avisos, próxima ação, link do painel, botões Útil/Não útil) a partir da resposta da API; `slack.py` só traduz o cartão para Block Kit. O bot consome apenas a API (`API_URL`).

1. Crie o app no workspace de teste a partir de `app/canais/slack_manifest.yaml` (Socket Mode, comando `/acervo`).
2. Gere um App-Level Token com `connections:write` e instale o app no workspace.
3. `cp .env.example .env` e preencha `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `API_URL`, `PAINEL_URL` (o `.env` não vai para o repositório).
4. Suba a API (`uvicorn app.main:app`) e o bot (`python -m app.canais.slack`).

Uso: `/acervo <pergunta>` ou `/acervo radar [tema]` (o radar depende de `GET /api/radar`, issue #7).
