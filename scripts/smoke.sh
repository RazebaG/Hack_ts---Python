#!/usr/bin/env bash
# ==============================================================================
# Script de Smoke Test da API (HACKA/TS 2026 - Issue #28)
# Valida ponta a ponta a API real com o acervo e confere os 7 casos-chave e CORS
# ==============================================================================

set -euo pipefail

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
BASE_URL="http://${API_HOST}:${API_PORT}"
PID_SERVER=""

cleanup() {
    if [ -n "${PID_SERVER}" ]; then
        echo "--> Encerrando servidor de teste (PID ${PID_SERVER})..."
        kill -TERM "${PID_SERVER}" 2>/dev/null || true
        wait "${PID_SERVER}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# 1. Verificar se a API já está em execução; caso contrário, iniciar servidor
if curl -s -f -o /dev/null "${BASE_URL}/api/saude"; then
    echo "--> API já está em execução em ${BASE_URL}"
else
    echo "--> Iniciando API local na porta ${API_PORT}..."
    export LLM_PROVIDER="${LLM_PROVIDER:-nenhum}"
    uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT}" --log-level warning &
    PID_SERVER=$!

    echo "--> Aguardando API responder..."
    READY=0
    for i in $(seq 1 30); do
        if curl -s -f -o /dev/null "${BASE_URL}/api/saude"; then
            READY=1
            break
        fi
        sleep 0.5
    done

    if [ "$READY" -ne 1 ]; then
        echo "ERRO: Servidor não respondeu dentro de 15 segundos em ${BASE_URL}" >&2
        exit 1
    fi
    echo "--> API pronta e respondendo em ${BASE_URL} (PID ${PID_SERVER})"
fi

echo "================================================================================"
echo "INICIANDO SMOKE TEST DA API (HACKA/TS 2026 - ISSUE #28)"
echo "================================================================================"

FALHAS=0

# Helper para asserção
pass() {
    echo "  ✓ PASS: $1"
}

fail() {
    echo "  ✗ FAIL: $1" >&2
    echo "    Detalhe: $2" >&2
    FALHAS=$((FALHAS + 1))
}

# ------------------------------------------------------------------------------
# Teste 0: Saúde e CORS para http://localhost:5173
# ------------------------------------------------------------------------------
echo "[0/7] Verificando /api/saude e cabeçalhos CORS..."
SAUDE_RES=$(curl -s "${BASE_URL}/api/saude")
DOC_COUNT=$(echo "${SAUDE_RES}" | jq -r '.documentos // empty')
if [ "${DOC_COUNT}" = "13" ]; then
    pass "/api/saude retornou status ok com 13 documentos"
else
    fail "/api/saude documentos inválidos" "${SAUDE_RES}"
fi

CORS_ORIGIN=$(curl -s -I -X OPTIONS "${BASE_URL}/api/perguntar" \
    -H "Origin: http://localhost:5173" \
    -H "Access-Control-Request-Method: POST" | grep -i "access-control-allow-origin" | tr -d '\r' | awk '{print $2}')
if [ "${CORS_ORIGIN}" = "http://localhost:5173" ] || [ "${CORS_ORIGIN}" = "*" ]; then
    pass "CORS configurado para http://localhost:5173"
else
    fail "CORS inválido" "Header retornado: '${CORS_ORIGIN}'"
fi

# ------------------------------------------------------------------------------
# Caso 1: Férias a partir de 05/05/2027 -> 21/03/2027 citando PX_1111-001 v1.0.0 Anexo D
# ------------------------------------------------------------------------------
echo "[1/7] Caso 1: Férias a partir de 05/05/2027 (prazo D-45 e citação PX_1111-001)..."
CASO1_PAYLOAD='{"pergunta": "Até quando peço férias que começam em 05/05/2027?", "perfil": "empregado"}'
CASO1_RES=$(curl -s -X POST "${BASE_URL}/api/perguntar" -H "Content-Type: application/json" -d "${CASO1_PAYLOAD}")

TEM_DATA=$(echo "${CASO1_RES}" | jq -r 'if .resposta | contains("21/03/2027") then "true" else "false" end')
TEM_CITACAO=$(echo "${CASO1_RES}" | jq -r 'any(.citacoes[]; .codigo == "PX_1111-001" and .versao == "1.0.0" and .secao == "Anexo D")')

