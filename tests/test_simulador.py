"""Testes do Simulador "E se?" (Issue #8, Adendo v0.2).

Prova de aceite da Issue #8:
- GET /api/regras traz 45 com fonte §4.5.1;
- novo_valor=30: solicitação 2027-03-21 → 2027-04-05 com muda=true;
  impacto conflito_interno citando §4.5.3;
  revisar_documento inclui PX_1111-001 e não inclui nenhuma versão substituída;
- novo_valor=45: nada muda;
- Regra desconhecida retorna 404 e novo_valor=0 retorna 422;
- Cenário alçada de gerente R$ 18.000 → 20.000: impacto muda_aprovador no CTR_2026-012;
- Toda fonte.secao ∈ secoes[].id do acervo e carrega camada (C15, Adendo v0.1 A).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.acervo import get_acervo

client = TestClient(app)
acervo = get_acervo()


def test_get_regras_traz_45_com_fonte_4_5_1_prova_aceite():
    """Prova de aceite: GET /api/regras traz 45 com fonte §4.5.1."""
    response = client.get("/api/regras")
    assert response.status_code == 200
    regras = response.json()
    assert isinstance(regras, list)
    assert len(regras) >= 1

    regra_ferias = next((r for r in regras if r["id"] == "ferias_antecedencia_dias"), None)
    assert regra_ferias is not None, "Regra 'ferias_antecedencia_dias' não encontrada em /api/regras"
    assert regra_ferias["valor"] == 45
    assert regra_ferias["unidade"] == "dias"

    fonte = regra_ferias["fonte"]
    assert fonte["codigo"] == "NG_111"
    assert fonte["versao"] == "3.0.0"
    assert fonte["secao"] == "4.5.1"
    assert "45 dias" in fonte["trecho"]
    assert fonte["camada"] is not None
    assert fonte["camada"]["sigla"] == "NG"
    assert fonte["camada"]["grupo"] == "Normativo"


def test_simular_ferias_30_dias_prova_aceite():
    """Prova de aceite: novo_valor=30: solicitação 2027-03-21 → 2027-04-05 com muda=true;

    impacto conflito_interno citando §4.5.3;
    revisar_documento inclui PX_1111-001 e não inclui nenhuma versão substituída.
    """
    payload = {
        "regra": "ferias_antecedencia_dias",
        "novo_valor": 30,
    }
    response = client.post("/api/simular", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["regra"] == "ferias_antecedencia_dias"
    assert data["valor_atual"] == 45
    assert data["novo_valor"] == 30
    assert data["unidade"] == "dias"
    assert data["aviso"] == "Simulação hipotética: não altera os documentos."

    # Linha do tempo: solicitação 2027-03-21 -> 2027-04-05 com muda=true
    linha = data["linha_do_tempo"]
    solic = next((m for m in linha if m["marco"] == "Solicitação"), None)
    assert solic is not None, "Marco 'Solicitação' não encontrado na linha do tempo"
    assert solic["antes"] == "2027-03-21"
    assert solic["depois"] == "2027-04-05"
    assert solic["muda"] is True
    assert solic["fonte"]["codigo"] == "NG_111"
    assert solic["fonte"]["versao"] == "3.0.0"
    assert solic["fonte"]["secao"] == "4.5.1"

    # Outros marcos não mudam
    aviso_marco = next((m for m in linha if "Aviso" in m["marco"]), None)
    assert aviso_marco is not None
    assert aviso_marco["muda"] is False

    # Impacto conflito_interno citando §4.5.3
    impactos = data["impactos"]
    conflito = next((i for i in impactos if i["tipo"] == "conflito_interno"), None)
    assert conflito is not None, "Impacto 'conflito_interno' não retornado"
    assert "D-35" in conflito["descricao"]
    assert "D-30" in conflito["descricao"]

    fontes_conflito = conflito["fontes"]
    assert any(f["codigo"] == "NG_111" and f["secao"] == "4.5.3" for f in fontes_conflito), (
        "Conflito interno deve citar NG_111 §4.5.3"
    )

    # revisar_documento inclui PX_1111-001 e não inclui nenhuma versão substituída
    revisar_itens = [i for i in impactos if i["tipo"] == "revisar_documento"]
    assert len(revisar_itens) > 0, "Deve haver itens de revisar_documento"

    px_item = next((i for i in revisar_itens if i["codigo"] == "PX_1111-001"), None)
    assert px_item is not None, "revisar_documento deve incluir PX_1111-001"
    assert px_item["versao"] == "1.0.0"
    assert any(f["secao"] == "8.2" for f in px_item["fontes"])

    # Nenhuma versão substituída pode estar em revisar_documento
    for item in revisar_itens:
        doc = acervo.buscar(item["codigo"], item["versao"])
        assert doc is not None, f"Documento {item['codigo']} v{item['versao']} não encontrado no acervo"
        assert doc.substituido is False, (
            f"Documento substituído {item['codigo']} v{item['versao']} foi incluído em revisar_documento"
        )
        assert item["versao"] != "2.0.0" if item["codigo"] == "NG_111" else True
        assert item["versao"] != "1.0.0" if item["codigo"] == "FM_1111-001" else True

    # Códigos esperados vigentes
    codigos_revisar = {i["codigo"] for i in revisar_itens}
    assert {"NG_111", "PX_1111-001", "FM_1111-001", "TB_1111-001", "FL_1111-001"}.issubset(codigos_revisar)

    # Resumo
    resumo = data["resumo"]
    assert any("05/04/2027" in r or "D-30" in r for r in resumo)
    assert any("D-35" in r for r in resumo)
    assert any("revisão" in r for r in resumo)


def test_simular_ferias_45_dias_nada_muda_prova_aceite():
    """Prova de aceite: novo_valor=45: nada muda."""
    payload = {
        "regra": "ferias_antecedencia_dias",
        "novo_valor": 45,
    }
    response = client.post("/api/simular", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["regra"] == "ferias_antecedencia_dias"
    assert data["valor_atual"] == 45
    assert data["novo_valor"] == 45

    # Nenhum marco muda
    for marco in data["linha_do_tempo"]:
        assert marco["muda"] is False
        assert marco["antes"] == marco["depois"]

    # Nenhum impacto
    assert data["impactos"] == []
    assert len(data["resumo"]) >= 1


def test_regra_desconhecida_retorna_404_prova_aceite():
    """Prova de aceite: Regra desconhecida retorna 404."""
    payload = {
        "regra": "regra_inexistente_xyz",
        "novo_valor": 30,
    }
    response = client.post("/api/simular", json=payload)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "regra_inexistente_xyz" in detail


def test_novo_valor_zero_retorna_422_prova_aceite():
    """Prova de aceite: novo_valor=0 retorna 422."""
    payload = {
        "regra": "ferias_antecedencia_dias",
        "novo_valor": 0,
    }
    response = client.post("/api/simular", json=payload)
    assert response.status_code == 422


def test_novo_valor_fora_de_faixa_retorna_422():
    """novo_valor negativo ou maior que 90 para férias retorna 422."""
    # Negativo
    resp_neg = client.post("/api/simular", json={"regra": "ferias_antecedencia_dias", "novo_valor": -5})
    assert resp_neg.status_code == 422

    # Maior que 90
    resp_alto = client.post("/api/simular", json={"regra": "ferias_antecedencia_dias", "novo_valor": 120})
    assert resp_alto.status_code == 422


def test_cenario_alcada_gerente_18000_para_20000():
    """Cenário 2 (atualização aprovada 12/11): regra alcada_gerente_max 18.000 → 20.000.

    Impacto muda_aprovador no CTR_2026-012 (R$ 18.250 deixa de exigir diretor).
    """
    # 1. GET /api/regras traz a regra de alçada
    resp_regras = client.get("/api/regras")
    assert resp_regras.status_code == 200
    regras = resp_regras.json()
    regra_alcada = next((r for r in regras if r["id"] == "alcada_gerente_max"), None)
    assert regra_alcada is not None
    assert regra_alcada["valor"] == 18000
    assert regra_alcada["unidade"] == "BRL"
    assert regra_alcada["fonte"]["codigo"] == "NT_2026-018"
    assert regra_alcada["fonte"]["secao"] == "Anexo F"

    # 2. Simular 20.000
    resp_sim = client.post(
        "/api/simular",
        json={"regra": "alcada_gerente_max", "novo_valor": 20000},
    )
    assert resp_sim.status_code == 200
    data = resp_sim.json()
    assert data["regra"] == "alcada_gerente_max"
    assert data["valor_atual"] == 18000
    assert data["novo_valor"] == 20000
    assert data["unidade"] == "BRL"

    muda_aprov = next((i for i in data["impactos"] if i["tipo"] == "muda_aprovador"), None)
    assert muda_aprov is not None, "Impacto 'muda_aprovador' não encontrado"
    assert muda_aprov["codigo"] == "CTR_2026-012"
    assert muda_aprov["antes"] == "Diretor (DIRAF)"
    assert muda_aprov["depois"] == "Gerente"

    # Fontes do impacto
    codigos_fontes = [f["codigo"] for f in muda_aprov["fontes"]]
    assert "NT_2026-018" in codigos_fontes
    assert "CTR_2026-012" in codigos_fontes

    # 3. Simular 18.000 (sem alteração)
    resp_same = client.post(
        "/api/simular",
        json={"regra": "alcada_gerente_max", "novo_valor": 18000},
    )
    assert resp_same.status_code == 200
    assert resp_same.json()["impactos"] == []


def test_todas_as_fontes_tem_secao_valida_e_camada():
    """Garante que toda fonte retornada em /api/regras e /api/simular tem secao real e camada."""
    # 1. Regras
    resp_regras = client.get("/api/regras")
    regras = resp_regras.json()
    for r in regras:
        fonte = r["fonte"]
        doc = acervo.buscar(fonte["codigo"], fonte["versao"])
        assert doc is not None
        secoes_ids = [s.id for s in doc.secoes]
        assert fonte["secao"] in secoes_ids, f"Seção {fonte['secao']} não existe em {fonte['codigo']} v{fonte['versao']}"
        assert fonte["camada"] is not None
        assert "sigla" in fonte["camada"]

    # 2. Simulação
    resp_sim = client.post("/api/simular", json={"regra": "ferias_antecedencia_dias", "novo_valor": 30})
    data = resp_sim.json()

    # Fontes na linha do tempo
    for marco in data["linha_do_tempo"]:
        fonte = marco["fonte"]
        doc = acervo.buscar(fonte["codigo"], fonte["versao"])
        assert doc is not None
        secoes_ids = [s.id for s in doc.secoes]
        assert fonte["secao"] in secoes_ids

    # Fontes nos impactos
    for imp in data["impactos"]:
        for fonte in imp["fontes"]:
            doc = acervo.buscar(fonte["codigo"], fonte["versao"])
            assert doc is not None
            secoes_ids = [s.id for s in doc.secoes]
            assert fonte["secao"] in secoes_ids
