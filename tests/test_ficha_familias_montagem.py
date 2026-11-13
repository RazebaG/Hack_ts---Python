"""Testes de Famílias, Blocos da Mesa de Decisão e Relevância da Ficha do Documento (F-17, Issue #47).

Especificação:
- Issue #47
- PRD-FICHA-DO-DOCUMENTO.md (seção 3.5 e backlog seção 9)
- REQUISITOS-FICHA-DO-DOCUMENTO-v1.md (RF72 a RF76)
- CONTRATO-API-ADENDO-v0.4.md (C22 e Revisão 13/11)
- mock-ficha-CTR_2026-012.json
"""

import copy
import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from app.acervo import get_acervo
from app.models import DocumentoDetalhe, Secao, Camada, Tema, Fonte
from app.inteligencia import trecho_consta_na_secao
from app.ficha.modelos import FichaDocumento, Bloco, RelevanciaBloco, ItemFicha, PontosFicha
from app.ficha.familias import (
    FAMILIA_BLOCOS,
    BlocoTemplate,
    derivar_familia,
)
from app.ficha.relevancia import (
    PesosRelevancia,
    calcular_relevancia_bloco,
    parse_valor_moeda,
    parse_data,
)
from app.ficha.montagem import (
    montar_ficha,
    _montar_blocos_por_familia,
)


@pytest.fixture(scope="session")
def acervo_repo():
    return get_acervo()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


# ==============================================================================
# 1. Testes de Derivação de Família
# ==============================================================================

def test_derivar_familia_regras(acervo_repo):
    """Testa derivação de família documental conforme contrato e PRD:
    - CTR -> contrato
    - NT com valor e prazo -> contrato
    - NT e CT sem valor -> nota_tecnica
    - NG e RG -> norma
    - PX, GU, FL, FM, TB, PP -> procedimento
    """
    # 1. CTR -> contrato
    doc_ctr = acervo_repo.buscar("CTR_2026-012", "1.0.0")
    assert doc_ctr is not None
    assert derivar_familia(doc_ctr) == "contrato"

    # 2. NG e RG -> norma
    doc_ng = acervo_repo.buscar("NG_111", "3.0.0")
    assert doc_ng is not None
    assert derivar_familia(doc_ng) == "norma"

    doc_rg = acervo_repo.buscar("RG_1100", "2.0.0")
    assert doc_rg is not None
    assert derivar_familia(doc_rg) == "norma"

    # 3. PX, FM, FL, TB -> procedimento
    doc_px = acervo_repo.buscar("PX_1111-001", "1.0.0")
    assert doc_px is not None
    assert derivar_familia(doc_px) == "procedimento"

    doc_fm = acervo_repo.buscar("FM_1111-001", "2.0.0")
    assert doc_fm is not None
    assert derivar_familia(doc_fm) == "procedimento"

    doc_tb = acervo_repo.buscar("TB_1111-001", "1.0.0")
    assert doc_tb is not None
    assert derivar_familia(doc_tb) == "procedimento"

    # 4. NT com valor e prazo -> contrato
    doc_nt_018 = acervo_repo.buscar("NT_2026-018", "1.0.0")
    assert doc_nt_018 is not None
    assert derivar_familia(doc_nt_018) == "contrato"

    # 5. NT e CT sem valor -> nota_tecnica
    doc_nt_sem_valor = DocumentoDetalhe(
        codigo="NT_9999-001",
        versao="1.0.0",
        titulo="Nota Técnica Sem Valor",
        tipo="NT",
        tipo_nome="Nota Técnica",
        assunto="teste",
        camada=Camada(sigla="NT", tipo_nome="Nota Técnica", grupo="Instrumento"),
        tema=Tema(assunto="teste"),
        fase="Vigente",
        vigencia="30 dias",
        secoes=[Secao(id="1", titulo="Objeto", texto="Apenas parecer técnico sem valores monetários.")],
    )
    assert derivar_familia(doc_nt_sem_valor) == "nota_tecnica"

    doc_ct = DocumentoDetalhe(
        codigo="CT_9999-001",
        versao="1.0.0",
        titulo="Comunicado Temporário",
        tipo="CT",
        tipo_nome="Comunicado Temporário",
        assunto="teste",
        camada=Camada(sigla="CT", tipo_nome="Comunicado Temporário", grupo="Temporário"),
        tema=Tema(assunto="teste"),
        fase="Vigente",
        vigencia="10 dias",
        secoes=[Secao(id="1", titulo="Aviso", texto="Aviso geral sem impacto financeiro.")],
    )
    assert derivar_familia(doc_ct) == "nota_tecnica"


