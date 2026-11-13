"""Testes de Controle de Acesso Baseado em Cargo (RBAC) - Issue #22 / HACKA/TS 2026.

Cobre os critérios de aceite definidos em `docs/propostas/RBAC-MVP.md`:
1. Cena Empregado x Financeiro:
   - Empregado pergunta "Qual a multa por inexecução do coworking?" -> abstenção sem citação de CTR_2026-012
   - Financeiro pergunta a mesma questão -> citação de CTR_2026-012 Apêndice B com R$ 912,50
2. Filtro de catálogo em GET /api/documentos por cargo e e-mail de fixture
3. Bloqueio 403 Forbidden para acesso direto a documentos não autorizados
4. Bloqueio 403 Forbidden em perspectivas não autorizadas
5. Bloqueio 403 Forbidden em radar de contradições
6. Bloqueio 403 Forbidden em comparar e relatórios executivos
7. Endpoints /api/rbac/usuarios e /api/rbac/matriz
8. Trilha de auditoria local em JSONL (sem PII)
9. Indicador rbac=true em /api/saude
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.rbac import get_rbac

client = TestClient(app)
AUDIT_FILE = Path(__file__).resolve().parent.parent / "data" / "rbac" / "audit.jsonl"


def test_saude_rbac():
    """GET /api/saude retorna rbac: True."""
    res = client.get("/api/saude")
    assert res.status_code == 200
    dados = res.json()
    assert dados["rbac"] is True
    assert dados["documentos"] == 13


def test_endpoints_rbac_metadados():
    """GET /api/rbac/usuarios e /api/rbac/matriz retornam fixtures e regras."""
    res_u = client.get("/api/rbac/usuarios")
    assert res_u.status_code == 200
    usuarios = res_u.json()
    emails = {u["email"]: u["cargo"] for u in usuarios}
    assert "maria.emp@acme.test" in emails
    assert emails["maria.emp@acme.test"] == "empregado"
    assert "bruno.fin@acme.test" in emails
    assert emails["bruno.fin@acme.test"] == "financeiro"
    assert "diretoria@acme.test" in emails
    assert emails["diretoria@acme.test"] == "diretoria"

    res_m = client.get("/api/rbac/matriz")
    assert res_m.status_code == 200
    matriz = res_m.json()
    assert "empregado" in matriz
    assert "financeiro" in matriz
    assert "diretoria" in matriz
    assert "CTR_2026-012" in matriz["empregado"]["documentos_proibidos"]
    assert matriz["empregado"]["ver_radar"] is False
    assert matriz["financeiro"]["ver_radar"] is True


def test_cena_empregado_vs_financeiro_multa_coworking():
    """Cena de 30s da Issue #22: Empregado não vê CTR; Financeiro obtém R$ 912,50 e citação do CTR."""
    pergunta = "Qual o valor da multa por inexecução no Apêndice B do contrato de coworking?"

    # 1. Empregado via Header X-Cargo
    res_emp = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta, "perfil": "empregado"},
        headers={"X-Cargo": "empregado"},
    )
    assert res_emp.status_code == 200
    dados_emp = res_emp.json()
    assert dados_emp["consta"] is False
    assert len(dados_emp["citacoes"]) == 0
    assert "CTR_2026-012" not in dados_emp["resposta"]
    assert "912,50" not in dados_emp["resposta"]

    # 2. Empregado via e-mail de fixture
    res_emp_email = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta, "email": "maria.emp@acme.test"},
    )
    assert res_emp_email.status_code == 200
    dados_emp_email = res_emp_email.json()
    assert dados_emp_email["consta"] is False
    assert len(dados_emp_email["citacoes"]) == 0

    # 3. Financeiro via Header X-Cargo
    res_fin = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta, "perfil": "financeiro"},
        headers={"X-Cargo": "financeiro"},
    )
    assert res_fin.status_code == 200
    dados_fin = res_fin.json()
    assert dados_fin["consta"] is True
    assert len(dados_fin["citacoes"]) > 0
    assert any(c["codigo"] == "CTR_2026-012" for c in dados_fin["citacoes"])
    assert "912,50" in dados_fin["resposta"]

    # 4. Financeiro via e-mail de fixture
    res_fin_email = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta, "email": "bruno.fin@acme.test"},
    )
    assert res_fin_email.status_code == 200
    dados_fin_email = res_fin_email.json()
    assert dados_fin_email["consta"] is True
    assert any(c["codigo"] == "CTR_2026-012" for c in dados_fin_email["citacoes"])
    assert "912,50" in dados_fin_email["resposta"]

    # 5. Pergunta geral sobre coworking: empregado bloqueado e financeiro permitido
    pergunta_geral = "Qual a multa do coworking?"
    res_emp_geral = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta_geral, "perfil": "empregado"},
        headers={"X-Cargo": "empregado"},
    )
    assert res_emp_geral.json()["consta"] is False
    assert len(res_emp_geral.json()["citacoes"]) == 0

    res_fin_geral = client.post(
        "/api/perguntar",
        json={"pergunta": pergunta_geral, "perfil": "financeiro"},
        headers={"X-Cargo": "financeiro"},
    )
    assert res_fin_geral.json()["consta"] is True
    assert len(res_fin_geral.json()["citacoes"]) > 0


