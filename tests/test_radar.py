"""Testes do Radar de Contradições (Issue #7, Adendo v0.2).

Prova de aceite da issue #7:
- o radar contém NG_111 30→45 com fontes NG_111@2.0.0 §2.3 e @3.0.0 §4.3.1;
- contém FM_1111-001 v1×v2;
- contém NG_012 como referencia_ausente;
- todo fonte.secao ∈ secoes[].id;
- ?perspectiva=pessoas filtra.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_radar_estrutura_completa():
    """GET /api/radar retorna gerado_em, resumo com divergente=2 e atencao=1, e 3 itens."""
    response = client.get("/api/radar")
    assert response.status_code == 200
    data = response.json()

    assert "gerado_em" in data
    assert "resumo" in data
    assert "itens" in data

    resumo = data["resumo"]
    assert resumo["divergente"] == 2
    assert resumo["atencao"] == 1

    itens = data["itens"]
    assert len(itens) == 3


def test_radar_contem_ng111_antecedencia_prova_aceite():
    """Prova de aceite #7: radar contém NG_111 30→45 com fontes NG_111@2.0.0 §2.3 e @3.0.0 §4.3.1."""
    response = client.get("/api/radar")
    assert response.status_code == 200
    data = response.json()

    item_ng = next(
        (it for it in data["itens"] if "NG_111" in it["id"] or any(f["codigo"] == "NG_111" for f in it["fontes"])),
        None,
    )
    assert item_ng is not None, "Item do NG_111 não encontrado no radar"
    assert item_ng["tipo"] == "versao_substituida"
    assert item_ng["status"] == "divergente"
    assert item_ng["codigo_ausente"] is None
    assert "pessoas" in item_ng["perspectivas"]

    # Prova de 30 -> 45
    texto_item = f"{item_ng['titulo']} {item_ng['explicacao']}".lower()
    assert "30" in texto_item and "45" in texto_item

    # Fontes NG_111@2.0.0 §2.3 e NG_111@3.0.0 §4.3.1
    fontes = item_ng["fontes"]
    assert len(fontes) == 2

    fonte_v3 = next((f for f in fontes if f["versao"] == "3.0.0"), None)
    assert fonte_v3 is not None, "Fonte NG_111@3.0.0 não encontrada"
    assert fonte_v3["codigo"] == "NG_111"
    assert fonte_v3["secao"] == "4.3.1"
    assert fonte_v3["camada"]["sigla"] == "NG"
    assert fonte_v3["camada"]["grupo"] == "Normativo"

    fonte_v2 = next((f for f in fontes if f["versao"] == "2.0.0"), None)
    assert fonte_v2 is not None, "Fonte NG_111@2.0.0 não encontrada"
    assert fonte_v2["codigo"] == "NG_111"
    assert fonte_v2["secao"] == "2.3"
    assert fonte_v2["camada"]["sigla"] == "NG"
    assert fonte_v2["camada"]["grupo"] == "Normativo"

    # Tema (C17)
    assert item_ng["tema"] is not None
    assert item_ng["tema"]["assunto"] == "ferias"
    assert item_ng["tema"]["serie"] == 1


def test_radar_contem_fm1111_001_v1_x_v2_prova_aceite():
    """Prova de aceite #7: radar contém FM_1111-001 v1×v2."""
    response = client.get("/api/radar")
    assert response.status_code == 200
    data = response.json()

    item_fm = next(
        (it for it in data["itens"] if "FM_1111-001" in it["id"] or any(f["codigo"] == "FM_1111-001" for f in it["fontes"])),
        None,
    )
    assert item_fm is not None, "Item FM_1111-001 v1×v2 não encontrado no radar"
    assert item_fm["tipo"] == "versao_substituida"
    assert item_fm["status"] == "divergente"
    assert item_fm["codigo_ausente"] is None
    assert "pessoas" in item_fm["perspectivas"]

    fontes = item_fm["fontes"]
    assert len(fontes) == 2
    versoes = {f["versao"] for f in fontes}
    assert "1.0.0" in versoes, "Versão 1.0.0 de FM_1111-001 não encontrada nas fontes"
    assert "2.0.0" in versoes, "Versão 2.0.0 de FM_1111-001 não encontrada nas fontes"

    for f in fontes:
        assert f["codigo"] == "FM_1111-001"
        assert f["camada"] is not None
        assert f["camada"]["sigla"] == "FM"
        assert f["camada"]["grupo"] == "Apoio"
        assert f["camada"]["subordinado_a"] == "NG_111"

    # Tema (C17)
    assert item_fm["tema"] is not None
    assert item_fm["tema"]["assunto"] == "ferias"


