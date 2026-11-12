import pytest
from fastapi.testclient import TestClient
from app.main import app, acervo
from app.models import CodigoDecodificado
from app.codigo import decodificar_codigo, extrair_sigla, detectar_ambiguidade

client = TestClient(app)


# ==============================================================================
# Prova de Aceite da Issue #3 (Os 7 Casos Obrigatórios)
# ==============================================================================


def test_aceite_caso_1_px_1111_001():
    """Prova de aceite 1: PX_1111-001.

    - Sigla PX, Procedimento, grupo Normativo
    - Herda de NG_111 (confirmado pelo acervo)
    - Série 1 (Gente e Cultura)
    - Vigência: 18 meses a partir da aprovação
    - Existe no acervo: True
    - Ambiguidade explicada em observação (1111 pode ser Série 1 ou Série 11)
    - Carrega camada e tema (Issue #13)
    """
    # 1. Via função direta
    res = decodificar_codigo("PX_1111-001", acervo=acervo)
    assert res.codigo == "PX_1111-001"
    assert res.tipo == "PX"
    assert res.tipo_nome == "Procedimento"
    assert res.vinculado_a == "NG_111"
    assert res.serie == "1"
    assert res.serie_nome == "Gente e Cultura"
    assert res.vigencia_regra == "18 meses a partir da aprovação"
    assert res.existe_no_acervo is True
    assert "ambíguo" in res.observacao.lower()
    assert "NG_111" in res.observacao
    assert res.camada.sigla == "PX"
    assert res.camada.grupo == "Normativo"
    assert res.camada.subordinado_a == "NG_111"
    assert res.tema.serie == 1
    assert res.tema.assunto == "ferias"

    # 2. Via endpoint da API GET /api/codigo/{codigo}
    resp = client.get("/api/codigo/PX_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "PX_1111-001"
    assert data["tipo"] == "PX"
    assert data["tipo_nome"] == "Procedimento"
    assert data["vinculado_a"] == "NG_111"
    assert data["serie"] == "1"
    assert data["serie_nome"] == "Gente e Cultura"
    assert data["vigencia_regra"] == "18 meses a partir da aprovação"
    assert data["existe_no_acervo"] is True
    assert "ambíguo" in data["observacao"].lower()
    assert data["camada"]["sigla"] == "PX"
    assert data["camada"]["tipo_nome"] == "Procedimento"
    assert data["camada"]["grupo"] == "Normativo"
    assert data["camada"]["subordinado_a"] == "NG_111"
    assert data["tema"]["assunto"] == "ferias"
    assert data["tema"]["serie"] == 1


def test_aceite_caso_2_px_1130_001():
    """Prova de aceite 2: PX_1130-001.

    - Sigla PX, Procedimento, grupo Normativo
    - Vinculado a NG_1130
    - Série: null (Catálogo §5 não define série para NG_1130, lacuna L-f)
    - Vigência: 18 meses a partir da aprovação
    - Existe no acervo: True
    - Observação registra a subordinação a NG_1130 sem série definida
    """
    # 1. Via função direta
    res = decodificar_codigo("PX_1130-001", acervo=acervo)
    assert res.codigo == "PX_1130-001"
    assert res.tipo == "PX"
    assert res.tipo_nome == "Procedimento"
    assert res.vinculado_a == "NG_1130"
    assert res.serie is None
    assert res.serie_nome is None
    assert res.vigencia_regra == "18 meses a partir da aprovação"
    assert res.existe_no_acervo is True
    assert "NG_1130" in res.observacao
    assert res.camada.sigla == "PX"
    assert res.camada.subordinado_a == "NG_1130"
    assert res.tema.serie is None
    assert res.tema.assunto == "inovacao"

    # 2. Via endpoint da API
    resp = client.get("/api/codigo/PX_1130-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "PX_1130-001"
    assert data["tipo"] == "PX"
    assert data["vinculado_a"] == "NG_1130"
    assert data["serie"] is None
    assert data["serie_nome"] is None
    assert data["existe_no_acervo"] is True
    assert "NG_1130" in data["observacao"]
    assert data["camada"]["subordinado_a"] == "NG_1130"


def test_aceite_caso_3_rg_1100():
    """Prova de aceite 3: RG_1100.

    - Sigla RG, Regulamento de Programa, grupo Programa
    - Numeração: não herda de NG; número vem da série do assunto (Catálogo §2)
    - Série 11 (Programas Institucionais)
    - Vigência: Por edição do programa
    - Existe no acervo: True
    - Vinculado a NG_1130 (registrado no cabeçalho do documento no acervo)
    """
    # 1. Via função direta
    res = decodificar_codigo("RG_1100", acervo=acervo)
    assert res.codigo == "RG_1100"
    assert res.tipo == "RG"
    assert res.tipo_nome == "Regulamento de Programa"
    assert res.vinculado_a == "NG_1130"
    assert res.serie == "11"
    assert res.serie_nome == "Programas Institucionais"
    assert res.vigencia_regra == "Por edição do programa"
    assert res.existe_no_acervo is True
    assert res.camada.sigla == "RG"
    assert res.camada.grupo == "Programa"
    assert res.tema.serie == 11
    assert res.tema.serie_nome == "Programas Institucionais"

    # 2. Via endpoint da API
    resp = client.get("/api/codigo/RG_1100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "RG_1100"
    assert data["tipo"] == "RG"
    assert data["tipo_nome"] == "Regulamento de Programa"
    assert data["serie"] == "11"
    assert data["serie_nome"] == "Programas Institucionais"
    assert data["vigencia_regra"] == "Por edição do programa"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Programa"
    assert data["tema"]["serie"] == 11


def test_aceite_caso_4_ctr_2026_012():
    """Prova de aceite 4: CTR_2026-012.

    - Sigla CTR, Contrato, grupo Instrumento
    - Formato próprio de numeração: ano e sequencial (sem série no catálogo)
    - Vigência: A do próprio instrumento
    - Vinculado a: None (documento raiz)
    - Existe no acervo: True
    - Observação indica numeração própria (ano/sequencial)
    """
    # 1. Via função direta
    res = decodificar_codigo("CTR_2026-012", acervo=acervo)
    assert res.codigo == "CTR_2026-012"
    assert res.tipo == "CTR"
    assert res.tipo_nome == "Contrato"
    assert res.vinculado_a is None
    assert res.serie is None
    assert res.serie_nome is None
    assert res.vigencia_regra == "A do próprio instrumento"
    assert res.existe_no_acervo is True
    assert "numeração própria" in res.observacao.lower()
    assert res.camada.sigla == "CTR"
    assert res.camada.grupo == "Instrumento"
    assert res.tema.assunto == "locacao"

    # 2. Via endpoint da API
    resp = client.get("/api/codigo/CTR_2026-012")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "CTR_2026-012"
    assert data["tipo"] == "CTR"
    assert data["tipo_nome"] == "Contrato"
    assert data["vinculado_a"] is None
    assert data["serie"] is None
    assert data["vigencia_regra"] == "A do próprio instrumento"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Instrumento"


def test_aceite_caso_5_nt_2026_021():
    """Prova de aceite 5: NT_2026-021.

    - Sigla NT, Nota Técnica, grupo Instrumento
    - Formato próprio de numeração: ano e sequencial (sem série no catálogo)
    - Vigência: Vale para a decisão a que se refere
    - Vinculado a: None
    - Existe no acervo: True
    """
    # 1. Via função direta
    res = decodificar_codigo("NT_2026-021", acervo=acervo)
    assert res.codigo == "NT_2026-021"
    assert res.tipo == "NT"
    assert res.tipo_nome == "Nota Técnica"
    assert res.vinculado_a is None
    assert res.serie is None
    assert res.serie_nome is None
    assert res.vigencia_regra == "Vale para a decisão a que se refere"
    assert res.existe_no_acervo is True
    assert "numeração própria" in res.observacao.lower()
    assert res.camada.sigla == "NT"
    assert res.camada.grupo == "Instrumento"
    assert res.tema.assunto == "inovacao"

    # 2. Via endpoint da API
    resp = client.get("/api/codigo/NT_2026-021")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "NT_2026-021"
    assert data["tipo"] == "NT"
    assert data["tipo_nome"] == "Nota Técnica"
    assert data["serie"] is None
    assert data["vigencia_regra"] == "Vale para a decisão a que se refere"
    assert data["existe_no_acervo"] is True


def test_aceite_caso_6_ct_dirtec_2026_003():
    """Prova de aceite 6: CT_Dirtec — 2026/003.

    - Sigla CT, Comunicado Temporário, grupo Temporário
    - Formato próprio de numeração: ano, sequencial e diretoria (Catálogo §2)
    - Vigência: No máximo 150 dias
    - Vinculado a: None
    - Existe no acervo: False (documento citado como acervo anterior no Catálogo)
    - Observação registra numeração própria e inexistência no acervo atual
    """
    codigo = "CT_Dirtec — 2026/003"

    # 1. Via função direta
    res = decodificar_codigo(codigo, acervo=acervo)
    assert res.codigo == codigo
    assert res.tipo == "CT"
    assert res.tipo_nome == "Comunicado Temporário"
    assert res.vinculado_a is None
    assert res.serie is None
    assert res.serie_nome is None
    assert res.vigencia_regra == "No máximo 150 dias"
    assert res.existe_no_acervo is False
    assert "acervo anterior" in res.observacao.lower()
    assert res.camada.sigla == "CT"
    assert res.camada.grupo == "Temporário"
    assert res.tema.serie is None

    # 2. Via endpoint da API com URL decodificada / codificada
    resp = client.get(f"/api/codigo/{codigo}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == codigo
    assert data["tipo"] == "CT"
    assert data["tipo_nome"] == "Comunicado Temporário"
    assert data["vigencia_regra"] == "No máximo 150 dias"
    assert data["existe_no_acervo"] is False
    assert data["camada"]["sigla"] == "CT"
    assert data["camada"]["grupo"] == "Temporário"


def test_aceite_caso_7_codigo_inexistente():
    """Prova de aceite 7: código inexistente.

    Testa dois cenários de código inexistente no acervo:
    1. Código com formato completamente desconhecido (CODIGO_INEXISTENTE):
       - existe_no_acervo: False
       - tipo: None
       - vigencia_regra: None
       - observacao esclarece que o código não foi reconhecido pelo catálogo
    2. Código com sigla válida mas que não existe no acervo (NG_999):
       - existe_no_acervo: False
       - tipo: "NG", Norma Geral
       - vigencia_regra: "18 meses a partir da aprovação"
       - serie: "9", Riscos e Conformidade
       - observacao registra que o documento não está cadastrado no acervo
    """
    # Cenário 1: Formato inválido/desconhecido
    resp1 = client.get("/api/codigo/CODIGO_INEXISTENTE")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["codigo"] == "CODIGO_INEXISTENTE"
    assert data1["existe_no_acervo"] is False
    assert data1["tipo"] is None
    assert data1["tipo_nome"] is None
    assert data1["vigencia_regra"] is None
    assert "não reconhecido" in data1["observacao"].lower()

    # Cenário 2: Sigla válida no catálogo, mas documento ausente do acervo
    resp2 = client.get("/api/codigo/NG_999")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["codigo"] == "NG_999"
    assert data2["tipo"] == "NG"
    assert data2["tipo_nome"] == "Norma Geral"
    assert data2["serie"] == "9"
    assert data2["serie_nome"] == "Riscos e Conformidade"
    assert data2["vigencia_regra"] == "18 meses a partir da aprovação"
    assert data2["existe_no_acervo"] is False
    assert "não cadastrado" in data2["observacao"].lower()
    assert data2["camada"]["sigla"] == "NG"
    assert data2["camada"]["grupo"] == "Normativo"


# ==============================================================================
# Testes Complementares de Decodificação e Resiliência
# ==============================================================================


def test_decodificar_ng_111_vigente():
    """NG_111 é norma geral, raiz, Série 1 (Gente e Cultura)."""
    resp = client.get("/api/codigo/NG_111")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "NG_111"
    assert data["tipo"] == "NG"
    assert data["tipo_nome"] == "Norma Geral"
    assert data["vinculado_a"] is None
    assert data["serie"] == "1"
    assert data["serie_nome"] == "Gente e Cultura"
    assert data["vigencia_regra"] == "18 meses a partir da aprovação"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Normativo"


def test_decodificar_fl_1111_001_subordinado_a_px():
    """FL_1111-001 herda de PX_1111-001, grupo Apoio, revisão conforme necessidade."""
    resp = client.get("/api/codigo/FL_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "FL_1111-001"
    assert data["tipo"] == "FL"
    assert data["tipo_nome"] == "Fluxo"
    assert data["vinculado_a"] == "PX_1111-001"
    assert data["serie"] == "1"
    assert data["vigencia_regra"] == "Revisão conforme a necessidade"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Apoio"


def test_decodificar_fm_1111_001():
    """FM_1111-001 formulário vinculado a NG_111, grupo Apoio."""
    resp = client.get("/api/codigo/FM_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "FM_1111-001"
    assert data["tipo"] == "FM"
    assert data["tipo_nome"] == "Formulário"
    assert data["vinculado_a"] == "NG_111"
    assert data["vigencia_regra"] == "Revisão conforme a necessidade"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Apoio"


def test_decodificar_tb_1111_001():
    """TB_1111-001 tabela vinculada a NG_111, grupo Apoio."""
    resp = client.get("/api/codigo/TB_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "TB_1111-001"
    assert data["tipo"] == "TB"
    assert data["tipo_nome"] == "Tabela"
    assert data["vinculado_a"] == "NG_111"
    assert data["vigencia_regra"] == "Revisão conforme a necessidade"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Apoio"


def test_decodificar_nt_2026_018():
    """NT_2026-018 nota técnica no acervo, grupo Instrumento."""
    resp = client.get("/api/codigo/NT_2026-018")
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "NT_2026-018"
    assert data["tipo"] == "NT"
    assert data["tipo_nome"] == "Nota Técnica"
    assert data["serie"] is None
    assert data["vigencia_regra"] == "Vale para a decisão a que se refere"
    assert data["existe_no_acervo"] is True
    assert data["camada"]["grupo"] == "Instrumento"


def test_decodificar_ct_variacoes_de_separador():
    """Testa variações de traço e espaço para CT_Dirtec."""
    # Com hífen simples e barra
    resp1 = client.get("/api/codigo/CT_Dirtec - 2026/003")
    assert resp1.status_code == 200
    assert resp1.json()["tipo"] == "CT"
    assert resp1.json()["vigencia_regra"] == "No máximo 150 dias"

    # URL-encoded (%20 e %2F)
    resp2 = client.get("/api/codigo/CT_Dirtec%20%E2%80%94%202026%2F003")
    assert resp2.status_code == 200
    assert resp2.json()["tipo"] == "CT"
    assert resp2.json()["vigencia_regra"] == "No máximo 150 dias"


def test_vigencias_todas_categorias_catalogo():
    """Garante que todas as 12 categorias do Catálogo possuem regra de vigência definida."""
    from app.codigo import VIGENCIA_REGRAS
    from app.taxonomia import CATEGORIAS_CATALOGO

    for sigla in CATEGORIAS_CATALOGO.keys():
        assert sigla in VIGENCIA_REGRAS, f"Sigla {sigla} sem regra de vigência em VIGENCIA_REGRAS"
        assert len(VIGENCIA_REGRAS[sigla]) > 0


def test_decodificar_case_insensitive():
    """Busca no decodificador funciona case-insensitively para documentos do acervo."""
    resp = client.get("/api/codigo/px_1111-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tipo"] == "PX"
    assert data["vinculado_a"] == "NG_111"
    assert data["existe_no_acervo"] is True


def test_decodificar_documentos_acervo_anterior():
    """Testa documentos mencionados no catálogo como acervo anterior ou fundacionais."""
    # PP_310-001 (Série 3 · Operações de Campo)
    r_pp = client.get("/api/codigo/PP_310-001").json()
    assert r_pp["tipo"] == "PP"
    assert r_pp["tipo_nome"] == "Padrão Operacional"
    assert r_pp["serie"] == "3"
    assert r_pp["serie_nome"] == "Operações de Campo"
    assert r_pp["vigencia_regra"] == "Revisão conforme a necessidade"
    assert r_pp["existe_no_acervo"] is False

    # GU_410-001 (Série 4 · Compras e Contratos)
    r_gu = client.get("/api/codigo/GU_410-001").json()
    assert r_gu["tipo"] == "GU"
    assert r_gu["tipo_nome"] == "Guia"
    assert r_gu["serie"] == "4"
    assert r_gu["serie_nome"] == "Compras e Contratos"
    assert r_gu["vigencia_regra"] == "18 meses a partir da aprovação"
    assert r_gu["existe_no_acervo"] is False

    # CAS (Carta Social - fundacional)
    r_cas = client.get("/api/codigo/CAS").json()
    assert r_cas["tipo"] == "CAS"
    assert r_cas["tipo_nome"] == "Carta Social"
    assert r_cas["serie"] is None
    assert r_cas["existe_no_acervo"] is False

