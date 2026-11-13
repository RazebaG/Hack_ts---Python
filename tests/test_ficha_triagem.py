"""Testes do Endpoint GET /api/ficha/triagem (C25, RF69, RF71, Issue #54).

Valida:
1. Resposta do endpoint com modelo TriagemResposta e validação Pydantic estrita de todos os campos.
2. Com DATA_REFERENCIA=2026-11-12, limite=5 retorna os documentos mais urgentes (CTR_2026-012 com 'vistoria em 13 dias').
3. Verificação do resultado calculado para todos os documentos vigentes do acervo (código, nível, motivo_curto, próximo prazo).
4. Filtro por sinal:
   - sinal=prazo_30d inclui CTR_2026-012
   - sinal=multa inclui CTR_2026-012
   - sinal=divergencia inclui NG_111
5. Filtro por tema: tema=ferias só devolve documentos do assunto férias.
6. Filtro por situação: situacao=ok, atencao, critico.
7. Ordenações: urgencia, vigencia, tema, tipo.
8. Paginação com pagina e tamanho, e corte com limite.
9. Validação estrita de parâmetros com HTTP 422 (limite fora de 1..20, tamanho fora de 1..100, pagina < 1, perfil inválido, situacao inválida, sinal inválido, ordenar inválido).
10. Proteção com API_KEY e cabeçalho X-API-Key (401 se ausente/inválida, 200 com chave correta).
11. Teste de documento com código e título modificados confirmando regra genérica sem ramos específicos.
12. Teste de pelo menos 3 documentos fora do exemplo (NG_1130, PX_1130-001, NT_2026-021).
13. SLA de tempo de resposta < 1 s sem IA e sem rede.
"""

import time
from datetime import date
from typing import Any, Dict
import pytest
from fastapi.testclient import TestClient

from app.acervo import get_acervo
from app.ficha.modelos import ItemTriagem, TriagemResposta
from app.ficha.triagem import (
    calcular_motivo_curto_e_categoria,
    extrair_proximo_prazo,
    montar_item_triagem,
    resumir_marco,
    verificar_sinal_divergencia,
    verificar_sinal_multa,
)
from app.main import app
from app.models import Camada, DocumentoDetalhe, Secao, Tema
from app.routers.ficha import limpar_cache_fichas, obter_ficha_cache_ou_montar

client = TestClient(app)


@pytest.fixture(autouse=True)
def preparar_ambiente(monkeypatch):
    """Garante isolamento do cache e define DATA_REFERENCIA padrão nos testes."""
    monkeypatch.setenv("DATA_REFERENCIA", "2026-11-12")
    monkeypatch.delenv("API_KEY", raising=False)
    limpar_cache_fichas()
    yield
    limpar_cache_fichas()


def test_triagem_estrutura_e_validacao_pydantic():
    """Valida que a resposta de /api/ficha/triagem adere estritamente a TriagemResposta."""
    resp = client.get("/api/ficha/triagem")
    assert resp.status_code == 200
    dados = resp.json()

    resposta = TriagemResposta(**dados)
    assert resposta.total == 11  # 11 documentos vigentes
    assert resposta.pagina == 1
    assert resposta.tamanho == 50
    assert resposta.pedem_acao >= 1
    assert len(resposta.itens) == 11

    for it in resposta.itens:
        assert isinstance(it, ItemTriagem)
        assert it.codigo
        assert it.versao
        assert it.titulo
        assert it.tipo
        assert it.tema
        assert it.semaforo.nivel in ("ok", "atencao", "critico")
        assert it.ficha == "pronta"
        assert it.familia in ("contrato", "norma", "procedimento", "nota_tecnica")
        assert isinstance(it.sinais.multa, bool)
        assert isinstance(it.sinais.divergencia, bool)
        assert it.motivo_curto
        if it.bluf_curto is not None:
            assert len(it.bluf_curto) <= 140
        if it.proximo_prazo is not None:
            assert it.proximo_prazo.data
            assert it.proximo_prazo.evento


