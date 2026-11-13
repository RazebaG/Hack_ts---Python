"""Testes de Segurança e Proteção da API (HACKA/TS 2026).

Valida os requisitos de segurança mínima:
1. API_KEY com cabeçalho X-API-Key (tempo constante, rotas abertas, desligada sem variável).
2. Rate limiting por minuto (RATE_LIMIT_POR_MINUTO, 429 com Retry-After, desligável).
3. Validação de upload em /api/lotes e digitalização (tipo real, 10 MB, 50 MB, nome sanitizado, 400/413/415).
4. Validação de resposta_id em /api/avaliacoes antes do 201.
5. Escapamento _esc() no campo text do fallback do Slack.
6. Configuração dinâmica de CORS_ORIGINS.
"""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app, avaliacoes_repo
from app.seguranca import (
    limpar_rate_limit,
    obter_cors_origins,
    sanitizar_nome_arquivo,
)
from app.canais import slack
from app.canais.cartao import Cartao, CitacaoCartao
from app.digitalizacao import LeituraFalhou, ler_imagem

client = TestClient(app)


# ==============================================================================
# 1. Autenticação por API_KEY e X-API-Key
# ==============================================================================

def test_api_key_desligada_permite_acesso(monkeypatch):
    """Sem API_KEY definida no ambiente, autenticação fica desligada (200 OK)."""
    monkeypatch.delenv("API_KEY", raising=False)
    resp = client.get("/api/documentos")
    assert resp.status_code == 200


def test_api_key_ausente_retorna_401(monkeypatch):
    """Com API_KEY configurada, requisição sem X-API-Key recebe 401 Unauthorized."""
    monkeypatch.setenv("API_KEY", "chave-secreta-hacka")
    resp = client.get("/api/documentos")
    assert resp.status_code == 401
    assert "API_KEY inválida ou ausente" in resp.json()["detail"]


def test_api_key_invalida_retorna_401(monkeypatch):
    """Com API_KEY configurada, cabeçalho X-API-Key incorreto recebe 401 Unauthorized."""
    monkeypatch.setenv("API_KEY", "chave-secreta-hacka")
    resp = client.get("/api/documentos", headers={"X-API-Key": "chave-errada"})
    assert resp.status_code == 401
    assert "API_KEY inválida ou ausente" in resp.json()["detail"]


def test_api_key_valida_retorna_200(monkeypatch):
    """Com API_KEY configurada, cabeçalho X-API-Key correto recebe 200 OK."""
    monkeypatch.setenv("API_KEY", "chave-secreta-hacka")
    resp = client.get("/api/documentos", headers={"X-API-Key": "chave-secreta-hacka"})
    assert resp.status_code == 200


