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

## Adendo v0.1 ao CONTRATO-API.md (Lead aprovou 12/11/2026)

Aplicar nos dois repos (`RazebaG/Hack_ts---Python` e `RazebaG/Hacka_ts-React`) no mesmo commit lógico, **antes** de implementar BE #4 e de fechar mocks FE #1/#3. Aditivo; não quebra v0.

### A) Âncora de seção
`secao` em `citacoes[]` e em todo `fonte` é **exatamente** o `secoes[].id` de `GET /api/documentos/{codigo}?versao=`.
O exemplo "Cláusula Sétima" do contrato passa a ser o id real gerado pela #1 (hoje tipicamente `"Cláusula Sétima"`).
Teste: para todo item, `fonte.secao ∈ secoes[].id` do documento/versão.

### B) Prazos com marco e cenário
`prazos[]` ganha:
- `marco` opcional (`"D-45"` … ou `null`)
- `cenario` opcional (`null` = prazo real; ex. `"Exemplo do PX_1111-001: férias a partir de 05/05/2027"`)

Datas de exemplo vêm do texto citado, **não** de cálculo do backend.

### C) Grafo e documentos ausentes
`/api/grafo` `nos[]` ganha `existe_no_acervo` (bool). Referências a documentos ausentes (NG_012, NG_010) aparecem como nó com `existe_no_acervo=false`, sem versão (`id` = código).

### D) Erros
404 `{"detail":"…"}` para código/versão/perspectiva inexistente.
`/api/comparar` sem os dois arquivos de versão → 404 (RG_1100 v1 fica P1 via curadoria).

### E) Aceite da multa (cena Financeiro do PRD)
Fonte da multa R$ 912,50 = **Apêndice B** do CTR_2026-012 (id de seção gerado pela #1).

### F) Destaque com versão anterior (cena 1 do PRD — armadilha 30→45) · Lead aprovou 12/11
`destaques[]` em `GET /api/perspectivas/{id}` ganha campos **opcionais**:
- `fonte_anterior`: `{codigo, versao, secao, trecho}` — passagem da versão substituída
- `aviso`: string curta (ex. `"v2 (substituída) dizia 30 dias"`)

Teste na PY#4: perspectiva `pessoas` contém destaque de antecedência **45 dias** com:
- `fonte` = NG_111 `3.0.0` seção `4.3.1` (id real da #1)
- `fonte_anterior` = NG_111 `2.0.0` seção `2.3` (id real da #1)
- `aviso` preenchido

Sem inventar formato paralelo nos mocks da FE#3.

**Fora do P0:** pergunta “só com base na v2” (sem `versao_base` em `/api/perguntar`) → **P1**.

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

## Adendo v0.4 (C18) — Envio em lote e digitalização (issue #10)

- `POST /api/lotes` (multipart, campo `arquivos` repetido) → 201 `{id, arquivos[], resumo}`. Até 20 arquivos, 10 MB cada, 50 MB no total (excesso do lote → 413). Tipos: `.md`, `.pdf` com texto, `.jpg`/`.png` (1 página). 1 arquivo = lote de 1.
- Cada item de `arquivos[]`: `id`, `nome`, `tipo` (`digital`|`foto`), `estado` (`classificado`, `sem_tema`, `revisar`, `publicado`, `erro`), `tema_sugerido{assunto, serie, serie_nome, confianca, motivo, rotulo}`, `tema_escolhido`, `erro{status, mensagem}` (415 tipo, 413 tamanho, 422 leitura/vazio, 409 duplicado), `documento{codigo, versao, titulo, origem}`, `texto_lido`, `linhas[{numero, texto, incerta}]`, `motor`, `revisado`, `avisos[]`. O erro de um arquivo não para os demais.
- `GET /api/lotes/{id}` → mesmo formato. `resumo.mensagem`, ex.: "3 de 4 arquivos prontos. 1 precisa da sua revisão."
- `PATCH /api/lotes/{id}/arquivos/{arq}` body `{assunto?, serie?, texto?, revisado?}`: corrige tema (`confirmado_por: "pessoa"`), texto lido (reclassifica) ou marca a revisão da foto.
- `POST /api/lotes/{id}/publicar` body opcional `{arquivos: [ids]}` → `{lote, resultados[{arquivo, nome, publicado, motivo?}]}`. Bloqueia: sem tema ("Sem tema: escolha um."), foto sem revisão, cabeçalho sem código, duplicado.
- Publicado entra em `/api/documentos` com `origem` = `upload` (digital) ou `digitalizado` (foto) e no índice de `/api/perguntar`. Documentos do acervo têm `origem: "acervo"`.
- Fotos: Bedrock Nova Pro (Converse, `BEDROCK_MODEL_OCR`, padrão `amazon.nova-pro-v1:0`; credenciais do ambiente) e Tesseract como reserva. Uma foto por vez.
