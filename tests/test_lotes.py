"""Envio em lote + digitalização (issue #10). Fixtures fictícias, sem rede."""

import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import digitalizacao
from app.acervo import get_acervo
from app.digitalizacao import LeituraFalhou, ler_com_bedrock
from app.main import app, perguntar_service

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures" / "lote"
ACERVO_DIR = Path(__file__).resolve().parent.parent / "data" / "acervo"
NG_111_BYTES = next((ACERVO_DIR / "ferias").glob("NG_111__*")).read_bytes()

TEXTO_FOTO_BEDROCK = """Documento: Fluxo
Título: Fluxograma Fictício de Teste
Sigla e Número: FL_1111-002
Versão: 1.0.0
Fase: Vigente
Vinculado a: PX_1111-001
1. Etapas
[?] 1.1. A pessoa empregada abre o pedido no portal fictício."""


def _md(nome: str):
    return ("arquivos", (nome, (FIXTURES / nome).read_bytes(), "text/markdown"))


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


def _pdf(linhas) -> bytes:
    """PDF mínimo com texto (1 página), montado à mão para não depender de rede."""
    conteudo = "BT /F1 10 Tf 40 800 Td 12 TL " + " ".join(
        f"({l.replace('(', '').replace(')', '')}) Tj T*" for l in linhas
    ) + " ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(conteudo.encode("latin-1")) + conteudo.encode("latin-1") + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


class StubBedrock:
    """Simula o cliente bedrock-runtime (API Converse)."""

    def __init__(self, texto=TEXTO_FOTO_BEDROCK):
        self.texto = texto
        self.chamadas = []

    def converse(self, **kwargs):
        self.chamadas.append(kwargs)
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.texto}]}}}


@pytest.fixture(autouse=True)
def isolamento(tmp_path, monkeypatch):
    """Uploads em pasta temporária, sem Bedrock real, e acervo restaurado (13 docs)."""
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DIGITALIZACAO_BEDROCK", "0")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setattr(digitalizacao, "leitor_customizado", None)
    yield
    acervo = get_acervo()
    for d in [d for d in acervo.documentos if d.origem != "acervo"]:
        acervo.remover(d.codigo, d.versao)
    perguntar_service.buscador._construir_indice()
    assert acervo.total() == 13


def _por_nome(lote):
    return {a["nome"]: a for a in lote["arquivos"]}


def test_lote_de_tres_md_classificado():
    inicio = time.perf_counter()
    r = client.post(
        "/api/lotes",
        files=[
            _md("PX_1111-002__TESTE_FICTICIO.md"),
            _md("NT_2026-099__TESTE_FICTICIO.md"),
            _md("SEM_CODIGO__TESTE_FICTICIO.md"),
        ],
    )
    duracao = time.perf_counter() - inicio
    assert r.status_code == 201, r.text
    lote = r.json()
    arqs = _por_nome(lote)

    px = arqs["PX_1111-002__TESTE_FICTICIO.md"]
    assert px["estado"] == "classificado"
    assert px["tipo"] == "digital"
    assert px["tema_sugerido"]["assunto"] == "ferias"
    assert px["tema_sugerido"]["serie"] == 1
    assert px["tema_sugerido"]["serie_nome"] == "Gente e Cultura"
    assert "se liga à NG_111" in px["tema_sugerido"]["motivo"]
    assert 0 < px["tema_sugerido"]["confianca"] <= 1
    assert px["tema_sugerido"]["rotulo"] == "Férias (Série 1 · Gente e Cultura)"

    nt = arqs["NT_2026-099__TESTE_FICTICIO.md"]
    assert nt["estado"] == "classificado"
    assert nt["tema_sugerido"]["assunto"] == "locacao"
    assert "CTR_2026-012" in nt["tema_sugerido"]["motivo"]

    sem = arqs["SEM_CODIGO__TESTE_FICTICIO.md"]
    assert sem["estado"] == "sem_tema"
    assert sem["tema_sugerido"] is None
    assert sem["mensagem_tema"] == "Sem tema: escolha um."

    # RNF18: cada arquivo digital classificado em < 5 s
    assert duracao < 5
    assert all(a["tempo_classificacao_ms"] < 5000 for a in lote["arquivos"])

    # GET devolve o mesmo estado
    g = client.get(f"/api/lotes/{lote['id']}")
    assert g.status_code == 200
    assert g.json()["resumo"]["total"] == 3
    assert g.json()["resumo"]["sem_tema"] == 1


