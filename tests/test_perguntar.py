import re
import pytest
from fastapi.testclient import TestClient

from app.acervo import AcervoRepository
from app.main import app

client = TestClient(app)
acervo = AcervoRepository()


# ==============================================================================
# Provas de Aceite da Issue #2 (Cenas 1 a 3 do PRD + Perfil sem mudar fontes)
# ==============================================================================


def test_aceite_cena_1_prazo_ferias_citando_px():
    """Prova de aceite 1 (Cena 1 do PRD):

    D-45 de 05/05/2027 = 21/03/2027 citando PX_1111-001.
    Retorna resposta_id (C13) e camada em cada citação (C15).
    """
    resp = client.post(
        "/api/perguntar",
        json={
            "pergunta": "Até quando peço férias que começam em 05/05/2027?",
            "perfil": "empregado",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["consta"] is True
    assert "21/03/2027" in data["resposta"]
    assert data["resposta_id"]
    assert len(data["citacoes"]) >= 1

    # Cita PX_1111-001 conforme critério da issue
    codigos = [c["codigo"] for c in data["citacoes"]]
    assert "PX_1111-001" in codigos

    # C15: camada da norma presente na citação
    px_cit = next(c for c in data["citacoes"] if c["codigo"] == "PX_1111-001")
    assert px_cit["versao"] == "1.0.0"
    assert px_cit["secao"] in {"Anexo D", "8.2"}
    assert px_cit["camada"]["sigla"] == "PX"
    assert px_cit["camada"]["tipo_nome"] == "Procedimento"
    assert px_cit["camada"]["grupo"] == "Normativo"
    assert px_cit["camada"]["subordinado_a"] == "NG_111"


def test_aceite_cena_2_aviso_versao_substituida():
    """Prova de aceite 2 (Cena 2 do PRD):

    Aviso de NG_111 v2.0.0 substituída pela v3.0.0 ao perguntar sobre antecedência de férias.
    Cita a versão vigente v3.0.0.
    """
    resp = client.post(
        "/api/perguntar",
        json={
            "pergunta": "Qual a antecedência mínima para pedir férias?",
            "perfil": "rh",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["consta"] is True
    assert "45" in data["resposta"]
    assert len(data["citacoes"]) >= 1

    # Citação da versão vigente
    assert any(c["codigo"] == "NG_111" and c["versao"] == "3.0.0" for c in data["citacoes"])

    # Aviso presente indicando substituição
    assert any("NG_111 v2.0.0 foi substituída pela v3.0.0" in av for av in data["avisos"])


def test_aceite_cena_3_abstencao_quando_nao_consta():
    """Prova de aceite 3 (Cena 3 / Abstenção do PRD):

    'Uma mesma pessoa pode elaborar, revisar e aprovar?'
    Abaixo do limiar ou tema fora do índice normativo -> consta=false, citacoes=[].
    """
    resp = client.post(
        "/api/perguntar",
        json={
            "pergunta": "Uma mesma pessoa pode elaborar, revisar e aprovar?",
            "perfil": "gestor",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["consta"] is False
    assert data["citacoes"] == []
    assert "não trata disso" in data["resposta"].lower()
    assert data["resposta_id"]


def test_aceite_perfil_muda_ordem_sem_mudar_fontes():
    """Prova de aceite extra:

    O parâmetro `perfil` muda a ordem e a forma da resposta, mas NUNCA as fontes.
    O conjunto de `citacoes` deve ser estritamente idêntico para todos os 6 perfis.
    """
    pergunta = "Até quando peço férias que começam em 05/05/2027?"
    perfis = ["empregado", "gestor", "diretoria", "financeiro", "juridico", "rh"]

    respostas_texto = {}
    conjuntos_citacoes = []

    for perfil in perfis:
        resp = client.post(
            "/api/perguntar",
            json={"pergunta": pergunta, "perfil": perfil},
        )
        assert resp.status_code == 200
        data = resp.json()

        respostas_texto[perfil] = data["resposta"]
        # Extrair lista canônica de citações (codigo, versao, secao)
        cits = [(c["codigo"], c["versao"], c["secao"]) for c in data["citacoes"]]
        conjuntos_citacoes.append(cits)

    # 1. As citações são idênticas para todos os perfis
    primeira_cit = conjuntos_citacoes[0]
    for i, cits in enumerate(conjuntos_citacoes[1:], 1):
        assert cits == primeira_cit, f"Citações divergiram para perfil {perfis[i]}"

    # 2. O texto da resposta varia de acordo com o perfil
    textos_unicos = set(respostas_texto.values())
    assert len(textos_unicos) == len(perfis), "Respostas dos perfis não variaram como esperado"

    # 3. O conteúdo é o mesmo: os trechos citados no texto (com suas fontes) formam
    #    o mesmo conjunto em todos os perfis; só a ordem e o rótulo mudam.
    def trechos(texto):
        return {t.strip() for t in re.findall(r"[^()]+?\(Fonte: [^)]+\)", texto.split(": ", 1)[1])}

    conteudos = {perfil: trechos(texto) for perfil, texto in respostas_texto.items()}
    assert all(c == conteudos["empregado"] for c in conteudos.values()), conteudos
    for perfil, texto in respostas_texto.items():
        assert "21/03/2027" in texto, f"Conclusão ausente para o perfil {perfil}"


def test_adendo_v01_a_secao_sempre_existe_no_documento():
    """Adendo v0.1 A: para toda citação gerada, secao ∈ secoes[].id do documento."""
    perguntas_teste = [
        "Até quando peço férias que começam em 05/05/2027?",
        "Qual o valor total do contrato de coworking?",
        "Quem aprova a contratação do coworking?",
        "Qual o orçamento do programa Ideias em Campo 2027?",
        "Qual a multa por inexecução do coworking?",
        "Até quando a GFI paga o aluguel?",
        "O contrato de coworking tem reajuste?",
    ]

    for p in perguntas_teste:
        resp = client.post("/api/perguntar", json={"pergunta": p})
        assert resp.status_code == 200
        data = resp.json()
        assert data["consta"] is True

        for c in data["citacoes"]:
            doc = acervo.buscar(c["codigo"], c["versao"])
            assert doc is not None, f"Documento citado {c['codigo']} v{c['versao']} não encontrado"
            secao_ids = {s.id for s in doc.secoes}
            assert c["secao"] in secao_ids, (
                f"Seção '{c['secao']}' citada não existe no documento {c['codigo']} v{c['versao']}. "
                f"Seções válidas: {secao_ids}"
            )


def test_palavra_fora_do_vocabulario_nao_forca_abstencao():
    """Uma palavra que não aparece no acervo não basta para responder 'não consta'."""
    data = client.post(
        "/api/perguntar",
        json={"pergunta": "Quantos dias de férias o colaborador tem direito por ano?", "perfil": None},
    ).json()
    assert data["consta"] is True
    assert any(c["codigo"] == "NG_111" for c in data["citacoes"])


def test_aviso_de_versao_substituida_sem_palavra_chave_fixa():
    """O aviso vem da relevância da versão substituída, não de palavras fixas na pergunta."""
    data = client.post("/api/perguntar", json={"pergunta": "Quem aprova as férias?", "perfil": None}).json()
    assert data["consta"] is True
    assert "NG_111 v2.0.0 foi substituída pela v3.0.0" in data["avisos"]


def test_resposta_e_extraida_das_citacoes():
    """Todo trecho usado no texto da resposta é o trecho de uma das citações devolvidas."""
    data = client.post(
        "/api/perguntar",
        json={"pergunta": "Posso sublocar o espaço de coworking?", "perfil": "juridico"},
    ).json()
    assert data["consta"] is True
    citados = [c["trecho"].rstrip(" ;,.") for c in data["citacoes"]]
    usados = re.findall(r"([^()]+?)\.? \(Fonte: ", data["resposta"].split(": ", 1)[1])
    assert usados
    for u in usados:
        assert any(u.strip().rstrip(".") in c or c in u for c in citados), u
