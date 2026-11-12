# Contrato da API v0 (backend Python ↔ frontend React)

Base: `http://localhost:8000` (frontend usa `VITE_API_URL`). JSON UTF-8. CORS liberado para `http://localhost:5173`.

## GET /api/saude
`{"status":"ok","documentos":13}`

## GET /api/documentos
Lista (vigentes e substituídos):
```json
[{"codigo":"NG_111","titulo":"Férias","tipo":"NG","tipo_nome":"Norma Geral","versao":"3.0.0","fase":"Vigente","vigencia":"…","vinculado_a":null,"referencia":null,"assunto":"ferias","substituido":false,"camada":{"sigla":"NG","tipo_nome":"Norma Geral","grupo":"Normativo","subordinado_a":null},"tema":{"assunto":"ferias","serie":1,"serie_nome":"Gente e Cultura","confirmado_por":"regra","observacao":null}}]
```

## GET /api/documentos/{codigo}?versao=3.0.0
Sem `versao` → a vigente. Retorna o item acima + `"secoes":[{"id":"2.1","titulo":"…","texto":"…"}]`.

## POST /api/perguntar
Entrada: `{"pergunta":"…","perfil":"empregado|gestor|ggc|gfi|gco|null"}`
Saída:
```json
{"resposta":"…","consta":true,
 "citacoes":[{"codigo":"PX_1111-001","versao":"1.0.0","secao":"Anexo D","trecho":"…","camada":{"sigla":"PX","tipo_nome":"Procedimento","grupo":"Normativo","subordinado_a":"NG_111"}}],
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

## Adendo v0.3 (C15, C17) — Camada da norma e tema

### C15: Camada em toda citação e fonte
Toda citação (`citacoes[]`) e fonte (`fonte` em perspectivas, radar e relatórios) carrega o objeto `camada`:
```json
{
  "sigla": "PX",
  "tipo_nome": "Procedimento",
  "grupo": "Normativo",
  "subordinado_a": "NG_111"
}
```
- `sigla`: Sigla do tipo documental (NG, PX, PP, GU, FM, TB, FL, RG, CT, DV, CTR, NT).
- `tipo_nome`: Nome por extenso da categoria documental (ex.: "Procedimento", "Norma Geral").
- `grupo`: Grupo derivado do catálogo:
  - `Normativo`: NG, PX
  - `Operacional`: PP
  - `Apoio`: GU, FM, TB, FL
  - `Programa`: RG
  - `Temporário`: CT
  - `Instrumento`: CTR, NT
  - `Residual`: DV
- `subordinado_a`: Código do documento pai direto pelo campo "Vinculado a" do cabeçalho (ex.: `FL_1111-001` → `"PX_1111-001"`; `PX_1111-001` → `"NG_111"`). Documentos raiz têm `null`.
- Exibições derivadas (RNF14/RF42):
  - Formato completo (web/T8/relatório): `SIGLA · Tipo · Grupo · subordinado a PAI` (ex.: `"PX · Procedimento · Normativo · subordinado a NG_111"`, `"FL · Fluxo · Apoio · subordinado a PX_1111-001"`, `"CTR · Contrato · Instrumento"`).
  - Formato curto (canais C0/Slack/Teams): `SIGLA · Grupo` (ex.: `"PX · Normativo"`, `"CTR · Instrumento"`).

### C17: Tema em documentos e itens
`/api/documentos` e `/api/documentos/{codigo}` expõem os objetos `camada` e `tema`:
```json
{
  "codigo": "NG_111",
  "titulo": "Férias",
  "camada": {
    "sigla": "NG",
    "tipo_nome": "Norma Geral",
    "grupo": "Normativo",
    "subordinado_a": null
  },
  "tema": {
    "assunto": "ferias",
    "serie": 1,
    "serie_nome": "Gente e Cultura",
    "confirmado_por": "regra",
    "observacao": null
  }
}
```
- `assunto`: Pasta / área de origem (ex.: `"ferias"`, `"inovacao"`, `"locacao"`).
- `serie`: Número da série de numeração conforme o Catálogo §5 (ex.: `1` para Gente e Cultura, `11` para Programas Institucionais). Quando o catálogo não define a série (ex.: `NG_1130` ou instrumentos `CTR`/`NT`), `serie: null` com `observacao`.
- `serie_nome`: Nome por extenso da série no catálogo (ex.: `"Gente e Cultura"`) ou `null` quando sem série.
- `confirmado_por`: `"regra"` (classificação determinística do catálogo).
- `observacao`: Detalhe textual quando `serie` não é definida pelo catálogo (ex.: `"Catálogo §5 não define explicitamente a série para NG_1130 (lacuna L-f)"`).
- Filtro por série: `GET /api/documentos?serie=1` retorna os documentos da série indicada (ex.: os 7 documentos de férias da Série 1 · Gente e Cultura: 5 vigentes + 2 substituídos).
