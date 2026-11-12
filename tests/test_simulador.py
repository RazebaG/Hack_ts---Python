"""Testes do simulador "E se?" (Issue #8, Adendo v0.2).

- GET /api/regras
- POST /api/simular: férias 45→30 (P0) e alçada de gerente 18.000→20.000.
- Prova de que nada é fixo no código: com um acervo alterado, valores e datas mudam.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.acervo import AcervoRepository, get_acervo
from app.inteligencia import trecho_consta_na_secao
from app.main import app
from app.models import SimularRequest
from app.simulador import SimuladorService, formatar_brl, ler_faixas, trecho_em_volta

client = TestClient(app)
ACERVO_DIR = Path(__file__).resolve().parent.parent / "data" / "acervo"
AVISO = "Simulação hipotética: não altera os documentos."


def simular(regra, novo_valor, **extra):
    return client.post("/api/simular", json={"regra": regra, "novo_valor": novo_valor, **extra})


def todas_as_fontes(data):
    for marco in data["linha_do_tempo"]:
        yield marco["fonte"]
    for impacto in data["impactos"]:
        yield from impacto["fontes"]


def assert_fontes_constam_no_acervo(fontes):
    """Toda fonte aponta para documento/versão/seção existentes e o trecho é literal."""
    acervo = get_acervo()
    for f in fontes:
        doc = acervo.buscar(f["codigo"], f["versao"])
        assert doc is not None, f
        textos = [s.texto for s in doc.secoes if s.id == f["secao"]]
        assert textos, f
        assert any(trecho_consta_na_secao(f["trecho"], t) for t in textos), f


# --- GET /api/regras -------------------------------------------------------------

def test_regras_traz_antecedencia_45_com_fonte_4_5_1():
    r = client.get("/api/regras")
    assert r.status_code == 200
    regra = next(x for x in r.json() if x["id"] == "ferias_antecedencia_dias")
    assert regra["valor"] == 45
    assert regra["unidade"] == "dias"
    assert regra["fonte"]["codigo"] == "NG_111"
    assert regra["fonte"]["versao"] == "3.0.0"
    assert regra["fonte"]["secao"] == "4.5.1"
    assert "45 dias" in regra["fonte"]["trecho"]


def test_regras_traz_alcada_gerente_do_anexo_f():
    regra = next(x for x in client.get("/api/regras").json() if x["id"] == "alcada_gerente_max")
    assert regra["valor"] == 18000
    assert regra["unidade"] == "BRL"
    assert (regra["fonte"]["codigo"], regra["fonte"]["secao"]) == ("NT_2026-018", "Anexo F")


def test_fontes_das_regras_constam_no_acervo():
    assert_fontes_constam_no_acervo(r["fonte"] for r in client.get("/api/regras").json())


# --- POST /api/simular: férias ---------------------------------------------------

def test_ferias_45_para_30_prova_de_aceite():
    r = simular("ferias_antecedencia_dias", 30)
    assert r.status_code == 200
    data = r.json()
    assert data["valor_atual"] == 45 and data["novo_valor"] == 30
    assert data["inicio_gozo"] == "2027-05-05"
    assert data["aviso"] == AVISO

    marcos = {m["fonte"]["secao"]: m for m in data["linha_do_tempo"]}
    assert set(marcos) == {"4.5.1", "4.5.3", "4.5.4", "4.5.5"}
    sol = marcos["4.5.1"]
    assert (sol["antes"], sol["depois"], sol["muda"]) == ("2027-03-21", "2027-04-05", True)
    # Só a solicitação muda; as datas dos outros marcos batem com o Anexo C/PX Anexo D.
    assert [m["muda"] for s, m in marcos.items() if s != "4.5.1"] == [False, False, False]
    assert marcos["4.5.3"]["antes"] == "2027-03-31"
    assert marcos["4.5.4"]["antes"] == "2027-04-05"
    assert marcos["4.5.5"]["antes"] == "2027-04-30"  # D-3 cai no domingo 02/05 → dia útil anterior

    conflitos = [i for i in data["impactos"] if i["tipo"] == "conflito_interno"]
    assert any(f["secao"] == "4.5.3" for c in conflitos for f in c["fontes"])

    revisar = [i for i in data["impactos"] if i["tipo"] == "revisar_documento"]
    codigos = {i["codigo"] for i in revisar}
    assert codigos == {"NG_111", "PX_1111-001", "FM_1111-001", "TB_1111-001", "FL_1111-001"}
    acervo = get_acervo()
    for i in revisar:
        assert not acervo.buscar(i["codigo"], i["versao"]).substituido
        assert all(f["versao"] == i["versao"] for f in i["fontes"])
    assert {(i["codigo"], i["versao"]) for i in revisar}.isdisjoint({("NG_111", "2.0.0"), ("FM_1111-001", "1.0.0")})
    assert data["resumo"]


def test_ferias_fontes_da_simulacao_constam_no_acervo():
    assert_fontes_constam_no_acervo(todas_as_fontes(simular("ferias_antecedencia_dias", 30).json()))


def test_ferias_45_nada_muda():
    data = simular("ferias_antecedencia_dias", 45).json()
    assert all(not m["muda"] for m in data["linha_do_tempo"])
    assert data["impactos"] == []
    assert data["aviso"] == AVISO


def test_ferias_aumentar_prazo_nao_gera_conflito():
    data = simular("ferias_antecedencia_dias", 60).json()
    sol = next(m for m in data["linha_do_tempo"] if m["fonte"]["secao"] == "4.5.1")
    assert sol["depois"] == "2027-03-06"
    assert not [i for i in data["impactos"] if i["tipo"] == "conflito_interno"]
    assert [i for i in data["impactos"] if i["tipo"] == "revisar_documento"]


def test_ferias_cenario_com_data_muda_o_inicio():
    data = simular("ferias_antecedencia_dias", 30, cenario="Férias a partir de 01/07/2027").json()
    assert data["inicio_gozo"] == "2027-07-01"
    sol = next(m for m in data["linha_do_tempo"] if m["fonte"]["secao"] == "4.5.1")
    assert (sol["antes"], sol["depois"]) == ("2027-05-17", "2027-06-01")


# --- POST /api/simular: alçada ---------------------------------------------------

def test_alcada_18000_para_20000_muda_aprovador_do_contrato():
    data = simular("alcada_gerente_max", 20000).json()
    assert data["valor_atual"] == 18000 and data["novo_valor"] == 20000
    assert data["aviso"] == AVISO
    muda = [i for i in data["impactos"] if i["tipo"] == "muda_aprovador"]
    assert len(muda) == 1
    assert muda[0]["codigo"] == "CTR_2026-012"
    assert (muda[0]["antes"], muda[0]["depois"]) == ("Diretor", "Gerente")
    assert "18.250,00" in muda[0]["descricao"]
    assert muda[0]["fontes"][0]["secao"] == "Cláusula Sétima"
    assert {i["codigo"] for i in data["impactos"] if i["tipo"] == "revisar_documento"} == {"NT_2026-018"}
    assert_fontes_constam_no_acervo(todas_as_fontes(data))


def test_alcada_que_nao_cobre_o_contrato_nao_muda_aprovador():
    data = simular("alcada_gerente_max", 18200).json()
    assert not [i for i in data["impactos"] if i["tipo"] == "muda_aprovador"]


def test_alcada_acima_do_teto_do_diretor_e_conflito_interno():
    data = simular("alcada_gerente_max", 150000).json()
    assert any(i["tipo"] == "conflito_interno" for i in data["impactos"])


def test_alcada_igual_nada_muda():
    assert simular("alcada_gerente_max", 18000).json()["impactos"] == []


# --- Erros -----------------------------------------------------------------------

def test_regra_desconhecida_404():
    r = simular("multa_inexistente", 10)
    assert r.status_code == 404
    assert "detail" in r.json()


@pytest.mark.parametrize("valor", [0, -5, 91, 30.5])
def test_novo_valor_invalido_422(valor):
    assert simular("ferias_antecedencia_dias", valor).status_code == 422


# --- Nada fixo no código ---------------------------------------------------------

def _acervo_alterado(tmp_path: Path, de: str, para: str) -> AcervoRepository:
    destino = tmp_path / "acervo"
    shutil.copytree(ACERVO_DIR, destino)
    norma = destino / "ferias" / "NG_111__FERIAS__v3.0.0.md"
    texto = norma.read_text(encoding="utf-8")
    assert de in texto
    norma.write_text(texto.replace(de, para), encoding="utf-8")
    return AcervoRepository(destino)


def test_valor_e_datas_vem_do_texto_do_acervo(tmp_path):
    acervo = _acervo_alterado(tmp_path, "Solicitação: até 45 dias antes.", "Solicitação: até 50 dias antes.")
    servico = SimuladorService(acervo=acervo)
    regra = next(r for r in servico.listar_regras() if r.id == "ferias_antecedencia_dias")
    assert regra.valor == 50
    resp = servico.simular(SimularRequest(regra="ferias_antecedencia_dias", novo_valor=50))
    assert resp.impactos == []
    sol = next(m for m in resp.linha_do_tempo if m.fonte.secao == "4.5.1")
    assert sol.antes == "2027-03-16"


def test_regra_sem_fonte_no_acervo_fica_fora(tmp_path):
    acervo = _acervo_alterado(tmp_path, "4.5.1. Solicitação: até 45 dias antes.", "")
    servico = SimuladorService(acervo=acervo)
    assert "ferias_antecedencia_dias" not in {r.id for r in servico.listar_regras()}


# --- Unidades ----------------------------------------------------------------------

def test_ler_faixas_do_quadro():
    faixas, _ = ler_faixas("Faixa\n\nQuem aprova\n\nAté R$ 10,00\n\nA\n\nDe R$ 10,01 a R$ 99,00\n\nB\n")
    assert [(f.papel, f.minimo, f.maximo) for f in faixas] == [("A", None, 10.0), ("B", 10.01, 99.0)]


def test_formatar_brl():
    assert formatar_brl(18250) == "R$ 18.250,00"
    assert formatar_brl(1234567.8) == "R$ 1.234.567,80"


def test_trecho_em_volta_corta_texto_longo():
    texto = " ".join(f"palavra{i}" for i in range(200)) + " ALVO " + " ".join(f"fim{i}" for i in range(200))
    ini = texto.index("ALVO")
    trecho = trecho_em_volta(texto, ini, ini + 4, maximo=80)
    assert "ALVO" in trecho and len(trecho) <= 90
    assert trecho.startswith("…") and trecho.endswith("…")
