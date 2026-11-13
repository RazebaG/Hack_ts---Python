"""Testes para modelos Pydantic e extração de metadados de governança (C22 / F-01).

Especificação: CONTRATO-API-ADENDO-v0.4.md, PRD-FICHA-DO-DOCUMENTO.md e Issue #45.
"""

import json
import math
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.acervo import get_acervo
from app.models import Fonte, DocumentoDetalhe, Secao
from app.parser import parse_header, parse_document_text
from app.ficha.modelos import (
    FichaDocumento,
    Identidade,
    Metricas,
    Semaforo,
    Governanca,
    CampoGov,
    FonteGov,
    ItemFicha,
    Acao,
    Bloco,
    RelevanciaBloco,
    CelulaMapa,
    SinaisCelula,
    Alerta,
    Cobertura,
    ProgressoFicha,
    VigenciaFicha,
    FamiliaDocumento,
)
from app.ficha.metadados import (
    extrair_metadados_documento,
    extrair_governanca,
    extrair_identidade,
    extrair_metricas,
    extrair_vigencia,
    extrair_classificacao,
    derivar_familia,
    gerar_semaforo_base,
    obter_cadeia_subordinacao,
)


@pytest.fixture
def mock_ficha_data() -> dict:
    caminhos = [
        Path("tests/fixtures/mock-ficha-CTR_2026-012.json"),
        Path("docs/ficha-do-documento/mock-ficha-CTR_2026-012.json"),
    ]
    for p in caminhos:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    pytest.fail("Fixture mock-ficha-CTR_2026-012.json não encontrada.")


def test_mock_ficha_ctr_2026_012_valida_contra_fichadocumento(mock_ficha_data):
    """O exemplo mock-ficha-CTR_2026-012.json valida contra FichaDocumento (ignora _nota)."""
    assert "_nota" in mock_ficha_data
    ficha = FichaDocumento.model_validate(mock_ficha_data)
    assert ficha.codigo == "CTR_2026-012"
    assert ficha.versao == "1.0.0"
    assert ficha.estado == "pronta"
    assert ficha.familia == "contrato"
    assert ficha.identidade.titulo == "Contrato de Locação de Espaço"
    assert ficha.identidade.classificacao == "interna"
    assert ficha.identidade.vigencia.texto == "30/11/2026 a 29/04/2027"
    assert ficha.identidade.vigencia.inicio == "2026-11-30"
    assert ficha.identidade.vigencia.fim == "2027-04-29"
    assert ficha.identidade.vigencia.dias_restantes == 168
    assert len(ficha.blocos) == 6
    assert ficha.governanca.elaborado_por.valor == "Gerência de Compras e Contratos (GCO)"
    assert ficha.governanca.aprovado_por.valor == "Diretoria Administrativa e Financeira (DIRAF)"
    assert ficha.governanca.assinada_em.valor is None
    assert ficha.governanca.aprovado_em.valor is None
    assert ficha.cobertura.itens_verificados == 14


def test_metadados_governanca_todos_13_documentos_acervo():
    """Valida metadados e governança para todos os 13 documentos do acervo."""
    acervo = get_acervo()
    assert len(acervo.documentos) == 13

    for doc in acervo.documentos:
        identidade, governanca, semaforo, familia = extrair_metadados_documento(
            doc, data_referencia="2026-11-12", acervo=acervo
        )
        assert isinstance(identidade, Identidade)
        assert isinstance(governanca, Governanca)
        assert isinstance(semaforo, Semaforo)
        assert familia in ("contrato", "norma", "procedimento", "nota_tecnica")

        # Classificação do cabeçalho
        assert identidade.classificacao == "interna"

        # Métricas determinísticas
        assert identidade.metricas.secoes == len(doc.secoes)
        assert identidade.metricas.palavras > 0
        assert identidade.metricas.paginas_estimadas == math.ceil(identidade.metricas.palavras / 400)
        assert identidade.metricas.leitura_integral_min == max(1, round(identidade.metricas.palavras / 200))

        # Governança: campo ausente deve ter valor: null e fonte: null
        for campo_nome in ("elaborado_por", "aprovado_por", "aprovado_em", "assinada_em", "vinculado_a"):
            campo_gov: CampoGov = getattr(governanca, campo_nome)
            if campo_gov.valor is None:
                assert campo_gov.fonte is None, f"{doc.codigo}: campo {campo_nome} valor é None mas fonte existe"
            else:
                assert campo_gov.fonte is not None, f"{doc.codigo}: campo {campo_nome} tem valor mas fonte é None"
                assert campo_gov.fonte.campo is not None
                assert campo_gov.valor in campo_gov.fonte.trecho

        # Cadeia começa com o próprio documento
        assert governanca.cadeia[0] == doc.codigo