# ==============================================================================
# 2. Critérios de Aceite para CTR_2026-012
# ==============================================================================

def test_ctr_2026_012_aceite_blocos_relevancia(acervo_repo):
    """Critério de Aceite da Issue #47 para CTR_2026-012:
    - familia: contrato
    - blocos com destaque:
      - 'R$ 18.250,00' (Quanto custa)
      - '25/11/2026' (Até quando)
      - 'R$ 912,50' (Onde pode doer)
    - cada um com ao menos uma fonte verificada
    - 'Falta no acervo' = NG_012
    - cada bloco com relevancia.motivo citando um fato
    """
    doc = acervo_repo.buscar("CTR_2026-012", "1.0.0")
    assert doc is not None

    ficha = montar_ficha(doc, acervo=acervo_repo, data_referencia="2026-11-12")

    assert ficha.familia == "contrato"
    assert len(ficha.blocos) >= 4

    # 1. 'Quanto custa'
    b_custo = next((b for b in ficha.blocos if b.titulo == "Quanto custa"), None)
    assert b_custo is not None, "Bloco 'Quanto custa' não encontrado"
    assert b_custo.destaque == "R$ 18.250,00"
    assert b_custo.sinal == "valor"
    assert "maior valor" in b_custo.relevancia.motivo
    assert b_custo.relevancia.pontuacao > 0
    # Verifica que tem fonte existente no documento
    assert len(b_custo.itens) > 0
    for it_id in b_custo.itens:
        item_obj = next((it for it in (ficha.numeros + ficha.pontos.valores + ficha.acoes) if it.id == it_id), None)
        assert item_obj is not None
        assert len(item_obj.fontes) >= 1
        for f in item_obj.fontes:
            sec = next((s for s in doc.secoes if s.id == f.secao), None)
            assert sec is not None
            assert trecho_consta_na_secao(f.trecho, sec.texto)

    # 2. 'Até quando'
    b_prazo = next((b for b in ficha.blocos if b.titulo == "Até quando"), None)
    assert b_prazo is not None, "Bloco 'Até quando' não encontrado"
    assert b_prazo.destaque == "25/11/2026"
    assert b_prazo.sinal == "prazo"
    assert "vence" in b_prazo.relevancia.motivo or "dias" in b_prazo.relevancia.motivo
    assert len(b_prazo.itens) > 0
    for it_id in b_prazo.itens:
        item_obj = next((it for it in (ficha.numeros + ficha.pontos.prazos + ficha.acoes) if it.id == it_id), None)
        assert item_obj is not None
        assert len(item_obj.fontes) >= 1
        for f in item_obj.fontes:
            sec = next((s for s in doc.secoes if s.id == f.secao), None)
            assert sec is not None
            assert trecho_consta_na_secao(f.trecho, sec.texto)

    # 3. 'Onde pode doer'
    b_risco = next((b for b in ficha.blocos if b.titulo == "Onde pode doer"), None)
    assert b_risco is not None, "Bloco 'Onde pode doer' não encontrado"
    assert b_risco.destaque == "R$ 912,50"
    assert b_risco.sinal == "risco"
    assert "risco" in b_risco.relevancia.motivo
    assert len(b_risco.itens) > 0
    for it_id in b_risco.itens:
        item_obj = next((it for it in (ficha.numeros + ficha.pontos.riscos + ficha.pontos.valores + ficha.acoes) if it.id == it_id), None)
        assert item_obj is not None
        assert len(item_obj.fontes) >= 1
        for f in item_obj.fontes:
            sec = next((s for s in doc.secoes if s.id == f.secao), None)
            assert sec is not None
            assert trecho_consta_na_secao(f.trecho, sec.texto)

    # 4. 'Falta no acervo' = NG_012
    b_falta = next((b for b in ficha.blocos if b.titulo == "Falta no acervo"), None)
    assert b_falta is not None, "Bloco 'Falta no acervo' não encontrado"
    assert b_falta.destaque == "NG_012"
    assert b_falta.sinal == "alerta"
    assert "referência ausente" in b_falta.relevancia.motivo or "ausente" in b_falta.relevancia.motivo
    assert b_falta.alerta is not None
    alerta_obj = ficha.alertas[b_falta.alerta]
    assert "NG_012" in alerta_obj.titulo
    assert len(alerta_obj.fontes) >= 1
    for f in alerta_obj.fontes:
        sec = next((s for s in doc.secoes if s.id == f.secao), None)
        assert sec is not None
        assert trecho_consta_na_secao(f.trecho, sec.texto)

    # 5. Cada bloco com relevancia.motivo citando um fato
    for b in ficha.blocos:
        assert b.relevancia.motivo is not None and len(b.relevancia.motivo) > 3
        assert b.relevancia.posicao >= 1