def test_radar_contem_ng012_referencia_ausente_prova_aceite():
    """Prova de aceite #7: radar contém NG_012 como referencia_ausente."""
    response = client.get("/api/radar")
    assert response.status_code == 200
    data = response.json()

    item_ausente = next(
        (it for it in data["itens"] if it["codigo_ausente"] == "NG_012" or "NG_012" in it["id"]),
        None,
    )
    assert item_ausente is not None, "Item NG_012 ausente não encontrado no radar"
    assert item_ausente["tipo"] == "referencia_ausente"
    assert item_ausente["status"] == "atencao"
    assert item_ausente["codigo_ausente"] == "NG_012"
    assert "juridico" in item_ausente["perspectivas"] or "financeiro" in item_ausente["perspectivas"]

    # Fonte comprovando a citação (NT_2026-018 §10)
    assert len(item_ausente["fontes"]) >= 1
    fonte_nt = item_ausente["fontes"][0]
    assert fonte_nt["codigo"] == "NT_2026-018"
    assert fonte_nt["versao"] == "1.0.0"
    assert fonte_nt["secao"] == "10"
    assert fonte_nt["camada"]["sigla"] == "NT"
    assert "NG_012" in fonte_nt["trecho"]

    # Tema (C17)
    assert item_ausente["tema"] is not None


def test_radar_todas_as_fontes_pertencem_ao_acervo_prova_aceite():
    """Prova de aceite #7: todo fonte.secao ∈ secoes[].id do acervo central."""
    response = client.get("/api/radar")
    assert response.status_code == 200
    data = response.json()

    for item in data["itens"]:
        assert item["tema"] is not None, f"Item {item['id']} sem tema"
        assert len(item["fontes"]) >= 1, f"Item {item['id']} sem fontes"

        for fonte in item["fontes"]:
            assert fonte["codigo"], f"Fonte com código vazio em {item['id']}"
            assert fonte["versao"], f"Fonte com versão vazia em {item['id']}"
            assert fonte["secao"], f"Fonte com seção vazia em {item['id']}"
            assert fonte["camada"] is not None, f"Fonte sem camada em {item['id']}"

            # Verificar existência no acervo
            doc_resp = client.get(f"/api/documentos/{fonte['codigo']}?versao={fonte['versao']}")
            assert doc_resp.status_code == 200, f"Documento {fonte['codigo']} v{fonte['versao']} não encontrado"
            doc = doc_resp.json()
            secao_ids = [s["id"] for s in doc["secoes"]]
            assert (
                fonte["secao"] in secao_ids
            ), f"Seção '{fonte['secao']}' não pertence a secoes[].id de {fonte['codigo']} v{fonte['versao']}. Disponíveis: {secao_ids}"


def test_radar_filtro_perspectiva_pessoas_prova_aceite():
    """Prova de aceite #7: ?perspectiva=pessoas filtra o radar."""
    response = client.get("/api/radar?perspectiva=pessoas")
    assert response.status_code == 200
    data = response.json()

    itens = data["itens"]
    assert len(itens) == 2, f"Esperados 2 itens para pessoas, obtidos {len(itens)}"

    # Contém NG_111 e FM_1111-001
    codigos_itens = {f["codigo"] for it in itens for f in it["fontes"]}
    assert "NG_111" in codigos_itens
    assert "FM_1111-001" in codigos_itens
    assert "NT_2026-018" not in codigos_itens

    # Resumo filtrado
    assert data["resumo"]["divergente"] == 2
    assert data["resumo"]["atencao"] == 0

    # Todos pertencem à perspectiva pessoas
    for it in itens:
        assert "pessoas" in it["perspectivas"]


def test_radar_filtro_outras_perspectivas():
    """Testa filtros de perspectiva financeiro, juridico e gestao."""
    # Financeiro contém o alerta de alçada NG_012
    resp_fin = client.get("/api/radar?perspectiva=financeiro")
    assert resp_fin.status_code == 200
    data_fin = resp_fin.json()
    assert len(data_fin["itens"]) == 1
    assert data_fin["itens"][0]["codigo_ausente"] == "NG_012"
    assert data_fin["resumo"]["divergente"] == 0
    assert data_fin["resumo"]["atencao"] == 1

    # Jurídico contém o alerta de alçada NG_012
    resp_jur = client.get("/api/radar?perspectiva=juridico")
    assert resp_jur.status_code == 200
    data_jur = resp_jur.json()
    assert len(data_jur["itens"]) == 1
    assert data_jur["itens"][0]["codigo_ausente"] == "NG_012"

    # Gestão não possui itens P0
    resp_ges = client.get("/api/radar?perspectiva=gestao")
    assert resp_ges.status_code == 200
    data_ges = resp_ges.json()
    assert len(data_ges["itens"]) == 0
    assert data_ges["resumo"]["divergente"] == 0
    assert data_ges["resumo"]["atencao"] == 0


def test_radar_perspectiva_invalida_retorna_404():
    """Adendo v0.1 D: perspectiva inexistente retorna 404."""
    response = client.get("/api/radar?perspectiva=invalida")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "não encontrada" in data["detail"].lower()
