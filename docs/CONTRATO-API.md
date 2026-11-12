# Contrato da API v0 (backend Python ↔ frontend React)

Base: `http://localhost:8000` (frontend usa `VITE_API_URL`). JSON UTF-8. CORS liberado para `http://localhost:5173`.

## GET /api/saude
`{"status":"ok","documentos":13}`

## GET /api/documentos
Lista (vigentes e substituídos):
```json
[{"codigo":"NG_111","titulo":"Férias","tipo":"NG","tipo_nome":"Norma Geral","versao":"3.0.0","fase":"Vigente","vigencia":"…","vinculado_a":null,"referencia":null,"assunto":"ferias","substituido":false}]
```

## GET /api/documentos/{codigo}?versao=3.0.0
Sem `versao` → a vigente. Retorna o item acima + `"secoes":[{"id":"2.1","titulo":"…","texto":"…"}]`.

## POST /api/perguntar
Entrada: `{"pergunta":"…","perfil":"empregado|gestor|ggc|gfi|gco|null"}`
Saída:
```json
{"resposta":"…","consta":true,
 "citacoes":[{"codigo":"PX_1111-001","versao":"1.0.0","secao":"Anexo D","trecho":"…"}],
 "avisos":["NG_111 v2.0.0 foi substituída pela v3.0.0"]}
```
`consta=false` → `citacoes=[]` e `resposta` explica que não consta nas fontes.

## GET /api/codigo/{codigo}
`{"codigo":"PX_1111-001","tipo":"PX","tipo_nome":"Procedimento","vinculado_a":"NG_111","serie":"1","serie_nome":"Gente e Cultura","vigencia_regra":"18 meses a partir da aprovação","existe_no_acervo":true,"observacao":"…"}`

Mudança de contrato = bloqueio comentado na issue e decisão do Lead.
