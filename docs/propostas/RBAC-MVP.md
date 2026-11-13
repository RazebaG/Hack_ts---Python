# RBAC no MVP — proposta (12/11/2026)

**Status:** escopo aprovado para desenvolvimento (Issue #22).

## Por que entra (júri / critério Viabilidade + confiança)
Pergunta provável: *“E a segurança? Qualquer um vê o contrato?”*  
Resposta em 20–30 s: *“Não. O cargo define o que o retrieval devolve. Empregado não acessa CTR; Financeiro vê valores; Diretoria vê o radar completo. No MVP o cargo vem de fixture/e-mail sintético; na BBTS pluga no IdP/e-mail corporativo no plano de 6 meses.”*  
Isso vira **ponto de pitch**, não só feature escondida.

## O que muda em relação ao escopo atual
Hoje o **perfil** só muda a forma da resposta (RF01/RF02): *as fontes são as mesmas para todos*.  
Com RBAC, o **cargo** passa a **restringir o que pode ser recuperado e exibido** (documentos, seções, painéis, radar, relatório).

## Cena de 30 s (MVP)
1. Cargo **Empregado** → pergunta “qual a multa do coworking?” → não devolve CTR (sem vazamento na citação).  
2. Troca para **Financeiro** (mesmo `X-Cargo` / e-mail fixture) → mesma pergunta → R$ 912,50 + Apêndice B.  
3. Frase: *“Mesma pergunta, mesmas fontes no índice — o filtro é por cargo antes de responder.”*

## Recorte mínimo viável
1. **Papéis (roles)** alinhados aos 6 perfis já usados, com matriz cargo → tipos/assuntos permitidos (`data/rbac/matriz.yaml`).
2. **Identidade no MVP:** header `X-Cargo` / query `cargo=` **ou** e-mail de fixture `nome@acme.test` mapeado em `data/rbac/usuarios.yaml` (nunca e-mail real de pessoa). Sem login OAuth no P0.
3. **Enforcement na API** (não só no FE): `/api/perguntar`, `/api/documentos`, `/api/perspectivas/*`, `/api/radar`, `/api/grafo`, `/api/relatorio`, `/api/comparar` filtram pelo cargo. Trecho fora do escopo → *não consta nas fontes para o seu cargo* (default = ocultar do retrieval; 403 Forbidden para acesso direto a recurso não autorizado).
4. **Canais:** Slack/Teams passam o cargo do mapeamento do usuário do bot (fixture) ou do perfil escolhido no slash; mesma regra da web.
5. **Auditoria mínima:** log local (sem PII) `cargo`, `endpoint`, `negado|ok` em JSONL (`data/rbac/audit.jsonl`).

### Matriz inicial (ACME)
| Cargo | Pode ver (tema/tipo) | Não vê (exemplo) |
|---|---|---|
| empregado | Férias e Inovação geral (NG/PX/FM/TB/FL/RG vigentes) | Contratos CTR, notas técnicas de locação NT_018, alçadas orçamentárias NT_021 |
| gestor | Férias + fluxos de aprovação e gestão | Detalhe financeiro de CTR (valores/multas) |
| rh | Férias completo + versões substituídas de férias | CTR/NT de locação |
| financeiro | Locação + inovação orçamento (CTR/NT/valores) + normas gerais | Detalhes restritos de pessoas |
| juridico | Locação CTR/NT + normas gerais citadas + radar | — |
| diretoria | Tudo vigente + substituídos + radar completo | — |

## Critérios de aceite (testáveis)
- Empregado pergunta “qual a multa do coworking?” → `consta=false` com mensagem de escopo, e **nenhum** `citacoes[]` de CTR.
- Financeiro pergunta a mesma → citação CTR Apêndice B com R$ 912,50.
- `GET /api/documentos` com `cargo=empregado` **não** lista CTR_2026-012.
- Diretoria lista todos os documentos do acervo.
- Acesso direto a documento/perspectiva/radar não autorizado retorna HTTP 403 Forbidden.
- Eval: 100% sem vazamento de fonte proibida.