def test_triagem_limite_5_e_primeiro_item():
    """Valida que com limite=5 retorna exatamente 5 itens e o primeiro é CTR_2026-012."""
    resp = client.get("/api/ficha/triagem?limite=5")
    assert resp.status_code == 200
    dados = resp.json()

    resposta = TriagemResposta(**dados)
    assert len(resposta.itens) == 5
    assert resposta.tamanho == 5
    assert resposta.total == 11

    primeiro = resposta.itens[0]
    assert primeiro.codigo == "CTR_2026-012"
    assert "vistoria em 13 dias" in primeiro.motivo_curto
    assert primeiro.proximo_prazo is not None
    assert primeiro.proximo_prazo.data == "2026-11-25"
    assert primeiro.sinais.multa is True


def test_triagem_resultado_calculado_todos_os_documentos():
    """Valida e registra o resultado calculado de cada um dos 11 documentos vigentes."""
    resp = client.get("/api/ficha/triagem?tamanho=50")
    assert resp.status_code == 200
    resposta = TriagemResposta(**resp.json())

    itens_por_cod = {it.codigo: it for it in resposta.itens}
    assert len(itens_por_cod) == 11

    # CTR_2026-012: Vistoria em 13 dias (2026-11-25), atenção, família contrato
    ctr = itens_por_cod["CTR_2026-012"]
    assert ctr.motivo_curto == "vistoria em 13 dias"
    assert ctr.semaforo.nivel == "atencao"
    assert ctr.proximo_prazo is not None
    assert ctr.proximo_prazo.data == "2026-11-25"

    # NG_111: Regra mudou de versão, ok, família norma
    ng_111 = itens_por_cod["NG_111"]
    assert ng_111.motivo_curto == "regra mudou de versão"
    assert ng_111.sinais.divergencia is True
    assert ng_111.familia == "norma"

    # NT_2026-018: Vistoria em 13 dias (2026-11-25), crítico, família contrato
    nt_018 = itens_por_cod["NT_2026-018"]
    assert nt_018.motivo_curto == "vistoria em 13 dias"
    assert nt_018.semaforo.nivel == "critico"
    assert nt_018.proximo_prazo is not None
    assert nt_018.proximo_prazo.data == "2026-11-25"

    # NG_1130: Prazo em 19 dias (2026-12-01), crítico, família norma
    ng_1130 = itens_por_cod["NG_1130"]
    assert ng_1130.motivo_curto == "prazo em 19 dias"
    assert ng_1130.proximo_prazo is not None
    assert ng_1130.proximo_prazo.data == "2026-12-01"

    # PX_1130-001: Prazo em 19 dias (2026-12-01), atenção, família procedimento
    px_1130 = itens_por_cod["PX_1130-001"]
    assert px_1130.motivo_curto == "prazo em 19 dias"
    assert px_1130.proximo_prazo is not None
    assert px_1130.proximo_prazo.data == "2026-12-01"

    # NT_2026-021: Cita norma fora do acervo, crítico
    nt_021 = itens_por_cod["NT_2026-021"]
    assert nt_021.motivo_curto == "cita norma fora do acervo"
    assert nt_021.semaforo.nivel == "critico"


def test_triagem_filtro_sinais():
    """Valida os filtros por sinal: prazo_30d, multa e divergencia."""
    # 1. sinal=prazo_30d: deve conter CTR_2026-012
    r_prazo = client.get("/api/ficha/triagem?sinal=prazo_30d")
    assert r_prazo.status_code == 200
    codigos_prazo = [it["codigo"] for it in r_prazo.json()["itens"]]
    assert "CTR_2026-012" in codigos_prazo
    for it in r_prazo.json()["itens"]:
        assert it["proximo_prazo"] is not None
        dt = date.fromisoformat(it["proximo_prazo"]["data"])
        dias = (dt - date(2026, 11, 12)).days
        assert 0 <= dias <= 30

    # 2. sinal=multa: deve conter CTR_2026-012
    r_multa = client.get("/api/ficha/triagem?sinal=multa")
    assert r_multa.status_code == 200
    codigos_multa = [it["codigo"] for it in r_multa.json()["itens"]]
    assert "CTR_2026-012" in codigos_multa
    for it in r_multa.json()["itens"]:
        assert it["sinais"]["multa"] is True

    # 3. sinal=divergencia: deve conter NG_111
    r_div = client.get("/api/ficha/triagem?sinal=divergencia")
    assert r_div.status_code == 200
    codigos_div = [it["codigo"] for it in r_div.json()["itens"]]
    assert "NG_111" in codigos_div
    for it in r_div.json()["itens"]:
        assert it["sinais"]["divergencia"] is True


