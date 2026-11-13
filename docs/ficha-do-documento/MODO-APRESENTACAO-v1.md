# Modo apresentação em 5 minutos, a partir da Mesa de decisão (PROPOSTA v1 · 13/11/2026)

> **Para:** frontend (telas) e backend (opcional). **Base:** `FLUXO-DE-TELAS-FICHA-v1.md` (seção 0, Mesa) e `REQUISITOS-FICHA-DO-DOCUMENTO-v1.md` (RF58). **Prioridade:** P1 (entra depois dos blocos e do mapa). **Esta tela é a que mais aparece no pitch.**
> **Regra de ouro:** a apresentação **não cria informação nova**. Todo cartão é montado com dados que já estão na ficha (`blocos`, `acoes`, `pontos`, `alertas`, `cobertura`), então herda as mesmas fontes verificadas e funciona sem IA.

---

## 1. Para que serve

Uma pessoa precisa **explicar um documento a outras em 5 minutos** (reunião, comitê, diretoria) sem montar slide. Ela aperta **"Apresentar em 5 min"** na Mesa e recebe 8 cartões em tela cheia, na ordem em que uma boa explicação acontece: o que é, o que decidir, quanto custa, até quando, onde pode dar problema, quem faz, de onde veio.

Duas funções ao mesmo tempo:
- **Para quem apresenta:** roteiro falado de cada cartão (notas do apresentador) e cronômetro.
- **Para quem assiste:** cartões limpos, com um número ou uma frase grande por vez e a fonte à vista.

## 2. Como entra e como sai

| Ação | Onde | Resultado |
|---|---|---|
| Apresentar em 5 min | Botão na Mesa (T1) e na Ficha (T14) | Abre `/documento/:codigo/apresentar` em tela cheia, no cartão 1 |
| Abrir num cartão | Link `?cartao=3` | Útil para compartilhar "vá direto aos prazos" |
| Sair | `Esc` ou botão "Sair" | Volta à Mesa/Ficha **no mesmo bloco que estava selecionado** |
| Abrir fonte | Clique em qualquer número/frase | Gaveta lateral com o trecho exato e a cláusula, **sem sair da apresentação** |

## 3. Os 8 cartões e o tempo (soma 300 s)

| # | Cartão | Tempo | O que mostra | De onde vem (campo da ficha) |
|---|---|---|---|---|
| 1 | **Capa** | 15 s | Título, código, tipo, vigência e dias restantes, selos de governança (elaborou, aprovou, classificação), semáforo | `identidade`, `governanca`, `semaforo` |
| 2 | **Em uma frase** | 30 s | O resumo de uma ou duas frases, em tamanho grande, com a fonte | `bluf` |
| 3 | **O que decidir** | 60 s | Até 3 ações: o quê, quem, até quando, o que acontece se não fizer | `acoes` (se vazio: bloco de sinal `regra` e título "O que muda para você") |
| 4 | **Números que importam** | 45 s | Até 4 destaques grandes, cada um com rótulo e fonte | `blocos[].destaque` dos blocos de sinal `valor` e `risco` (os de maior relevância) |
| 5 | **Linha do tempo** | 45 s | Prazos em ordem, com a marca "hoje" e quantos dias faltam para cada um | `pontos.prazos` + `acoes[].prazo` (bloco de sinal `prazo`) |
| 6 | **Riscos e alertas** | 45 s | Multas, vedações, divergência de versão, referência ausente | bloco de sinal `risco` + `alertas` |
| 7 | **Quem faz o quê** | 45 s | Quem é responsável por cada etapa ou obrigação | bloco de sinal `responsavel` |
| 8 | **De onde vem** | 15 s | Quantas seções foram lidas, quantos itens verificados e descartados, modo (IA ou extrativo), botão "Abrir texto completo" | `cobertura`, `modo` |

**Regra de adaptação por família:** o cartão é escolhido pelo **sinal** do bloco, não pelo título, então a mesma lógica serve para contrato, norma, procedimento e nota técnica. Se um sinal não tem bloco (por exemplo, norma sem valores), **o cartão é pulado e o tempo dele é redistribuído** proporcionalmente aos outros (a soma continua 300 s). Mínimo para existir apresentação: cartões 1, 2 e 8; abaixo disso o botão "Apresentar" fica desativado com o motivo ("Este documento ainda não tem resumo pronto").

## 4. Roteiro falado (notas do apresentador)

Cada cartão tem um texto curto para a pessoa falar, **montado por modelo de texto a partir dos mesmos dados** (sem IA). Limite de palavras = tempo × 2,5 palavras por segundo (≈ 150 palavras por minuto), ex.: 15 s → até 38 palavras; 60 s → até 150.

Exemplo para o `CTR_2026-012` (valores do exemplo `mock-apresentacao-CTR_2026-012.json`):

