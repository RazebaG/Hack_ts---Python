# Assistente do Arquivo Central de Normas (ACME)

Backend de inteligência sobre o acervo normativo da ACME para o **HACKA/TS 2026** (Desafio 2 · Team 5 Clankers).

Transforma contratos, normas e políticas em decisões fundamentadas com citação auditável (`código · versão · seção · camada`), aponta contradições em radar determinístico, simula cenários "E se?" e integra-se à interface web React, Slack e Teams.

---

## Execução Local em 5 Passos

### Passo 1: Clonar os Repositórios
```bash
# Repositório do Backend (Python)
git clone https://github.com/RazebaG/Hack_ts---Python.git
cd Hack_ts---Python

# Repositório do Frontend (React / TypeScript)
git clone https://github.com/RazebaG/Hacka_ts-React.git
```

### Passo 2: Configurar as Variáveis de Ambiente
Copie o modelo `.env.example` para `.env` no backend. **Atenção:** nunca insira credenciais, chaves de acesso ou IDs de conta. O ambiente do evento utiliza perfil local seguro.

**Backend (`Hack_ts---Python/.env`):**
- `LLM_PROVIDER`: Provedor do modelo de linguagem (`nenhum` para extração direta determinística; `bedrock` para Amazon Bedrock)
- `AWS_PROFILE`: Nome do perfil de autenticação local da AWS (padrão: `hackats`)
- `AWS_REGION`: Região da AWS (padrão: `us-east-1`)
- `BEDROCK_MODEL_ID`: Modelo de texto principal (padrão: `amazon.nova-pro-v1:0`)
- `BEDROCK_FALLBACK_MODEL_ID`: Modelo de fallback rápido (padrão: `amazon.nova-lite-v1:0`)
- `BEDROCK_EMBED_MODEL_ID`: Modelo de embeddings (padrão: `us.cohere.embed-v4:0`)

**Frontend (`Hacka_ts-React/.env`):**
- `VITE_API_URL`: URL base do backend (ex: `http://localhost:8000`)

### Passo 3: Instalar as Dependências
```bash
# Backend (Python 3.10+)
cd Hack_ts---Python
pip install -r requirements.txt

# Frontend (Node.js 18+)
cd ../Hacka_ts-React
npm install
```

### Passo 4: Inicializar os Serviços
Em terminais separados:

```bash
# Terminal 1: Iniciar API FastAPI do Backend (porta 8000)
cd Hack_ts---Python
make run
# ou: uvicorn app.main:app --reload --port 8000

# Terminal 2: Iniciar Servidor de Desenvolvimento do Frontend (porta 5173)
cd Hacka_ts-React
npm run dev
```

Acesse a interface web em: `http://localhost:5173`
A documentação interativa da API estará disponível em: `http://localhost:8000/docs`

### Passo 5: Executar Testes e Smoke Integrado
```bash
# No diretório do Backend (Hack_ts---Python):
make test    # Executa a suíte de testes com pytest (110 testes)
make smoke   # Executa o smoke test ponta a ponta com acervo real e validação de CORS
make eval    # Executa a avaliação de perguntas e respostas (/api/perguntar)

# No diretório do Frontend (Hacka_ts-React):
npm test -- --run   # Executa os testes unitários e de integração do frontend
```

---

## Endpoints da API e Conformidade com o Frontend

Todos os endpoints operam em JSON UTF-8 com suporte a CORS para `http://localhost:5173`.

| Método | Endpoint | Descrição | Consumido no Frontend | Status |
|---|---|---|---|---|
| `GET` | `/api/saude` | Status da API, total de documentos e status de IA | `fetchSaude()` | ✓ Conforme |
| `GET` | `/api/documentos` | Catálogo completo (vigentes e substituídos), com filtro `?serie=` | `fetchDocumentos()` | ✓ Conforme |
| `GET` | `/api/documentos/{codigo}` | Detalhes e seções estruturadas (suporta `?versao=`) | `fetchDocumentoDetalhe()` | ✓ Conforme |
| `POST` | `/api/perguntar` | Respostas ancoradas com perfil, citações, avisos e camada | `postPerguntar()` | ✓ Conforme |
| `GET` | `/api/codigo/{codigo}` | Decodificador de código taxonômico conforme catálogo | `fetchCodigo()` | ✓ Conforme |
| `GET` | `/api/perspectivas` | Lista das 4 perspectivas analíticas homologadas | `fetchPerspectivas()` | ✓ Conforme |
| `GET` | `/api/perspectivas/{id}` | Painel analítico com destaques, valores, prazos e riscos | `fetchPerspectivaDetalhe()` | ✓ Conforme |
| `GET` | `/api/grafo` | Grafo de interligação de normas com nós ausentes sinalizados | `fetchGrafo()` | ✓ Conforme |
| `GET` | `/api/comparar` | Comparador estruturado seção a seção entre versões | `fetchComparar()` | ✓ Conforme |
| `GET` | `/api/relatorio` | Relatório executivo consolidado por perspectiva ou documento | `fetchRelatorio()` | ✓ Conforme |
| `GET` | `/api/radar` | Radar determinístico de divergências e referências ausentes | `fetchRadar()` | ✓ Conforme |
| `GET` | `/api/regras` | Catálogo de regras paramétricas para simulação | `fetchRegras()` | ✓ Conforme |
| `POST` | `/api/simular` | Simulador de cenários "E se?" com marcos e impactos | `postSimular()` | ✓ Conforme |
| `POST` | `/api/avaliacoes` | Registro de feedback útil/não-útil por canal | `avaliacoesApi` | ✓ Conforme |
| `GET` | `/api/avaliacoes/resumo` | Métricas consolidadas de avaliações por canal | `avaliacoesApi` | ✓ Conforme |

---

## Roteiro das 5 Cenas do Pitch

1. **Cena 1 (Pessoas · Armadilha de Versão):** Pergunta sobre antecedência mínima de férias retorna 45 dias da versão vigente `NG_111 v3.0.0` com aviso explícito de que a `v2.0.0` (30 dias) foi substituída.
2. **Cena 2 (Financeiro · Multa do Coworking):** Painel financeiro destaca o valor global de R$ 18.250,00 e a multa de R$ 912,50 no Apêndice B do `CTR_2026-012`, além do alerta de que a `NG_012` é citada mas não consta no acervo.
3. **Cena 3 (O Que Mudou · Linha do Tempo):** Comparação entre `NG_111` v2.0.0 e v3.0.0 exibindo a alteração na seção 4.3.1 (30 para 45 dias) e o reflexo no formulário `FM_1111-001`.
4. **Cena 4 (Perguntar · Abstenção e Citações):** Consulta sobre acumulação de funções retorna abstenção segura (`consta: false`, `citacoes: []`); pergunta com resposta retorna citações com metadados de camada (`sigla`, `tipo_nome`, `grupo`).
5. **Cena 5 (Relatório Executivo e Radar):** Geração de relatório consolidado com fontes auditáveis e radar apontando divergências e lacunas sem uso de IA (100% determinístico).
