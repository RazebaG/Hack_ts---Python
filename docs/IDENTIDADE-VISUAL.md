# Identidade visual — paleta HACKA/TS Azul

Decisão da equipe em 12/11/2026. A paleta herda o azul e o rosa da marca HACKA/TS. Todas as combinações abaixo passam no contraste WCAG AA (critério de aceite do escopo).

Canvas de comparação: https://claude.ai/artifact/GoTyeJ6K4xQZ6fPHo6aLZ9

## Regras de uso

- **Azul primário** em botões, abas ativas e links de fonte.
- **Rosa** só como acento de marca (logo, destaque do pitch). Nunca para estado ou alerta.
- **Cores semânticas são fixas** em todos os perfis e telas, e nunca viram cor de marca:
  - verde = documento **vigente**
  - âmbar = simulação **hipotética** ("E se?") e citação a documento ausente
  - vermelho = **conflito** no radar de contradições
- Documento substituído usa o cinza neutro (`line` + `muted`).
- Códigos de documento (`NG_111 v3`, `CTR_2026-012`) em fonte monoespaçada.

## Tokens

| Token | Hex | Uso |
|---|---|---|
| `bg` | `#F4F7FD` | Fundo da página |
| `surface` | `#FFFFFF` | Cartões |
| `ink` | `#0D1B3D` | Texto principal |
| `muted` | `#56617A` | Texto secundário, rótulos |
| `line` | `#DCE3F0` | Bordas, selo "substituído" |
| `primary` | `#1D5FE0` | Botões, aba ativa, links de fonte |
| `on-primary` | `#FFFFFF` | Texto sobre o primário |
| `accent` | `#FF5C86` | Acento de marca |
| `on-accent` | `#3A0614` | Texto sobre o acento |
| `nav` | `#0D1B3D` | Menu lateral |
| `nav-text` | `#EEF3FF` | Texto do menu |
| `nav-active` | `#1D5FE0` | Item ativo do menu |
| `ok-fg` / `ok-bg` | `#0B6B3A` / `#E1F4E8` | Vigente |
| `warn` / `warn-fg` / `warn-bg` | `#D99100` / `#7A4F00` / `#FFF1D4` | Hipotético |
| `danger` / `danger-fg` / `danger-bg` | `#D6304F` / `#A8173A` / `#FFE5EB` | Conflito |

## Contraste conferido

| Par | Mínimo |
|---|---|
| `ink` sobre `bg` | 4,5:1 |
| `muted` sobre `surface` | 4,5:1 |
| `on-primary` sobre `primary` | 4,5:1 |
| `primary` (link) sobre `surface` | 4,5:1 |
| `nav-text` sobre `nav` | 4,5:1 |
| `ok-fg` / `warn-fg` / `danger-fg` sobre o próprio `*-bg` | 4,5:1 |
| `danger` (borda) sobre `surface` | 3:1 |
| `on-accent` sobre `accent` | 4,5:1 |

## CSS pronto para o frontend (`Hacka_ts-React`)

A versão aplicada no frontend está em `Hacka_ts-React/src/index.css` (branch `feat/tokens-cor-hackats`), com nomes semânticos `--color-*` (ex.: `--color-success-text`, `--color-warning-bg`, `--color-danger-border`, `--color-neutral-*` para substituído). O bloco abaixo é o resumo.

```css
:root {
  --bg: #F4F7FD;
  --surface: #FFFFFF;
  --ink: #0D1B3D;
  --muted: #56617A;
  --line: #DCE3F0;
  --primary: #1D5FE0;
  --on-primary: #FFFFFF;
  --accent: #FF5C86;
  --on-accent: #3A0614;
  --nav: #0D1B3D;
  --nav-text: #EEF3FF;
  --nav-active: #1D5FE0;
  --ok-fg: #0B6B3A;   --ok-bg: #E1F4E8;
  --warn: #D99100;    --warn-fg: #7A4F00;   --warn-bg: #FFF1D4;
  --danger: #D6304F;  --danger-fg: #A8173A; --danger-bg: #FFE5EB;
  --font-display: "Sora", "Segoe UI", system-ui, sans-serif;
  --font-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
```