def test_api_key_saude_e_options_abertos(monkeypatch):
    """/api/saude e requisições OPTIONS permanecem abertos mesmo com API_KEY ativada."""
    monkeypatch.setenv("API_KEY", "chave-secreta-hacka")

    # /api/saude sem X-API-Key
    resp_saude = client.get("/api/saude")
    assert resp_saude.status_code == 200
    assert resp_saude.json()["status"] == "ok"

    # OPTIONS preflight sem X-API-Key
    resp_options = client.options(
        "/api/documentos",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp_options.status_code == 200


# ==============================================================================
# 2. Rate Limiting por Minuto
# ==============================================================================

def test_rate_limit_desligado_sem_variavel(monkeypatch):
    """Sem RATE_LIMIT_POR_MINUTO definida, requisições ocorrem sem bloqueio."""
    monkeypatch.delenv("RATE_LIMIT_POR_MINUTO", raising=False)
    limpar_rate_limit()

    for _ in range(5):
        resp = client.get("/api/saude")
        assert resp.status_code == 200


def test_rate_limit_bloqueia_excesso_e_retorna_429_com_retry_after(monkeypatch):
    """Com limite atingido, responde 429 Too Many Requests com cabeçalho Retry-After."""
    monkeypatch.setenv("RATE_LIMIT_POR_MINUTO", "3")
    limpar_rate_limit()

    # 3 requisições dentro do limite
    for _ in range(3):
        resp = client.get("/api/saude")
        assert resp.status_code == 200

    # 4ª requisição deve ser bloqueada com 429
    resp_bloqueada = client.get("/api/saude")
    assert resp_bloqueada.status_code == 429
    assert "Retry-After" in resp_bloqueada.headers
    retry_after = int(resp_bloqueada.headers["Retry-After"])
    assert 1 <= retry_after <= 60
    assert "Limite de requisições excedido" in resp_bloqueada.json()["detail"]

    # Limpeza reseta a cota
    limpar_rate_limit()
    resp_reset = client.get("/api/saude")
    assert resp_reset.status_code == 200


def test_rate_limit_options_nao_consome_cota(monkeypatch):
    """Requisições OPTIONS não consomem a cota de rate limit."""
    monkeypatch.setenv("RATE_LIMIT_POR_MINUTO", "2")
    limpar_rate_limit()

    # Preflight OPTIONS repetidos
    for _ in range(5):
        resp = client.options(
            "/api/documentos",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code == 200


# ==============================================================================
# 3. Validação de Upload em /api/lotes e Digitalização
# ==============================================================================

def test_sanitizar_nome_arquivo():
    """Valida a sanitização e detecção de Directory Traversal."""
    # Nomes válidos são normalizados
    assert sanitizar_nome_arquivo("relatorio_2026.md") == "relatorio_2026.md"
    assert sanitizar_nome_arquivo("documento com espaços.pdf") == "documento_com_espa_os.pdf"

    # Tentativa de Directory Traversal resulta em HTTP 400
    with pytest.raises(Exception) as exc1:
        sanitizar_nome_arquivo("../../etc/passwd")
    assert exc1.value.status_code == 400

    with pytest.raises(Exception) as exc2:
        sanitizar_nome_arquivo("pasta/arquivo.md")
    assert exc2.value.status_code == 400

    with pytest.raises(Exception) as exc3:
        sanitizar_nome_arquivo("..\\win.ini")
    assert exc3.value.status_code == 400

    # Nomes vazios
    with pytest.raises(Exception) as exc4:
        sanitizar_nome_arquivo("")
    assert exc4.value.status_code == 400


def test_upload_path_traversal_rejeitado_pela_api():
    """POST /api/lotes com nome malicioso em arquivo deve responder HTTP 400."""
    resp = client.post(
        "/api/lotes",
        files=[("arquivos", ("../../malicioso.md", b"# Titulo", "text/markdown"))],
    )
    assert resp.status_code == 400
    assert "caracteres de caminho não permitidos" in resp.json()["detail"]


def test_upload_nome_vazio_rejeitado_com_400():
    """POST /api/lotes com nome de arquivo em branco responde HTTP 400."""
    resp = client.post(
        "/api/lotes",
        files=[("arquivos", ("   ", b"# Titulo", "text/markdown"))],
    )
    assert resp.status_code == 400
    assert "Nome de arquivo inválido ou ausente" in resp.json()["detail"]


def test_upload_lote_acima_50mb_rejeitado_com_413(monkeypatch):
    """Lote cujo total ultrapassa 50 MB deve ser rejeitado com 413 Payload Too Large."""
    from app import ingestao

    monkeypatch.setattr(ingestao, "MAX_BYTES_LOTE", 500)
    resp = client.post(
        "/api/lotes",
        files=[
            ("arquivos", ("a1.md", b"x" * 300, "text/markdown")),
            ("arquivos", ("a2.md", b"x" * 300, "text/markdown")),
        ],
    )
    assert resp.status_code == 413
    assert "Lote maior que 50 MB" in resp.json()["detail"]


def test_upload_tipo_invalido_registra_415():
    """Arquivo de extensão não suportada (.xlsx) é marcado com erro 415 no lote."""
    resp = client.post(
        "/api/lotes",
        files=[("arquivos", ("planilha.xlsx", b"coluna1,coluna2\n", "application/vnd.ms-excel"))],
    )
    assert resp.status_code == 201
    dados = resp.json()
    arq = dados["arquivos"][0]
    assert arq["estado"] == "erro"
    assert arq["erro"]["status"] == 415
    assert "tipo não aceito" in arq["erro"]["mensagem"]


def test_upload_assinatura_falsa_registra_415():
    """Arquivo de texto disfarçado de imagem .png é marcado com erro 415 no lote."""
    resp = client.post(
        "/api/lotes",
        files=[("arquivos", ("falso.png", b"isto nao e imagem png", "image/png"))],
    )
    assert resp.status_code == 201
    dados = resp.json()
    arq = dados["arquivos"][0]
    assert arq["estado"] == "erro"
    assert arq["erro"]["status"] == 415


def test_digitalizacao_valida_formato_e_tamanho():
    """ler_imagem() valida formato suportado e tamanho limite de 10 MB."""
    # Formato não aceito
    with pytest.raises(LeituraFalhou) as exc1:
        ler_imagem(b"conteudo", "gif")
    assert "não aceito" in str(exc1.value)

    # Imagem maior que 10 MB
    conteudo_enorme = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1)
    with pytest.raises(LeituraFalhou) as exc2:
        ler_imagem(conteudo_enorme, "png")
    assert "10 MB" in str(exc2.value)

    # Assinatura falsa
    with pytest.raises(LeituraFalhou) as exc3:
        ler_imagem(b"texto puro", "png")
    assert "não corresponde a uma imagem PNG" in str(exc3.value)


# ==============================================================================
# 4. Validação de resposta_id em /api/avaliacoes
# ==============================================================================

def test_avaliacao_resposta_id_obrigatorio_e_nao_vazio():
    """/api/avaliacoes valida se resposta_id foi enviado e não é vazio antes do 201."""
    avaliacoes_repo.limpar()

    # 1. Sem campo resposta_id -> 422
    resp_ausente = client.post(
        "/api/avaliacoes",
        json={"util": True, "canal": "web"},
    )
    assert resp_ausente.status_code == 422

    # 2. resposta_id vazio ("") -> 422 (min_length=1)
    resp_vazio = client.post(
        "/api/avaliacoes",
        json={"resposta_id": "", "util": True, "canal": "web"},
    )
    assert resp_vazio.status_code == 422

    # 3. resposta_id composto apenas por espaços -> 400
    resp_espacos = client.post(
        "/api/avaliacoes",
        json={"resposta_id": "   ", "util": True, "canal": "web"},
    )
    assert resp_espacos.status_code == 400
    assert "não pode ser vazio" in resp_espacos.json()["detail"]

    # 4. resposta_id válido -> 201 Created
    resp_valido = client.post(
        "/api/avaliacoes",
        json={"resposta_id": "resp_segura_123", "util": True, "canal": "web"},
    )
    assert resp_valido.status_code == 201
    assert resp_valido.json()["id"].startswith("aval_")


# ==============================================================================
# 5. Escapamento _esc() no campo text do fallback do Slack
# ==============================================================================

def test_slack_renderizar_escapa_fallback_text():
    """renderizar() aplica _esc() no campo 'text' de fallback além dos blocos."""
    cartao = Cartao(
        titulo="Alerta: valor < R$ 100 & multa > 5%",
        conclusao="Consulte a norma & aplique o desconto < 10% > 2%",
        citacoes=[
            CitacaoCartao(
                codigo="NG_111",
                versao="v1.0.0",
                secao="§1",
                trecho="Regra geral",
                selo="NORM · Geral",
            )
        ],
    )
    payload = slack.renderizar([cartao])
    fallback_text = payload["text"]

    # Deve conter entidades escapadas &amp;, &lt;, &gt; e NÃO os caracteres brutos
    assert "&lt;" in fallback_text
    assert "&gt;" in fallback_text
    assert "&amp;" in fallback_text
    assert "<" not in fallback_text
    assert ">" not in fallback_text


# ==============================================================================
# 6. Configuração de CORS_ORIGINS
# ==============================================================================

def test_cors_origins_configuravel(monkeypatch):
    """obter_cors_origins() lê variável CORS_ORIGINS e fornece fallback seguro."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    padrao = obter_cors_origins()
    assert "http://localhost:5173" in padrao

    monkeypatch.setenv("CORS_ORIGINS", "https://app.acme.test, https://portal.acme.test")
    custom = obter_cors_origins()
    assert custom == ["https://app.acme.test", "https://portal.acme.test"]
