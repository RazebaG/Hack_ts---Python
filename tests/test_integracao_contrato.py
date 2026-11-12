"""Testes de integração de contrato com o frontend React (Issue #28 / PRD / CONTRATO-API).

Valida cada endpoint consumido pelo frontend (Hacka_ts-React PR #21 / src/api/):
- GET /api/saude
- GET /api/documentos (vigentes, substituídos, filtro ?serie=)
- GET /api/documentos/{codigo}?versao=
- POST /api/perguntar (formato estendido C13/C15 com camada, avisos, proxima_acao)
- GET /api/codigo/{codigo} (decodificação taxonômica do catálogo)
- GET /api/perspectivas e GET /api/perspectivas/{id}
- GET /api/grafo (nós com existe_no_acervo e arestas)
- GET /api/comparar?codigo=&de=&para=
- GET /api/relatorio?perspectiva=
- GET /api/radar
- GET /api/regras
- POST /api/simular
- POST /api/avaliacoes e GET /api/avaliacoes/resumo
- Headers CORS liberados para http://localhost:5173
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app, avaliacoes_repo

client = TestClient(app)


@pytest.fixture(autouse=True)
def limpar_estado():
    avaliacoes_repo.limpar()
    yield
    avaliacoes_repo.limpar()


# ------------------------------------------------------------------------------
# 1. GET /api/saude
# ------------------------------------------------------------------------------
def test_contrato_saude():
    resp = client.get("/api/saude")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["documentos"] == 13
    assert "ia" in data
    assert "provedor" in data["ia"]


# ------------------------------------------------------------------------------
# 2. GET /api/documentos
# ------------------------------------------------------------------------------
def test_contrato_documentos():
    resp = client.get("/api/documentos")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 13

    # Verificar campos obrigatórios exigidos pelo frontend DocumentoResumo
    campos_esperados = {
        "codigo", "titulo", "tipo", "tipo_nome", "versao", "fase",
        "vigencia", "vinculado_a", "referencia", "assunto", "substituido",
        "camada", "tema"
    }
    for doc in docs:
        for campo in campos_esperados:
            assert campo in doc, f"Campo {campo} ausente no documento {doc.get('codigo')}"
        # Verificar camada (C15)
        assert "sigla" in doc["camada"]
        assert "grupo" in doc["camada"]
        # Verificar tema (C17)
        assert "assunto" in doc["tema"]
        assert "confirmado_por" in doc["tema"]

    # Filtro por série (C17)
    resp_serie1 = client.get("/api/documentos?serie=1")
    assert resp_serie1.status_code == 200
    docs_serie1 = resp_serie1.json()
    assert len(docs_serie1) == 7
    assert all(d["tema"]["serie"] == 1 for d in docs_serie1)


# ------------------------------------------------------------------------------
# 3. GET /api/documentos/{codigo} e com ?versao=
# ------------------------------------------------------------------------------
def test_contrato_documento_detalhe():
    # Vigente
    resp = client.get("/api/documentos/NG_111")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["codigo"] == "NG_111"
    assert doc["versao"] == "3.0.0"
    assert doc["substituido"] is False
    assert len(doc["secoes"]) > 0
    assert "id" in doc["secoes"][0]
    assert "titulo" in doc["secoes"][0]
    assert "texto" in doc["secoes"][0]

    # Versão substituída
    resp_v2 = client.get("/api/documentos/NG_111?versao=2.0.0")
    assert resp_v2.status_code == 200
    doc_v2 = resp_v2.json()
    assert doc_v2["versao"] == "2.0.0"
    assert doc_v2["substituido"] is True

    # 404 para documento inexistente
    resp_404 = client.get("/api/documentos/DOC_INEXISTENTE")
    assert resp_404.status_code == 404
    assert "detail" in resp_404.json()


# ------------------------------------------------------------------------------
# 4. POST /api/perguntar
# ------------------------------------------------------------------------------
def test_contrato_perguntar():
    # Pergunta com resposta e citações
    resp = client.post(
        "/api/perguntar",
        json={"pergunta": "Até quando peço férias que começam em 05/05/2027?", "perfil": "empregado"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consta"] is True
    assert "21/03/2027" in data["resposta"]
    assert len(data["citacoes"]) > 0

    citacao = data["citacoes"][0]
    assert "codigo" in citacao
    assert "versao" in citacao
    assert "secao" in citacao
    assert "trecho" in citacao
    assert "camada" in citacao
    assert citacao["camada"]["sigla"]

    assert "resposta_id" in data
    assert "avisos" in data
    assert "proxima_acao" in data

    # Pergunta com abstenção (fora do acervo)
    resp_abs = client.post(
        "/api/perguntar",
        json={"pergunta": "Qual o valor do benefício alimentação pago aos empregados?", "perfil": "empregado"}
    )
    assert resp_abs.status_code == 200
    data_abs = resp_abs.json()
    assert data_abs["consta"] is False
    assert data_abs["citacoes"] == []


# ------------------------------------------------------------------------------
# 5. GET /api/codigo/{codigo}
# ------------------------------------------------------------------------------
def test_contrato_codigo():
    resp = client.get("/api/codigo/PX_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "PX_1111-001"
    assert data["tipo"] == "PX"
    assert data["tipo_nome"] == "Procedimento"
    assert data["vinculado_a"] == "NG_111"
    assert data["serie"] == "1"
    assert data["serie_nome"] == "Gente e Cultura"
    assert data["existe_no_acervo"] is True

    # Documento ausente
    resp_ausente = client.get("/api/codigo/NG_012")
    assert resp_ausente.status_code == 200
    assert resp_ausente.json()["existe_no_acervo"] is False


# ------------------------------------------------------------------------------
# 6. GET /api/perspectivas e /api/perspectivas/{id}
# ------------------------------------------------------------------------------
def test_contrato_perspectivas():
    resp = client.get("/api/perspectivas")
    assert resp.status_code == 200
    persp_list = resp.json()
    assert len(persp_list) == 4
    ids = [p["id"] for p in persp_list]
    assert "financeiro" in ids
    assert "pessoas" in ids

    # Detalhe financeiro
    resp_fin = client.get("/api/perspectivas/financeiro")
    assert resp_fin.status_code == 200
    fin = resp_fin.json()
    assert fin["id"] == "financeiro"
    assert len(fin["destaques"]) > 0
    assert len(fin["valores"]) > 0
    assert any(v["numero"] == 912.5 for v in fin["valores"])

    # 404 para perspectiva desconhecida
    resp_invalida = client.get("/api/perspectivas/desconhecida")
    assert resp_invalida.status_code == 404


# ------------------------------------------------------------------------------
# 7. GET /api/grafo
# ------------------------------------------------------------------------------
def test_contrato_grafo():
    resp = client.get("/api/grafo")
    assert resp.status_code == 200
    data = resp.json()
    assert "nos" in data
    assert "arestas" in data
    assert len(data["nos"]) > 0
    assert any(n["codigo"] == "NG_012" and not n["existe_no_acervo"] for n in data["nos"])


# ------------------------------------------------------------------------------
# 8. GET /api/comparar
# ------------------------------------------------------------------------------
def test_contrato_comparar():
    resp = client.get("/api/comparar?codigo=NG_111&de=2.0.0&para=3.0.0")
    assert resp.status_code == 200
    comp = resp.json()
    assert comp["codigo"] == "NG_111"
    assert comp["de"] == "2.0.0"
    assert comp["para"] == "3.0.0"
    assert len(comp["mudancas"]) > 0
    assert len(comp["resumo"]) > 0


# ------------------------------------------------------------------------------
# 9. GET /api/relatorio
# ------------------------------------------------------------------------------
def test_contrato_relatorio():
    resp = client.get("/api/relatorio?perspectiva=juridico")
    assert resp.status_code == 200
    rel = resp.json()
    assert "titulo" in rel
    assert "gerado_em" in rel
    assert len(rel["secoes"]) > 0


# ------------------------------------------------------------------------------
# 10. GET /api/radar
# ------------------------------------------------------------------------------
def test_contrato_radar():
    resp = client.get("/api/radar")
    assert resp.status_code == 200
    radar = resp.json()
    assert radar["resumo"]["divergente"] == 2
    assert radar["resumo"]["atencao"] == 1
    assert len(radar["itens"]) == 3


# ------------------------------------------------------------------------------
# 11. GET /api/regras e POST /api/simular
# ------------------------------------------------------------------------------
def test_contrato_simulador():
    resp_regras = client.get("/api/regras")
    assert resp_regras.status_code == 200
    regras = resp_regras.json()
    assert len(regras) == 2
    assert any(r["id"] == "ferias_antecedencia_dias" for r in regras)

    resp_sim = client.post(
        "/api/simular",
        json={"regra": "ferias_antecedencia_dias", "novo_valor": 30}
    )
    assert resp_sim.status_code == 200
    sim = resp_sim.json()
    assert sim["regra"] == "ferias_antecedencia_dias"
    assert sim["valor_atual"] == 45
    assert sim["novo_valor"] == 30
    assert len(sim["linha_do_tempo"]) > 0
    assert len(sim["impactos"]) > 0


# ------------------------------------------------------------------------------
# 12. POST /api/avaliacoes e GET /api/avaliacoes/resumo
# ------------------------------------------------------------------------------
def test_contrato_avaliacoes():
    resp_post = client.post(
        "/api/avaliacoes",
        json={"resposta_id": "resp-test-01", "util": True, "canal": "web", "perfil": "empregado"}
    )
    assert resp_post.status_code == 201

    resp_resumo = client.get("/api/avaliacoes/resumo")
    assert resp_resumo.status_code == 200
    resumo = resp_resumo.json()
    assert resumo["total"] == 1
    assert resumo["uteis"] == 1


# ------------------------------------------------------------------------------
# 13. CORS liberado para http://localhost:5173
# ------------------------------------------------------------------------------
def test_contrato_cors_preflight():
    resp = client.options(
        "/api/perguntar",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        }
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
