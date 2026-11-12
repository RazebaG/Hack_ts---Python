# PRD — Plataforma de Inteligência Empresarial · Backend (escopo APROVADO pela equipe em 12/11/2026)

HACKA/TS 2026 · Desafio 2 · Team 5 Clankers. Prioridade: **MVP funcional o quanto antes**, em uso real na web, no Slack e no Teams.

## Produto
Agente de IA no **Slack e no Teams**, com **painel web**, que transforma contratos, normas e políticas em decisões fundamentadas, sempre mostrando o trecho que sustenta cada conclusão (código · versão · seção · camada). Aponta contradições, simula o impacto de mudar uma regra e aceita documentos novos (lote, foto ou scan).

## Fontes desta especificação (ler na ordem)
1. `docs/requisitos/REQUISITOS-v2.md` + `docs/requisitos/REQUISITOS-v3.md` (delta) — requisitos RF/RNF com critérios de aceite.
2. `docs/requisitos/FLUXO-DE-TELAS-v2.md` §3 (canais C0/S1/S2) e **§7 (C13–C21: o que a API precisa expor)**.
3. `docs/CONTRATO-API.md` + `docs/CONTRATO-API-ADENDO-v0.1.md` + `docs/CONTRATO-API-ADENDO-v0.2.md` (radar, regras, simular, decisões, lote, resumo).
4. `docs/requisitos/FUNCIONALIDADES-ESPERADAS.md` — as 8 funcionalidades da organização.
5. Acervo: `data/acervo/`. Regras de UX e textos: `docs/requisitos/PESQUISA-LEGAL-DESIGN-UX-WRITING.md`.

## Decisões aprovadas
- Slack (Bolt for Python, Socket Mode) e Teams (Microsoft 365 Agents SDK em Python, testado no Microsoft 365 Agents Playground, sem tenant) no MVP, ambos sobre a **mesma API** e uma camada comum de canais (`canais/cartao.py`).
- Upload em lote com classificação por tema e digitalização de foto/scan (Bedrock Nova Pro com imagem; Tesseract de reserva) no MVP, com revisão humana antes de publicar.
- "E se?": antecedência de férias 45 → 30 e alçada de gerente R$ 18.000 → 20.000, só com dados do acervo. Documentos fictícios da equipe não entram.
- IA: Amazon Bedrock da conta do evento (Nova Pro, Nova Lite, Cohere Embed v4), sempre ancorada nos trechos recuperados; sem IA, resposta extrativa.
- P1 (só depois do P0 verde): resumo da conversa, análises semelhantes, registrar decisão, fluxograma interativo.

## Ondas (ordem de entrega)
| Onda | Meta | Issues |
|---|---|---|
| 1 · Núcleo | API respondendo com fonte e camada; painéis com tema; avaliação | #1 (PR #5), #13, #2, #4, #6 |
| 2 · Diferenciais | Radar e "E se?" | #7, #8 |
| 3 · Canais | Mesma resposta no Slack e no Teams | #9, #14 |
| 4 · Entrada de documentos | Lote com tema + digitalização | #10 |
| Depois | Decodificador e P1 | #3, #11, #15, #16 |

## Regras de qualidade
Nada de número sem fonte; radar e simulação determinísticos (sem IA); credenciais só por variável de ambiente, nunca no repositório; testes simulados para Bedrock, Slack e Teams (sem rede no CI).