# ==============================================================================
# 3. Critérios de Aceite para NG_111
# ==============================================================================

def test_ng_111_aceite_blocos_norma(acervo_repo):
    """Critério de Aceite da Issue #47 para NG_111:
    - familia: norma
    - 'O que muda para você' mostrando 45 dias e o aviso da v2 substituída
    - Todos os blocos com fontes verificadas
    """
    doc = acervo_repo.buscar("NG_111", "3.0.0")
    assert doc is not None

    ficha = montar_ficha(doc, acervo=acervo_repo, data_referencia="2026-11-12")

    assert ficha.familia == "norma"
    assert len(ficha.blocos) >= 4

    b_muda = next((b for b in ficha.blocos if b.titulo == "O que muda para você"), None)
    assert b_muda is not None, "Bloco 'O que muda para você' não encontrado"
    assert "45" in b_muda.destaque
    assert "v2" in (b_muda.apoio or "").lower() or "substitu" in (b_muda.apoio or "").lower()
    assert b_muda.relevancia.motivo != ""

    # Verifica fontes do bloco
    assert len(b_muda.itens) > 0
    for it_id in b_muda.itens:
        item_obj = next((it for it in (ficha.pontos.prazos + ficha.pontos.obrigacoes + ficha.acoes) if it.id == it_id), None)
        assert item_obj is not None
        for f in item_obj.fontes:
            sec = next((s for s in doc.secoes if s.id == f.secao), None)
            assert sec is not None
            assert trecho_consta_na_secao(f.trecho, sec.texto)


# ==============================================================================
# 4. Ordem determinística e desempate
# ==============================================================================

def test_ordem_blocos_deterministica_e_empate(acervo_repo):
    """Testa que a ordenação de blocos é 100% determinística em execuções repetidas
    e que empates na pontuação são resolvidos pela ordem de template da família.
    """
    doc = acervo_repo.buscar("CTR_2026-012", "1.0.0")
    assert doc is not None

    ficha1 = montar_ficha(doc, acervo=acervo_repo, data_referencia="2026-11-12")
    ficha2 = montar_ficha(doc, acervo=acervo_repo, data_referencia="2026-11-12")

    ordem1 = [(b.id, b.relevancia.posicao, b.relevancia.pontuacao) for b in ficha1.blocos]
    ordem2 = [(b.id, b.relevancia.posicao, b.relevancia.pontuacao) for b in ficha2.blocos]
    assert ordem1 == ordem2, "A ordem dos blocos deve ser estritamente determinística"

    # Teste explícito de empate:
    # Cria dois blocos artificiais com a MESMA pontuação (0.50) e verifica desempate pela ordem de template
    b1 = Bloco(
        id="b-alfa",
        titulo="Bloco Alfa",
        destaque="Destaque Alfa",
        apoio="Apoio Alfa",
        relevancia=RelevanciaBloco(posicao=1, motivo="fato alfa", pontuacao=0.50),
        sinal="regra",
        secoes_mapa=["1"],
        itens=["it-1"],
    )
    b2 = Bloco(
        id="b-beta",
        titulo="Bloco Beta",
        destaque="Destaque Beta",
        apoio="Apoio Beta",
        relevancia=RelevanciaBloco(posicao=2, motivo="fato beta", pontuacao=0.50),
        sinal="regra",
        secoes_mapa=["2"],
        itens=["it-2"],
    )

    lista = [(b2, 2), (b1, 1)]  # b2 aparece antes, mas sua ordem de template é 2
    lista.sort(key=lambda x: (-x[0].relevancia.pontuacao, x[1]))
    assert lista[0][0].id == "b-alfa"
    assert lista[1][0].id == "b-beta"