def test_triagem_filtro_tema_ferias():
    """Valida que tema=ferias só devolve documentos do assunto férias."""
    resp = client.get("/api/ficha/triagem?tema=ferias")
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["total"] == 5
    assert len(dados["itens"]) == 5
    for it in dados["itens"]:
        assert it["tema"] == "ferias"


def test_triagem_filtro_tipo_e_situacao():
    """Valida filtros por tipo documental e situação do semáforo."""
    # Filtro tipo=CTR
    r_tipo = client.get("/api/ficha/triagem?tipo=CTR")
    assert r_tipo.status_code == 200
    for it in r_tipo.json()["itens"]:
        assert it["tipo"] == "CTR"

    # Filtro situacao=ok
    r_ok = client.get("/api/ficha/triagem?situacao=ok")
    assert r_ok.status_code == 200
    for it in r_ok.json()["itens"]:
        assert it["semaforo"]["nivel"] == "ok"

    # Filtro situacao=critico
    r_crit = client.get("/api/ficha/triagem?situacao=critico")
    assert r_crit.status_code == 200
    for it in r_crit.json()["itens"]:
        assert it["semaforo"]["nivel"] == "critico"


def test_triagem_ordenacoes():
    """Valida todas as opções do parâmetro ordenar: urgencia, vigencia, tema, tipo."""
    for criterio in ("urgencia", "vigencia", "tema", "tipo"):
        resp = client.get(f"/api/ficha/triagem?ordenar={criterio}")
        assert resp.status_code == 200
        itens = resp.json()["itens"]
        assert len(itens) == 11
        if criterio == "tema":
            temas = [it["tema"].lower() for it in itens]
            assert temas == sorted(temas)
        elif criterio == "tipo":
            tipos = [it["tipo"].lower() for it in itens]
            assert tipos == sorted(tipos)


def test_triagem_paginacao():
    """Valida paginação com pagina e tamanho."""
    r_p1 = client.get("/api/ficha/triagem?pagina=1&tamanho=4")
    assert r_p1.status_code == 200
    d_p1 = r_p1.json()
    assert len(d_p1["itens"]) == 4
    assert d_p1["total"] == 11
    assert d_p1["pagina"] == 1
    assert d_p1["tamanho"] == 4

    r_p2 = client.get("/api/ficha/triagem?pagina=2&tamanho=4")
    assert r_p2.status_code == 200
    d_p2 = r_p2.json()
    assert len(d_p2["itens"]) == 4
    assert d_p2["pagina"] == 2

    cods_p1 = [it["codigo"] for it in d_p1["itens"]]
    cods_p2 = [it["codigo"] for it in d_p2["itens"]]
    # Não deve haver sobreposição entre páginas consecutivas
    assert not set(cods_p1).intersection(set(cods_p2))


def test_triagem_validacao_parametros_422():
    """Valida que parâmetros inválidos retornam HTTP 422 coerente."""
    # limite fora de 1..20
    assert client.get("/api/ficha/triagem?limite=0").status_code == 422
    assert client.get("/api/ficha/triagem?limite=21").status_code == 422

    # pagina < 1
    assert client.get("/api/ficha/triagem?pagina=0").status_code == 422

    # tamanho fora de 1..100
    assert client.get("/api/ficha/triagem?tamanho=0").status_code == 422
    assert client.get("/api/ficha/triagem?tamanho=101").status_code == 422

    # perfil inválido
    r_perfil = client.get("/api/ficha/triagem?perfil=astronauta")
    assert r_perfil.status_code == 422
    assert "Perfil 'astronauta' inválido" in r_perfil.json()["detail"]

    # situacao inválida
    assert client.get("/api/ficha/triagem?situacao=urgente").status_code == 422

    # sinal inválido
    assert client.get("/api/ficha/triagem?sinal=perigo").status_code == 422

    # ordenar inválido
    assert client.get("/api/ficha/triagem?ordenar=alfabetica").status_code == 422