if [ "${TEM_DATA}" = "true" ] && [ "${TEM_CITACAO}" = "true" ]; then
    pass "Caso 1: data 21/03/2027 confirmada citando PX_1111-001 v1.0.0 §Anexo D"
else
    fail "Caso 1 divergente" "TEM_DATA=${TEM_DATA}, TEM_CITACAO=${TEM_CITACAO}, RESPOSTA=${CASO1_RES}"
fi

# ------------------------------------------------------------------------------
# Caso 2: NG_111 v3 (45 dias) com aviso de que a v2 (30 dias) foi substituída
# ------------------------------------------------------------------------------
echo "[2/7] Caso 2: NG_111 v3 (45 dias) com aviso de substituição da v2..."
CASO2_PAYLOAD='{"pergunta": "Qual a antecedência mínima para pedir férias?", "perfil": "rh"}'
CASO2_RES=$(curl -s -X POST "${BASE_URL}/api/perguntar" -H "Content-Type: application/json" -d "${CASO2_PAYLOAD}")

TEM_45=$(echo "${CASO2_RES}" | jq -r 'if .resposta | contains("45 dias") then "true" else "false" end')
TEM_AVISO=$(echo "${CASO2_RES}" | jq -r 'any(.avisos[]; contains("NG_111 v2.0.0 foi substituída pela v3.0.0"))')
TEM_NG111=$(echo "${CASO2_RES}" | jq -r 'any(.citacoes[]; .codigo == "NG_111" and .versao == "3.0.0")')

if [ "${TEM_45}" = "true" ] && [ "${TEM_AVISO}" = "true" ] && [ "${TEM_NG111}" = "true" ]; then
    pass "Caso 2: regra vigente de 45 dias com aviso de que NG_111 v2.0.0 foi substituída pela v3.0.0"
else
    fail "Caso 2 divergente" "TEM_45=${TEM_45}, TEM_AVISO=${TEM_AVISO}, TEM_NG111=${TEM_NG111}"
fi

# ------------------------------------------------------------------------------
# Caso 3: Pergunta fora do acervo -> consta=false e citacoes=[]
# ------------------------------------------------------------------------------
echo "[3/7] Caso 3: Pergunta fora do acervo (abstenção com consta=false)..."
CASO3_PAYLOAD='{"pergunta": "Uma mesma pessoa pode elaborar, revisar e aprovar?", "perfil": "gestor"}'
CASO3_RES=$(curl -s -X POST "${BASE_URL}/api/perguntar" -H "Content-Type: application/json" -d "${CASO3_PAYLOAD}")

CONSTA=$(echo "${CASO3_RES}" | jq -r '.consta')
NUM_CITACOES=$(echo "${CASO3_RES}" | jq -r '.citacoes | length')

if [ "${CONSTA}" = "false" ] && [ "${NUM_CITACOES}" = "0" ]; then
    pass "Caso 3: abstenção correta (consta=false e citacoes=[])"
else
    fail "Caso 3 divergente" "CONSTA=${CONSTA}, NUM_CITACOES=${NUM_CITACOES}"
fi

# ------------------------------------------------------------------------------
# Caso 4: /api/perspectivas/financeiro com R$ 18.250,00 e R$ 912,50
# ------------------------------------------------------------------------------
echo "[4/7] Caso 4: Perspectiva Financeiro (R$ 18.250,00 global e R$ 912,50 multa)..."
CASO4_RES=$(curl -s "${BASE_URL}/api/perspectivas/financeiro")

TEM_VALOR_GLOBAL=$(echo "${CASO4_RES}" | jq -r 'any(.destaques[]; .valor | contains("18.250"))')
TEM_MULTA=$(echo "${CASO4_RES}" | jq -r 'any(.valores[]; .numero == 912.5)')

if [ "${TEM_VALOR_GLOBAL}" = "true" ] && [ "${TEM_MULTA}" = "true" ]; then
    pass "Caso 4: financeiro com valor global R$ 18.250,00 e multa de R$ 912,50"
else
    fail "Caso 4 divergente" "TEM_VALOR_GLOBAL=${TEM_VALOR_GLOBAL}, TEM_MULTA=${TEM_MULTA}"
fi

