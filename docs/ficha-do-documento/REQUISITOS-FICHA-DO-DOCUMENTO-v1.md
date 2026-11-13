# Ficha do Documento + Fontes em evidência: requisitos v1 (PROPOSTA · 12/11/2026)

> **Status:** proposta para a equipe aprovar. Depois de aprovada, o backend gera issues a partir do `PRD-FICHA-DO-DOCUMENTO.md` e o frontend desenha as telas a partir do `FLUXO-DE-TELAS-FICHA-v1.md`.
> **Continua:** `REQUISITOS-v3.md` (numeração segue: RF44 a RF76, RNF19 em diante, contrato C22 em diante, telas T14 em diante).
> **Origem:** insight do mentor do desafio (produto e técnica) + lacuna apontada pela equipe (o usuário não vê quais documentos foram consultados).

---

## 0. Revisão de 13/11: a experiência muda (decisão da equipe)

A primeira versão deixava o resumo numa tela secundária (a Ficha), que só se alcançava pelo catálogo ou por uma citação. A equipe pediu o oposto: **na tela inicial, o documento importante já aparece desmiuçado, com as informações precisas para decidir**, de forma intuitiva e agradável. Decisões:

1. **A T1 (início) mantém o topo atual** (título "Arquivo Central de Normas" e os 4 atalhos: Tirar Dúvida, Regras que Mudaram, Consultar Acervo, Montar Relatório) **e ganha, logo abaixo, "Documentos que pedem sua atenção"**: lista curta (3 a 5 itens) para a pessoa escolher, por perfil.
2. O documento escolhido abre ali mesmo na **Mesa de decisão** (componente `MesaDocumento`): faixa "Precisa de você", frase-resumo, mapa de posição, blocos e detalhe com o trecho exato.
3. **Os blocos mudam conforme o tipo do documento** (4 famílias, seção 2.2): um contrato não tem os mesmos blocos que uma norma.
4. Os blocos são **ordenados pelo que pesa na decisão** e cada um diz por que está ali ("1º · maior valor", "2º · vence em 13 dias").
5. O resto da T1 atual (faixa do radar, resumo por área, próximo prazo, dúvidas frequentes) **continua** abaixo da mesa.
6. A Ficha (T14) passa a ser a **versão em página inteira da mesma Mesa**, com governança completa, cobertura e alertas: reaproveita o componente, não é uma tela feita do zero.

Requisitos novos: **RF71 a RF76** (seção 5.4). RF44 a RF57 continuam valendo; onde dizem "Ficha", leia "Mesa de decisão (T1 e T14)".

---

## 1. O insight do mentor, em uma frase

Os documentos da empresa **já trazem** quem elaborou, quem aprovou, quem assinou, a classificação de segurança, a vigência e a versão. O valor que falta é **transformar um documento de 100 páginas em algo que se entende em 5 minutos**, numa interface em que a pessoa **bate o olho** e sabe: do que se trata, se está em vigor, o que exige dela, quanto custa, até quando, quem faz o quê e onde está o risco. E isso para **1.000 documentos**, não para um.

Duas consequências de produto:

1. **Não inventar o que já existe.** Governança (elaborado, aprovado, assinado, classificação, versão, vínculo) é **lida do documento**, não gerada pela IA. Aparece como selos de confiança.
2. **A IA entra onde dá trabalho:** síntese, destaque do que exige decisão e priorização. Tudo com fonte verificada.

## 2. Funcionalidade 1 · Ficha do Documento ("bata o olho")

Uma tela por documento, em **três profundidades**, sem trocar de página:

| Nível | Tempo | O que a pessoa vê | Pergunta que responde |
|---|---|---|---|
| **1 · Relance** | 10 s | Identidade, selos de governança, semáforo de situação, **uma frase** (BLUF), 3 números, próximo prazo | "Do que se trata e preciso me preocupar?" |
| **2 · Decisão** | 2 min | "O que isso exige de mim": ações com prazo, responsável e consequência; pontos-chave por tema; alertas de vigência e divergência | "O que eu faço, até quando, com quem?" |
| **3 · Estudo** | 5 min+ | Mapa de calor do documento inteiro; modo apresentação (pitch do documento); leitura completa com trecho destacado; perguntas sugeridas | "Onde está o detalhe e como eu explico isso a outra pessoa?" |

