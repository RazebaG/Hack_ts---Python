# Adendo v0.3 ao CONTRATO-API.md (Lead aprovou 12/11/2026)

Este adendo detalha as necessidades C15 e C17 do backend conforme `docs/requisitos/FLUXO-DE-TELAS-v2.md` §7 e `docs/requisitos/REQUISITOS-v3.md` (issue #13).

## C15: Camada da norma em toda citação e fonte
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

## C17: Tema em documentos e itens
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
