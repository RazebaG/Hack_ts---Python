# Requisitos v3: delta da v2 (PROPOSTA, Planner, 12/11/2026)

**Status:** proposta. Só vale depois de aprovada pela equipe.
**Conteúdo:** **apenas** requisitos novos ou alterados em relação a `REQUISITOS-v2.md`; o que não aparece aqui continua como na v2. Telas e contrato: `FLUXO-DE-TELAS-v2.md` (§7, C13–C21).
**Entradas:**
- decisões humanas de 12/11: Slack + Teams no MVP; upload e digitalização no MVP;
- `docs/FUNCIONALIDADES-ESPERADAS.md` (8 funcionalidades);
- FE PR #6 (T10 e T11 implementados, `qa:aprovado`);
- `docs/propostas/QA-FLUXO-v2.md` (Bússola: 12 ajustar, 2 remover), já aplicado.

**Nota:** o RF38 não é usado (a linha reservada foi removida pelo QA).

## 0. O que mudou após QA-FLUXO-v2
| Item | Veredito | Mudança aplicada |
|---|---|---|
| **C1** RF42 / RF04 / RNF14 | ajustar | A subordinação segue o `Vinculado a` do cabeçalho até a NG (FL_1111-001 → PX_1111-001 → NG_111), e o chip mostra o pai direto. Aceite acrescido com o FL. O nome do tipo segue o CATÁLOGO: "FL Fluxo" (o QA escreveu "Fluxograma"). Nos canais, o chip é curto ("PX · Normativo"); o texto completo fica no T8 |
| **C2** RF17 / RF37 / T4 / C16 | **remover** | Saem o filtro de prazo do T4 e o `vigencia_ate`. Fica o tema em T3, T4, T7 e T10, e o prazo só no T3 |
| **C3** RF33 | ajustar | Timebox de 1 h para o "eco" no Agents Playground, com plano B (o mesmo Adaptive Card gerado pela C0 como prova de paridade, e o Slack ao vivo). "Abrir no painel" vai ao T2 com a pergunta; cada citação abre o T8 na seção |
| **C4** RF41 | ajustar | O aviso de fonte alterada vem da conferência no FE com `GET /api/documentos/{codigo}`, que já existe. O `POST /api/relatorio` continua opcional (P1) |
| **C5** ordem de corte | ajustar | A conta foi documentada: F2–F8 (≈ 15–22 h) + F10–F17 (≈ 15–22,5 h) ≈ **30–44 h**, o que não fecha na janela. Protegidos reduzidos; nova sequência de rebaixamento; proposta de pacote por camadas (§6) com soma |
| RF36 | ajustar | A regra 3 (semelhança) vai para P1. No MVP, sem código → "Sem tema: escolha um." |
| RF37 | ajustar | Filtros só no FE (sem parâmetros novos na API); a C16 é retirada do adendo v0.3 |
| RF17 | ajustar | A interface distingue **"versão substituída → vale a vigente"** de **"divergência entre fontes → mostramos as duas, sem escolher"**. O caso do júri está na Matriz da FLUXO-v2 (§6, item 7) |
| RF39 | ajustar | Cada clique gera 1 registro, contado por resposta (sem sobrescrever em canal compartilhado). O ciclo fecha no T1 com "Respostas avaliadas: n · úteis: n" |
| RF40 | ajustar | Mostra só perguntas do mesmo perfil; o histórico não guarda nome, e-mail nem ID (RNF16) |
| RF14 / RF15 | ajustar | O que está implementado (PR #6) fica protegido. Os **Δ novos** (T10 tema/legenda; T11 modo seleção = RF41) entram na ordem de corte como itens próprios |
| RF11 | ajustar | A NG_1130 sai do aceite. O CATÁLOGO §5 só tem faixas de 3 dígitos e não diz a série da NG_1130 (L-f) |
| RF38 | **remover** | Linha apagada; fica a nota no topo |
| Matriz, item 7 | ajustar | Opção (a) por padrão: no ACME, as divergências são de versão e de norma ausente. A opção (b) (documento sintético de teste no lote) depende da ⚖️3/L-g |
| RF43, RF34, RNF17, RF35, RF23/24, RF27–29, RNF06/09/16/18 | OK | Sem mudança |

## 1. Decisões que mudam prioridades
| Item | v2 | v3 | Motivo |
|---|---|---|---|
| ⚖️1 Slack | P0 dependente | **P0 firme** | Decisão humana de 12/11 |
| Teams | não previsto | **P0 com timebox de 1 h** (RF33); se falhar → P1 com plano B | Decisão humana de 12/11; QA C3 |
| Decisões 5 e 6 | P0 | P0, agora com envio em lote (RF35) | Funcionalidade esperada 1 |
| T10 Mapa (RF14) / T11 Relatório (RF15) | P0, primeiros do corte | **Parte implementada protegida**; os Δ novos podem ser cortados | Já implementados na FE PR #6; QA |
| ⚖️2, ⚖️3, ⚖️4 | pendentes | continuam pendentes (recomendações do ESCOPO mantidas) | — |

## 2. Requisitos funcionais alterados
| RF | Alteração | Prior. | Tela | Endpoint | Novo critério de aceite |
|---|---|---|---|---|---|
| RF04 | A citação exibe a **camada** da norma (RF42). Na web, o chip é completo; no Slack/Teams, é curto ("PX · Normativo") | P0 | todas com fonte, S1, S2 | `fonte.camada` **[novo]** | Teste de componente para PX, FM, FL, CTR e NT nas duas formas (completa e curta) |
| RF09 | (a) "Responsáveis" vira **"Responsáveis e obrigações"** (funcionalidade 3); (b) filtros de tema e prazo **no FE** (RF37); (c) "Incluir no relatório" (RF41) | P0 | T3 | `/api/perspectivas/{id}` (sem parâmetro novo) | Financeiro com tema "Locação" + "Próximos 30 dias" a partir de 12/11/2026 → mostra 25/11/2026 (vistoria, CTR_2026-012 · v1.0.0 · Apêndice C) e 30/11/2026 (início, Cláusula Segunda), sem 30/03/2027; "Obrigações" mostra o atesto em 5 dias úteis (CTR_2026-012 · Cláusula Nona) |
| RF11 | Filtro e agrupamento por **tema** (assunto + série do catálogo) e coluna "Camada" | P0 | T7 | `/api/documentos` + `tema` **[novo]** | Filtrar "Série 1 · Gente e Cultura" lista os 7 documentos de férias (5 vigentes + 2 substituídos; 6 no modo demo antes da digitalização do FL). A NG_1130 fica fora do aceite até a L-f ser resolvida |
| RF14 | **Implementado na FE PR #6 (protegido).** Δ **cortável**: filtro por tema (no FE) e legenda por camada | P0 (Δ cortável) | T10 | `/api/grafo` (sem parâmetro novo) | Δ: o filtro "Férias" mostra só NG_111, PX, FM, TB e FL; a legenda tem texto, não só cor |
| RF15 | **Implementado na FE PR #6 (protegido).** Δ: modo "Relatório da seleção" = RF41 | P0 | T11 | `/api/relatorio` (v0) | Os critérios da v2 continuam; o modo da seleção está no RF41 |
| RF17 | **Filtro de tema** (no FE); "Incluir no relatório"; a interface distingue dois casos: **versão substituída** ("Esta regra mudou. Vale a versão vigente 3.0.0.") e **divergência entre fontes vigentes** ("As fontes divergem. Mostramos as duas, sem escolher."), citando a regra de precedência do próprio acervo quando existir (PX_1111-001 · v1.0.0 · 2.2) | P0 | T4 | `/api/radar` (sem parâmetro novo) | Tema "Locação" → só o item NG_012 (CTR_2026-012 e NT_2026-018 a citam); tema "Férias" → os 2 itens de versão; sem filtro, a lista fechada da v2 não muda; os 2 itens de versão usam o texto de "versão substituída", e nenhum item do ACME usa o texto de "divergência" (opção a da Matriz) |
| RF23, RF24 | Passam a ser um caso do envio em lote (RF35): 1 arquivo = lote de 1 | P0 | T12 | `/api/lotes` **[novo]** (`POST /api/documentos` e `POST /api/digitalizacoes` continuam válidos na API) | Os aceites da v2 continuam e rodam dentro do lote |
| RF27, RF28 | ⚖️1 resolvida: **P0 firme**. A formatação passa pela camada comum (RF34). Botões "Útil" / "Não útil" (RF39) | P0 | S1 | `/api/perguntar`, `/api/radar`, `/api/avaliacoes` | Os aceites da v2 + o mesmo conteúdo do cartão do Teams (RNF17) |
| RF29 | Vale para Slack **e** Teams | P1 | S1, S2 | `/api/decisoes` | `origem` = `slack` ou `teams` |

## 3. Requisitos funcionais novos
| RF | Descrição | Perfis | Prior. | Tela | Endpoint | Regra · fonte | Critério de aceite testável |
|---|---|---|---|---|---|---|---|
| RF33 | **Teams:** agente com o Microsoft 365 Agents SDK (Python), testado no Microsoft 365 Agents Playground, sem tenant. Aceita `acervo <pergunta>`, `acervo radar [tema]` ou a pergunta direta. Resposta em Adaptive Card | todos | **P0 com timebox** | S2 | `/api/perguntar`, `/api/radar`, `/api/avaliacoes` | Mesma API do Slack; publicação no tenant da BBTS no plano de 6 meses. **Timebox: 1 h para rodar o "eco" no Agents Playground. Se não rodar, o Teams vira P1 e o pitch mostra o mesmo cartão (Adaptive Card gerado pela C0) como prova de paridade, com o Slack ao vivo.** | No Playground, "Até quando peço férias que começam em 05/05/2027?" → cartão com "21/03/2027", `NG_111 · v3.0.0 · Anexo C` com camada curta e próxima ação. **"Abrir no painel" abre o T2 com a pergunta; cada citação abre o T8 na seção.** Nenhuma credencial no código; só nomes em `.env.example`. Plano B: o teste do RF34 gera o JSON do Adaptive Card e ele é validado como Adaptive Card |
| RF34 | **Camada comum de canais:** uma função única gera o cartão neutro (conclusão, até 3 citações, avisos, próxima ação, botões), e dois adaptadores o convertem em Block Kit e Adaptive Card. Estados: respondendo, resposta, não consta, radar, avaliação registrada, API fora | todos | P0 | S1, S2 | — (módulo `canais/` no backend) | FLUXO-v2 §3 | Teste unitário: para as 18 perguntas sugeridas (v2 §2.6), os dois adaptadores produzem o mesmo texto, as mesmas citações e o mesmo link (RNF17); API fora → o mesmo texto padronizado nos dois |
| RF35 | **Envio em lote:** vários arquivos (digitais e fotos) num envio, com progresso e erro **por arquivo**, sem que o erro de um arquivo pare os demais. Fotos seguem para a revisão (T13) no mesmo fluxo | P-JUR, P-RH | P0 | T12, T13 | `POST /api/lotes`, `GET /api/lotes/{id}`, `POST /api/lotes/{id}/publicar` **[novo]** | ≤ 20 arquivos, ≤ 10 MB cada, ≤ 50 MB no total; tipos da v2 §4 | Lote com 1 .md válido, 1 .jpg, 1 .xlsx e 1 duplicado → o .md fica "classificado", o .jpg "revisar", o .xlsx em erro de tipo e o duplicado em 409, cada um com a sua mensagem; publicar leva só o .md; o .jpg publica depois do T13 |
| RF36 | **Classificação automática por tema** (assunto + série), editável antes de publicar | P-JUR, P-RH | P0 (regras 1–2); **P1 (regra 3)** | T12, T13, T7 | `GET /api/lotes/{id}` (`tema_sugerido`), `PATCH /api/lotes/{id}/arquivos/{arq}` **[novo]** | Determinística: (1) código → série pela faixa do CATÁLOGO §5 e documento pai pelo `Vinculado a` / herança de número; (2) número próprio (CTR, NT, CT) → assunto do documento em `Referência`. **Sem código → "Sem tema: escolha um."** (P1: regra 3, semelhança com limiar definido) | Um PX_1111-002 de teste → "Férias · Série 1 · Gente e Cultura", motivo "código se liga à NG_111"; NT de teste com `Referência: CTR_2026-012` → "Locação"; arquivo sem código → "Sem tema: escolha um." e publicar bloqueado até escolher; o tema editado aparece no T7 com `confirmado_por` |
| RF37 | **Filtros no FE:** tema em T3, T4, T7 e T10; **prazo só no T3** (janela a partir da data de referência, RF31). Chips removíveis; estado "Nenhum item neste filtro. Remova um filtro ou amplie o prazo." + [Limpar filtros] | todos | P0 | T3, T4, T7, T10 | Sem parâmetros novos. Exige `tema` em cada item ou documento (C17) e `data` nos prazos (já existe) | Os filtros vão para a URL (rotas profundas) | Os casos do RF09 e do RF17; abrir `/radar?tema=ferias` em outra aba mantém o filtro; o estado vazio tem botão e texto (não só ícone) |
| RF39 | **Avaliar resposta:** "Esta resposta foi útil?" Sim/Não; no "Não", motivo opcional (Fonte errada, Faltou informação, Difícil de entender, Outro + texto ≤ 200 caracteres); vale para respostas e "não consta". **Cada clique gera 1 registro**, contado por resposta. **O ciclo fecha** com o resumo no T1: "Respostas avaliadas: n · úteis: n" | todos | P0 | T2, S1, S2, T1 | `resposta_id` em `/api/perguntar` + `POST /api/avaliacoes` + `GET /api/avaliacoes/resumo` **[novo]** | Persistência em JSONL no MVP (mesma justificativa do RF22: PostgreSQL no mês 1 do plano de 6 meses). Sem ID de usuário (RNF16) | Avaliar na web, no Slack e no Teams gera 3 registros com o `canal` correto; 2 cliques na mesma resposta no mesmo canal geram 2 registros; o T1 mostra os totais atualizados; a confirmação "Obrigado. Sua avaliação ajuda a melhorar as respostas." aparece no lugar do botão; erro → "Não conseguimos registrar agora. Tente de novo em alguns segundos." |
| RF40 | **Análises anteriores semelhantes:** até 3 perguntas parecidas **do mesmo perfil**, com data e avaliação; "Reaproveitar" abre a resposta anterior e confere se a fonte mudou | todos | **P1** | T2 | `GET /api/analises/semelhantes?q=&perfil=` **[novo]** | Semelhança lexical (BM25 da BE #2) sobre o histórico; prioriza as avaliadas como úteis; o histórico não guarda nome, e-mail nem ID (RNF16) | Depois de 2 perguntas sobre prazo de férias no perfil Empregado, a 3ª no mesmo perfil mostra as duas; no perfil Gestor, não mostra; se a fonte citada estiver substituída: "A fonte desta resposta mudou desde <data>. Veja a versão vigente." |
| RF41 | **Relatório a partir de itens selecionados:** "Incluir no relatório" em respostas (T2), cartões e prazos (T3), itens do radar (T4), lado a lado (T5) e simulação (T6). Contador "Seleção (n)" no T0. O T11 no modo da seleção permite reordenar, retirar, dar título e imprimir | P-DIR, todos | P0 | T0, T2–T6, T11 | Nenhum endpoint novo: o FE compõe a partir das `fonte` dos itens e **confere cada fonte com `GET /api/documentos/{codigo}`** (já existe). `POST /api/relatorio` com `itens[]` fica opcional (P1: síntese) | A seleção fica no navegador da pessoa; a simulação entra marcada "Simulação hipotética" | Marcar 1 resposta, 1 prazo e 1 item do radar → T11 com 3 itens na ordem marcada, cada um com citação e camada; retirar 1 → 2; imprimir em até 2 páginas A4. **Ao abrir o T11, o FE confere cada fonte com GET /api/documentos/{codigo}; se a versão vigente for outra, o item recebe "Esta fonte mudou desde que foi selecionada."** Seleção vazia → "Nenhum item selecionado. Marque 'Incluir no relatório' numa resposta, painel ou radar." |
| RF42 | **Camada da norma em cada citação:** sigla, tipo, grupo do catálogo e subordinação | todos | P0 | todas com fonte, S1, S2, T8 (cabeçalho) | `fonte.camada` **[novo]** + `camada` em `/api/documentos/{codigo}` | Grupos do CATÁLOGO: NG e PX = Normativo; PP = Operacional; GU, FM, TB e FL = Apoio; RG = Programa; CT = Temporário; CTR e NT = Instrumento; DV = Residual. **Subordinação pelo `Vinculado a` do cabeçalho, seguindo a cadeia até a NG (ex.: FL_1111-001 → PX_1111-001 → NG_111). O chip mostra o pai direto.** | `PX_1111-001` → "PX Procedimento · Normativo · subordinado à NG_111"; `FM_1111-001` → "FM Formulário · Apoio · subordinado à NG_111"; **`FL_1111-001` → "FL Fluxo · Apoio · subordinado à PX_1111-001"**; `CTR_2026-012` → "CTR Contrato · Instrumento"; o T8 do FL mostra a cadeia completa "FL_1111-001 → PX_1111-001 → NG_111"; 100% das fontes com `camada` |
| RF43 | **Fluxograma interativo** do FL: o T8 de um documento FL renderiza o fluxo, com cada etapa clicável até a seção correspondente (funcionalidade 4). É o P1 que mais rende se sobrar 1–2 h | P-EMP, P-RH | **P1** | T8 | `/api/documentos/FL_1111-001` + ligação etapa → seção **[novo]** | FL_1111-001 · v1.0.0 (D-45, D-35, D-30, D-3) ↔ PX_1111-001 · v1.0.0 · 8.2/8.4/8.5/8.6 | A etapa "Empregado solicita até D-45" abre o PX_1111-001 · 8.2; todas as etapas têm fonte |

## 4. Requisitos não funcionais novos ou alterados
| RNF | Requisito | Critério testável |
|---|---|---|
| RNF09 (alterado) | Acrescentar os nomes de variável do Teams ao `.env.example` (só nomes; no Playground não há credencial). Registro de app, credenciais do Azure Bot e publicação no tenant = plano de 6 meses | Varredura de segredos verde; o Playground roda sem segredo commitado |
| RNF14 (alterado) | Citação: `CÓDIGO · vVERSÃO · Seção`. Selo de camada **completo** na web (`SIGLA Tipo · Grupo [· subordinado a X]`) e **curto** nos canais (`SIGLA · Grupo`) | Função única de formatação no FE e em `canais/`, com teste das duas formas |
| RNF16 | **Privacidade do histórico e das avaliações:** guardar só pergunta, perfil, canal, `resposta_id`, avaliação e data; nunca nome, e-mail, ID de usuário do Slack/Teams nem token. Arquivos em `data/` no `.gitignore` | Teste: o registro de uma avaliação vinda do Slack não contém o ID de usuário; o log dos bots não tem texto de usuário |
| RNF17 | **Paridade de canais:** mesma pergunta + mesmo perfil = mesmo conteúdo (conclusão, citações, avisos, próxima ação, link) na web, no Slack e no Teams. A única diferença permitida é a forma curta do selo de camada | O teste do RF34 roda as 18 perguntas sugeridas nos 2 adaptadores e compara com a resposta da API |
| RNF18 | **Desempenho do lote:** cada arquivo digital é classificado em < 5 s; o progresso por arquivo atualiza em ≤ 1 s; o lote de 20 arquivos não trava a interface; a leitura de fotos é uma por vez (RAM de 7,7 GB) | Medição local na PR com o lote de teste do RF35 |
| RNF06 (alterado) | Os canais confirmam em < 3 s ("Consultando o acervo…") também no Teams | Teste no Playground registrado na PR (ou plano B do RF33) |

## 5. Contrato: itens para o adendo v0.3 (somar aos C1–C12 da v2)
Itens C13–C21, conforme a `FLUXO-DE-TELAS-v2.md` §7, já com o QA:
- `resposta_id`;
- `POST /api/avaliacoes` + `GET /api/avaliacoes/resumo`;
- `fonte.camada` (com o pai direto);
- `tema` em documentos e nos itens (para o filtro no FE);
- `/api/lotes` (4 rotas);
- P1 `/api/analises/semelhantes`;
- `POST /api/relatorio` opcional (P1).

**A C16 (parâmetros de filtro na API e `vigencia_ate`) foi retirada.** Tudo é aditivo. Nenhum endpoint novo deve ser implementado antes da aprovação do Lead.

## 6. Esforço, corte e fatias
### 6.1 A conta não fecha (C5)
- Fatias da v2 (F2–F8): ≈ 15–22 h.
- Fatias da v3 (F10–F17): ≈ 15–22,5 h.
- Total: **≈ 30–44 h**, além das issues P0 já em andamento (BE #2–#8, FE #2, #5).
- Janela: até ~07h30 de 13/11 (inferido; EVENTO), menos 4–6 h de reserva para integração, QA, ensaio e entrega. A partir de ~12h de 12/11, isso dá **≈ 13–15 h de trabalho em sequência**. Se backend e frontend correrem em paralelo (dois fluxos do Forja), dá até ≈ 26–30 h; essa hipótese precisa ser confirmada pelo Lead.
- A lista de corte anterior só tirava itens pequenos (≈ 5–8 h) e protegia quase todo o novo. **Não fecha.**

### 6.2 Protegidos e ordem de rebaixamento
**Protegidos:**
- RF34;
- RF35 (com as regras 1–2 do RF36);
- RF39 (sem o RF40);
- RF41;
- RF42;
- a parte já implementada de RF14/RF15 (PR #6);
- os protegidos da v2: RF04, RF06, RF10, RF17–RF20 e RF24–RF26 com 1 página.

**Rebaixáveis, nesta ordem, depois dos já listados na v2 (RF25 rolagem sincronizada → PDF com várias páginas → RF29 → F8 enxuto → RF21 ⚖️2 → RF22 ⚖️4 vira fala):**
1. RF36 regra 3 (já P1);
2. RF37 parâmetros na API (fica só no FE; já aplicado);
3. Δ do T10 (tema/legenda);
4. RF33, se a timebox de 1 h falhar (C3);
5. filtro de prazo no T4 (já removido, C2).

Depois desses, se ainda não couber: RF40 e RF43 (já P1) → RF37 inteiro → T1 resumo de avaliações (RF39 fica só com o botão).

**Regra:** antes de abrir issues, somar as fatias aprovadas. O total P0 deve caber na janela menos 4–6 h de reserva.

### 6.3 Fatias (estimativas em intervalo)
| Fatia | Conteúdo | Responsável | Entrada | Estimativa | Camada |
|---|---|---|---|---|---|
| F2 | BE upload digital + modo demo `ACERVO_RESERVADOS` (v2) | Forja | BE #1 na main | 1,5–2,5 h | A |
| F3 | BE digitalização de 1 página + revisão + publicação (v2) | Forja | F2, teste Nova Pro/Tesseract | 3–5 h | A |
| F4+F14 | FE T12 (lote + tema editável) + T13 (revisão), numa fatia só | Forja | mock v0.3 | 4–6 h | A |
| F13 | BE `/api/lotes` + regras 1–2 do RF36 | Forja | F2 | 2–3 h | A |
| F10 | `canais/cartao.py` + adaptador Slack (refatorar a BE #9) | Forja | BE #2, BE #7 | 1,5–2,5 h | A |
| F12 | `fonte.camada` (com o pai direto) + chip no FE | Forja | catálogo | 1–1,5 h | A |
| F11 | Adaptador Teams + Playground, **timebox de 1 h** para o eco + até 1 h para o cartão | Forja | F10 | 1–2 h | B |
| F16 | Avaliação (`resposta_id`, `/api/avaliacoes`, resumo no T1, botões nos 3 canais) | Forja | F10 | 1,5–2 h | B |
| F17 | Seleção → relatório no FE, com conferência de fonte (RF41) | Forja | FE PR #6 na main | 2–3 h | B |
| F15 | Filtros no FE (RF37) | Forja | C17 (`tema`) | 1–1,5 h | B |
| F5, F6, F7, F8 | Decisões, alçada, Slack `/acervo`, Visão geral (v2) | Forja | ⚖️2/⚖️4; F10 | 6–10 h | C |

**Somas:**
- **Camada A** (decisões humanas 5 e 6 + base dos canais e da camada): ≈ 13–20,5 h.
- **Camada B** (Teams, avaliação, seleção, filtros): ≈ 5,5–8,5 h.
- **Camada C**: ≈ 6–10 h.

**Proposta do Planner, sem decisão:**
- se o trabalho for em sequência, só a camada A cabe, e no limite;
- com backend e frontend em paralelo, cabem A + B;
- a camada C só entra se sobrar tempo.

O Lead decide a camada e a hipótese de paralelismo.

## 7. Lacunas
- **L-e.** O Microsoft 365 Agents SDK (Python) e o Agents Playground não foram instalados nem testados. Isso agora é coberto pela timebox de 1 h e pelo plano B do RF33.
- **L-f.** O CATÁLOGO §5 só tem faixas de 3 dígitos (NG_100–NG_199). A série da NG_1130 não está explícita; a RG_1100 é da Série 11 pelo texto do CATÁLOGO. A NG_1130 fica fora dos aceites até ser confirmada.
- **L-g.** "Dados sintéticos" no slide sugere que documentos sintéticos da equipe podem ser aceitos. A ⚖️3 continua pendente. Ela decide entre a opção (a) e a (b) do item 7 da Matriz.