### 2.1 Diferenciais (o que nos separa de um "resumidor de PDF")

| # | Diferencial | Por que importa | Prioridade | Esforço |
|---|---|---|---|---|
| D1 | **BLUF por perfil:** a mesma frase-resumo e a ênfase mudam entre Empregado, Gestor, Jurídico, Financeiro, RH e Diretoria | Responde ao que a pessoa precisa, não ao que o documento diz primeiro | P0 (frase única) · P1 (por perfil) | M |
| D2 | **Selos de governança lidos do documento** (elaborou, aprovou, assinou, classificação, versão, vínculo) | Aproveita o que a empresa já tem; zero risco de alucinação | P0 | S |
| D3 | **Mapa de calor do documento:** uma faixa horizontal que representa as 100 páginas, colorida por onde há prazo, valor, obrigação e risco; clicar leva à seção | É o "bater o olho" literal: mostra *onde* olhar sem ler | P0 | S (sem IA) |
| D4 | **"O que isso exige de mim":** lista de ações com quem, até quando e o que acontece se não fizer | Transforma resumo em decisão (a tese do desafio) | P0 | M |
| D5 | **Origem de cada afirmação:** selo "Trecho literal", "Resumo da IA" ou "Calculado", com fonte clicável; o que não se verifica é descartado | Confiança e auditoria; diferencia de chatbots | P0 | S (já temos o verificador) |
| D6 | **Cobertura declarada:** "li 47 de 47 seções; 3 pontos descartados por falta de fonte" | Honestidade sobre o que a IA fez e não fez | P0 | S |
| D7 | **Modo apresentação (pitch do documento):** 7 a 8 cartões cronometrados em 5 min, gerados a partir da própria ficha | Pedido explícito: "como se fosse um pitch do documento"; serve para reunião e comitê | P1 (P0 se sobrar tempo) | S (derivado, sem IA extra) |
| D8 | **Fila de atenção (triagem de 1.000):** lista ordenada por urgência (prazo mais próximo, divergência, vigência acabando) | Escala: ninguém abre 1.000 fichas, abre as 10 que importam hoje | P1 | M |
| D9 | **Tempo economizado:** "Documento de ~100 págs · leitura 50 min · ficha 4 min" | Métrica de valor para o pitch e para o usuário | P0 | S |
| D10 | **Delta de versão:** "o que mudou desde a v2" e "novidades desde a sua última visita" | Em acervo vivo, mudança importa mais que estoque | P1 | M (reaproveita `/api/comparar`) |
| D11 | **Linguagem simples:** alternar o texto da ficha entre "como está no documento" e "em palavras simples" | Legal design (pesquisa já feita) | P1 | S |
| D12 | **Ficha onde a pessoa já está:** `/ficha NG_111` no Slack e no Teams; exportar PDF de 1 página | Mesma ficha em qualquer canal | P1 | M |
| D13 | **Perguntas sugeridas por documento** ("Posso rescindir sem multa?") que abrem o chat já limitado àquele documento | Liga a Ficha ao Pergunte (T2) | P0 | S |

**Corte recomendado para o MVP (sobram ~8 h até o fim do evento):** D2, D3, D4 (versão simples), D5, D6, D9, D13 no P0; D1 por perfil, D7, D8, D10, D11, D12 entram se sobrar fôlego, nessa ordem (D7 primeiro: é o que mais aparece no pitch).

### 2.2 Blocos por família de documento (decisão da equipe: cada tipo tem os seus)

A **família** vem da taxonomia do catálogo (sigla e grupo, campo `camada`), **não da IA**. Cada família tem de 4 a 6 blocos; a **relevância** reordena os blocos de cada documento. Bloco sem conteúdo não aparece.

| Família | Tipos | Blocos (ordem inicial) | Prio |
|---|---|---|---|
| **Contrato e instrumento** | CTR (e NT com valor e prazo) | Quanto custa · Até quando · Quem faz o quê · Onde pode doer · Regras que valem · Falta no acervo | P0 |
| **Norma e regulamento** | NG, RG | O que muda para você · Prazos que valem · Quem faz o quê · Limites e valores · Penalidades e exceções · Versão em vigor e o que mudou · Documentos ligados | P0 |
| **Procedimento, guia e fluxo** | PX, GU, FL, FM, TB | Passo a passo em 5 linhas · Quem faz cada etapa · Prazos por etapa · Formulários e tabelas usados · Onde costuma travar · Norma de origem | P1 |
| **Nota técnica e comunicado** | NT, CT | Decisão e o porquê · Valores e alçada · Prazo e vigência · Impacto em outras normas · Documentos citados e ausentes | P1 |

