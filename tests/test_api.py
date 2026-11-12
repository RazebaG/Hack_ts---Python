import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_saude():
    """GET /api/saude retorna status 'ok' e total de 13 documentos."""
    response = client.get("/api/saude")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["documentos"] == 13


def test_total_documentos():
    """GET /api/documentos retorna exatamente 13 documentos."""
    response = client.get("/api/documentos")
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) == 13

    # 11 vigentes e 2 substituídos
    vigentes = [d for d in docs if not d["substituido"]]
    substituidos = [d for d in docs if d["substituido"]]
    assert len(vigentes) == 11
    assert len(substituidos) == 2


def test_ng_111_versoes_e_vigente_default():
    """NG_111 tem versões 2.0.0 (substituída) e 3.0.0 (vigente).

    GET /api/documentos/NG_111 sem versão retorna 3.0.0.
    GET /api/documentos/NG_111?versao=2.0.0 retorna 2.0.0.
    """
    # Consulta sem versão -> versão vigente (3.0.0)
    resp_vigente = client.get("/api/documentos/NG_111")
    assert resp_vigente.status_code == 200
    data_vigente = resp_vigente.json()
    assert data_vigente["codigo"] == "NG_111"
    assert data_vigente["versao"] == "3.0.0"
    assert data_vigente["substituido"] is False
    assert data_vigente["fase"] == "Vigente"

    # Consulta da versão 2.0.0 específica
    resp_v2 = client.get("/api/documentos/NG_111?versao=2.0.0")
    assert resp_v2.status_code == 200
    data_v2 = resp_v2.json()
    assert data_v2["codigo"] == "NG_111"
    assert data_v2["versao"] == "2.0.0"
    assert data_v2["substituido"] is True
    assert data_v2["fase"] == "Versão anterior"


def test_fm_1111_001_v2_vinculado_a_ng_111():
    """FM_1111-001 v2.0.0 vinculado a NG_111."""
    response = client.get("/api/documentos/FM_1111-001?versao=2.0.0")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "FM_1111-001"
    assert data["versao"] == "2.0.0"
    assert data["vinculado_a"] == "NG_111"


def test_px_1130_001_vinculado_a_ng_1130():
    """PX_1130-001 vinculado a NG_1130."""
    response = client.get("/api/documentos/PX_1130-001")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "PX_1130-001"
    assert data["versao"] == "1.0.0"
    assert data["vinculado_a"] == "NG_1130"


def test_ctr_2026_012_vigencia():
    """CTR_2026-012 vigência 30/11/2026 a 29/04/2027."""
    response = client.get("/api/documentos/CTR_2026-012")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "CTR_2026-012"
    assert data["vigencia"] == "30/11/2026 a 29/04/2027"


def test_cada_documento_tem_ao_menos_uma_secao():
    """Cada um dos 13 documentos tem >= 1 seção com id e titulo preenchidos."""
    docs_resp = client.get("/api/documentos")
    docs = docs_resp.json()
    assert len(docs) == 13

    for doc_meta in docs:
        resp = client.get(f"/api/documentos/{doc_meta['codigo']}?versao={doc_meta['versao']}")
        assert resp.status_code == 200
        doc = resp.json()
        assert "secoes" in doc
        secoes = doc["secoes"]
        assert len(secoes) >= 1, f"Documento {doc['codigo']} v{doc['versao']} não possui seções"
        for s in secoes:
            assert s["id"], f"Seção sem id em {doc['codigo']} v{doc['versao']}"
            assert s["titulo"], f"Seção sem titulo em {doc['codigo']} v{doc['versao']}"


def test_documento_nao_encontrado():
    """Retorna 404 para documento ou versão inexistente."""
    resp_inexistente = client.get("/api/documentos/DOC_INEXISTENTE")
    assert resp_inexistente.status_code == 404

    resp_versao_errada = client.get("/api/documentos/NG_111?versao=9.9.9")
    assert resp_versao_errada.status_code == 404


def test_cors_headers():
    """Verifica se CORS está liberado para o frontend http://localhost:5173."""
    response = client.get("/api/saude", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_filtros_por_assunto():
    """Verifica filtros por assunto na listagem."""
    resp_ferias = client.get("/api/documentos?assunto=ferias")
    assert resp_ferias.status_code == 200
    assert len(resp_ferias.json()) == 7

    resp_inovacao = client.get("/api/documentos?assunto=inovacao")
    assert resp_inovacao.status_code == 200
    assert len(resp_inovacao.json()) == 4

    resp_locacao = client.get("/api/documentos?assunto=locacao")
    assert resp_locacao.status_code == 200
    assert len(resp_locacao.json()) == 2


def test_estatisticas():
    """GET /api/acervo/estatisticas retorna consolidados corretos."""
    resp = client.get("/api/acervo/estatisticas")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total"] == 13
    assert stats["vigentes"] == 11
    assert stats["substituidos"] == 2
    assert stats["por_assunto"]["ferias"] == 7
    assert stats["por_assunto"]["inovacao"] == 4
    assert stats["por_assunto"]["locacao"] == 2
