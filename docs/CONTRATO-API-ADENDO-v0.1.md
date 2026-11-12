# Adendo v0.1 ao CONTRATO-API.md (Lead aprovou 12/11/2026)

Aplicar nos dois repos (`RazebaG/Hack_ts---Python` e `RazebaG/Hacka_ts-React`) no mesmo commit lógico, **antes** de implementar BE #4 e de fechar mocks FE #1/#3. Aditivo; não quebra v0.

## A) Âncora de seção
`secao` em `citacoes[]` e em todo `fonte` é **exatamente** o `secoes[].id` de `GET /api/documentos/{codigo}?versao=`.
O exemplo "Cláusula Sétima" do contrato passa a ser o id real gerado pela #1 (hoje tipicamente `"CLÁUSULA SÉTIMA"`).
Teste: para todo item, `fonte.secao ∈ secoes[].id` do documento/versão.

## B) Prazos com marco e cenário
`prazos[]` ganha:
- `marco` opcional (`"D-45"` … ou `null`)
- `cenario` opcional (`null` = prazo real; ex. `"Exemplo do PX_1111-001: férias a partir de 05/05/2027"`)

Datas de exemplo vêm do texto citado, **não** de cálculo do backend.

## C) Grafo e documentos ausentes
`/api/grafo` `nos[]` ganha `existe_no_acervo` (bool). Referências a documentos ausentes (NG_012, NG_010) aparecem como nó com `existe_no_acervo=false`, sem versão (`id` = código).

## D) Erros
404 `{"detail":"…"}` para código/versão/perspectiva inexistente.
`/api/comparar` sem os dois arquivos de versão → 404 (RG_1100 v1 fica P1 via curadoria).

## E) Aceite da multa (cena Financeiro do PRD)
Fonte da multa R$ 912,50 = **Apêndice B** do CTR_2026-012 (id de seção gerado pela #1).

## F) Destaque com versão anterior (cena 1 do PRD — armadilha 30→45) · Lead aprovou 12/11
`destaques[]` em `GET /api/perspectivas/{id}` ganha campos **opcionais**:
- `fonte_anterior`: `{codigo, versao, secao, trecho}` — passagem da versão substituída
- `aviso`: string curta (ex. `"v2 (substituída) dizia 30 dias"`)

Teste na PY#4: perspectiva `pessoas` contém destaque de antecedência **45 dias** com:
- `fonte` = NG_111 `3.0.0` seção `4.3.1` (id real da #1)
- `fonte_anterior` = NG_111 `2.0.0` seção `2.3` (id real da #1)
- `aviso` preenchido

Sem inventar formato paralelo nos mocks da FE#3.

**Fora do P0:** pergunta “só com base na v2” (sem `versao_base` em `/api/perguntar`) → **P1**.

## Espelhamento obrigatório (Forja)
Nos 2 repos, no mesmo commit lógico (ou PR imediata de docs): `docs/CONTRATO-API.md` (+ A–F) e `docs/PRD.md` (ordem de cenas do workspace Lead). Aceite narrativo da PY#4: manter marcos D-45… (item B); a **cena 1 da demo** passa a ser o destaque 45 + `fonte_anterior`, não a timeline sozinha.

## Ordem de merge (Lead)
BE: #1 → #4 → #2 → #3. FE: #1 → #3 (mock v0.1) → #2.
Gate FE#2: BE #4 e #2 na main. Decodificador pode mockar se #3 atrasar.
CATALOGO não entra no índice de `/api/perguntar`.
