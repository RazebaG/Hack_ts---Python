# PRD — Plataforma de Inteligência Empresarial (HACKA/TS 2026 · Desafio 2)

Acervo: dados sintéticos da ACME (catálogo + 13 documentos de Férias, Inovação/Ideias em Campo e Locação de coworking) em `RazebaG/Hack_ts---Python/data/acervo/`. Regulamento e critérios: `docs/EVENTO.md` do planejamento.

## Problema (texto do desafio)
Documentos extensos e dispersos; consultar exige especialista; consolidar para relatórios executivos custa tempo. Pedem: organizar, sintetizar e destacar o relevante **sob diferentes perspectivas**, com **visuais, gráficos e interação**, **respostas confiáveis** e **acesso rápido** para **decidir**.

## Proposta
Uma plataforma que transforma o acervo em **inteligência por perspectiva**, sempre rastreável até a fonte:
1. **Painéis por perspectiva** — Jurídico/Contratos, Financeiro, Pessoas (RH), Gestão/Inovação. Cada painel mostra o que importa para aquela área: prazos e marcos (linha do tempo), valores, multas e alçadas (gráficos), responsáveis (matriz), riscos e próximas datas críticas.
2. **Mapa do acervo** — grafo interativo NG → PX/FM/TB/FL, CTR ↔ NT, versões vigentes × substituídas.
3. **O que mudou** — comparação entre versões (NG_111 v2 → v3, FM_1111-001 v1 → v2, RG_1100).
4. **Pergunte ao acervo** — resposta confiável **com citação** (documento·versão·seção), só da versão vigente, e "não consta nas fontes" quando não houver evidência.
5. **Relatório executivo** — síntese de uma perspectiva ou documento pronta para apresentar (exportar/imprimir), com fontes.

Diferencial: cada número, prazo ou frase de qualquer gráfico abre a passagem exata de origem (confiança verificável) e alerta quando a fonte é uma versão substituída.

## Cena da demo (≤ 2 min dentro do pitch)
1. Abre o painel **Financeiro**: valor global do coworking R$ 18.250,00, alçada de diretor (NG_012 via NT_2026-018), multa de inexecução R$ 912,50 — clique leva ao Apêndice B do CTR_2026-012.
2. Painel **Pessoas**: linha do tempo D-45 → D-3 de férias que começam em 05/05/2027 (21/03, 31/03, 05/04, 15/04, 30/04).
3. **O que mudou** NG_111 v2 → v3.
4. Pergunta "Uma mesma pessoa pode elaborar, revisar e aprovar?" → "não consta nas fontes".
5. Gera o **relatório executivo** da perspectiva Jurídico/Contratos.

## P0 (sem isso não há demo)
- Ingestão estruturada + catálogo (backend #1); perguntas com citação e abstenção (#2); decodificador de código (#3); **extração de inteligência: prazos, valores, responsáveis, relações e diferenças entre versões (#4)**.
- Frontend: base com mock (#1); **painéis por perspectiva + mapa + o que mudou + relatório (#3)**; integração real (#2).
## P1
PostgreSQL (stack BBTS) para persistência; upload de documento novo com ingestão automática; LLM opcional (sem chave tudo funciona); acessibilidade AA.
## P2
Deploy AWS; perfis de acesso.

## Avaliação interna
`eval/perguntas.yaml` (≥ 15 perguntas das FAQs do acervo): ≥ 80% corretas com citação certa; 100% das "não consta" abstidas. Valores-chave do painel conferidos contra o texto.