Cada bloco tem: **título**, **destaque** (um número ou uma frase curta, em tamanho grande), **apoio** (até 2 linhas), **posição na relevância** com o **motivo** em palavras simples, **sinal** (valor, prazo, responsável, risco, regra), **seções do mapa** que ele acende e os **itens** com fonte que o sustentam.

**Regra de relevância (RF74):** a posição sai de uma pontuação por regra, não de opinião da IA: prazo mais próximo (maior peso), valor mais alto do documento, risco financeiro, divergência ou versão substituída, mudança recente. A IA só desempata e escreve o motivo, e o motivo precisa citar o fato ("vence em 13 dias", "maior valor do contrato").

## 3. Funcionalidade 2 · Fontes em evidência

**Lacuna:** hoje a resposta mostra chips de citação, mas a pessoa **não vê, em destaque, quais documentos foram consultados** nem se a base estava vigente. Isso enfraquece a confiança e a tese "decisão com fonte verificável".

Solução: um **Painel de Fontes** permanente ao lado (ou abaixo, no celular) de toda resposta e relatório.

- Cabeçalho da resposta: **"Respondido com 3 documentos"** + chips `NG_111 v3.0.0 · vigente`.
- Painel: cada documento consultado com código, título, versão, selo vigente/substituída, camada, quem aprovou e **os trechos usados** (seção + trecho).
- Distingue **citado** (sustenta a resposta) de **consultado e não usado** (foi recuperado mas não entrou), para a pessoa ver o que a IA olhou.
- **Escopo controlado pela pessoa:** "Perguntar só neste documento" e "Fixar documentos" (chips removíveis). Faz a ponte com a Ficha: botão "Perguntar sobre este documento" já fixa o escopo.
- Mesmo bloco ("Baseado em") em Painel por perspectiva (T3), Radar (T4), E se? (T6), Relatório (T11), e linha "Fontes consultadas" nos cartões do Slack e do Teams.

## 4. Perfis (ênfase da Ficha)

| Perfil | O que sobe para o topo |
|---|---|
| Empregado | "O que muda para mim", prazos pessoais, a quem pedir |
| Gestor | Ações com prazo, responsáveis, aprovações, alçadas |
| Jurídico | Riscos, multas, rescisão, divergências, versão em vigor |
| Financeiro | Valores, reajuste, pagamento, multas calculadas |
| RH | Direitos, prazos de pessoas, dados pessoais |
| Diretoria | BLUF, valor global, risco, decisão pendente |

## 5. Requisitos funcionais (RF44 em diante)

Prioridade: **P0** = MVP · **P1** = se sobrar tempo · **P2** = depois do evento. Tela: ver `FLUXO-DE-TELAS-FICHA-v1.md`. Contrato: `CONTRATO-API-ADENDO-v0.4.md`.

### 5.1 Ficha do Documento