def test_documentos_filtro_por_cargo():
    """GET /api/documentos com cargo filtra documentos proibidos."""
    # Empregado: CTR_2026-012 e NT_2026-018 ausentes
    res_emp = client.get("/api/documentos", headers={"X-Cargo": "empregado"})
    assert res_emp.status_code == 200
    docs_emp = res_emp.json()
    codigos_emp = [d["codigo"] for d in docs_emp]
    assert "CTR_2026-012" not in codigos_emp
    assert "NT_2026-018" not in codigos_emp
    assert "NT_2026-021" not in codigos_emp
    # Férias vigentes estão presentes
    assert "NG_111" in codigos_emp
    assert "PX_1111-001" in codigos_emp

    # Diretoria: todos os 13 documentos
    res_dir = client.get("/api/documentos", headers={"X-Cargo": "diretoria"})
    assert res_dir.status_code == 200
    docs_dir = res_dir.json()
    assert len(docs_dir) == 13
    codigos_dir = [d["codigo"] for d in docs_dir]
    assert "CTR_2026-012" in codigos_dir
    assert "NT_2026-018" in codigos_dir


def test_documento_bloqueio_403():
    """GET /api/documentos/{codigo} retorna 403 para documento fora da alçada do cargo."""
    # Empregado tentando acessar contrato de locação
    res_negado = client.get("/api/documentos/CTR_2026-012", headers={"X-Cargo": "empregado"})
    assert res_negado.status_code == 403
    assert "Acesso negado" in res_negado.json()["detail"]

    # Financeiro acessando o mesmo contrato
    res_ok = client.get("/api/documentos/CTR_2026-012", headers={"X-Cargo": "financeiro"})
    assert res_ok.status_code == 200
    assert res_ok.json()["codigo"] == "CTR_2026-012"

    # Empregado tentando acessar versão substituída de norma
    res_sub_negado = client.get(
        "/api/documentos/NG_111?versao=2.0.0",
        headers={"X-Cargo": "empregado"},
    )
    assert res_sub_negado.status_code == 403

    # RH pode acessar versão substituída de norma
    res_sub_ok = client.get(
        "/api/documentos/NG_111?versao=2.0.0",
        headers={"X-Cargo": "rh"},
    )
    assert res_sub_ok.status_code == 200
    assert res_sub_ok.json()["versao"] == "2.0.0"


