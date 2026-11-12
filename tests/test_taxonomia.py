import pytest
from fastapi.testclient import TestClient
from app.main import app, acervo
from app.models import Camada, Tema, Fonte, Citacao
from app.taxonomia import (
    derivar_camada,
    derivar_tema,
    formatar_camada,
    enriquecer_citacao,
    enriquecer_fonte,
    CATEGORIAS_CATALOGO,
    SERIES_CATALOGO,
)

client = TestClient(app)


# ==============================================================================
# Prova de Aceite da Issue #13
# ==============================================================================


def test_aceite_px_1111_001_camada():
    """Prova de aceite 1: PX_1111-001 -> 'PX · Procedimento · Normativo · subordinado a NG_111'."""
    camada = derivar_camada("PX_1111-001")
    assert camada.sigla == "PX"
    assert camada.tipo_nome == "Procedimento"
    assert camada.grupo == "Normativo"
    assert camada.subordinado_a == "NG_111"
    assert camada.rotulo() == "PX · Procedimento · Normativo · subordinado a NG_111"
    assert str(camada) == "PX · Procedimento · Normativo · subordinado a NG_111"

    # Verificação via API
    resp = client.get("/api/documentos/PX_1111-001")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["camada"]["sigla"] == "PX"
    assert doc["camada"]["tipo_nome"] == "Procedimento"
    assert doc["camada"]["grupo"] == "Normativo"
    assert doc["camada"]["subordinado_a"] == "NG_111"


def test_aceite_fl_1111_001_subordinado_a_px():
    """Prova de aceite 2: FL_1111-001 subordinado a PX_1111-001."""
    camada = derivar_camada("FL_1111-001", vinculado_a="PX_1111-001")
    assert camada.sigla == "FL"
    assert camada.tipo_nome == "Fluxo"
    assert camada.grupo == "Apoio"
    assert camada.subordinado_a == "PX_1111-001"
    assert camada.rotulo() == "FL · Fluxo · Apoio · subordinado a PX_1111-001"

    # Verificação via API
    resp = client.get("/api/documentos/FL_1111-001")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["camada"]["sigla"] == "FL"
    assert doc["camada"]["grupo"] == "Apoio"
    assert doc["camada"]["subordinado_a"] == "PX_1111-001"


def test_aceite_fm_1111_001_v2_grupo_apoio():
    """Prova de aceite 3: FM_1111-001 v2.0.0 grupo Apoio."""
    camada = derivar_camada("FM_1111-001", tipo_nome="Formulário", vinculado_a="NG_111")
    assert camada.sigla == "FM"
    assert camada.grupo == "Apoio"
    assert camada.subordinado_a == "NG_111"

    # Verificação via API na versão 2.0.0
    resp = client.get("/api/documentos/FM_1111-001?versao=2.0.0")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["camada"]["sigla"] == "FM"
    assert doc["camada"]["tipo_nome"] == "Formulário"
    assert doc["camada"]["grupo"] == "Apoio"
    assert doc["camada"]["subordinado_a"] == "NG_111"


def test_aceite_ctr_2026_012_grupo_instrumento():
    """Prova de aceite 4: CTR_2026-012 grupo Instrumento."""
    camada = derivar_camada("CTR_2026-012")
    assert camada.sigla == "CTR"
    assert camada.tipo_nome == "Contrato"
    assert camada.grupo == "Instrumento"
    assert camada.subordinado_a is None
    assert camada.rotulo() == "CTR · Contrato · Instrumento"

    # Verificação via API
    resp = client.get("/api/documentos/CTR_2026-012")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["camada"]["sigla"] == "CTR"
    assert doc["camada"]["tipo_nome"] == "Contrato"
    assert doc["camada"]["grupo"] == "Instrumento"
    assert doc["camada"]["subordinado_a"] is None


def test_aceite_filtrar_serie_1_devolve_7_docs_ferias():
    """Prova de aceite 5: filtrar série 1 (Gente e Cultura) devolve os 7 documentos de férias (5 vigentes + 2 substituídos)."""
    # 1. Via repositório direto
    docs_repo = acervo.listar(serie=1)
    assert len(docs_repo) == 7
    vigentes_repo = [d for d in docs_repo if not d.substituido]
    substituidos_repo = [d for d in docs_repo if d.substituido]
    assert len(vigentes_repo) == 5
    assert len(substituidos_repo) == 2
    for d in docs_repo:
        assert d.assunto == "ferias"
        assert d.tema.serie == 1
        assert d.tema.serie_nome == "Gente e Cultura"

    # 2. Via endpoint da API GET /api/documentos?serie=1
    resp = client.get("/api/documentos?serie=1")
    assert resp.status_code == 200
    docs_api = resp.json()
    assert len(docs_api) == 7

    vigentes_api = [d for d in docs_api if not d["substituido"]]
    substituidos_api = [d for d in docs_api if d["substituido"]]
    assert len(vigentes_api) == 5
    assert len(substituidos_api) == 2

    # Códigos esperados no grupo de férias
    codigos_vigentes = {d["codigo"] for d in vigentes_api}
    assert codigos_vigentes == {"FL_1111-001", "FM_1111-001", "NG_111", "PX_1111-001", "TB_1111-001"}

    codigos_substituidos = {f"{d['codigo']}@v{d['versao']}" for d in substituidos_api}
    assert codigos_substituidos == {"FM_1111-001@v1.0.0", "NG_111@v2.0.0"}


# ==============================================================================
# Testes Detalhados de Taxonomia e Casos de Borda
# ==============================================================================