| ID | Requisito | Prio | Tela | Contrato |
|---|---|---|---|---|
| RF44 | Abrir a **Ficha** de qualquer documento do acervo (e dos enviados em lote após publicar) em `/documento/:codigo/ficha`, a partir do Catálogo, do Documento (T8), do resultado de busca e de qualquer citação | P0 | T14 | C22 |
| RF45 | **Relance (nível 1):** código, título, tipo e camada, fase e vigência com contagem de dias, versão, tema, classificação de segurança, origem (acervo, enviado, digitalizado) e **semáforo de situação** (vigente · vence em 30 dias · substituída · com divergência) | P0 | T14 | C22 |
| RF46 | **Selos de governança lidos do documento:** elaborado por, aprovado por, aprovado em, assinado em, versão, vinculado a, referência. Cada selo mostra o campo e a fonte (cabeçalho). Campo ausente aparece como "não consta no documento", nunca é preenchido pela IA | P0 | T14 | C22 |
| RF47 | **BLUF:** uma frase (até 2) que diz do que se trata e o que pesa, com fonte(s) clicável(is) e selo de origem | P0 | T14 | C22 |
| RF48 | **Três números que importam** (valor, prazo e risco/multa, quando existirem), cada um com fonte | P0 | T14 | C22 |
| RF49 | **"O que isso exige de mim":** ações com quem, até quando, consequência se não cumprir e fonte; ordenadas por urgência | P0 | T14 | C22 |
| RF50 | **Pontos-chave por tema** (obrigações, prazos, valores, riscos, responsáveis, condições), cada um com fonte, selo de origem e botão "Incluir no relatório" (RF41) | P0 | T14 | C22 |
| RF51 | **Selo de origem** em todo item: "Trecho literal", "Resumo da IA" ou "Calculado". Item sem fonte verificada **não é exibido** e entra na contagem de descartados | P0 | T14 | C22 |
| RF52 | **Cobertura declarada:** seções lidas/total, itens verificados, itens descartados e modo (IA ou extrativo) | P0 | T14 | C22 |
| RF53 | **Mapa de calor** do documento: faixa com uma célula por seção, proporcional ao tamanho, colorida por tipo de sinal (prazo, valor, obrigação, risco); passar o mouse mostra a seção; clicar abre o T8 na seção. Alternável por sinal | P0 | T14 | C22 |
| RF54 | **Tempo economizado:** páginas estimadas, tempo de leitura integral e tempo da ficha | P0 | T14 | C22 |
| RF55 | **Perguntas sugeridas** (até 4) por documento; ao clicar, abre o T2 com o escopo fixado no documento (RF63) | P0 | T14 | C22 |
| RF56 | **Alertas do documento:** itens do Radar (T4) que citam este documento (versão substituída, referência ausente) e conflitos com outras fontes | P0 | T14 | C22 |
| RF57 | **Estados de geração:** `gerando` (com progresso por etapa), `parcial` (extrativo pronto, IA pendente), `pronta`, `erro` (com tentar de novo). A pessoa pode usar o relance enquanto o resto carrega | P0 | T14 | C22 |
| RF58 | **Modo apresentação:** 7 a 8 cartões navegáveis por teclado (capa, em uma frase, o que decidir, números, prazos, riscos, quem faz o quê, de onde vem), com cronômetro opcional de 5 min, tela cheia e fonte clicável em cada cartão | P1 | T16 | C24 |
| RF59 | **Visão por perfil:** o perfil escolhido reordena e enfatiza a ficha (seção 4) e ajusta o BLUF | P1 | T14 | C22 (`perfil`) |
| RF60 | **Linguagem simples:** alternar o texto entre "como está" e "em palavras simples" | P1 | T14 | C22 (`linguagem`) |
| RF61 | **Delta de versão:** "o que mudou desde a v2" no topo da ficha e "novidades desde a sua última visita" | P1 | T14, T17 | C26 |
| RF62 | **Exportar** a ficha em PDF de 1 página e **compartilhar** em Slack/Teams como cartão | P1 | T14 | C27 |

### 5.2 Fontes em evidência

| ID | Requisito | Prio | Tela | Contrato |
|---|---|---|---|---|
| RF63 | **Escopo da pergunta:** o chat aceita documentos fixados; chips removíveis; "Perguntar só neste documento" na Ficha e no T8 | P0 | T2, T14, T8 | C23 |
| RF64 | **Cabeçalho "Respondido com n documentos"** em toda resposta, com código, versão e selo vigente/substituída | P0 | T2 | C23 |
| RF65 | **Painel de Fontes:** por documento, os trechos usados (seção + trecho), camada, aprovador e vigência; clicar abre o T8 com destaque | P0 | T2 | C23 |
| RF66 | **Citado × consultado:** distinguir o que sustenta a resposta do que foi apenas recuperado | P0 | T2 | C23 |
| RF67 | **"Baseado em"** nos cabeçalhos de T3, T4, T6 e T11, e **"Fontes consultadas"** nos cartões Slack/Teams | P1 | T3, T4, T6, T11, C0 | C23 |
| RF68 | **Fonte substituída em evidência:** se um documento consultado estiver substituído, o painel destaca em âmbar e oferece "abrir a vigente" | P0 | T2 | C23 |

