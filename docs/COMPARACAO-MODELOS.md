# Comparação de Modelos no Amazon Bedrock: Nova Pro vs. Qwen 32B

**Projeto:** Assistente do Arquivo Central de Normas (ACME) · HACKA/TS 2026 · Desafio 2  
**Ambiente:** AWS Bedrock (`us-east-1`, conta do evento via perfil local `hackats`)  
**Data da Aferição:** 12/11/2026  
**Autoria:** Forja (Developer)  

---

## 1. Resumo Executivo e Recomendação

Foi realizado benchmark comparativo entre o modelo padrão primário **`amazon.nova-pro-v1:0`** e o modelo candidato **`qwen.qwen3-32b-v1:0`**, ambos operando com reserva rápida **`amazon.nova-lite-v1:0`** no endpoint de inferência Converse do Amazon Bedrock (`bedrock-runtime`).

O teste submeteu todas as **23 perguntas do dataset oficial de avaliação** (`eval/perguntas.yaml` — incluindo casos das Cenas 1, 2 e 3 do PRD, perguntas frequentes de contratos, normas e notas técnicas, e testes de abstenção rigorosa) através do fluxo completo da API `/api/perguntar`.

### Recomendação Final
> [!IMPORTANT]
> **Manter `amazon.nova-pro-v1:0` como modelo padrão principal.**  
> O modelo `qwen.qwen3-32b-v1:0` demonstrou viabilidade e excelente suporte ao português, porém o **Amazon Nova Pro** superou o candidato em previsibilidade de latência (P95 significativamente menor), concisão segundo as diretrizes de Legal Design/UX Writing e, crucialmente, **maior precisão de ancoragem** sem contaminação cruzada de contexto.

- **Modelo Padrão Primário:** `amazon.nova-pro-v1:0` (mantido inalterado).
- **Modelo de Reserva Rápida (Fallback 1):** `amazon.nova-lite-v1:0` (mantido inalterado).
- **Modelo Candidato para Reserva Secundária (Fallback 2):** `qwen.qwen3-32b-v1:0` (qualificado e compatível com a API Converse).

---

## 2. Tabela Comparativa Consolidada

A tabela a seguir consolida as métricas observadas durante a execução real contra o Amazon Bedrock (23 perguntas, acervo oficial completo):

| Métrica / Critério de Aceite | `amazon.nova-pro-v1:0` (Padrão) | `qwen.qwen3-32b-v1:0` (Candidato) | Vencedor / Observação |
|---|:---:|:---:|---|
| **Tempo Total da Requisição (Mediana)** | **1,340 s** | **1,256 s** | Qwen ligeiramente mais rápido na mediana (-6%) |
| **Tempo Total da Requisição (P95)** | **1,731 s** | **2,183 s** | **Nova Pro mais estável** (+26% mais rápido no P95) |
| **Tempo Exclusivo do LLM (Mediana)** | **0,873 s** | **0,856 s** | Praticamente idênticos |
| **Tempo Exclusivo do LLM (P95)** | **1,363 s** | **3,813 s** | **Nova Pro 2,8x mais previsível** (Qwen teve picos de quase 4s) |
| **% Citação Válida no Acervo** | **100,0%** (20/20) | **100,0%** (20/20) | Empate: ambos ancoram nos documentos recuperados |
| **% Formato Estrito `(Fonte: COD vVER, SEC)`** | **100,0%** (20/20) | **100,0%** (20/20) | Empate: 100% de conformidade com o prompt |
| **% Abstenção Correta ("Não consta")** | **100,0%** (3/3) | **100,0%** (3/3) | Empate: filtro BM25 barrou antes do LLM |
| **Quedas para Fallback** | **0** (0%) | **0** (0%) | Ambos responderam diretamente sem acionar reserva |
| **Erros na API Converse** | **0** | **0** | Suporte total de ambos na Converse API em `us-east-1` |
| **Aderência aos Rótulos de Perfil (UX Writing)** | **100,0%** (20/20) | **100,0%** (20/20) | Ambos iniciam com rótulo correto (`O que fazer:`, etc.) |
| **Média de Palavras por Resposta** | **22,4 palavras** | **28,4 palavras** | **Nova Pro é 27% mais conciso** (ideal para Legal Design) |
| **Frases Longas (> 25 palavras)** | **2** | **2** | Empate técnico |
| **Fidelidade e Filtragem de Ruído de Contexto** | **Excelente (Alta)** | **Média (Contaminação pontual)** | **Nova Pro superior**: Qwen misturou chunks em pergunta complexa |

