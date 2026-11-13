"""Testes dos sinais por seção e do mapa de posição (F-02, issue #42). Sem rede."""

import pytest

from app.acervo import get_acervo
from app.ficha.modelos import CelulaMapa, Metricas
from app.ficha.sinais import (
    FORTE,
    MEDIO,
    FRACO,
    SINAIS,
    PontuacaoSecao,
    limiares_do_documento,
    mapa_do_documento,
    metricas_do_documento,
    pontuar_texto,
)
from app.models import DocumentoDetalhe, Secao


def _doc(*secoes) -> DocumentoDetalhe:
    """Documento do acervo com as seções trocadas por textos curtos de teste."""
    base = get_acervo().buscar("CTR_2026-012", "1.0.0")
    return base.model_copy(update={"secoes": [Secao(id=i, titulo=t, texto=x) for i, t, x in secoes]})


def _celula(mapa, secao_id) -> CelulaMapa:
    return next(c for c in mapa if c.secao_id == secao_id)


# ---------------------------------------------------------------------------
# Padrões e forças
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto, sinal, forca",
    [
        ("O aluguel é de R$ 3.650,00.", "valor", FORTE),
        ("Resultado 18.250,00 conforme a tabela.", "valor", FORTE),
        ("Multa equivalente a um aluguel mensal.", "valor", FORTE),
        ("Acréscimo limitado a 20% do contrato.", "valor", MEDIO),
        ("Entrega em 25/11/2026.", "prazo", FORTE),
        ("Solicitar até D-45.", "prazo", FORTE),
        ("Pagamento até o dia 8 de cada mês.", "prazo", FORTE),
        ("Se ocorrer até o 90º dia de vigência.", "prazo", FORTE),
        ("Aviso por escrito de 30 dias.", "prazo", MEDIO),
        ("Respeitar o prazo informado.", "prazo", FRACO),
        ("A LOCADORA obriga-se a manter o espaço.", "obrigacao", FORTE),
        ("Cabe ao NIN operar o funil.", "obrigacao", FORTE),
        ("O fiscal técnico atesta a prestação.", "obrigacao", FORTE),
        ("Por isso a DIRAF aprova.", "obrigacao", FORTE),
        ("Gasto entre os limites: diretor da DIRTEC.", "obrigacao", FORTE),
        ("A GGC emite o aviso.", "obrigacao", MEDIO),
        ("O empregado deve registrar.", "obrigacao", FRACO),
        ("Aplica-se multa por inexecução.", "risco", FORTE),
        ("Fica na alçada de diretor.", "risco", FORTE),
        ("É vedado o início nesses dias.", "risco", MEDIO),
        ("Antecedência mínima de 45 dias.", "risco", MEDIO),
        ("Até o limite do orçamento.", "risco", FRACO),
    ],
)
def test_cada_padrao_acende_o_sinal_com_a_forca_esperada(texto, sinal, forca):
    p = pontuar_texto(texto)
    assert p.contagens[sinal] >= 1
    assert p.pontos[sinal] >= forca
    assert p.tem_forte[sinal] is (forca == FORTE)


def test_valor_com_r_cifrao_conta_uma_vez_so():
    assert pontuar_texto("O aluguel é de R$ 3.650,00.").contagens["valor"] == 1
    assert pontuar_texto("Total R$3.650,00 e 18.250,00.").contagens["valor"] == 2


def test_so_palavras_fracas_nao_acendem_o_sinal():
    doc = _doc(("1", "Prazos", "Observe o prazo, o prazo e a antecedência."), ("2", "Neutra", "Nada aqui."))
    assert _celula(mapa_do_documento(doc), "1").sinais.prazo == 0


def test_texto_neutro_nao_acende_nada():
    p = pontuar_texto("Este documento descreve o funcionamento geral do espaço de trabalho.")
    assert all(p.contagens[s] == 0 for s in SINAIS)


def test_padroes_ignoram_acento_e_caixa():
    assert pontuar_texto("RESCISÃO e PENALIDADE").contagens["risco"] == 2
    assert pontuar_texto("rescisao e penalidade").contagens["risco"] == 2


# ---------------------------------------------------------------------------
# Normalização por documento
# ---------------------------------------------------------------------------

def _pont(pontos: int, forte: bool = False) -> PontuacaoSecao:
    base = {s: 0 for s in SINAIS}
    return PontuacaoSecao(
        contagens={**base, "prazo": 1 if pontos else 0},
        pontos={**base, "prazo": pontos},
        tem_forte={**{s: False for s in SINAIS}, "prazo": forte},
    )


def test_limiar_e_o_quartil_superior_das_pontuacoes_positivas():
    # Posto mais próximo: percentil 75 de [1, 1, 2, 6] é o 3º valor (2); o zero não entra.
    limiares = limiares_do_documento([_pont(1), _pont(1), _pont(2), _pont(6), _pont(0)])
    assert limiares["prazo"] == 2.0
    assert limiares["valor"] == float("inf")  # sinal ausente no documento nunca acende