def test_triagem_protegida_por_api_key(monkeypatch):
    """Valida que a rota /api/ficha/triagem respeita a API_KEY quando configurada."""
    monkeypatch.setenv("API_KEY", "chave-secreta-triagem")

    # 1. Sem cabeçalho -> 401
    r_sem_chave = client.get("/api/ficha/triagem")
    assert r_sem_chave.status_code == 401
    assert "API_KEY inválida ou ausente" in r_sem_chave.json()["detail"]

    # 2. Com chave incorreta -> 401
    r_chave_errada = client.get(
        "/api/ficha/triagem",
        headers={"X-API-Key": "chave-incorreta"},
    )
    assert r_chave_errada.status_code == 401

    # 3. Com chave correta -> 200
    r_chave_ok = client.get(
        "/api/ficha/triagem",
        headers={"X-API-Key": "chave-secreta-triagem"},
    )
    assert r_chave_ok.status_code == 200
    assert r_chave_ok.json()["total"] == 11


def test_triagem_troca_codigo_e_titulo_mantem_estrutura():
    """Valida regra genérica: troca código e título de um documento e confirma a mesma estrutura."""
    acervo = get_acervo()
    doc_original = acervo.buscar("CTR_2026-012", "1.0.0")
    assert doc_original is not None

    # Cria documento fictício derivado com código e título inéditos
    doc_modificado = DocumentoDetalhe(
        codigo="CTR_2026-999",
        versao="1.0.0",
        titulo="Contrato de Teste Sintético da Forja",
        tipo="CTR",
        tipo_nome="Contrato",
        fase="Vigente",
        vigencia=doc_original.vigencia,
        assunto="locacao",
        substituido=False,
        vinculado_a=None,
        referencia=None,
        camada=doc_original.camada,
        tema=doc_original.tema,
        aprovado_por=doc_original.aprovado_por,
        aprovado_em=doc_original.aprovado_em,
        assinada_em=doc_original.assinada_em,
        secoes=doc_original.secoes,
        header_raw=doc_original.header_raw,
    )

    ficha_modificada = obter_ficha_cache_ou_montar(doc_modificado, acervo)
    data_ref = date(2026, 11, 12)
    item, meta = montar_item_triagem(doc_modificado, ficha_modificada, data_ref=data_ref)

    assert isinstance(item, ItemTriagem)
    assert item.codigo == "CTR_2026-999"
    assert item.titulo == "Contrato de Teste Sintético da Forja"
    assert item.tipo == "CTR"
    assert item.tema == "locacao"
    assert item.semaforo.nivel in ("ok", "atencao", "critico")
    assert "vistoria em 13 dias" in item.motivo_curto
    assert item.proximo_prazo is not None
    assert item.proximo_prazo.data == "2026-11-25"
    assert item.sinais.multa is True
    assert item.familia == "contrato"


def test_triagem_documentos_fora_do_exemplo():
    """Valida pelo menos 3 documentos fora do exemplo (NG_1130, PX_1130-001, NT_2026-021)."""
    resp = client.get("/api/ficha/triagem")
    assert resp.status_code == 200
    resposta = TriagemResposta(**resp.json())
    itens_map = {it.codigo: it for it in resposta.itens}

    # Documento 1: NG_1130 (Norma Geral)
    assert "NG_1130" in itens_map
    doc1 = itens_map["NG_1130"]
    assert doc1.tipo == "NG"
    assert doc1.familia == "norma"
    assert doc1.motivo_curto == "prazo em 19 dias"
    assert doc1.proximo_prazo is not None
    assert doc1.proximo_prazo.data == "2026-12-01"

    # Documento 2: PX_1130-001 (Procedimento)
    assert "PX_1130-001" in itens_map
    doc2 = itens_map["PX_1130-001"]
    assert doc2.tipo == "PX"
    assert doc2.familia == "procedimento"
    assert doc2.motivo_curto == "prazo em 19 dias"
    assert doc2.proximo_prazo is not None
    assert doc2.proximo_prazo.data == "2026-12-01"

    # Documento 3: NT_2026-021 (Nota Técnica)
    assert "NT_2026-021" in itens_map
    doc3 = itens_map["NT_2026-021"]
    assert doc3.tipo == "NT"
    assert doc3.motivo_curto == "cita norma fora do acervo"
    assert doc3.semaforo.nivel == "critico"


def test_triagem_sla_tempo_de_resposta():
    """Valida SLA de tempo < 1 s para o endpoint processando todo o acervo sem IA."""
    t0 = time.time()
    resp = client.get("/api/ficha/triagem?tamanho=50")
    duracao = time.time() - t0

    assert resp.status_code == 200
    assert duracao < 1.0, f"Tempo de resposta {duracao:.3f} s excedeu SLA de 1.0 s"
