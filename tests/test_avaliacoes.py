import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app, avaliacoes_repo

client = TestClient(app)


@pytest.fixture(autouse=True)
def limpar_avaliacoes():
    """Garante ambiente limpo antes de cada teste de avaliação."""
    avaliacoes_repo.limpar()
    yield
    avaliacoes_repo.limpar()


# ==============================================================================
# Provas de Aceite da Avaliação (C14, RF39, RNF16)
# ==============================================================================


def test_aceite_registrar_avaliacao_e_resumo():
    """Prova de aceite C14 / RF39:

    POST /api/avaliacoes {resposta_id, util, motivo?, comentario?, canal, perfil} -> {id, registrado_em}
    GET /api/avaliacoes/resumo -> {total, uteis, por_canal}
    """
    # 1. Resumo inicial vazio
    resp_ini = client.get("/api/avaliacoes/resumo")
    assert resp_ini.status_code == 200
    assert resp_ini.json() == {"total": 0, "uteis": 0, "por_canal": {"web": 0, "slack": 0, "teams": 0}}

    # 2. Registrar avaliação útil via web
    resp1 = client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_123456",
            "util": True,
            "motivo": None,
            "comentario": "Resposta clara e rápida",
            "canal": "web",
            "perfil": "empregado",
        },
    )
    assert resp1.status_code == 201
    d1 = resp1.json()
    assert d1["id"].startswith("aval_")
    assert d1["registrado_em"]

    # 3. Registrar avaliação não útil via slack com motivo
    resp2 = client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_123456",
            "util": False,
            "motivo": "Faltou informação",
            "comentario": "Gostaria de mais detalhes",
            "canal": "slack",
            "perfil": "gestor",
        },
    )
    assert resp2.status_code == 201
    d2 = resp2.json()
    assert d2["id"] != d1["id"]

    # 4. Registrar avaliação via teams
    resp3 = client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_789012",
            "util": True,
            "canal": "teams",
            "perfil": "diretoria",
        },
    )
    assert resp3.status_code == 201

    # 5. Conferir resumo consolidado
    resp_resumo = client.get("/api/avaliacoes/resumo")
    assert resp_resumo.status_code == 200
    resumo = resp_resumo.json()
    assert resumo["total"] == 3
    assert resumo["uteis"] == 2
    assert resumo["por_canal"]["web"] == 1
    assert resumo["por_canal"]["slack"] == 1
    assert resumo["por_canal"]["teams"] == 1


def test_cada_clique_gera_um_registro():
    """RF39: cada clique gera 1 registro, inclusive múltiplos cliques na mesma resposta."""
    for _ in range(3):
        r = client.post(
            "/api/avaliacoes",
            json={
                "resposta_id": "resp_compartilhada",
                "util": True,
                "canal": "slack",
            },
        )
        assert r.status_code == 201

    resumo = client.get("/api/avaliacoes/resumo").json()
    assert resumo["total"] == 3
    assert resumo["uteis"] == 3
    assert resumo["por_canal"]["slack"] == 3


def test_validacao_comentario_max_200_chars():
    """Comentário com mais de 200 caracteres deve ser rejeitado com 422."""
    comentario_longo = "A" * 201
    resp = client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_val",
            "util": False,
            "comentario": comentario_longo,
            "canal": "web",
        },
    )
    assert resp.status_code == 422


def test_validacao_canal_permitido():
    """Canal deve ser estritamente web, slack ou teams."""
    resp = client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_val",
            "util": True,
            "canal": "canal_invalido",
        },
    )
    assert resp.status_code == 422


def test_privacidade_rnf16_sem_dados_usuario():
    """RNF16: nenhum dado pessoal (nome, email, id_usuario, token) é armazenado."""
    client.post(
        "/api/avaliacoes",
        json={
            "resposta_id": "resp_privacidade",
            "util": True,
            "motivo": "Tudo certo",
            "comentario": "Sem dados pessoais aqui",
            "canal": "web",
            "perfil": "empregado",
        },
    )

    arquivo = avaliacoes_repo.file_path
    assert arquivo.exists()
    conteudo = arquivo.read_text(encoding="utf-8")
    for linha in conteudo.splitlines():
        if linha.strip():
            dado = json.loads(linha)
            assert "nome" not in dado
            assert "email" not in dado
            assert "user_id" not in dado
            assert "usuario_id" not in dado
            assert "token" not in dado
            assert set(dado.keys()) == {
                "id",
                "resposta_id",
                "util",
                "motivo",
                "comentario",
                "canal",
                "perfil",
                "registrado_em",
            }
