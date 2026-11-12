"""Testes dos endpoints de Inteligência por perspectiva (Issue #4).

Cobre a prova de aceite da issue #4 e Adendos v0.1 e v0.3:
- GET /api/perspectivas
- GET /api/perspectivas/{id} (financeiro, pessoas, juridico, gestao)
- GET /api/grafo
- GET /api/comparar
- GET /api/relatorio
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_listar_perspectivas():
    """GET /api/perspectivas retorna as 4 perspectivas do contrato."""
    response = client.get("/api/perspectivas")
    assert response.status_code == 200
    perspectivas = response.json()
    assert len(perspectivas) == 4
    ids = [p["id"] for p in perspectivas]
    assert ids == ["juridico", "financeiro", "pessoas", "gestao"]
    nomes = [p["nome"] for p in perspectivas]
    assert "Jurídico e Contratos" in nomes
    assert "Financeiro" in nomes
    assert "Pessoas (RH)" in nomes
    assert "Gestão e Inovação" in nomes


def test_perspectiva_financeiro_prova_aceite():
    """Prova de aceite #4: financeiro contém R$ 18.250,00 (CTR_2026-012, Cláusula Sétima),

    multa R$ 912,50 (Apêndice B) e alçada de diretor citando NT_2026-018.
    """
    response = client.get("/api/perspectivas/financeiro")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "financeiro"
    assert data["nome"] == "Financeiro"

    # 1. R$ 18.250,00 em destaques ou valores com fonte CTR_2026-012 e Cláusula Sétima
    destaque_global = next(
        (d for d in data["destaques"] if "18.250,00" in (d.get("valor") or "")),
        None,
    )
    assert destaque_global is not None, "Destaque R$ 18.250,00 não encontrado"
    assert destaque_global["fonte"]["codigo"] == "CTR_2026-012"
    assert destaque_global["fonte"]["secao"] == "Cláusula Sétima"
    assert destaque_global["fonte"]["camada"]["sigla"] == "CTR"
    assert destaque_global["tema"] is not None

    valor_global = next(
        (v for v in data["valores"] if v["numero"] == 18250.0),
        None,
    )
    assert valor_global is not None, "Valor numérico 18250.0 não encontrado"
    assert valor_global["fonte"]["codigo"] == "CTR_2026-012"
    assert valor_global["fonte"]["secao"] == "Cláusula Sétima"

    # 2. Multa R$ 912,50 com fonte Apêndice B do CTR_2026-012 (Adendo v0.1 E)
    multa_item = next(
        (v for v in data["valores"] if v["numero"] == 912.5),
        None,
    )
    assert multa_item is not None, "Multa R$ 912,50 não encontrada em valores"
    assert multa_item["fonte"]["codigo"] == "CTR_2026-012"
    assert multa_item["fonte"]["secao"] == "Apêndice B"
    assert multa_item["fonte"]["camada"]["sigla"] == "CTR"
    assert multa_item["tema"] is not None

    # 3. Alçada de diretor citando NT_2026-018
    resp_diretor = next(
        (
            r
            for r in data["responsaveis"]
            if r["papel"] == "DIRAF" and r["fonte"]["codigo"] == "NT_2026-018"
        ),
        None,
    )
    assert resp_diretor is not None, "Alçada DIRAF citando NT_2026-018 não encontrada em responsáveis"
    assert resp_diretor["fonte"]["camada"]["sigla"] == "NT"
    assert "diretor" in resp_diretor["responsabilidade"].lower()

    # 4. Prazos do financeiro incluem 25/11/2026 e 30/11/2026
    datas_prazos = [p["data"] for p in data["prazos"] if p.get("data")]
    assert "2026-11-25" in datas_prazos
    assert "2026-11-30" in datas_prazos


def test_perspectiva_pessoas_prova_aceite():
    """Prova de aceite #4: pessoas contém marcos D-45/D-35/D-30/D-20/D-3 do PX_1111-001

    e destaque de antecedência 45 dias com fonte_anterior e aviso (Adendo v0.1 F).
    """
    response = client.get("/api/perspectivas/pessoas")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "pessoas"
    assert data["nome"] == "Pessoas (RH)"

    # 1. Marcos D-45, D-35, D-30, D-20, D-3 do PX_1111-001 (Adendo v0.1 B)
    marcos_encontrados = {
        p.get("marco"): p
        for p in data["prazos"]
        if p.get("marco") and p["fonte"]["codigo"] == "PX_1111-001"
    }
    for m in ["D-45", "D-35", "D-30", "D-20", "D-3"]:
        assert m in marcos_encontrados, f"Marco {m} não encontrado nos prazos de pessoas"
        item_m = marcos_encontrados[m]
        assert item_m["fonte"]["secao"] in ["Anexo B", "Anexo D"]
        assert item_m["fonte"]["camada"]["sigla"] == "PX"
        assert item_m["fonte"]["camada"]["subordinado_a"] == "NG_111"
        assert item_m["tema"] is not None

    # 2. Destaque antecedência 45 dias com fonte NG_111@3.0.0 §4.3.1, fonte_anterior NG_111@2.0.0 §2.3 e aviso (Adendo v0.1 F)
    destaque_ant = next(
        (d for d in data["destaques"] if "45" in (d.get("valor") or "") or "Antecedência" in d["titulo"]),
        None,
    )
    assert destaque_ant is not None, "Destaque antecedência 45 dias não encontrado"
    assert destaque_ant["fonte"]["codigo"] == "NG_111"
    assert destaque_ant["fonte"]["versao"] == "3.0.0"
    assert destaque_ant["fonte"]["secao"] == "4.3.1"
    assert destaque_ant["fonte"]["camada"]["sigla"] == "NG"

    assert destaque_ant["fonte_anterior"] is not None, "fonte_anterior ausente no destaque"
    assert destaque_ant["fonte_anterior"]["codigo"] == "NG_111"
    assert destaque_ant["fonte_anterior"]["versao"] == "2.0.0"
    assert destaque_ant["fonte_anterior"]["secao"] == "2.3"
    assert destaque_ant["fonte_anterior"]["camada"]["sigla"] == "NG"

    assert destaque_ant["aviso"] is not None, "aviso ausente no destaque"
    assert "30" in destaque_ant["aviso"]
    assert "v2" in destaque_ant["aviso"].lower() or "substituída" in destaque_ant["aviso"].lower()


def test_perspectiva_juridico_prova_aceite():
    """Jurídico contém rescisão até o 90º dia com multa de 1 aluguel (CTR_2026-012)

    e alçadas com amparo na NG_012 (NT_2026-018).
    """
    response = client.get("/api/perspectivas/juridico")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "juridico"

    destaque_resc = next(
        (d for d in data["destaques"] if "rescisão" in d["titulo"].lower()),
        None,
    )
    assert destaque_resc is not None
    assert destaque_resc["fonte"]["codigo"] == "CTR_2026-012"
    assert destaque_resc["fonte"]["secao"] == "Cláusula Décima Terceira"

    multa_resc = next(
        (v for v in data["valores"] if "rescisão" in v["rotulo"].lower()),
        None,
    )
    assert multa_resc is not None
    assert multa_resc["numero"] == 3650.0
    assert multa_resc["fonte"]["secao"] in ["Cláusula Décima Terceira", "Apêndice B"]


def test_perspectiva_gestao_prova_aceite():
    """Gestão contém orçamento de R$ 96.000,00 (NT_2026-021 · v1.0.0 · 4.5)."""
    response = client.get("/api/perspectivas/gestao")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "gestao"

    valor_orc = next(
        (v for v in data["valores"] if v["numero"] == 96000.0),
        None,
    )
    assert valor_orc is not None, "Orçamento R$ 96.000,00 não encontrado em gestão"
    assert valor_orc["fonte"]["codigo"] == "NT_2026-021"
    assert valor_orc["fonte"]["secao"] == "4.5"
    assert valor_orc["fonte"]["camada"]["sigla"] == "NT"


def test_perspectiva_inexistente_retorna_404():
    """Adendo v0.1 D: 404 {"detail":"…"} para perspectiva inexistente."""
    response = client.get("/api/perspectivas/inexistente")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "não encontrada" in data["detail"].lower()


def test_comparar_ng111_v2_v3_prova_aceite():
    """Prova de aceite #4: /api/comparar?codigo=NG_111&de=2.0.0&para=3.0.0

    lista ao menos a mudança de antecedência.
    """
    response = client.get("/api/comparar?codigo=NG_111&de=2.0.0&para=3.0.0")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "NG_111"
    assert data["de"] == "2.0.0"
    assert data["para"] == "3.0.0"

    # Mudanças por seção
    mudancas = data["mudancas"]
    assert len(mudancas) >= 1
    secoes_alteradas = [m["secao"] for m in mudancas]
    assert "2.3" in secoes_alteradas

    # Resumo com antecedência (30 para 45)
    resumo_texto = " ".join(data["resumo"]).lower()
    assert "antecedência" in resumo_texto or "antecedencia" in resumo_texto
    assert "30" in resumo_texto and "45" in resumo_texto


def test_comparar_sem_ambos_arquivos_retorna_404():
    """Adendo v0.1 D: comparar sem os dois arquivos de versão -> 404 (ex: RG_1100 v1 não está no acervo)."""
    response = client.get("/api/comparar?codigo=RG_1100&de=1.0.0&para=2.0.0")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data

    response_inex = client.get("/api/comparar?codigo=DOC_INEXISTENTE&de=1.0.0&para=2.0.0")
    assert response_inex.status_code == 404


def test_grafo_prova_aceite():
    """Prova de aceite #4: grafo liga PX_1111-001->NG_111 e CTR_2026-012<->NT_2026-018.

    Nós têm existe_no_acervo, tema e camada; ausentes NG_012 e NG_010 aparecem sem versão.
    """
    response = client.get("/api/grafo")
    assert response.status_code == 200
    data = response.json()
    nos = data["nos"]
    arestas = data["arestas"]

    # Validar nós
    nos_por_id = {n["id"]: n for n in nos}
    assert "NG_111@3.0.0" in nos_por_id
    assert "PX_1111-001@1.0.0" in nos_por_id
    assert "CTR_2026-012@1.0.0" in nos_por_id
    assert "NT_2026-018@1.0.0" in nos_por_id

    # Documentos ausentes sem versão e com existe_no_acervo=False (Adendo v0.1 C, RF14)
    assert "NG_012" in nos_por_id
    assert nos_por_id["NG_012"]["existe_no_acervo"] is False
    assert nos_por_id["NG_012"]["versao"] is None

    assert "NG_010" in nos_por_id
    assert nos_por_id["NG_010"]["existe_no_acervo"] is False
    assert nos_por_id["NG_010"]["versao"] is None

    # Todos os nós carregam tema e camada (C17)
    for n in nos:
        assert n["camada"] is not None, f"Nó {n['id']} sem camada"
        assert n["tema"] is not None, f"Nó {n['id']} sem tema"

    # Validar arestas: PX_1111-001 -> NG_111
    aresta_px_ng = next(
        (a for a in arestas if a["de"] == "PX_1111-001@1.0.0" and a["para"] == "NG_111@3.0.0"),
        None,
    )
    assert aresta_px_ng is not None, "Aresta PX_1111-001@1.0.0 -> NG_111@3.0.0 não encontrada"
    assert aresta_px_ng["tipo"] == "vinculado_a"

    # Validar arestas bidirecionais: CTR_2026-012 <-> NT_2026-018
    aresta_ctr_nt = next(
        (a for a in arestas if a["de"] == "CTR_2026-012@1.0.0" and a["para"] == "NT_2026-018@1.0.0"),
        None,
    )
    aresta_nt_ctr = next(
        (a for a in arestas if a["de"] == "NT_2026-018@1.0.0" and a["para"] == "CTR_2026-012@1.0.0"),
        None,
    )
    assert aresta_ctr_nt is not None, "Aresta CTR_2026-012 -> NT_2026-018 não encontrada"
    assert aresta_nt_ctr is not None, "Aresta NT_2026-018 -> CTR_2026-012 não encontrada"
    assert aresta_ctr_nt["tipo"] == "referencia"
    assert aresta_nt_ctr["tipo"] == "referencia"

    # RF14: 5 arestas apontam para a ausente NG_012
    arestas_ng_012 = [a for a in arestas if a["para"] == "NG_012"]
    assert len(arestas_ng_012) == 5, f"Esperadas 5 arestas para NG_012, encontradas {len(arestas_ng_012)}"

    # Aresta de substituição NG_111@3.0.0 -> NG_111@2.0.0
    aresta_sub = next(
        (a for a in arestas if a["de"] == "NG_111@3.0.0" and a["para"] == "NG_111@2.0.0"),
        None,
    )
    assert aresta_sub is not None
    assert aresta_sub["tipo"] == "substitui"


def test_relatorio_por_perspectiva():
    """GET /api/relatorio?perspectiva=juridico retorna relatório com fontes e camada."""
    response = client.get("/api/relatorio?perspectiva=juridico")
    assert response.status_code == 200
    data = response.json()
    assert "titulo" in data
    assert "gerado_em" in data
    assert data["perspectiva"] == "juridico"
    assert len(data["secoes"]) >= 1

    for sec in data["secoes"]:
        assert "titulo" in sec
        assert "itens" in sec
        for item in sec["itens"]:
            assert "texto" in item
            assert "fonte" in item
            fonte = item["fonte"]
            assert fonte["codigo"]
            assert fonte["secao"]
            assert fonte["camada"] is not None


def test_relatorio_por_codigo():
    """GET /api/relatorio?codigo=CTR_2026-012 retorna relatório do documento."""
    response = client.get("/api/relatorio?codigo=CTR_2026-012")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "CTR_2026-012"
    assert len(data["secoes"]) >= 1


def test_relatorio_erros():
    """GET /api/relatorio sem parâmetros retorna 422; perspectiva inválida ou código inexistente retorna 404."""
    resp_sem_param = client.get("/api/relatorio")
    assert resp_sem_param.status_code == 422

    resp_persp_inv = client.get("/api/relatorio?perspectiva=inexistente")
    assert resp_persp_inv.status_code == 404

    resp_cod_inv = client.get("/api/relatorio?codigo=DOC_INEXISTENTE")
    assert resp_cod_inv.status_code == 404


def test_todas_as_fontes_das_perspectivas_existem_no_acervo():
    """Regra contratual de ouro: todo item extraído carrega fonte com codigo,

    versao e secao existentes no acervo (Adendo v0.1 A e E).
    """
    for p_id in ["juridico", "financeiro", "pessoas", "gestao"]:
        resp = client.get(f"/api/perspectivas/{p_id}")
        assert resp.status_code == 200
        p_data = resp.json()

        for cat in ["destaques", "valores", "prazos", "responsaveis", "riscos"]:
            itens = p_data.get(cat, [])
            for item in itens:
                assert "fonte" in item, f"Item sem fonte em {p_id} {cat}: {item}"
                fonte = item["fonte"]
                assert fonte["codigo"], f"Código vazio em {fonte}"
                assert fonte["versao"], f"Versão vazia em {fonte}"
                assert fonte["secao"], f"Seção vazia em {fonte}"
                assert fonte["camada"] is not None, f"Camada ausente em {fonte}"
                assert "tema" in item and item["tema"] is not None, f"Tema ausente em {item}"

                # Conferir no endpoint de documentos se a seção existe
                doc_resp = client.get(f"/api/documentos/{fonte['codigo']}?versao={fonte['versao']}")
                assert doc_resp.status_code == 200, f"Doc {fonte['codigo']} v{fonte['versao']} não encontrado"
                doc = doc_resp.json()
                secao_ids = [s["id"] for s in doc["secoes"]]
                assert (
                    fonte["secao"] in secao_ids
                ), f"Seção '{fonte['secao']}' não encontrada em {fonte['codigo']} v{fonte['versao']}. Seções disponíveis: {secao_ids}"

                # Se houver fonte anterior, também deve existir no acervo
                if "fonte_anterior" in item and item["fonte_anterior"]:
                    fa = item["fonte_anterior"]
                    doc_a_resp = client.get(f"/api/documentos/{fa['codigo']}?versao={fa['versao']}")
                    assert doc_a_resp.status_code == 200
                    doc_a = doc_a_resp.json()
                    secao_a_ids = [s["id"] for s in doc_a["secoes"]]
                    assert (
                        fa["secao"] in secao_a_ids
                    ), f"Seção anterior '{fa['secao']}' não encontrada em {fa['codigo']} v{fa['versao']}"


def test_curadoria_toda_fonte_confere_com_o_acervo():
    """Nunca valor sem fonte: código, versão, seção e trecho de toda curadoria existem no acervo."""
    from app.inteligencia import InteligenciaService

    assert InteligenciaService().erros_curadoria() == []


def test_trecho_inventado_e_descartado():
    """Uma fonte cujo trecho não está na seção é recusada pela validação."""
    from app.inteligencia import InteligenciaService

    svc = InteligenciaService()
    erro = svc.validar_fonte(
        {"codigo": "NG_1130", "versao": "1.0.0", "secao": "4.9", "trecho": "o orçamento anual aprovado pela DIRAF"}
    )
    assert erro and "trecho não consta" in erro


def test_tema_das_fontes_vem_do_documento_citado():
    """tema.assunto é a pasta do documento (ferias/inovacao/locacao), não o id da perspectiva."""
    for pid in ("financeiro", "pessoas", "juridico", "gestao"):
        data = client.get(f"/api/perspectivas/{pid}").json()
        for grupo in ("destaques", "valores", "prazos", "responsaveis", "riscos"):
            for item in data[grupo]:
                doc = client.get(
                    f"/api/documentos/{item['fonte']['codigo']}", params={"versao": item["fonte"]["versao"]}
                ).json()
                assert item["tema"]["assunto"] == doc["assunto"], (pid, grupo, item["fonte"])
                assert item["fonte"]["camada"] == doc["camada"]


def test_grafo_ng010_vem_do_texto_da_versao_substituida():
    """NG_010 é citada só no item 4.1 da NG_111 v2.0.0; a aresta sai do texto, não de lista fixa."""
    data = client.get("/api/grafo").json()
    citantes = {a["de"] for a in data["arestas"] if a["para"] == "NG_010"}
    assert citantes == {"NG_111@2.0.0"}
