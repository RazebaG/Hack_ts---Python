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

## Inteligência (issue backend #4)
### GET /api/perspectivas
`[{"id":"juridico","nome":"Jurídico e Contratos"},{"id":"financeiro","nome":"Financeiro"},{"id":"pessoas","nome":"Pessoas (RH)"},{"id":"gestao","nome":"Gestão e Inovação"}]`
### GET /api/perspectivas/{id}
```json
{"id":"financeiro","nome":"Financeiro","destaques":[{"titulo":"Valor global do coworking","valor":"R$ 18.250,00","fonte":{"codigo":"CTR_2026-012","versao":"1.0.0","secao":"Cláusula Sétima","trecho":"…"}}],
 "valores":[{"rotulo":"Multa por inexecução","numero":912.5,"unidade":"BRL","fonte":{…}}],
 "prazos":[{"data":"2026-11-25","evento":"Último dia para vistoria","fonte":{…}}],
 "responsaveis":[{"papel":"GOC","responsabilidade":"Fiscal técnico; atesta em 5 dias úteis","fonte":{…}}],
 "riscos":[{"descricao":"…","fonte":{…}}]}
```
### GET /api/grafo
`{"nos":[{"id":"NG_111@3.0.0","codigo":"NG_111","tipo":"NG","versao":"3.0.0","substituido":false}],"arestas":[{"de":"PX_1111-001@1.0.0","para":"NG_111@3.0.0","tipo":"vinculado_a|referencia|substitui"}]}`
### GET /api/comparar?codigo=NG_111&de=2.0.0&para=3.0.0
`{"codigo":"NG_111","de":"2.0.0","para":"3.0.0","mudancas":[{"secao":"2.3","tipo":"alterado|incluido|removido","antes":"…","depois":"…"}],"resumo":["Antecedência passou de 30 para 45 dias"]}`
### GET /api/relatorio?perspectiva=juridico  (ou ?codigo=CTR_2026-012)
`{"titulo":"…","gerado_em":"…","secoes":[{"titulo":"…","itens":[{"texto":"…","fonte":{…}}]}]}`

Todo item extraído carrega `fonte` (codigo, versao, secao, trecho). Extração por regras/regex sobre o texto + revisão em `data/curadoria/*.yaml` quando a regra falhar; nunca valor sem fonte.