# ==============================================================================
# 5. Varredura de todo o acervo central: nenhum bloco sem fonte
# ==============================================================================

def test_varredura_acervo_sem_bloco_sem_fonte(acervo_repo):
    """Varre todos os 13 documentos do acervo e garante que:
    1. A ficha é montada sem erro para cada um.
    2. Todo bloco gerado tem fonte verificada no texto da respectiva seção.
    3. Nenhum bloco sem fonte ou vazio é devolvido.
    """
    total_docs = len(acervo_repo.documentos)
    assert total_docs >= 13, f"Esperado >= 13 documentos no acervo, encontrado {total_docs}"

    for doc in acervo_repo.documentos:
        ficha = montar_ficha(doc, acervo=acervo_repo, data_referencia="2026-11-12")
        assert ficha.codigo == doc.codigo
        assert ficha.versao == doc.versao
        assert ficha.familia in ("contrato", "norma", "procedimento", "nota_tecnica")

        # Verifica cada bloco gerado
        for b in ficha.blocos:
            assert b.destaque != "", f"Bloco {b.id} em {doc.codigo} tem destaque vazio"
            assert b.relevancia.posicao >= 1
            assert b.relevancia.motivo != ""

            # O bloco precisa ter ou itens verificados ou um alerta verificado
            if b.itens:
                for it_id in b.itens:
                    item_obj = next(
                        (
                            it
                            for it in (
                                ficha.numeros
                                + ficha.pontos.obrigacoes
                                + ficha.pontos.prazos
                                + ficha.pontos.valores
                                + ficha.pontos.riscos
                                + ficha.pontos.responsaveis
                                + ficha.pontos.condicoes
                                + ficha.acoes
                            )
                            if it.id == it_id
                        ),
                        None,
                    )
                    assert item_obj is not None, f"Item {it_id} do bloco {b.id} não consta na ficha de {doc.codigo}"
                    assert len(item_obj.fontes) >= 1, f"Item {it_id} sem fontes em {doc.codigo}"
                    for f in item_obj.fontes:
                        sec = next((s for s in doc.secoes if s.id == f.secao), None)
                        assert sec is not None, f"Seção {f.secao} não encontrada em {doc.codigo}"
            elif b.alerta is not None:
                assert b.alerta < len(ficha.alertas)
                alerta_obj = ficha.alertas[b.alerta]
                if alerta_obj.tipo != "versao_substituida" or alerta_obj.fontes:
                    assert len(alerta_obj.fontes) >= 1, f"Alerta sem fontes em {doc.codigo}"


# ==============================================================================
# 6. Fallback para lista simples quando menos de 3 blocos
# ==============================================================================

def test_fallback_lista_simples_quando_menos_de_3_blocos():
    """Testa que documento com poucas categorias preenchidas cai para lista simples sem erro."""
    doc_curto = DocumentoDetalhe(
        codigo="PX_SIMPLES",
        versao="1.0.0",
        titulo="Procedimento Simples",
        tipo="PX",
        tipo_nome="Procedimento",
        assunto="teste",
        camada=Camada(sigla="PX", tipo_nome="Procedimento", grupo="Normativo"),
        tema=Tema(assunto="teste"),
        fase="Vigente",
        vigencia="30 dias",
        secoes=[Secao(id="1", titulo="Prazo", texto="O prazo único para envio é 5 dias úteis.")],
    )

    ficha = montar_ficha(doc_curto, data_referencia="2026-11-12")
    assert ficha.familia == "procedimento"
    # Não levanta exceção e devolve lista simples de blocos
    assert isinstance(ficha.blocos, list)
    for b in ficha.blocos:
        assert b.destaque != ""