def test_ctr_2026_012_aceite_especifico():
    """CTR_2026-012: elaborado, aprovado, assinada_em e aprovado_em nulos, classificação interna, vigência 30/11/2026 a 29/04/2027."""
    acervo = get_acervo()
    doc = acervo.buscar("CTR_2026-012")
    assert doc is not None

    identidade, governanca, semaforo, familia = extrair_metadados_documento(
        doc, data_referencia="2026-11-12", acervo=acervo
    )

    assert governanca.elaborado_por.valor == "Gerência de Compras e Contratos (GCO)"
    assert governanca.elaborado_por.fonte.trecho == "Elaborado por: Gerência de Compras e Contratos (GCO)"
    assert governanca.aprovado_por.valor == "Diretoria Administrativa e Financeira (DIRAF)"
    assert governanca.aprovado_por.fonte.trecho == "Aprovado por: Diretoria Administrativa e Financeira (DIRAF)"

    assert governanca.assinada_em.valor is None
    assert governanca.assinada_em.fonte is None

    assert governanca.aprovado_em.valor is None
    assert governanca.aprovado_em.fonte is None

    assert identidade.classificacao == "interna"
    assert identidade.vigencia.texto == "30/11/2026 a 29/04/2027"
    assert identidade.vigencia.inicio == "2026-11-30"
    assert identidade.vigencia.fim == "2027-04-29"
    assert identidade.vigencia.dias_restantes == 168
    assert familia == "contrato"
    assert governanca.referencias == ["NT_2026-018", "NG_012"]
    assert governanca.cadeia == ["CTR_2026-012"]


def test_documento_sem_assinada_em_nunca_recebe_valor():
    """Documentos sem 'Assinada em' no cabeçalho nunca recebem valor para esse campo."""
    acervo = get_acervo()
    docs_sem_assinatura = [
        "CTR_2026-012",
        "NG_111",
        "PX_1111-001",
        "FM_1111-001",
        "TB_1111-001",
        "FL_1111-001",
        "NG_1130",
        "PX_1130-001",
        "RG_1100",
    ]
    for codigo in docs_sem_assinatura:
        doc = acervo.buscar(codigo)
        assert doc is not None
        gov = extrair_governanca(doc, acervo=acervo)
        assert gov.assinada_em.valor is None, f"{codigo} não deveria ter assinada_em"
        assert gov.assinada_em.fonte is None, f"{codigo} não deveria ter fonte em assinada_em"


def test_documento_com_assinada_em_recebe_valor_e_fonte():
    """Notas técnicas NT_2026-021 e NT_2026-018 têm 'Assinada em' no cabeçalho."""
    acervo = get_acervo()

    doc_21 = acervo.buscar("NT_2026-021")
    assert doc_21 is not None
    gov_21 = extrair_governanca(doc_21, acervo=acervo)
    assert gov_21.assinada_em.valor == "14/10/2026"
    assert gov_21.assinada_em.fonte is not None
    assert gov_21.assinada_em.fonte.campo == "Assinada em"
    assert gov_21.assinada_em.fonte.trecho == "Assinada em: 14/10/2026"
    assert gov_21.aprovado_em.valor is None

    doc_18 = acervo.buscar("NT_2026-018")
    assert doc_18 is not None
    gov_18 = extrair_governanca(doc_18, acervo=acervo)
    assert gov_18.assinada_em.valor == "05/11/2026"
    assert gov_18.assinada_em.fonte is not None
    assert gov_18.assinada_em.fonte.campo == "Assinada em"
    assert gov_18.assinada_em.fonte.trecho == "Assinada em: 05/11/2026"
    assert gov_18.aprovado_em.valor is None


def test_documento_com_aprovado_em_recebe_valor_e_fonte():
    """Documentos com 'Aprovado em' recebem valor e fonte corretos."""
    acervo = get_acervo()
    doc_fl = acervo.buscar("FL_1111-001")
    assert doc_fl is not None
    gov_fl = extrair_governanca(doc_fl, acervo=acervo)
    assert gov_fl.aprovado_em.valor == "10/08/2026"
    assert gov_fl.aprovado_em.fonte is not None
    assert gov_fl.aprovado_em.fonte.campo == "Aprovado em"
    assert gov_fl.aprovado_em.fonte.trecho == "Aprovado em: 10/08/2026"
    assert gov_fl.assinada_em.valor is None


def test_dias_restantes_com_data_referencia_fixa(monkeypatch):
    """dias_restantes calculado corretamente com DATA_REFERENCIA fixa."""
    # Teste com DATA_REFERENCIA via env
    monkeypatch.setenv("DATA_REFERENCIA", "2026-11-12")
    vig = extrair_vigencia("30/11/2026 a 29/04/2027")
    assert vig.dias_restantes == 168

    # Teste com DATA_REFERENCIA explícita: 7 dias antes do fim
    vig_7d = extrair_vigencia("30/11/2026 a 29/04/2027", data_referencia="2027-04-22")
    assert vig_7d.dias_restantes == 7

    # Teste com DATA_REFERENCIA após o fim (vencido)
    vig_venc = extrair_vigencia("30/11/2026 a 29/04/2027", data_referencia="2027-04-30")
    assert vig_venc.dias_restantes == -1

    # Documento com vigência de data única (sem termo final) -> dias_restantes é None
    vig_unica = extrair_vigencia("10/08/2026", data_referencia="2026-11-12")
    assert vig_unica.inicio == "2026-08-10"
    assert vig_unica.fim is None
    assert vig_unica.dias_restantes is None