---

## 3. Análise Qualitativa Detalhada

### 3.1. Latência e Previsibilidade
- **Mediana:** Ambos os modelos entregam respostas no endpoint `/api/perguntar` em cerca de 1,25 a 1,35 segundo total (com tempo de LLM em torno de 850 a 870 ms).
- **Percentil 95 (P95):** O `amazon.nova-pro-v1:0` manteve-se muito estável, com P95 de 1,73s (LLM: 1,36s). Já o `qwen.qwen3-32b-v1:0` exibiu picos de latência em perguntas que exigiam consolidação de múltiplos parágrafos:
  - Na pergunta `faq_ng111_abono` ("Posso converter dias de férias em abono?"), o Qwen levou **3,81s de inferência LLM** (4,25s total), enquanto o Nova Pro respondeu em **0,80s de inferência** (1,28s total).
  - Em aplicações voltadas a canais de chat síncrono (Slack e Microsoft Teams), a estabilidade de cauda do Nova Pro reduz significativamente o risco de timeouts.

### 3.2. Qualidade de Ancoragem e Isolamento de Contexto
Um achado fundamental durante o benchmark foi a capacidade de filtragem do contexto recuperado:
- Na pergunta `faq_ctr_pagamento_aluguel` (*"Até quando a GFI paga o aluguel?"*):
  - **Nova Pro:**
    > *"Valores e datas: A GFI paga o aluguel após o atesto do GCO. (Fonte: CTR_2026-012 v1.0.0, Apêndice F)"*  
    *(Foco absoluto na pergunta do aluguel do coworking).*
  - **Qwen 32B:**
    > *"Valores e datas: técnico) GFI Pagar o aluguel após o atesto. GJU Analisar os aditivos. (Fonte: CTR_2026-012 v1.0.0, Apêndice F.) A GFI paga as férias até 3 dias corridos antes do início de gozo. Os procedimentos operacionais de cada etapa estão no PX_1111-001. Os prazos aparecem em forma de quadro no TB_1111-001 e em forma de fluxo no FL_1111-001. (Fonte: NG_111 v3.0.0, item 5.)"*
  - **Diagnóstico:** O Qwen incorporou ruído de fragmento de tabela (`"técnico)"`) e, por ter recebido também trechos recuperados da norma de férias no ranking híbrido, **misturou regras de pagamento de férias na resposta sobre pagamento de aluguel**. O Nova Pro isolou estritamente o trecho correspondente ao aluguel, ignorando o ruído irrelevante.

### 3.3. Legal Design e UX Writing
- Conforme as diretrizes em `docs/requisitos/PESQUISA-LEGAL-DESIGN-UX-WRITING.md`, as respostas devem ser diretas, com foco na ação do perfil, sem frases prolixas.
- O **Nova Pro** gerou respostas com média de **22,4 palavras**, iniciando diretamente com o verbo de ação e o marco temporal.
- O **Qwen 32B** gerou respostas com média de **28,4 palavras**, tendendo a parafrasear e expandir informações acessórias desnecessárias.

### 3.4. Erros no Converse API e Degradação
- Ambos os modelos chamaram a API `converse` do `boto3` sem exceções (`ClientError`, `ValidationException` ou `AccessDeniedException`).
- Nenhuma chamada acionou a queda para o modelo de reserva rápida (`amazon.nova-lite-v1:0`) ou para a resposta extrativa.

---

## 4. Comparação Pergunta a Pergunta (Amostra Representativa)

