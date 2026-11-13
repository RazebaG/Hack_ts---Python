"""Módulo de Segurança e Proteção da API (HACKA/TS 2026).

Funcionalidades de segurança mínima:
1. Autenticação via API_KEY e cabeçalho X-API-Key:
   - Validação em tempo constante (secrets.compare_digest)
   - /api/saude e OPTIONS abertos para monitoramento e preflight CORS
   - Desligada automaticamente se a variável API_KEY não estiver configurada
   - HTTP 401 Unauthorized se inválida ou ausente

2. Limite de requisições por minuto (Rate Limiting):
   - Configurável via variável RATE_LIMIT_POR_MINUTO (ex.: 60)
   - Janela deslizante de 60 segundos por IP de cliente
   - HTTP 429 Too Many Requests com cabeçalho Retry-After
   - Desligado automaticamente se a variável não estiver definida (ou <= 0)

3. Origens CORS dinâmicas:
   - Configurável via variável CORS_ORIGINS (separada por vírgula)
   - Fallback padrão seguro para localhost e 127.0.0.1 (portas 5173 e 3000)

4. Validação e sanitização de uploads:
   - Sanitização de nome de arquivo contra Directory Traversal (HTTP 400)
   - Limite por arquivo de 10 MB e lote de 50 MB (HTTP 413)
   - Validação de formato e magic bytes reais (HTTP 415)
"""

import os
import secrets
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuração de CORS dinâmico
# ---------------------------------------------------------------------------
ORIGENS_CORS_PADRAO = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def obter_cors_origins() -> List[str]:
    """Retorna lista de origens CORS configuradas no ambiente ou o padrão."""
    env_origins = os.getenv("CORS_ORIGINS", "").strip()
    if not env_origins:
        return list(ORIGENS_CORS_PADRAO)
    origens = [o.strip() for o in env_origins.split(",") if o.strip()]
    return origens if origens else list(ORIGENS_CORS_PADRAO)


# ---------------------------------------------------------------------------
# Autenticação por API_KEY (X-API-Key)
# ---------------------------------------------------------------------------
ROTAS_ABERTAS = {
    "/api/saude",
    "/api/saude/",
    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",
    "/openapi.json",
}


def verificar_api_key(request: Request) -> Optional[JSONResponse]:
    """Valida o cabeçalho X-API-Key em tempo constante quando API_KEY estiver definida."""
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        return None  # Desligada se a variável não existir ou for vazia

    # Métodos OPTIONS (CORS preflight) e rotas abertas não exigem API_KEY
    if request.method == "OPTIONS" or request.url.path in ROTAS_ABERTAS:
        return None

    chave_fornecida = request.headers.get("x-api-key")
    if not chave_fornecida or not secrets.compare_digest(chave_fornecida, api_key):
        return JSONResponse(
            status_code=401,
            content={"detail": "API_KEY inválida ou ausente no cabeçalho X-API-Key."},
        )

    return None


# ---------------------------------------------------------------------------
# Rate Limiting (Janela deslizante de 60s)
# ---------------------------------------------------------------------------
_historico_requisicoes: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()


def obter_ip_cliente(request: Request) -> str:
    """IP do cliente para o rate limit.

    Usa só `request.client.host`. O `X-Forwarded-For` não é lido aqui porque o
    cliente controla o primeiro valor do cabeçalho e poderia trocar de "IP" a
    cada requisição para escapar do limite. Atrás de um proxy confiável (ALB do
    ECS), o uvicorn já reescreve `request.client` a partir do cabeçalho quando
    `FORWARDED_ALLOW_IPS` lista a rede do proxy (ver docs/DEPLOY.md).
    """
    if request.client and request.client.host:
        return request.client.host
    return "desconhecido"


def verificar_rate_limit(request: Request) -> Optional[JSONResponse]:
    """Verifica limite de requisições por minuto com janela deslizante."""
    env_limit = os.getenv("RATE_LIMIT_POR_MINUTO", "").strip()
    if not env_limit:
        return None  # Desligado se a variável não existir

    try:
        limite = int(env_limit)
        if limite <= 0:
            return None
    except ValueError:
        return None

    # OPTIONS não consome cota de rate limit
    if request.method == "OPTIONS":
        return None

    agora = time.time()
    ip = obter_ip_cliente(request)
    janela_segundos = 60.0

    with _rate_limit_lock:
        timestamps = _historico_requisicoes[ip]
        # Remove timestamps fora da janela de 60 segundos
        limite_janela = agora - janela_segundos
        _historico_requisicoes[ip] = [t for t in timestamps if t > limite_janela]
        timestamps = _historico_requisicoes[ip]

        if len(timestamps) >= limite:
            mais_antigo = timestamps[0]
            segundos_espera = max(1, int(janela_segundos - (agora - mais_antigo) + 1))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Limite de requisições excedido ({limite} req/min). Tente novamente mais tarde."
                },
                headers={"Retry-After": str(segundos_espera)},
            )

        timestamps.append(agora)

    return None


def limpar_rate_limit() -> None:
    """Reseta o histórico de requisições em memória (para testes isolados)."""
    with _rate_limit_lock:
        _historico_requisicoes.clear()


# ---------------------------------------------------------------------------
# Validação e Sanitização de Nomes de Upload
# ---------------------------------------------------------------------------
def sanitizar_nome_arquivo(nome: Optional[str]) -> str:
    """Rejeita nomes vazios ou com componentes de caminho (path traversal).

    Devolve o nome original (com acentos e espaços), que é o que a pessoa vê no
    lote. O nome usado em disco continua saneado em `LotesService._salvar`.
    """
    if not nome or not nome.strip():
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido ou ausente.")
    if "/" in nome or "\\" in nome or "\x00" in nome or nome.strip() in (".", ".."):
        raise HTTPException(
            status_code=400,
            detail="Nome de arquivo inválido (caracteres de caminho não permitidos).",
        )
    return nome