def test_cadeia_de_subordinacao_completa():
    """Valida a cadeia de subordinação até a norma raiz."""
    acervo = get_acervo()

    # FL -> PX -> NG
    cadeia_fl = obter_cadeia_subordinacao("FL_1111-001", "PX_1111-001", acervo=acervo)
    assert cadeia_fl == ["FL_1111-001", "PX_1111-001", "NG_111"]

    # PX -> NG
    cadeia_px = obter_cadeia_subordinacao("PX_1111-001", "NG_111", acervo=acervo)
    assert cadeia_px == ["PX_1111-001", "NG_111"]

    # CTR (sem subordinação)
    cadeia_ctr = obter_cadeia_subordinacao("CTR_2026-012", None, acervo=acervo)
    assert cadeia_ctr == ["CTR_2026-012"]


def test_parser_limpeza_cabecalho_quebrado_com_slashes():
    """Parser lida com cabeçalho quebrado e slashes como no CTR_2026-012."""
    header_raw = (
        "ACME Tecnologia e Serviços\n"
        "#interna\n"
        "Documento: Contrato\n"
        "Título: Contrato de Teste\n"
        "Sigla e Número: CTR_2026-999\n"
        "Versão: 1.0.0\n"
        "Elaborado por: Gerência de Compras e /\n"
        "Contratos (GCO)\n"
        "Aprovado por: Diretoria Administrativa e /\n"
        "Financeira (DIRAF)\n"
        "Fase: Vigente\n"
        "Vigência: 01/01/2027 a 01/07/2027\n"
    )
    data = parse_header(header_raw)
    assert data["elaborado_por"] == "Gerência de Compras e Contratos (GCO)"
    assert data["aprovado_por"] == "Diretoria Administrativa e Financeira (DIRAF)"
    assert data["classificacao"] == "interna"


def test_item_ficha_valida_min_length_fontes():
    """ItemFicha exige pelo menos uma fonte (min_length=1)."""
    fonte_valida = Fonte(
        codigo="CTR_2026-012",
        versao="1.0.0",
        secao="Cláusula Sétima",
        trecho="O aluguel mensal é de R$ 3.650,00",
    )

    item = ItemFicha(
        id="v-1",
        titulo="Aluguel mensal",
        valor="R$ 3.650,00",
        origem="literal",
        fontes=[fonte_valida],
    )
    assert item.id == "v-1"

    with pytest.raises(ValidationError):
        ItemFicha(
            id="v-invalido",
            titulo="Sem fonte",
            origem="literal",
            fontes=[],
        )


def test_item_ficha_valida_origem_literal():
    """ItemFicha só aceita 'literal', 'resumo' ou 'calculado'."""
    fonte_valida = Fonte(
        codigo="CTR_2026-012",
        versao="1.0.0",
        secao="Cláusula Sétima",
        trecho="trecho",
    )
    for origem_valida in ("literal", "resumo", "calculado"):
        it = ItemFicha(
            id="item-ok",
            titulo="Título",
            origem=origem_valida,  # type: ignore[arg-type]
            fontes=[fonte_valida],
        )
        assert it.origem == origem_valida

    with pytest.raises(ValidationError):
        ItemFicha(
            id="item-erro",
            titulo="Título",
            origem="inventado",  # type: ignore[arg-type]
            fontes=[fonte_valida],
        )


def test_bloco_estrutura_revisao_13_11():
    """Bloco contém relevância, sinal, secoes_mapa, itens e alerta opcional."""
    bloco = Bloco(
        id="b-custo",
        titulo="Quanto custa",
        destaque="R$ 18.250,00",
        apoio="R$ 3.650 por mês",
        relevancia=RelevanciaBloco(posicao=1, motivo="maior valor do contrato", pontuacao=0.78),
        sinal="valor",
        secoes_mapa=["Cláusula Sétima", "Apêndice B"],
        itens=["n-valor", "v-1"],
        alerta=None,
    )
    assert bloco.sinal == "valor"
    assert bloco.relevancia.posicao == 1
    assert bloco.alerta is None

    bloco_alerta = Bloco(
        id="b-falta",
        titulo="Falta no acervo",
        destaque="NG_012",
        relevancia=RelevanciaBloco(posicao=6, motivo="referência ausente", pontuacao=0.2),
        sinal="alerta",
        secoes_mapa=["Apêndice K"],
        itens=[],
        alerta=0,
    )
    assert bloco_alerta.sinal == "alerta"
    assert bloco_alerta.alerta == 0
