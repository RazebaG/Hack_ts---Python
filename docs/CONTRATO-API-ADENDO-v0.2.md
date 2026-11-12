# Adendo v0.2 ao CONTRATO-API.md (Lead aprovou a Opção A, 12/11, ~10h)

Este adendo é aditivo: não quebra a v0 nem a v0.1 (itens A–F). Todo item extraído continua com `fonte` = `{codigo, versao, secao, trecho}` e `secao` = `secoes[].id` (v0.1 A). Erros seguem a v0.1 D (404 `{"detail":"…"}`; entrada inválida → 422 do FastAPI).
Configuração só por nomes de variável: nada de token, chave ou ID de conta em código, teste, issue ou PR.

**Prioridade (Lead):**
- P0: Radar (BE #7) + `GET /api/regras` e `POST /api/simular` no cenário de férias/antecedência (BE #8).
- P1: Slack (BE #9), upload/S3 (BE #10), resumo da conversa (BE #11), simular alçada e `POST /api/decisoes`.
- Fora do MVP: documentos fictícios criados pela equipe, simulação 8%→10%, demo ao vivo começando pelo Slack.

## P0: Radar de contradições (BE #7), reutilizando a extração da #4
### GET /api/radar?perspectiva=juridico|financeiro|pessoas|gestao (opcional)
```json
{"gerado_em":"2026-11-12T15:00:00-03:00",
 "resumo":{"divergente":2,"atencao":1},
 "itens":[{"id":"versao-NG_111-antecedencia","tipo":"versao_substituida|referencia_ausente",
   "status":"divergente|atencao","severidade":"alta|media|baixa",
   "titulo":"Antecedência de férias: v2 dizia 30 dias, v3 exige 45",
   "explicacao":"A versão vigente prevalece; a 2.0.0 foi substituída.",
   "perspectivas":["pessoas"],
   "codigo_ausente":null,
   "fontes":[{"codigo":"NG_111","versao":"3.0.0","secao":"4.3.1","trecho":"…"},
             {"codigo":"NG_111","versao":"2.0.0","secao":"2.3","trecho":"…"}]}]}
```
Regras P0 (só estas):
- `versao_substituida` (`divergente`, 2 fontes): mesmo fato com valor diferente entre a vigente e a substituída.
  - NG_111 2.0.0 §2.3 × 3.0.0 §4.3.1 (30 → 45 dias).
  - FM_1111-001 1.0.0 × 2.0.0 (antecedência de 30 dias e envio ao gerente → Portal Raiz).
- `referencia_ausente` (`atencao`, ≥ 1 fonte = o trecho que cita): documento citado que não está no acervo. Caso: NG_012, base das alçadas na NT_2026-018. `codigo_ausente:"NG_012"`.

Não entram no P0: `hierarquia` (PX × NG), `alcada` e `vigencia` (P1). O radar nunca inventa conflito.

## P0: "E se?" cenário 1 (BE #8), antecedência de férias 45 → 30
### GET /api/regras
```json
[{"id":"ferias_antecedencia_dias","rotulo":"Antecedência mínima para pedir férias","valor":45,"unidade":"dias",
  "fonte":{"codigo":"NG_111","versao":"3.0.0","secao":"4.5.1","trecho":"Solicitação: até 45 dias antes."}}]
```
### POST /api/simular
Entrada: `{"regra":"ferias_antecedencia_dias","novo_valor":30,"cenario":"Exemplo NG_111 Anexo C / PX_1111-001: férias a partir de 05/05/2027"}` (`cenario` é opcional)
Saída:
```json
{"regra":"ferias_antecedencia_dias","valor_atual":45,"novo_valor":30,"unidade":"dias",
 "linha_do_tempo":[
  {"marco":"Solicitação","antes":"2027-03-21","depois":"2027-04-05","muda":true,
   "fonte":{"codigo":"NG_111","versao":"3.0.0","secao":"4.5.1","trecho":"…"}},
  {"marco":"Aviso da GGC (D-35)","antes":"2027-03-31","depois":"2027-03-31","muda":false,
   "fonte":{"codigo":"NG_111","versao":"3.0.0","secao":"4.5.3","trecho":"…"}}],
 "impactos":[
  {"tipo":"conflito_interno","descricao":"O aviso D-35 ficaria antes do fim do prazo de solicitação (D-30).",
   "fontes":[{"codigo":"NG_111","versao":"3.0.0","secao":"4.5.3","trecho":"…"}]},
  {"tipo":"revisar_documento","codigo":"PX_1111-001","versao":"1.0.0","descricao":"Cita o marco D-45",
   "fontes":[{"codigo":"PX_1111-001","versao":"1.0.0","secao":"8.2","trecho":"…"}]}],
 "resumo":["A solicitação passa para D-30 (05/04/2027 no exemplo).","O D-35 do aviso fica incompatível.","Documentos vigentes que citam 45 dias exigiriam revisão."],
 "aviso":"Simulação hipotética: não altera os documentos."}
```
- O cálculo é determinístico, sem IA. As datas partem do início de gozo do exemplo citado (05/05/2027). Os outros marcos do §4.5 não mudam, e os conflitos com eles viram `conflito_interno`.
- `revisar_documento` lista só trechos **vigentes** que citam "45 dias"/"D-45": NG_111 v3, PX_1111-001, FM_1111-001 v2, TB_1111-001 e FL_1111-001.
- Uma regra desconhecida retorna 404 e `novo_valor` fora de 1–90 retorna 422.

## P1: Mais cenários do "E se?"
`alcada_gerente_max` (NT_2026-018 Anexo F, 18.000 → 20.000: o CTR_2026-012 deixa de exigir diretor) e `multa_inexecucao_pct`. Mesmo formato, com `impactos[].tipo = "muda_aprovador"` e `antes`/`depois`.

## P1: Registro de decisão
`POST /api/decisoes` `{"item_radar","acao":"encaminhar_revisao|aceitar|descartar","responsavel","nota","origem":"web|slack"}` → registro com `id` e `registrado_em`. `GET /api/decisoes` retorna a lista. Persistência em memória + `data/decisoes.jsonl` (no `.gitignore`).

## P1: Ponte Slack (BE #9), sem endpoint novo
O bot (Bolt Python, Socket Mode) consome `/api/perguntar`, `/api/radar` e `/api/simular`. Variáveis: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `API_URL`. Se o bot cair, a API e o web continuam funcionando.

## P1: Upload e ingestão (BE #10)
`POST /api/documentos` (multipart: `arquivo` .md ou .pdf) → `{"codigo","versao","secoes":N,"origem":"upload","avisos":[]}`.
- O documento entra no catálogo, no índice, nas perspectivas e no radar.
- Duplicata retorna 409 e tipo inválido retorna 415.
- Usa S3 só se `S3_BUCKET` estiver definida; sem ela, guarda em `data/uploads/` (no `.gitignore`).
- `GET /api/documentos` ganha o campo opcional `origem` (`acervo|upload`).

## P1: Resumo da conversa (BE #11)
`POST /api/resumo-conversa` `{"mensagens":[{"papel":"usuario|assistente","texto","citacoes":[]}]}` → `{"resumo":[],"decisoes":[],"pendencias":[],"citacoes":[],"provedor":"bedrock|extrativo"}`.
- Usa o Bedrock (config da BE #6). Sem Bedrock, faz um resumo extrativo. Nunca usa xAI nem outra API paga.
- As citações do resumo precisam ser um subconjunto das citações das mensagens.

## Ordem de merge (Lead)
- BE: #1 → #4 → #2 → #3 → #6 → #7 (radar) → #8 (E se?) → P1 (#9 Slack, #10 upload, #11 resumo).
- FE: #3 → #2 → #5 (telas Radar + E se?, com mock v0.2 desde já).