def test_todos_documentos_possuem_camada_e_tema():
    """Garante que todos os documentos do acervo possuem camada e tema válidos."""
    resp = client.get("/api/documentos")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 13

    for doc in docs:
        assert "camada" in doc, f"Documento {doc['codigo']} sem camada"
        camada = doc["camada"]
        assert camada["sigla"]
        assert camada["tipo_nome"]
        assert camada["grupo"] in {
            "Normativo",
            "Operacional",
            "Apoio",
            "Programa",
            "Temporário",
            "Instrumento",
            "Residual",
        }

        assert "tema" in doc, f"Documento {doc['codigo']} sem tema"
        tema = doc["tema"]
        assert tema["assunto"] in {"ferias", "inovacao", "locacao"}
        assert tema["confirmado_por"] == "regra"


def test_caso_ng_1130_serie_null_com_observacao():
    """Conforme catálogo §5 e lacuna L-f: NG_1130 tem serie = null com observacao."""
    tema = derivar_tema("NG_1130", assunto="inovacao")
    assert tema.serie is None
    assert tema.serie_nome is None
    assert tema.observacao is not None
    assert "Catálogo §5" in tema.observacao

    # Via API
    resp = client.get("/api/documentos/NG_1130")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["tema"]["serie"] is None
    assert doc["tema"]["serie_nome"] is None
    assert doc["tema"]["observacao"] is not None
    assert doc["camada"]["sigla"] == "NG"
    assert doc["camada"]["grupo"] == "Normativo"
    assert doc["camada"]["subordinado_a"] is None


def test_caso_px_1130_001_subordinado_a_ng_1130():
    """PX_1130-001 subordinado a NG_1130."""
    resp = client.get("/api/documentos/PX_1130-001")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["camada"]["sigla"] == "PX"
    assert doc["camada"]["grupo"] == "Normativo"
    assert doc["camada"]["subordinado_a"] == "NG_1130"
    assert doc["tema"]["serie"] is None
    assert doc["tema"]["observacao"] is not None


def test_caso_rg_1100_serie_11_programas_institucionais():
    """RG_1100 conforme catálogo §2 tem Série 11 (Programas Institucionais)."""
    tema = derivar_tema("RG_1100", assunto="inovacao")
    assert tema.serie == 11
    assert tema.serie_nome == "Programas Institucionais"
    assert tema.observacao is None

    # Via API
    resp = client.get("/api/documentos/RG_1100")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["tema"]["serie"] == 11
    assert doc["tema"]["serie_nome"] == "Programas Institucionais"
    assert doc["camada"]["sigla"] == "RG"
    assert doc["camada"]["grupo"] == "Programa"
    assert doc["camada"]["subordinado_a"] == "NG_1130"


def test_caso_nt_2026_021_e_nt_2026_018_instrumento():
    """Notas técnicas NT_2026-021 e NT_2026-018 são instrumentos com numeração própria."""
    for codigo in ("NT_2026-021", "NT_2026-018"):
        resp = client.get(f"/api/documentos/{codigo}")
        assert resp.status_code == 200
        doc = resp.json()
        assert doc["camada"]["sigla"] == "NT"
        assert doc["camada"]["tipo_nome"] == "Nota Técnica"
        assert doc["camada"]["grupo"] == "Instrumento"
        assert doc["camada"]["subordinado_a"] is None
        assert doc["tema"]["serie"] is None
        assert doc["tema"]["observacao"] is not None


def test_formatar_camada_completo_e_curto():
    """Testa formatação de camada para web (completo) e canais C0/Slack/Teams (curto)."""
    c_px = derivar_camada("PX_1111-001")
    assert formatar_camada(c_px, "completo") == "PX · Procedimento · Normativo · subordinado a NG_111"
    assert formatar_camada(c_px, "curto") == "PX · Normativo"

    c_ctr = derivar_camada("CTR_2026-012")
    assert formatar_camada(c_ctr, "completo") == "CTR · Contrato · Instrumento"
    assert formatar_camada(c_ctr, "curto") == "CTR · Instrumento"

    c_fl = derivar_camada("FL_1111-001", vinculado_a="PX_1111-001")
    assert formatar_camada(c_fl, "completo") == "FL · Fluxo · Apoio · subordinado a PX_1111-001"
    assert formatar_camada(c_fl, "curto") == "FL · Apoio"


def test_enriquecer_citacao_e_fonte():
    """Testa utilitário de enriquecimento de citações e fontes com camada."""
    # 1. Enriquecimento de objeto Fonte
    fonte = Fonte(
        codigo="PX_1111-001",
        versao="1.0.0",
        secao="Anexo D",
        trecho="Trecho citado do procedimento",
    )
    enriquecer_fonte(fonte)
    assert fonte.camada is not None
    assert fonte.camada.sigla == "PX"
    assert fonte.camada.grupo == "Normativo"
    assert fonte.camada.subordinado_a == "NG_111"

    # 2. Enriquecimento de objeto Citacao
    citacao = Citacao(
        codigo="FL_1111-001",
        versao="1.0.0",
        secao="1",
        trecho="Trecho do fluxograma",
    )
    enriquecer_citacao(citacao)
    assert citacao.camada is not None
    assert citacao.camada.sigla == "FL"
    assert citacao.camada.grupo == "Apoio"
    assert citacao.camada.subordinado_a == "PX_1111-001"

    # 3. Enriquecimento de dict
    d = {
        "codigo": "CTR_2026-012",
        "versao": "1.0.0",
        "secao": "Cláusula Primeira",
        "trecho": "Objeto da locação",
    }
    enriquecido = enriquecer_citacao(d)
    assert "camada" in enriquecido
    assert enriquecido["camada"]["sigla"] == "CTR"
    assert enriquecido["camada"]["grupo"] == "Instrumento"