def test_perspectivas_bloqueio_403():
    """GET /api/perspectivas/{id} bloqueia acesso a perspectivas não autorizadas."""
    # Empregado não pode acessar perspectiva financeira
    res_negado = client.get("/api/perspectivas/financeiro", headers={"X-Cargo": "empregado"})
    assert res_negado.status_code == 403

    # Empregado pode acessar perspectiva de pessoas
    res_ok = client.get("/api/perspectivas/pessoas", headers={"X-Cargo": "empregado"})
    assert res_ok.status_code == 200

    # Financeiro pode acessar perspectiva financeira
    res_fin = client.get("/api/perspectivas/financeiro", headers={"X-Cargo": "financeiro"})
    assert res_fin.status_code == 200


def test_radar_bloqueio_403():
    """GET /api/radar restrito a cargos com alçada (RH, Financeiro, Jurídico, Diretoria)."""
    # Empregado bloqueado
    res_emp = client.get("/api/radar", headers={"X-Cargo": "empregado"})
    assert res_emp.status_code == 403

    # Gestor bloqueado
    res_ges = client.get("/api/radar", headers={"X-Cargo": "gestor"})
    assert res_ges.status_code == 403

    # RH permitido
    res_rh = client.get("/api/radar", headers={"X-Cargo": "rh"})
    assert res_rh.status_code == 200
    assert "resumo" in res_rh.json()

    # Financeiro permitido
    res_fin = client.get("/api/radar", headers={"X-Cargo": "financeiro"})
    assert res_fin.status_code == 200

    # Diretoria permitida
    res_dir = client.get("/api/radar", headers={"X-Cargo": "diretoria"})
    assert res_dir.status_code == 200


def test_comparar_e_relatorio_bloqueio_403():
    """GET /api/comparar e GET /api/relatorio bloqueiam itens restritos."""
    # Comparar contrato proibido para empregado
    res_comp_negado = client.get(
        "/api/comparar?codigo=CTR_2026-012&de=1.0.0&para=1.0.0",
        headers={"X-Cargo": "empregado"},
    )
    assert res_comp_negado.status_code == 403

    # Comparar norma de férias permitida para empregado
    res_comp_ok = client.get(
        "/api/comparar?codigo=NG_111&de=2.0.0&para=3.0.0",
        headers={"X-Cargo": "rh"},
    )
    assert res_comp_ok.status_code == 200

    # Relatório de contrato proibido para empregado
    res_rel_negado = client.get(
        "/api/relatorio?codigo=CTR_2026-012",
        headers={"X-Cargo": "empregado"},
    )
    assert res_rel_negado.status_code == 403

    # Relatório de contrato permitido para financeiro
    res_rel_ok = client.get(
        "/api/relatorio?codigo=CTR_2026-012",
        headers={"X-Cargo": "financeiro"},
    )
    assert res_rel_ok.status_code == 200


def test_grafo_filtro_por_cargo():
    """GET /api/grafo filtra nós e arestas conforme cargo."""
    res_emp = client.get("/api/grafo", headers={"X-Cargo": "empregado"})
    assert res_emp.status_code == 200
    dados_emp = res_emp.json()
    codigos_emp = [n["codigo"] for n in dados_emp["nos"]]
    assert "CTR_2026-012" not in codigos_emp
    assert "NT_2026-018" not in codigos_emp

    res_dir = client.get("/api/grafo", headers={"X-Cargo": "diretoria"})
    assert res_dir.status_code == 200
    dados_dir = res_dir.json()
    codigos_dir = [n["codigo"] for n in dados_dir["nos"]]
    assert "CTR_2026-012" in codigos_dir


def test_auditoria_rbac():
    """Verifica que registros de auditoria JSONL são gerados sem PII."""
    assert AUDIT_FILE.exists()
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        linhas = [json.loads(line) for line in f if line.strip()]

    assert len(linhas) > 0
    ultimo = linhas[-1]
    assert "timestamp" in ultimo
    assert "cargo" in ultimo
    assert "endpoint" in ultimo
    assert "status" in ultimo
    # Sem PII nos campos do log
    assert "@" not in ultimo["cargo"]