def test_publicar_lote_entra_no_catalogo_e_na_busca():
    lote = client.post(
        "/api/lotes",
        files=[_md("PX_1111-002__TESTE_FICTICIO.md"), _md("SEM_CODIGO__TESTE_FICTICIO.md")],
    ).json()
    r = client.post(f"/api/lotes/{lote['id']}/publicar")
    assert r.status_code == 200
    res = {x["nome"]: x for x in r.json()["resultados"]}
    assert res["PX_1111-002__TESTE_FICTICIO.md"]["publicado"] is True
    # sem código continua bloqueado
    assert res["SEM_CODIGO__TESTE_FICTICIO.md"]["publicado"] is False
    assert res["SEM_CODIGO__TESTE_FICTICIO.md"]["motivo"] == "Sem tema: escolha um."

    lista = client.get("/api/documentos").json()
    assert len(lista) == 14
    docs = {d["codigo"]: d for d in lista}
    assert docs["PX_1111-002"]["origem"] == "upload"
    assert docs["PX_1111-002"]["tema"]["confirmado_por"] == "regra"
    assert client.get("/api/documentos/NG_111").json()["origem"] == "acervo"

    resp = client.post("/api/perguntar", json={"pergunta": "Onde registro a remarcação zeta?", "perfil": "empregado"})
    assert resp.status_code == 200
    codigos = [c["codigo"] for c in resp.json()["citacoes"]]
    assert "PX_1111-002" in codigos

    # publicar de novo não duplica
    again = client.post(f"/api/lotes/{lote['id']}/publicar").json()
    assert all(x["nome"] != "PX_1111-002__TESTE_FICTICIO.md" for x in again["resultados"])


def test_tema_editado_libera_publicacao_com_confirmado_por_pessoa():
    lote = client.post("/api/lotes", files=[_md("NT_2026-099__TESTE_FICTICIO.md")]).json()
    arq = lote["arquivos"][0]
    p = client.patch(f"/api/lotes/{lote['id']}/arquivos/{arq['id']}", json={"assunto": "Inovação", "serie": 11})
    assert p.status_code == 200
    assert p.json()["tema_escolhido"]["assunto"] == "inovacao"
    assert p.json()["tema_escolhido"]["serie_nome"] == "Programas Institucionais"
    client.post(f"/api/lotes/{lote['id']}/publicar")
    doc = client.get("/api/documentos/NT_2026-099").json()
    assert doc["tema"]["assunto"] == "inovacao"
    assert doc["tema"]["serie"] == 11
    assert doc["tema"]["confirmado_por"] == "pessoa"

    serie_ruim = client.patch(f"/api/lotes/{lote['id']}/arquivos/{arq['id']}", json={"assunto": "x", "serie": 99})
    assert serie_ruim.status_code == 409  # já publicado


def test_serie_inexistente_e_404():
    lote = client.post("/api/lotes", files=[_md("SEM_CODIGO__TESTE_FICTICIO.md")]).json()
    arq_id = lote["arquivos"][0]["id"]
    assert client.patch(f"/api/lotes/{lote['id']}/arquivos/{arq_id}", json={"assunto": "x", "serie": 99}).status_code == 422
    assert client.patch(f"/api/lotes/{lote['id']}/arquivos/arq-99", json={"assunto": "x"}).status_code == 404
    assert client.get("/api/lotes/lote-inexistente").status_code == 404


def test_arquivo_invalido_nao_para_o_lote():
    r = client.post(
        "/api/lotes",
        files=[
            _md("PX_1111-002__TESTE_FICTICIO.md"),
            ("arquivos", ("planilha.xlsx", b"PK\x03\x04 fake", "application/octet-stream")),
            ("arquivos", ("falso.png", b"isto nao e png", "image/png")),
            ("arquivos", ("vazio.md", b"", "text/markdown")),
            ("arquivos", ("NG_111.md", NG_111_BYTES, "text/markdown")),
        ],
    )
    assert r.status_code == 201
    arqs = _por_nome(r.json())
    assert arqs["PX_1111-002__TESTE_FICTICIO.md"]["estado"] == "classificado"
    assert arqs["planilha.xlsx"]["estado"] == "erro"
    assert arqs["planilha.xlsx"]["erro"]["status"] == 415
    assert "tipo não aceito. Envie PDF, Markdown, JPG ou PNG." in arqs["planilha.xlsx"]["erro"]["mensagem"]
    assert arqs["falso.png"]["erro"]["status"] == 415
    assert arqs["vazio.md"]["erro"]["status"] == 422
    dup = arqs["NG_111.md"]
    assert dup["erro"]["status"] == 409
    assert "NG_111 v3.0.0 já existe no acervo" in dup["erro"]["mensagem"]
    assert r.json()["resumo"]["erros"] == 4

    pub = client.post(f"/api/lotes/{r.json()['id']}/publicar").json()
    publicados = [x["nome"] for x in pub["resultados"] if x["publicado"]]
    assert publicados == ["PX_1111-002__TESTE_FICTICIO.md"]


