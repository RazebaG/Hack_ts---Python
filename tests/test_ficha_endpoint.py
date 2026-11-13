"""Testes do Endpoint GET /api/documentos/{codigo}/ficha (C22, F-07, Issue #48).

Valida:
1. Resposta do endpoint com modelo FichaDocumento e equivalência ao mock-ficha-CTR_2026-012.json.
2. Estado 'pronta', modo extrativo, cobertura.itens_descartados informado.
3. Semáforo determinístico: crítico para substituído, atenção para prazos <= 30d e ref ausente, ok nos demais.
4. Consulta por versão vigente e versão específica (?versao=).
5. Parâmetros perfil e linguagem válidos (aceitos) e inválidos (HTTP 422).
6. Documento ou versão inexistente (HTTP 404).
7. Cache em memória por hash de conteúdo e suporte a cabeçalho ETag / HTTP 304 Not Modified.
8. Atualização do /api/saude com contadores de fichas {prontas, total} e status de autenticação.
9. Proteção com API_KEY e cabeçalho X-API-Key quando ativada.
10. Tempo de resposta < 1 s para todos os 13 documentos do acervo.
"""

import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.acervo import get_acervo
from app.ficha.modelos import FichaDocumento
from app.routers.ficha import limpar_cache_fichas

client = TestClient(app)


@pytest.fixture(autouse=True)
def resetar_cache():
    """Garante isolamento do cache em memória antes de cada teste."""
    limpar_cache_fichas()
    yield
    limpar_cache_fichas()


def test_ficha_ctr_2026_012_estrutura_mock_e_modelo():
    """Valida a ficha de CTR_2026-012 contra o modelo FichaDocumento e mock-ficha-CTR_2026-012.json."""
    resp = client.get("/api/documentos/CTR_2026-012/ficha")
    assert resp.status_code == 200
    dados = resp.json()

    # Validação com Pydantic
    ficha = FichaDocumento(**dados)
    assert ficha.codigo == "CTR_2026-012"
    assert ficha.versao == "1.0.0"
    assert ficha.estado == "pronta"
    assert ficha.modo.ia == "extrativo"
    assert ficha.modo.modelo is None
    assert ficha.familia == "contrato"

    # Semáforo determinístico
    assert ficha.semaforo.nivel == "atencao"
    motivos_str = " ".join(ficha.semaforo.motivos)
    assert "Vistoria" in motivos_str
    assert "NG_012" in motivos_str

    # Blocos da Mesa de Decisão (mínimo 4)
    assert len(ficha.blocos) >= 4
    titulos_blocos = [b.titulo for b in ficha.blocos]
    assert "Quanto custa" in titulos_blocos
    assert "Até quando" in titulos_blocos

    # Cobertura de verificação
    assert ficha.cobertura.secoes_total == 43
    assert ficha.cobertura.itens_descartados == 0
    assert isinstance(ficha.cobertura.motivos_descarte, list)

    # Confronto com chaves do mock
    mock_path = Path("docs/ficha-do-documento/mock-ficha-CTR_2026-012.json")
    if mock_path.exists():
        with open(mock_path, "r", encoding="utf-8") as f:
            mock_data = json.load(f)
        for chave, valor_mock in mock_data.items():
            if chave.startswith("_"):
                continue
            assert chave in dados, f"Chave '{chave}' do mock deve estar presente na resposta da API"
            assert type(dados[chave]) is type(valor_mock), f"Tipo da chave '{chave}' divergente do mock"


def test_ficha_ng_111_vigente_e_substituida():
    """Valida a ficha da norma NG_111 na versão vigente (3.0.0) e versão substituída (2.0.0)."""
    # 1. Versão vigente v3.0.0 (padrão sem query)
    resp_v3 = client.get("/api/documentos/NG_111/ficha")
    assert resp_v3.status_code == 200
    d_v3 = resp_v3.json()
    assert d_v3["codigo"] == "NG_111"
    assert d_v3["versao"] == "3.0.0"
    assert d_v3["familia"] == "norma"
    assert d_v3["estado"] == "pronta"
    assert d_v3["modo"]["ia"] == "extrativo"
    assert d_v3["semaforo"]["nivel"] == "ok"

    # 2. Versão substituída v2.0.0 via query ?versao=2.0.0
    resp_v2 = client.get("/api/documentos/NG_111/ficha?versao=2.0.0")
    assert resp_v2.status_code == 200
    d_v2 = resp_v2.json()
    assert d_v2["codigo"] == "NG_111"
    assert d_v2["versao"] == "2.0.0"
    assert d_v2["semaforo"]["nivel"] == "critico"
    assert any("substituída" in m.lower() for m in d_v2["semaforo"]["motivos"])