| ID da Pergunta | Perfil | Resposta `amazon.nova-pro-v1:0` | Resposta `qwen.qwen3-32b-v1:0` |
|---|---|---|---|
| `cena_1_prazo_ferias` | empregado | *O que fazer: Solicite as férias até 21/03/2027. (Fonte: PX_1111-001 v1.0.0, Anexo D)* | *O que fazer: Peça as férias até 21/03/2027. (Fonte: PX_1111-001 v1.0.0, Anexo D)* |
| `cena_2_antecedencia_aviso` | rh | *Regra vigente: A antecedência mínima para pedir férias é de 45 dias corridos do início de gozo. (Fonte: NG_111 v3.0.0, 4.3.1) Atenção: NG_111 v2.0.0 foi substituída pela v3.0.0; FM_1111-001 v1.0.0 foi substituída pela v2.0.0.* | *Regra vigente: A antecedência mínima para pedir férias é de 45 dias corridos (Fonte: NG_111 v3.0.0, 4.3.1.). Atenção: NG_111 v2.0.0 foi substituída pela v3.0.0; FM_1111-001 v1.0.0 foi substituída pela v2.0.0.* |
| `cena_3_abstencao_mesma_pessoa` | gestor | *O acervo não trata disso. Não foram encontradas informações sobre este tema nas normas vigentes.* | *O acervo não trata disso. Não foram encontradas informações sobre este tema nas normas vigentes.* |
| `faq_ng111_fracionamento` | empregado | *O que fazer: Você pode dividir as férias em até 3 períodos. (Fonte: NG_111 v3.0.0, 4.4.1)* | *O que fazer: As férias podem ser divididas em até 3 períodos (Fonte: NG_111 v3.0.0, 4.4.1).* |
| `faq_ctr_valor` | diretoria | *Em resumo: O valor total do contrato de coworking é de R$ 18.250,00. (Fonte: CTR_2026-012 v1.0.0, Apêndice E.)* | *Em resumo: O valor total do contrato de coworking é R$ 18.250,00 (Fonte: CTR_2026-012 v1.0.0, Cláusula Sétima).* |
| `faq_ctr_multa_inexecucao` | financeiro | *Valores e datas: A multa por inexecução do coworking é de 5% do valor global. (Fonte: NT_2026-018 v1.0.0, Seção 4)* | *Valores e datas: A multa por inexecução do coworking é de 5% do valor global do contrato (Fonte: NT_2026-018 v1.0.0, 4; CTR_2026-012 v1.0.0, 8).* |
| `faq_ctr_sublocar` | juridico | *Disposição normativa: É vedado sublocar, ceder ou emprestar o espaço, no todo ou em parte. (Fonte: CTR_2026-012 v1.0.0, Cláusula Décima Sexta)* | *Disposição normativa: Não é permitida a sublocação do espaço de coworking. (Fonte: CTR_2026-012 v1.0.0, Cláusula Décima Sexta)* |
| `nt018_quem_aprova` | diretoria | *Em resumo: A DIRAF aprova a contratação do coworking. (Fonte: NT_2026-018 v1.0.0, Anexo C.)* | *Em resumo: A contratação do coworking é aprovada pela DIRAF (09/11/2026) (Fonte: NT_2026-018 v1.0.0, 12).* |
| `abstencao_alimentacao` | empregado | *O acervo não trata disso. Não foram encontradas informações sobre este tema nas normas vigentes.* | *O acervo não trata disso. Não foram encontradas informações sobre este tema nas normas vigentes.* |

---

## 5. Como Reproduzir o Benchmark

O repositório disponibiliza o utilitário [scripts/comparar_modelos.py](file:///home/adminut/orca/workspaces/Hack_ts---Python/forja-comparar-modelos/scripts/comparar_modelos.py).

### Execução Real (AWS Bedrock)
```bash
AWS_PROFILE=hackats AWS_REGION=us-east-1 python3 scripts/comparar_modelos.py
```
Para salvar os resultados brutos em JSON:
```bash
AWS_PROFILE=hackats AWS_REGION=us-east-1 python3 scripts/comparar_modelos.py --salvar-json data/benchmarks/comparacao.json
```

### Execução Simulada / Offline (Sem Rede no CI)
```bash
python3 scripts/comparar_modelos.py --simulado
```
*Garante validação completa das rotinas e estruturas de dados em pipelines de Integração Contínua sem requisições externas ou dependência de credenciais.*