def test_limites_de_tamanho_e_quantidade(monkeypatch):
    from app import ingestao

    monkeypatch.setattr(ingestao, "MAX_BYTES_ARQUIVO", 100)
    r = client.post(
        "/api/lotes",
        files=[("arquivos", ("grande.md", b"a" * 200, "text/markdown")), _md("NT_2026-099__TESTE_FICTICIO.md")],
    )
    arqs = _por_nome(r.json())
    assert arqs["grande.md"]["erro"]["status"] == 413
    assert "10 MB" in arqs["grande.md"]["erro"]["mensagem"]

    muitos = [("arquivos", (f"a{i}.md", b"x", "text/markdown")) for i in range(21)]
    assert client.post("/api/lotes", files=muitos).status_code == 413


def test_pdf_com_texto_e_classificado():
    pdf = _pdf([
        "Documento: Procedimento",
        "Título: Procedimento PDF de teste",
        "Sigla e Número: PX_1111-003",
        "Versão: 1.0.0",
        "Vinculado a: NG_111",
        "1. Objetivo",
        "Teste fictício de leitura de PDF.",
    ])
    r = client.post("/api/lotes", files=[("arquivos", ("px.pdf", pdf, "application/pdf"))])
    arq = r.json()["arquivos"][0]
    assert arq["tipo"] == "digital", arq
    assert arq["estado"] == "classificado", arq
    assert arq["documento"]["codigo"] == "PX_1111-003"
    assert arq["tema_sugerido"]["assunto"] == "ferias"


def test_foto_com_bedrock_simulado_gera_texto_e_exige_revisao(monkeypatch):
    stub = StubBedrock()
    monkeypatch.setattr(digitalizacao, "leitor_customizado", lambda c, f: ler_com_bedrock(c, f, cliente=stub))

    r = client.post("/api/lotes", files=[("arquivos", ("FL_foto.png", _png(), "image/png"))])
    assert r.status_code == 201
    arq = r.json()["arquivos"][0]
    lote_id = r.json()["id"]

    # Converse recebeu a imagem
    bloco_img = stub.chamadas[0]["messages"][0]["content"][0]["image"]
    assert bloco_img["format"] == "png"
    assert bloco_img["source"]["bytes"].startswith(b"\x89PNG")

    assert arq["tipo"] == "foto"
    assert arq["estado"] == "revisar"
    assert arq["motor"].startswith("bedrock:")
    assert "FL_1111-002" in arq["texto_lido"]
    assert arq["linhas_incertas"] == 1
    assert [l for l in arq["linhas"] if l["incerta"]][0]["texto"].startswith("1.1.")
    assert arq["tema_sugerido"]["assunto"] == "ferias"
    assert arq["documento"]["origem"] == "digitalizado"

    # Nada é publicado sem revisão humana
    pub = client.post(f"/api/lotes/{lote_id}/publicar").json()
    assert pub["resultados"][0]["publicado"] is False
    assert "revise o texto" in pub["resultados"][0]["motivo"]
    assert client.get("/api/documentos/FL_1111-002").status_code == 404

    # Pessoa corrige o texto e confere
    texto_corrigido = TEXTO_FOTO_BEDROCK.replace("[?] ", "")
    p = client.patch(
        f"/api/lotes/{lote_id}/arquivos/{arq['id']}", json={"texto": texto_corrigido, "revisado": True}
    )
    assert p.status_code == 200
    assert p.json()["estado"] == "classificado"
    assert p.json()["linhas_incertas"] == 0

    pub = client.post(f"/api/lotes/{lote_id}/publicar").json()
    assert pub["resultados"][0]["publicado"] is True
    doc = client.get("/api/documentos/FL_1111-002").json()
    assert doc["origem"] == "digitalizado"
    assert doc["camada"]["subordinado_a"] == "PX_1111-001"