def test_palavra_solta_nao_acende_quando_ha_sinais_mais_fortes_no_documento():
    doc = _doc(
        ("1", "Geral", "Observe o prazo."),
        ("2", "Prazo", "Observe o prazo e a antecedência."),
        ("3", "Datas", "Entrega em 25/11/2026 e vistoria em 30/11/2026."),
        ("4", "Outros", "Respeite o prazo."),
    )
    mapa = mapa_do_documento(doc)
    assert _celula(mapa, "3").sinais.prazo == 2
    assert [_celula(mapa, i).sinais.prazo for i in ("1", "2", "4")] == [0, 0, 0]


def test_padrao_medio_so_acende_acima_do_limiar_e_empate_nao_acende():
    doc = _doc(
        ("1", "A", "Em 30 dias."),            # médio: 2 pontos
        ("2", "B", "Em 30 dias."),            # médio: 2 pontos
        ("3", "C", "Em 30 dias."),            # médio: 2 pontos (3º quartil = 2)
        ("4", "D", "Em 30 dias e 60 dias."),  # médio: 4 pontos, acima do limiar
    )
    mapa = mapa_do_documento(doc)
    assert [_celula(mapa, i).sinais.prazo for i in ("1", "2", "3", "4")] == [0, 0, 0, 2]


def test_padrao_forte_sempre_acende_mesmo_abaixo_do_limiar():
    doc = _doc(
        ("1", "A", "Até 10/01/2027."),
        ("2", "B", "Entre 10/01/2027 e 20/01/2027, em 30 dias, 60 dias e 90 dias, prazo e prorrogação."),
    )
    mapa = mapa_do_documento(doc)
    assert _celula(mapa, "1").sinais.prazo == 1
    assert _celula(mapa, "2").sinais.prazo > 0


def test_intensidade_vai_de_0_a_1_e_a_secao_mais_carregada_vale_1():
    doc = _doc(
        ("1", "Neutra", "Texto descritivo sem nada relevante."),
        ("2", "Valor", "Valor de R$ 1.000,00."),
        ("3", "Multa", "Multa de R$ 500,00 e rescisão em 25/11/2026."),
    )
    mapa = mapa_do_documento(doc)
    intensidades = {c.secao_id: c.intensidade for c in mapa}
    assert intensidades["1"] == 0.0
    assert intensidades["3"] == 1.0
    assert 0.0 < intensidades["2"] < 1.0


# ---------------------------------------------------------------------------
# Estrutura, peso e determinismo
# ---------------------------------------------------------------------------

def test_mapa_tem_uma_celula_por_secao_na_ordem_e_valida_contra_o_modelo():
    doc = _doc(("1", "Um", "texto"), ("2", "Dois", "mais texto aqui"), ("Anexo A", "Três", "x"))
    mapa = mapa_do_documento(doc)
    assert [c.secao_id for c in mapa] == ["1", "2", "Anexo A"]
    assert [c.ordem for c in mapa] == [1, 2, 3]
    for c in mapa:
        CelulaMapa.model_validate(c.model_dump())


def test_documento_sem_secoes_devolve_mapa_vazio():
    assert mapa_do_documento(_doc()) == []


def test_mesmo_texto_gera_o_mesmo_mapa():
    doc = get_acervo().buscar("CTR_2026-012", "1.0.0")
    assert [c.model_dump() for c in mapa_do_documento(doc)] == [c.model_dump() for c in mapa_do_documento(doc)]


@pytest.mark.parametrize("codigo", [d.codigo for d in get_acervo().listar()])
def test_soma_dos_pesos_e_1_em_todos_os_documentos_do_acervo(codigo):
    for doc in get_acervo().documentos:
        if doc.codigo != codigo:
            continue
        mapa = mapa_do_documento(doc)
        assert len(mapa) == len(doc.secoes)
        assert abs(sum(c.peso for c in mapa) - 1.0) <= 0.01
        assert all(0.0 <= c.intensidade <= 1.0 for c in mapa)


# ---------------------------------------------------------------------------
# Aceite da issue #42 no CTR_2026-012
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mapa_ctr():
    return mapa_do_documento(get_acervo().buscar("CTR_2026-012", "1.0.0"))


def test_ctr_clausula_setima_tem_valor(mapa_ctr):
    assert _celula(mapa_ctr, "Cláusula Sétima").sinais.valor > 0


def test_ctr_clausula_decima_terceira_tem_prazo_e_risco(mapa_ctr):
    s = _celula(mapa_ctr, "Cláusula Décima Terceira").sinais
    assert s.prazo > 0 and s.risco > 0


def test_ctr_apendice_b_tem_valor_e_risco(mapa_ctr):
    s = _celula(mapa_ctr, "Apêndice B").sinais
    assert s.valor > 0 and s.risco > 0


def test_metricas_do_ctr():
    doc = get_acervo().buscar("CTR_2026-012", "1.0.0")
    m = metricas_do_documento(doc)
    assert isinstance(m, Metricas)
    assert m.secoes == 43
    assert m.paginas_estimadas == -(-m.palavras // 400)
    assert m.leitura_integral_min == max(1, round(m.palavras / 200))


# ---------------------------------------------------------------------------
# Metas do eval contra a curadoria
# ---------------------------------------------------------------------------

def test_eval_sinais_cumpre_as_metas_da_issue():
    from eval.sinais import avaliar

    r = avaliar()
    assert r["prazo"]["pct_marcadas"] <= 20.0
    assert r["prazo"]["recall"] >= 90.0
    assert r["obrigacao"]["recall"] >= 70.0
    assert r["risco"]["recall"] >= 70.0