def test_ficha_validacao_perfil_e_linguagem():
    """Valida aceitação de perfis e linguagens válidas e rejeição com 422 para inválidos."""
    perfis_validos = ["empregado", "gestor", "diretoria", "financeiro", "juridico", "rh"]
    for p in perfis_validos:
        r = client.get(f"/api/documentos/CTR_2026-012/ficha?perfil={p}")
        assert r.status_code == 200
        assert r.json()["perfil"] == p

    linguagens_validas = ["original", "simples"]
    for l in linguagens_validas:
        r = client.get(f"/api/documentos/CTR_2026-012/ficha?linguagem={l}")
        assert r.status_code == 200
        assert r.json()["linguagem"] == l

    # Perfil inválido -> 422
    r_bad_perfil = client.get("/api/documentos/CTR_2026-012/ficha?perfil=astronauta")
    assert r_bad_perfil.status_code == 422
    assert "Perfil 'astronauta' inválido" in r_bad_perfil.json()["detail"]

    # Linguagem inválida -> 422
    r_bad_ling = client.get("/api/documentos/CTR_2026-012/ficha?linguagem=esperanto")
    assert r_bad_ling.status_code == 422
    assert "Linguagem 'esperanto' inválida" in r_bad_ling.json()["detail"]


def test_ficha_erros_404():
    """Valida HTTP 404 para documento inexistente ou versão inexistente."""
    # Documento inexistente
    r_no_doc = client.get("/api/documentos/NAO_EXISTE_123/ficha")
    assert r_no_doc.status_code == 404
    assert "não encontrado no acervo" in r_no_doc.json()["detail"]

    # Versão inexistente de documento existente
    r_no_ver = client.get("/api/documentos/CTR_2026-012/ficha?versao=99.0.0")
    assert r_no_ver.status_code == 404
    assert "versão 99.0.0" in r_no_ver.json()["detail"]


def test_ficha_cache_em_memoria_e_etag():
    """Valida cálculo determinístico em memória, cabeçalho ETag e resposta condicional 304."""
    # 1ª chamada: calcula e guarda em memória
    r1 = client.get("/api/documentos/CTR_2026-012/ficha")
    assert r1.status_code == 200
    etag1 = r1.headers.get("etag")
    assert etag1 is not None and etag1.startswith('"') and etag1.endswith('"')

    # 2ª chamada: serve do cache com mesmo ETag
    r2 = client.get("/api/documentos/CTR_2026-012/ficha")
    assert r2.status_code == 200
    assert r2.headers.get("etag") == etag1
    assert r2.json() == r1.json()

    # 3ª chamada condicional com If-None-Match: deve devolver 304 Not Modified
    r3 = client.get("/api/documentos/CTR_2026-012/ficha", headers={"If-None-Match": etag1})
    assert r3.status_code == 304
    assert r3.headers.get("etag") == etag1


def test_saude_contadores_fichas_e_autenticacao(monkeypatch):
    """Valida se /api/saude retorna fichas: {prontas, total} e status de autenticacao."""
    # Estado inicial: cache limpo -> 0 prontas
    r_init = client.get("/api/saude")
    assert r_init.status_code == 200
    d_init = r_init.json()
    assert d_init["documentos"] == 13
    assert d_init["fichas"]["prontas"] == 0
    assert d_init["fichas"]["total"] == 13
    assert d_init["autenticacao"] == "desligada"

    # Gera ficha para CTR_2026-012
    client.get("/api/documentos/CTR_2026-012/ficha")

    # Agora deve constar 1 ficha pronta
    r_after = client.get("/api/saude")
    d_after = r_after.json()
    assert d_after["fichas"]["prontas"] == 1
    assert d_after["fichas"]["total"] == 13

    # Com API_KEY configurada, indica autenticacao ligada
    monkeypatch.setenv("API_KEY", "minha-chave-teste")
    r_auth = client.get("/api/saude")
    assert r_auth.json()["autenticacao"] == "ligada"


def test_ficha_protegida_por_api_key(monkeypatch):
    """Quando API_KEY estiver ligada, a rota /api/documentos/{codigo}/ficha exige a chave."""
    monkeypatch.setenv("API_KEY", "chave-secreta-hacka")

    # 1. Sem cabeçalho -> 401
    r_no_key = client.get("/api/documentos/CTR_2026-012/ficha")
    assert r_no_key.status_code == 401

    # 2. Com chave incorreta -> 401
    r_bad_key = client.get(
        "/api/documentos/CTR_2026-012/ficha",
        headers={"X-API-Key": "chave-incorreta"},
    )
    assert r_bad_key.status_code == 401

    # 3. Com chave correta -> 200
    r_ok = client.get(
        "/api/documentos/CTR_2026-012/ficha",
        headers={"X-API-Key": "chave-secreta-hacka"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["codigo"] == "CTR_2026-012"

    # 4. /api/saude permanece aberta sem chave
    r_saude = client.get("/api/saude")
    assert r_saude.status_code == 200
    assert r_saude.json()["autenticacao"] == "ligada"


def test_tempo_de_resposta_todos_os_documentos():
    """Valida SLA de tempo < 1 s para todos os 13 documentos do acervo."""
    acervo = get_acervo()
    for doc in acervo.documentos:
        t0 = time.time()
        resp = client.get(f"/api/documentos/{doc.codigo}/ficha?versao={doc.versao}")
        duracao = time.time() - t0

        assert resp.status_code == 200, f"Falha ao obter ficha para {doc.codigo} v{doc.versao}"
        assert duracao < 1.0, f"Tempo de resposta {duracao:.3f} s excedeu 1.0 s para {doc.codigo}"