def test_foto_ilegivel_tem_erro_amigavel(monkeypatch):
    def falha(c, f):
        raise LeituraFalhou("sem texto")

    monkeypatch.setattr(digitalizacao, "leitor_customizado", falha)
    r = client.post(
        "/api/lotes",
        files=[("arquivos", ("foto_pag2.jpg", b"\xff\xd8\xff\xe0 jpeg", "image/jpeg")), _md("PX_1111-002__TESTE_FICTICIO.md")],
    )
    arqs = _por_nome(r.json())
    assert arqs["foto_pag2.jpg"]["estado"] == "erro"
    assert arqs["foto_pag2.jpg"]["erro"]["mensagem"] == (
        "foto_pag2.jpg: não deu para ler esta foto. Tente com mais luz e a página inteira no quadro."
    )
    assert arqs["PX_1111-002__TESTE_FICTICIO.md"]["estado"] == "classificado"


def test_sem_motor_configurado_vira_erro_de_leitura(monkeypatch):
    monkeypatch.setattr(digitalizacao, "tesseract_disponivel", lambda: False)
    r = client.post("/api/lotes", files=[("arquivos", ("scan.png", _png(), "image/png"))])
    assert r.json()["arquivos"][0]["erro"]["status"] == 422


def test_arquivos_salvos_em_uploads(tmp_path):
    r = client.post("/api/lotes", files=[_md("NT_2026-099__TESTE_FICTICIO.md")])
    salvos = list((tmp_path / "uploads" / r.json()["id"]).iterdir())
    assert len(salvos) == 1 and salvos[0].name.endswith("NT_2026-099__TESTE_FICTICIO.md")


# --- Correções do QA da PR #31 ------------------------------------------------

def _md_inline(nome: str, codigo: str, vinculado: str, corpo: str):
    """Markdown fictício montado no teste (nenhum dado do acervo real)."""
    texto = f"""Documento: Norma
Título: Norma Fictícia de Teste {codigo}
Sigla e Número: {codigo}
Versão: 1.0.0
Fase: Vigente
Vinculado a: {vinculado}

DOCUMENTO SINTÉTICO. FIXTURE DE TESTE (FICTÍCIA).

1. Objetivo
{corpo}
"""
    return ("arquivos", (nome, texto.encode("utf-8"), "text/markdown"))


def test_publicacao_atualiza_embeddings_da_busca_hibrida(monkeypatch):
    from app import recuperacao

    buscador = perguntar_service.buscador
    chave = buscador._chave_densa
    # Simula o índice denso já carregado do cache (provedor Bedrock), sem rede.
    base = {chave(s): [1.0, 0.0] for s in buscador.sections}
    monkeypatch.setattr(buscador, "dense_embeddings", dict(base))
    chamadas = []

    def stub_embeddings(textos, input_type=None):
        chamadas.append(list(textos))
        return [[0.0, 1.0] for _ in textos]

    monkeypatch.setattr(recuperacao, "get_llm_provider", lambda: "bedrock")
    monkeypatch.setattr(recuperacao, "gerar_embeddings", stub_embeddings)

    lote = client.post("/api/lotes", files=[_md("PX_1111-002__TESTE_FICTICIO.md")]).json()
    assert client.post(f"/api/lotes/{lote['id']}/publicar").json()["resultados"][0]["publicado"] is True

    novas = [chave(s) for s in buscador.sections if s.codigo == "PX_1111-002"]
    assert novas, "seções do publicado entram no BM25"
    assert all(k in buscador.dense_embeddings for k in novas), "e também no índice denso"
    # Só as seções novas são enviadas ao provedor; as do acervo base reaproveitam o vetor.
    assert len(chamadas) == 1 and len(chamadas[0]) == len(novas)
    assert all(buscador.dense_embeddings[k] == v for k, v in base.items())