### 5.3 Triagem de 1.000 documentos

| ID | Requisito | Prio | Tela | Contrato |
|---|---|---|---|---|
| RF69 | **Fila de atenção:** lista de cartões compactos (BLUF curto, semáforo, próximo prazo, nº de alertas, tempo de leitura) ordenada por urgência; filtros por tema, tipo, perfil e situação; paginação | P1 | T17 | C25 |
| RF70 | **Busca e filtro por sinal:** "documentos com prazo nos próximos 30 dias", "com multa", "com divergência" | P1 | T17 | C25 |

### 5.4 Revisão 13/11: a Mesa de decisão na tela inicial

| ID | Requisito | Prio | Tela | Contrato |
|---|---|---|---|---|
| RF71 | **Tela inicial:** mantém o topo atual (título e 4 atalhos) e ganha abaixo **"Documentos que pedem sua atenção"**: de 3 a 5 chips, cada um com semáforo, código e o motivo curto ("vistoria em 13 dias"). Ordem por urgência e pelo perfil escolhido. Escolher um chip abre a Mesa embaixo, sem trocar de página | P0 | T1 | C25 (`limite`) |
| RF72 | **Mesa de decisão:** faixa "Precisa de você" (ação, quem, até quando, consequência), frase-resumo, selos de governança, mapa de posição, blocos, detalhe e campo de pergunta limitado ao documento | P0 | T1, T14 | C22 |
| RF73 | **Blocos por família** (seção 2.2), de 4 a 6 por documento, com destaque grande, apoio curto e selo de relevância | P0 (contrato e norma) · P1 (procedimento e nota técnica) | T1, T14 | C22 (`familia`, `blocos`) |
| RF74 | **Relevância com motivo:** cada bloco mostra "1º · maior valor", "2º · vence em 13 dias"; a posição é calculada por regra | P0 | T1, T14 | C22 |
| RF75 | **Mapa ↔ bloco:** escolher um bloco acende no mapa as seções de onde ele veio; passar o mouse numa seção mostra o título; escolher uma seção mostra os blocos que dependem dela | P0 | T1, T14 | C22 (`secoes_mapa`) |
| RF76 | **Detalhe com a fonte:** ao escolher um bloco, mostrar o trecho exato, a cláusula, o selo de origem e o atalho "Abrir no texto completo" (T8) | P0 | T1, T14 | C22 |

Na lista de prioridades da seção 2.1, **RF71 a RF76 entram no P0 e substituem, em tamanho, o D3/D4 isolados**: o mapa e "o que isso exige de você" passam a viver dentro da Mesa.

## 6. Requisitos não funcionais (RNF19 em diante)

| ID | Requisito |
|---|---|
| RNF19 | **Latência:** a ficha pronta abre em < 1 s a partir do cache. A geração de um documento de ~100 páginas em ≤ 90 s no p95 (meta a medir; o relance extrativo em < 3 s) |
| RNF20 | **Verificabilidade:** 100% dos itens exibidos têm fonte verificada contra o texto da seção. Sem fonte, não aparece |
| RNF21 | **Degradação:** sem IA (credencial expirada, erro), a ficha sai em modo extrativo (governança, números, prazos, mapa de calor) e declara o modo |
| RNF22 | **Escala:** o portfólio (T17) lista 1.000 fichas sem gerar nenhuma na hora: usa o cache e o relance determinístico |
| RNF23 | **Determinismo parcial:** governança, mapa de calor, números e prazos são extraídos por regra (mesmo resultado a cada leitura); só BLUF, ações e resumos usam IA |
| RNF24 | **Cache por conteúdo:** a ficha é invalidada quando muda o texto, a versão, o modelo ou a versão do prompt |
| RNF25 | **Segurança e LGPD (pós-MVP, mas desenhado agora):** a ficha herda a classificação do documento; texto de documento nunca vai para log; documento é tratado como dado não confiável (ver prompt-injection no PRD) |
| RNF26 | **Acessibilidade e celular:** funciona a 375 px, navegável por teclado, mapa de calor com alternativa em lista, contraste AA, cor nunca é o único sinal |

## 7. Critérios de aceite (os que decidem se está pronto)