| Cartão | Nota do apresentador |
|---|---|
| 1 Capa | "Este é o contrato de locação do coworking, vigente até 29 de abril de 2027, faltam 168 dias. Foi elaborado pela GCO e aprovado pela DIRAF. A classificação é interna." |
| 2 Em uma frase | "Em resumo: locação de 8 estações e uma sala por 150 dias, R$ 18.250 no total. A vistoria vence em 25 de novembro e o pedido de prorrogação em 30 de março." |
| 3 O que decidir | "Três coisas: fazer a vistoria até 25 de novembro, com a GOC e a locadora; decidir a prorrogação até 30 de março; e atestar a nota todo mês em até 5 dias úteis, senão não há pagamento." |
| 4 Números | "O aluguel é R$ 3.650 por mês. A multa por inexecução é de R$ 912,50, que é 5% do valor global." |
| 5 Linha do tempo | "25 de novembro: vistoria. 30 de novembro: início. 30 de março: último dia para pedir prorrogação. 29 de abril: fim da vigência." |
| 6 Riscos | "A multa por inexecução é 5% do valor global. Sair antes do 90º dia custa um aluguel. E a norma de alçadas, a NG_012, é citada e não está no acervo." |
| 7 Quem faz | "A GOC fiscaliza e atesta. A GFI paga até o dia 8. A GCO gere o contrato." |
| 8 De onde vem | "Tudo isto foi lido das 43 seções do contrato, com fonte em cada número. Nada foi descartado." |

**Honestidade na nota:** quando o item é "Resumo da IA" ou "Calculado", a nota diz isso ("calculado sobre o valor global").

## 5. Comportamento da tela

### 5.1 Layout (1280×720)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ CTR_2026-012 · Locação de coworking          ●●●○○○○○  3 de 8      ⏱ 3:42  [Sair]│
│                                                                              │
│                         O que decidir                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ 1  Fazer a vistoria e assinar o termo de entrega                          │ │
│  │    GOC e locadora · até 25/11/2026 (13 dias)                  [Literal ▸] │ │
│  │ 2  Decidir e pedir a prorrogação, se houver interesse                     │ │
│  │    GCO · até 30/03/2027                                       [Literal ▸] │ │
│  │ 3  Atestar a nota de cada mês                                             │ │
│  │    GOC · em até 5 dias úteis · sem atesto, não há pagamento   [Literal ▸] │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│ ◀ Anterior                    Notas do apresentador (N)                  Próximo ▶ │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Uma ideia por cartão**: no máximo 4 itens, fonte em tamanho legível, número em tamanho grande (≥ 48 px no desktop).
- **Indicador de ritmo**: 8 segmentos com o tempo previsto de cada cartão; o segmento atual mostra se a pessoa está **adiantada, no ritmo ou atrasada** em relação ao relógio. Não avança sozinho.
- **Cronômetro** de 5:00 (regressivo), pausável. Fica âmbar nos últimos 60 s e vermelho em 0:00, **sem cortar a apresentação**.
- **Notas do apresentador** (tecla `N`): painel inferior só para quem apresenta (em tela compartilhada, ficam escondidas por padrão).

### 5.2 Teclado e toque

| Tecla / gesto | Ação |
|---|---|
| `→`, `Espaço`, toque à direita | Próximo cartão |
| `←`, toque à esquerda | Cartão anterior |
| `Home` / `End` | Primeiro / último |
| `1` a `8` | Ir ao cartão |
| `T` | Pausar/retomar cronômetro |
| `N` | Mostrar/ocultar notas |
| `S` | Abrir a fonte do item em foco |
| `F` | Tela cheia do navegador (se disponível; senão ocupa a janela) |
| `Esc` | Fecha a gaveta de fonte; se não houver gaveta, sai da apresentação |

### 5.3 Gaveta de fonte

Clicar num número ou frase abre, à direita, o trecho literal, a cláusula, o selo de origem (**Trecho literal**, **Resumo da IA** ou **Calculado**) e o botão "Abrir no texto completo" (T8, em nova aba). Fechar volta ao mesmo cartão.

### 5.4 Estados

| Estado | O que aparece |
|---|---|
| Ficha `gerando` ou `parcial` | Botão "Apresentar" mostra "Preparando (n de m)"; cartões 1, 5 (prazos por regra) e 8 já podem aparecer; os demais entram quando prontos |
| Ficha em modo extrativo | Cartão 8 avisa "Resumo sem IA: só o que se extrai por regra"; o cartão 2 usa a frase extrativa |
| Sem ações, sem valores etc. | Cartão correspondente é pulado (seção 3), tempo redistribuído |
| Erro de rede ao abrir a gaveta | "Não consegui abrir a fonte agora" + tentar de novo; a apresentação continua |

### 5.5 Impressão e compartilhamento