# ------------------------------------------------------------------------------
# Caso 5: /api/radar com os 3 casos conhecidos
# ------------------------------------------------------------------------------
echo "[5/7] Caso 5: Radar de contradições (2 divergentes, 1 atenção, 3 casos)..."
CASO5_RES=$(curl -s "${BASE_URL}/api/radar")

DIVERGENTE=$(echo "${CASO5_RES}" | jq -r '.resumo.divergente')
ATENCAO=$(echo "${CASO5_RES}" | jq -r '.resumo.atencao')
TOTAL_ITENS=$(echo "${CASO5_RES}" | jq -r '.itens | length')
TEM_NG012=$(echo "${CASO5_RES}" | jq -r 'any(.itens[]; .codigo_ausente == "NG_012")')

if [ "${DIVERGENTE}" = "2" ] && [ "${ATENCAO}" = "1" ] && [ "${TOTAL_ITENS}" = "3" ] && [ "${TEM_NG012}" = "true" ]; then
    pass "Caso 5: radar consolidado com 2 divergentes, 1 atenção e referência ausente NG_012"
else
    fail "Caso 5 divergente" "DIVERGENTE=${DIVERGENTE}, ATENCAO=${ATENCAO}, TOTAL=${TOTAL_ITENS}, NG012=${TEM_NG012}"
fi

# ------------------------------------------------------------------------------
# Caso 6: /api/simular 45 -> 30
# ------------------------------------------------------------------------------
echo "[6/7] Caso 6: Simulador 'E se?' (antecedência 45 -> 30)..."
CASO6_PAYLOAD='{"regra": "ferias_antecedencia_dias", "novo_valor": 30}'
CASO6_RES=$(curl -s -X POST "${BASE_URL}/api/simular" -H "Content-Type: application/json" -d "${CASO6_PAYLOAD}")

REGRA_OK=$(echo "${CASO6_RES}" | jq -r '.regra == "ferias_antecedencia_dias"')
ATUAL_45=$(echo "${CASO6_RES}" | jq -r '.valor_atual == 45')
NOVO_30=$(echo "${CASO6_RES}" | jq -r '.novo_valor == 30')
TEM_IMPACTOS=$(echo "${CASO6_RES}" | jq -r '(.impactos | length) > 0')

if [ "${REGRA_OK}" = "true" ] && [ "${ATUAL_45}" = "true" ] && [ "${NOVO_30}" = "true" ] && [ "${TEM_IMPACTOS}" = "true" ]; then
    pass "Caso 6: simulação 45 -> 30 executada com impactos e linha do tempo"
else
    fail "Caso 6 divergente" "REGRA_OK=${REGRA_OK}, ATUAL_45=${ATUAL_45}, NOVO_30=${NOVO_30}"
fi

# ------------------------------------------------------------------------------
# Caso 7: /api/documentos com camada e tema
# ------------------------------------------------------------------------------
echo "[7/7] Caso 7: /api/documentos com camada e tema preenchidos..."
CASO7_RES=$(curl -s "${BASE_URL}/api/documentos")

DOC_TOTAL=$(echo "${CASO7_RES}" | jq -r 'length')
TODOS_TEM_CAMADA=$(echo "${CASO7_RES}" | jq -r 'all(.[]; .camada.sigla != null and .camada.grupo != null)')
TODOS_TEM_TEMA=$(echo "${CASO7_RES}" | jq -r 'all(.[]; .tema.assunto != null and .tema.confirmado_por != null)')

if [ "${DOC_TOTAL}" = "13" ] && [ "${TODOS_TEM_CAMADA}" = "true" ] && [ "${TODOS_TEM_TEMA}" = "true" ]; then
    pass "Caso 7: 13 documentos com metadados de camada e tema estruturados"
else
    fail "Caso 7 divergente" "DOC_TOTAL=${DOC_TOTAL}, CAMADA=${TODOS_TEM_CAMADA}, TEMA=${TODOS_TEM_TEMA}"
fi

echo "================================================================================"
if [ "${FALHAS}" -eq 0 ]; then
    echo "VEREDITO DO SMOKE TEST: TODOS OS 7 CASOS-CHAVE E CONTRATO DE CORS APROVADOS!"
    echo "================================================================================"
    exit 0
else
    echo "VEREDITO DO SMOKE TEST: ${FALHAS} FALHAS DETECTADAS!" >&2
    echo "================================================================================"
    exit 1
fi