1. **Relance em 10 segundos.** Dado `CTR_2026-012`, a pessoa abre a ficha e, sem rolar, identifica: contrato de locação de coworking, vigente até 29/04/2027, R$ 18.250,00 no total, aprovado pela DIRAF, classificação interna, próximo prazo (25/11/2026, vistoria).
2. **Nada sem fonte.** Dado qualquer item exibido, ao clicar na fonte abre o T8 na seção e o trecho aparece destacado. Dado um item gerado cuja citação não existe na seção, ele não aparece e a cobertura mostra "1 descartado".
3. **Governança sem IA.** Dado um documento sem "Assinada em", o selo mostra "não consta no documento" e o teste falha se a IA preencher.
4. **Mapa de calor.** Dado um documento com 60 seções, a faixa tem 60 células; a cláusula "Valor" aparece com sinal de valor; clicar leva à seção.
5. **Documento grande.** Dado o documento sintético de ~100 páginas, a ficha fica `pronta` em até 90 s, e o relance extrativo aparece antes disso.
6. **Sem IA.** Dado `LLM_PROVIDER=nenhum`, a ficha abre em modo extrativo, com o aviso, e os números e prazos corretos.
7. **Fontes em evidência.** Dada a pergunta "Qual a antecedência mínima para pedir férias?", a resposta mostra "Respondido com 2 documentos", o painel lista `NG_111 v3.0.0` (citado) e destaca o aviso de que a v2 foi substituída.
8. **Escopo.** Dado o botão "Perguntar sobre este documento" na ficha do `CTR_2026-012`, a próxima pergunta só recupera trechos desse documento.
9. **Avaliação (eval) da ficha.** Em 10 documentos, os fatos-chave de referência (valor, prazo, partes, multa) estão presentes e corretos em ≥ 90%; 0 itens sem fonte.

## 8. Métricas de sucesso (para o pitch)

- Tempo para entender um documento: **leitura integral ~50 min → ficha ~4 min** (mostrar com o documento de 100 páginas).
- **100%** dos itens com fonte verificada; **n** itens descartados declarados.
- Fatos-chave corretos nas fichas de referência (eval): meta ≥ 90%.
- Fichas no cache / total do acervo; tempo p95 de geração.

## 9. Fora de escopo (por ora)

- Edição do documento ou da ficha pela pessoa (só avaliar "útil/não útil" por bloco, RF39).
- OCR de PDF de várias páginas além do que a digitalização já faz (P1 da v2).
- Voz (ler a ficha em áudio): P2.
- RBAC por cargo na ficha (issue #22): P1 pós-MVP; a ficha só prepara o campo `classificacao`.
- Tradução e outros idiomas.

## 10. Riscos

| Risco | Efeito | Mitigação |
|---|---|---|
| Acervo atual tem só 13 documentos curtos; "100 páginas" e "1.000 documentos" não estão demonstráveis | Pitch sem prova de escala | Gerar 1 documento sintético de ~100 páginas e um lote de carga (issue F-08); a triagem de 1.000 usa só o relance determinístico |
| A curadoria atual é manual (YAML por perspectiva) e não escala | Ficha não generaliza | A ficha usa extração automática com verificação; a curadoria vira "gabarito" do eval |
| A IA omite uma ressalva ou transforma condição em regra absoluta | Decisão errada com aparência de confiável | Selo de origem, trecho literal ao lado do resumo, cobertura declarada, eval com fatos-chave |
| Tempo: ~8 h até o fim do evento | Não fecha tudo | Corte da seção 2.1; P0 mínimo definido |
| Documento com instrução maliciosa ("ignore as regras") | IA obedece o texto do documento | Prompt separa dados de instruções; saída em JSON com esquema; verificação de fonte; teste de prompt-injection |
| Credencial AWS temporária expira | Ficha cai | Modo extrativo (RNF21) e cache |

## 11. Perguntas em aberto (a equipe decide)

1. A ficha de documento **enviado em lote** é gerada ao publicar (recomendado) ou sob demanda?
2. Classificação de segurança: usar a que vem no cabeçalho (`#interna`) e mostrar como selo, sem aplicar bloqueio nesta fase. Combinado?
3. O pitch vai usar o documento sintético de 100 páginas? Se sim, quem escreve o conteúdo (o backend gera estrutura; o conteúdo precisa ser plausível)?