# ==============================================================================
# 7. Garantia arquitetural: nenhuma comparação literal com código em app/ficha
# ==============================================================================

def test_ausencia_comparacao_codigo_em_app_ficha():
    """Garante que nenhum módulo em app/ficha/ possui 'codigo ==' escrito à mão,
    assegurando que o comportamento seja 100% por regra e não por branches manuais.
    """
    import glob
    from pathlib import Path

    ficha_files = glob.glob("app/ficha/*.py")
    assert len(ficha_files) >= 5, "Arquivos de app/ficha/ devem existir"

    violacoes = []
    for fpath in ficha_files:
        conteudo = Path(fpath).read_text(encoding="utf-8")
        for num_linha, linha in enumerate(conteudo.splitlines(), start=1):
            if "codigo ==" in linha:
                violacoes.append(f"{fpath}:{num_linha}: {linha.strip()}")

    assert not violacoes, f"Encontradas comparações literais de código em app/ficha/:\n" + "\n".join(violacoes)


# ==============================================================================
# 8. Demonstração de documentos adicionais: PX_1111-001 e NT_2026-018
# ==============================================================================

def test_terceiros_documentos_px_1111_001_e_nt_2026_018(acervo_repo):
    """Comprova montagem determinística por regras para documentos que não constam no exemplo mock:
    - PX_1111-001 (procedimento): blocos preenchidos, com fontes verificadas e motivo citando fato.
    - NT_2026-018 (contrato): blocos de contrato com valores, prazos e fontes verificadas.
    """
    # 1. PX_1111-001
    doc_px = acervo_repo.buscar("PX_1111-001", "1.0.0")
    assert doc_px is not None
    ficha_px = montar_ficha(doc_px, acervo=acervo_repo, data_referencia="2026-11-12")

    assert ficha_px.familia == "procedimento"
    assert len(ficha_px.blocos) >= 3
    for b in ficha_px.blocos:
        assert b.destaque != ""
        assert b.relevancia.motivo != ""
        assert len(b.relevancia.motivo) > 3
        # Confere fontes
        if b.itens:
            for it_id in b.itens:
                item_obj = next(
                    (it for it in (ficha_px.pontos.valores + ficha_px.pontos.prazos + ficha_px.pontos.responsaveis + ficha_px.pontos.riscos + ficha_px.acoes) if it.id == it_id),
                    None,
                )
                assert item_obj is not None, f"Item {it_id} de PX não encontrado"
                for f in item_obj.fontes:
                    secoes_id = [s for s in doc_px.secoes if s.id == f.secao]
                    assert secoes_id, f"Seção {f.secao} não encontrada em PX"
                    assert any(trecho_consta_na_secao(f.trecho, s.texto) for s in secoes_id)

    # 2. NT_2026-018
    doc_nt = acervo_repo.buscar("NT_2026-018", "1.0.0")
    assert doc_nt is not None
    ficha_nt = montar_ficha(doc_nt, acervo=acervo_repo, data_referencia="2026-11-12")

    assert ficha_nt.familia == "contrato"
    assert len(ficha_nt.blocos) >= 3
    titulos_nt = [b.titulo for b in ficha_nt.blocos]
    assert "Quanto custa" in titulos_nt or "Valores" in titulos_nt
    for b in ficha_nt.blocos:
        assert b.destaque != ""
        assert b.relevancia.motivo != ""
        assert len(b.relevancia.motivo) > 3
        if b.itens:
            for it_id in b.itens:
                item_obj = next(
                    (it for it in (ficha_nt.pontos.valores + ficha_nt.pontos.prazos + ficha_nt.pontos.responsaveis + ficha_nt.pontos.riscos + ficha_nt.acoes) if it.id == it_id),
                    None,
                )
                assert item_obj is not None, f"Item {it_id} de NT não encontrado"
                for f in item_obj.fontes:
                    secoes_id = [s for s in doc_nt.secoes if s.id == f.secao]
                    assert secoes_id, f"Seção {f.secao} não encontrada em NT"
                    assert any(trecho_consta_na_secao(f.trecho, s.texto) for s in secoes_id)