- **Exportar PDF:** o botão usa a impressão do navegador com layout próprio (`@media print`): **um cartão por página, A4 paisagem**, com a fonte impressa abaixo de cada item e as notas do apresentador opcionais (caixa de seleção). Sem endpoint (P1 do contrato C27).
- **Link:** `?cartao=N` e `?perfil=` preservados.
- **Slack e Teams** (P2): comando `/apresentar {codigo}` devolve o cartão 2 e os 3 de decisão com o botão "Abrir apresentação".

### 5.6 Celular (375 px)

Um cartão por tela, deslizar para trocar, cronômetro e indicador fixos no topo, notas em gaveta inferior, fonte em tela cheia ao tocar. Sem tela cheia do navegador obrigatória.

### 5.7 Acessibilidade

Foco visível e ordem de tabulação lógica; anúncio do cartão atual por `aria-live="polite"` ("Cartão 3 de 8: O que decidir"); contraste AA; nada depende só de cor (o ritmo tem texto "adiantado/no ritmo/atrasado"); respeitar `prefers-reduced-motion` (sem animação de troca); cronômetro com opção de ocultar.

## 6. Quem monta os cartões

**Recomendação para o MVP: o frontend monta os cartões a partir da ficha**, sem esperar o backend (o issue F-11 do PRD fica para depois). Algoritmo de montagem (cliente):

1. Entrada: `FichaDocumento` (C22, com `blocos`).
2. Para cada cartão da tabela da seção 3, escolher os dados pelo **sinal** (`blocos.filter(b => b.sinal === ...)`), respeitando a ordem de `relevancia.posicao`.
3. Truncar a no máximo 4 itens por cartão; guardar as `fontes` de cada item para a gaveta.
4. Pular cartões sem dado e redistribuir o tempo (soma 300 s, arredondando para múltiplos de 5 s).
5. Gerar as notas com os modelos de texto da seção 4 (arquivo `src/ficha/notasApresentador.ts`, testável).

O backend só precisa fornecer o endpoint `GET /api/documentos/{codigo}/apresentacao` (C24, F-11) quando houver necessidade de montar a apresentação **fora do navegador** (Slack/Teams, PDF no servidor). Nesse caso o formato é:

```
{ "codigo": "CTR_2026-012", "versao": "1.0.0", "duracao_alvo_s": 300,
  "cartoes": [ { "ordem": 1, "tipo": "capa", "titulo": "Locação de espaço de coworking", "tempo_s": 15,
                 "itens": ["..."], "notas": "texto falado", "fontes": [Fonte] } ] }
```
`itens` referencia ids existentes na ficha (`ItemFicha`/`Acao`/`Bloco`). O exemplo completo está em `mock-apresentacao-CTR_2026-012.json`.

## 7. Aceite

1. Para o `CTR_2026-012`, a apresentação tem **8 cartões** e o tempo previsto soma **300 s (± 15 s)**.
2. **Todo número, data e frase** exibidos tem fonte clicável que abre o trecho exato; nenhum cartão tem informação que não esteja na ficha.
3. Funciona **sem IA** (modo extrativo): os cartões 1, 3 a 8 aparecem; o 2 usa a frase extrativa.
4. Teclado completo (seção 5.2), sem mouse; leitor de tela anuncia o cartão atual.
5. **Norma (`NG_111`)**: o cartão 3 mostra "O que muda para você" (45 dias, antes eram 30) e o cartão 6 mostra o aviso da versão substituída; cartão sem dado é pulado e a soma segue em 300 s.
6. Exportar PDF produz **um cartão por página** em A4 paisagem, com fonte impressa.
7. Sair da apresentação volta à Mesa **no bloco que estava selecionado**.
8. Teste de unidade da montagem: para os dois mocks (contrato e norma), tempos somam 300 s e nenhum cartão fica vazio.

## 8. Entrega sugerida (frontend)

| Passo | O que | Prio |
|---|---|---|
| 1 | Montagem dos cartões a partir do mock da ficha (função pura + testes) | P1 |
| 2 | Tela cheia com 8 cartões, navegação por teclado e toque, indicador | P1 |
| 3 | Cronômetro, ritmo e notas do apresentador | P1 |
| 4 | Gaveta de fonte | P1 |
| 5 | Impressão em PDF (`@media print`) | P1 |
| 6 | Slack/Teams e perfil | P2 |

Estimativa: de **3 a 4 h** para o frontend (passos 1 a 4), sem depender de backend, porque os mocks de contrato e norma já cobrem os dados.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Apresentação parecer um slide bonito sem lastro | Toda informação vem da ficha e tem fonte à vista; cartão 8 declara cobertura e modo |
| Documento sem ações ou sem valores | Cartão pulado e tempo redistribuído; mínimo de 3 cartões |
| Nota do apresentador soar robótica | Modelos curtos, em frases diretas; a pessoa pode ocultá-las; revisão de texto com o guia de voz (`PESQUISA-LEGAL-DESIGN-UX-WRITING.md`) |
| Tempo do evento | É P1: só entra depois dos blocos e do mapa; o pitch pode usar a Mesa direto se faltar tempo |