def test_publicacao_com_falha_de_embedding_segue_no_bm25(monkeypatch):
    from app import recuperacao

    buscador = perguntar_service.buscador
    monkeypatch.setattr(buscador, "dense_embeddings", {buscador._chave_densa(s): [1.0] for s in buscador.sections})
    monkeypatch.setattr(recuperacao, "get_llm_provider", lambda: "bedrock")

    def falha(*a, **k):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(recuperacao, "gerar_embeddings", falha)
    lote = client.post("/api/lotes", files=[_md("PX_1111-002__TESTE_FICTICIO.md")]).json()
    assert client.post(f"/api/lotes/{lote['id']}/publicar").json()["resultados"][0]["publicado"] is True
    assert any(s.codigo == "PX_1111-002" for s in buscador.sections)


def test_radar_enxerga_documento_publicado():
    antes = client.get("/api/radar").json()
    assert "NG_012" in [i.get("codigo_ausente") for i in antes["itens"]]

    lote = client.post(
        "/api/lotes",
        files=[
            _md_inline("NG_012.md", "NG_012", "CTR_2026-012",
                       "Definir alçadas fictícias de aprovação usadas apenas em testes."),
            _md_inline("PX_9999-001.md", "PX_9999-001", "NG_999",
                       "Procedimento fictício que cita a NG_999, ausente do acervo."),
        ],
    ).json()
    for arq in lote["arquivos"]:
        if arq["estado"] == "sem_tema":
            client.patch(f"/api/lotes/{lote['id']}/arquivos/{arq['id']}", json={"assunto": "locacao", "serie": 3})
    res = client.post(f"/api/lotes/{lote['id']}/publicar").json()["resultados"]
    assert all(r["publicado"] for r in res), res

    depois = client.get("/api/radar").json()
    ausentes = {i.get("codigo_ausente"): i for i in depois["itens"]}
    # A referência P0 some quando o documento passa a existir no acervo
    assert "NG_012" not in ausentes
    # E o publicado que cita um documento ausente vira item, com fonte nele próprio
    item = ausentes["NG_999"]
    assert item["tipo"] == "referencia_ausente"
    assert item["fontes"][0]["codigo"] == "PX_9999-001"
    assert item["fontes"][0]["versao"] == "1.0.0"


def test_sem_codigo_com_tema_fica_em_revisar_ate_ter_codigo():
    lote = client.post("/api/lotes", files=[_md("SEM_CODIGO__TESTE_FICTICIO.md")]).json()
    arq = lote["arquivos"][0]
    url = f"/api/lotes/{lote['id']}/arquivos/{arq['id']}"

    p = client.patch(url, json={"assunto": "locacao", "serie": 3})
    assert p.status_code == 200
    assert p.json()["estado"] == "revisar"
    resumo = client.get(f"/api/lotes/{lote['id']}").json()["resumo"]
    assert resumo["prontos"] == 0

    pub = client.post(f"/api/lotes/{lote['id']}/publicar").json()["resultados"][0]
    assert pub["publicado"] is False
    assert "sem código" in pub["motivo"]

    texto = (FIXTURES / "SEM_CODIGO__TESTE_FICTICIO.md").read_text(encoding="utf-8").replace(
        "Título: Rascunho fictício sem código",
        "Título: Rascunho fictício sem código\nSigla e Número: NT_2026-098\nVersão: 1.0.0",
    )
    p2 = client.patch(url, json={"texto": texto})
    assert p2.json()["estado"] == "classificado"
    assert client.get(f"/api/lotes/{lote['id']}").json()["resumo"]["prontos"] == 1
    pub2 = client.post(f"/api/lotes/{lote['id']}/publicar").json()["resultados"][0]
    assert pub2["publicado"] is True
    doc = client.get("/api/documentos/NT_2026-098").json()
    assert doc["tema"]["confirmado_por"] == "pessoa"
    assert doc["tema"]["assunto"] == "locacao"


def test_mensagem_415_sem_duplicacao():
    r = client.post("/api/lotes", files=[("arquivos", ("falso.png", b"isto nao e png", "image/png"))]).json()
    msg = r["arquivos"][0]["erro"]["mensagem"]
    assert msg.count("Envie") == 1
    assert "tipo não aceito" not in msg


def test_rotas_de_lote_sao_sincronas():
    """Leitura de PDF e Bedrock são síncronas: as rotas rodam no threadpool, não no event loop."""
    import inspect
    from app.routers import lotes

    for rota in lotes.router.routes:
        assert not inspect.iscoroutinefunction(rota.endpoint), rota.path
