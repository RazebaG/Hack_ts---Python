# Adendo v0.4 ao CONTRATO-API.md · Ficha do Documento e Fontes em evidência (PROPOSTO · 12/11/2026)

> **Status:** C22 entregue no backend em modo extrativo determinístico (F-07, Issue #48). Soma-se a C1–C21 (v0.1 a v0.3).
> **Prefixo:** `/api`. **Erros:** mesmo formato do contrato base. **Autenticação:** quando `API_KEY` estiver ligada, cabeçalho `X-API-Key` (exceto `/api/saude`).
> **Exemplo completo:** `mock-ficha-CTR_2026-012.json` (validado contra resposta do backend).

---

## C22 · `GET /api/documentos/{codigo}/ficha`

Ficha do documento. Query: `versao` (padrão: vigente), `perfil` (`empregado|gestor|diretoria|financeiro|juridico|rh`, opcional; P1), `linguagem` (`original|simples`, padrão `original`; P1).

**Resposta `200`:** objeto `FichaDocumento`.

```
FichaDocumento {
  codigo, versao, gerada_em (ISO 8601), perfil | null, linguagem,
  estado: "gerando" | "parcial" | "pronta" | "erro",
  progresso?: { etapa: string, feito: int, total: int },        // só em "gerando"/"parcial"
  modo: { ia: "bedrock" | "extrativo", modelo: string | null },
  identidade: {
    titulo, tipo, tipo_nome, camada: Camada, tema: Tema,
    fase, substituido: bool, vigente_em?: { codigo, versao },   // se substituido
    vigencia: { texto, inicio: "AAAA-MM-DD" | null, fim: "AAAA-MM-DD" | null, dias_restantes: int | null },
    origem: "acervo" | "upload" | "digitalizado",
    classificacao: string | null,                                // ex.: "interna" (lida do cabeçalho)
    metricas: { secoes: int, palavras: int, paginas_estimadas: int, leitura_integral_min: int, leitura_ficha_min: int }
  },
  semaforo: { nivel: "ok" | "atencao" | "critico", motivos: [string] },
  governanca: {
    elaborado_por, aprovado_por, aprovado_em, assinada_em, vinculado_a, referencias: [string],
    cadeia: [string]
    // cada campo: { valor: string | null, fonte: FonteGov | null }  (valor null = "não consta no documento")
  },
  bluf: ItemFicha | null,
  numeros: [ItemFicha],                                          // até 3 (RF48)
  acoes: [Acao],                                                 // RF49, ordenadas por urgência
  pontos: {                                                      // RF50
    obrigacoes: [ItemFicha], prazos: [ItemFicha], valores: [ItemFicha],
    riscos: [ItemFicha], responsaveis: [ItemFicha], condicoes: [ItemFicha]
  },
  mapa_calor: [CelulaMapa],                                      // RF53
  alertas: [Alerta],                                             // RF56
  perguntas_sugeridas: [string],                                 // RF55, até 4
  cobertura: { secoes_lidas, secoes_total, itens_verificados, itens_descartados, motivos_descarte: [string] }  // RF52
}

ItemFicha {
  id, titulo, valor | null, texto | null,
  origem: "literal" | "resumo" | "calculado",                    // RF51
  fontes: [Fonte],                                               // >= 1 e verificadas; "calculado" lista as fontes dos operandos
  calculo?: string                                               // ex.: "5% × R$ 18.250,00 = R$ 912,50"
}

Acao {
  id, acao, quem | null, prazo: { data: "AAAA-MM-DD" | null, regra: string | null } | null,
  consequencia | null, urgencia: "alta" | "media" | "baixa", origem, fontes: [Fonte]
}

CelulaMapa {
  secao_id, titulo, ordem: int, peso: float (0..1, tamanho relativo do texto),
  sinais: { prazo: int, valor: int, obrigacao: int, risco: int },   // contagens por regra
  intensidade: float (0..1)                                          // para a cor "Tudo"
}

Alerta { tipo: "versao_substituida" | "referencia_ausente" | "divergencia" | "vigencia_proxima", titulo, explicacao, radar_id | null, fontes: [Fonte] }

FonteGov { campo: string, trecho: string }                       // cabeçalho do documento
Fonte = { codigo, versao, secao, trecho, camada }                // igual a C15
```

**Regras:**
1. Todo `ItemFicha` e `Acao` tem pelo menos uma `Fonte` cujo `trecho` consta no texto da `secao` (mesma verificação do contrato C15). Item que falha **não** é devolvido e conta em `cobertura.itens_descartados`.
2. `governanca`, `identidade.metricas`, `mapa_calor`, `numeros` de valor e prazo vêm de **extração por regra** (sem IA) e estão presentes em qualquer `modo`.
3. `estado = "gerando"`: devolve `identidade`, `governanca` e `mapa_calor` (relance extrativo) com `bluf: null`; o cliente repete a chamada a cada 3 s.
4. `estado = "parcial"`: extrativo pronto, IA pendente. `estado = "erro"`: relance extrativo + `modo.ia = "extrativo"`.
5. Resposta vem do cache em memória por hash do conteúdo; `ETag` = hash do conteúdo; requisições com `If-None-Match` correspondente recebem `304 Not Modified`.
6. `404` se o documento não existe (ou versão inexistente); `422` para `perfil` ou `linguagem` inválidos.
7. Em modo extrativo determinístico (F-07), devolve `estado = "pronta"` e `modo = { ia: "extrativo", modelo: null }`.

## C22b · `POST /api/documentos/{codigo}/ficha/regenerar`

Força nova geração. Corpo opcional `{ "versao": "1.0.0" }`. Resposta `202 { "estado": "gerando" }`. Limitado por taxa (ver RNF de segurança).

## C23 · Fontes em evidência (`/api/perguntar` ampliado)

**Pedido** (campos novos opcionais):
```
POST /api/perguntar
{ "pergunta": "...", "perfil": "gestor",
  "documentos": ["CTR_2026-012"] }          // escopo fixado pela pessoa (RF63); ausente = todo o acervo
```
**Resposta** (campos novos; os atuais não mudam):
```
{ ..., "consultados": [
    { "codigo": "CTR_2026-012", "versao": "1.0.0", "titulo": "Contrato de Locação de Espaço",
      "fase": "Vigente", "substituido": false, "vigente_em": null,
      "camada": { ... }, "aprovado_por": "DIRAF",
      "citado": true,
      "secoes_usadas": ["Cláusula Décima Terceira"],
      "relevancia": 0.91 }
  ],
  "escopo": { "fixado": true, "documentos": ["CTR_2026-012"] },
  "documentos_pesquisados": 13 }
```
**Regras:** `consultados` inclui os documentos recuperados mesmo que não citados (`citado: false`), ordenados por `citado` e `relevancia`; em abstenção (`consta: false`) continua preenchido, para mostrar "procurei em n documentos"; `documentos` inexistentes devolvem `422` com a lista dos desconhecidos. Para a resposta de documento substituído, `vigente_em` aponta a versão em vigor.

## C24 · `GET /api/documentos/{codigo}/apresentacao` (P1)

Cartões da apresentação, derivados da ficha (sem IA extra). Query: `versao`, `perfil`.
```
{ "codigo", "versao", "duracao_alvo_s": 300,
  "cartoes": [ { "ordem": 1, "tipo": "capa|frase|decidir|numeros|prazos|riscos|quem|fontes",
                 "titulo": "...", "itens": [ItemFicha | Acao], "tempo_s": 15 } ] }
```

## C25 · `GET /api/ficha/triagem` (P1)

Fila de atenção. Query: `tema`, `tipo`, `situacao` (`ok|atencao|critico`), `sinal` (`prazo_30d|multa|divergencia`), `perfil`, `ordenar` (`urgencia|vigencia|tema|tipo`), `pagina` (1), `tamanho` (50, máx. 100).
```
{ "total": 1000, "pagina": 1, "tamanho": 50, "pedem_acao": 38,
  "itens": [ { "codigo", "versao", "titulo", "tipo", "tema", "semaforo": { "nivel", "motivos" },
               "bluf_curto": "...", "proximo_prazo": { "data", "evento" } | null,
               "alertas": 2, "leitura_integral_min": 12, "leitura_ficha_min": 3, "ficha": "pronta|gerando|sem_ficha" } ] }
```
**Regra:** nunca dispara geração; usa o cache e o relance extrativo. `ficha: "sem_ficha"` indica documento ainda não processado (o cliente oferece "Gerar ficha").

## C26 · Delta de versão (P1)

`GET /api/documentos/{codigo}/ficha` ganha `delta: { de, para, resumo: [string], mudancas: int } | null`, calculado por `/api/comparar` (C-v0.1). "Novidades desde a última visita" fica no cliente (guarda a data da última visita) e usa `GET /api/ficha/triagem?alterado_desde=AAAA-MM-DD`.

## C27 · Compartilhar e exportar (P1)

- **Slack/Teams:** comando `/ficha {codigo}` usa o cartão comum (`canais/cartao.py`) com relance, 3 números, 2 ações e botão "Abrir ficha".
- **PDF:** o frontend gera pela impressão do navegador (como o T8); sem endpoint.

## Mudanças em `/api/saude`

Acrescenta `fichas: { prontas: int, total: int }` e `autenticacao: "ligada" | "desligada"`.

## Perfis e `perfil` na ficha (P1)

`perfil` não muda os dados, só a **ordem** e o texto do `bluf`/`acoes`; a lista completa de pontos continua a mesma. O cache guarda uma variante por perfil usado.

---

## Revisão 13/11: blocos por família e lista de atenção (tela inicial)

### C22 · campos novos em `FichaDocumento`

```
familia: "contrato" | "norma" | "procedimento" | "nota_tecnica",     // vem da taxonomia (camada), não da IA
blocos: [Bloco],                                                       // 4 a 6, já ordenados por relevância

Bloco {
  id, titulo,                                  // ex.: "Quanto custa", "O que muda para você"
  destaque: string,                            // número ou frase curta (tamanho grande)
  apoio: string | null,                        // até 2 linhas
  relevancia: { posicao: int, motivo: string, pontuacao: float },   // posição por regra; motivo em palavras simples e com fato
  sinal: "valor" | "prazo" | "responsavel" | "risco" | "regra" | "alerta",
  secoes_mapa: [string],                       // secao_id das seções que o bloco acende no mapa
  itens: [string],                             // ids de ItemFicha/Acao (as fontes ficam neles)
  alerta?: int                                 // índice em alertas[], quando o bloco vem do radar
}
```

- **`numeros` fica descontinuado:** o `destaque` de cada bloco o substitui. Mantido na resposta por compatibilidade até o frontend migrar.
- `blocos[].itens` referencia ids existentes em `acoes` e `pontos`: toda afirmação continua com fonte verificada (RNF20). Bloco sem item verificado não é devolvido.
- A ordem de `blocos` é a ordem de exibição; `relevancia.posicao` começa em 1.
- Pontuação de relevância (regra, ver PRD seção 3.5): prazo mais próximo, valor, risco financeiro, divergência ou versão substituída, mudança recente.

### C25 · lista de atenção da tela inicial vira P0

`GET /api/ficha/triagem?limite=5&perfil=gestor` devolve os documentos mais urgentes para o perfil, cada um com `semaforo`, `bluf_curto`, `proximo_prazo`, `motivo_curto` (ex.: "vistoria em 13 dias") e `familia`. `limite` (1 a 20, padrão 5). Só usa o cache e o relance extrativo; nunca gera ficha. Sem nenhum documento urgente: `itens: []`.

### Famílias e blocos (referência)

| `familia` | `blocos[].titulo` possíveis |
|---|---|
| `contrato` | Quanto custa · Até quando · Quem faz o quê · Onde pode doer · Regras que valem · Falta no acervo |
| `norma` | O que muda para você · Prazos que valem · Quem faz o quê · Limites e valores · Penalidades e exceções · Versão em vigor e o que mudou · Documentos ligados |
| `procedimento` (P1) | Passo a passo em 5 linhas · Quem faz cada etapa · Prazos por etapa · Formulários e tabelas usados · Onde costuma travar · Norma de origem |
| `nota_tecnica` (P1) | Decisão e o porquê · Valores e alçada · Prazo e vigência · Impacto em outras normas · Documentos citados e ausentes |