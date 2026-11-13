"""Testes para extração de candidatos e verificador de fontes da Ficha do Documento (C22 / F-03 e F-05).

Especificação: Issue #46, PRD-FICHA-DO-DOCUMENTO.md e REQUISITOS-FICHA-DO-DOCUMENTO-v1.md (RF47 a RF52, RNF20, RNF21).
"""

import time
import pytest
from typing import List

from app.acervo import get_acervo
from app.models import DocumentoDetalhe, Secao, Fonte, Camada, Tema
from app.ficha.modelos import ItemFicha, PontosFicha, Cobertura
from app.ficha.candidatos import (
    extrair_candidatos,
    extrair_pontos_candidatos,
    extrair_candidatos_por_categoria,
    dividir_em_sentencas,
)
from app.ficha.verificador import (
    verificar_item,
    verificar_candidatos,
    verificar_pontos,
    extrair_e_verificar,
)


@pytest.fixture(scope="session")
def acervo_repo():
    return get_acervo()


def test_ctr_2026_012_extracao_e_verificacao_aceite(acervo_repo):
    """Critério de aceite para CTR_2026-012:
    - R$ 18.250,00 (Cláusula Sétima)
    - R$ 3.650,00
    - 25/11/2026 (Apêndice C)
    - 30/03/2027
    - 29/04/2027
    - Multa R$ 912,50 (calculado, 5% × 18.250,00)
    - Responsáveis GOC, GFI e GCO
    Todos com fonte verificada e zero descartes.
    """
    doc = acervo_repo.buscar("CTR_2026-012", "1.0.0")
    assert doc is not None, "CTR_2026-012 v1.0.0 não encontrado no acervo"

    pontos, cob = extrair_e_verificar(doc)
    assert cob.itens_descartados == 0
    assert cob.itens_verificados > 0
    assert cob.secoes_total == len(doc.secoes)
    assert cob.secoes_lidas == len(doc.secoes)

    # 1. R$ 18.250,00 (Cláusula Sétima)
    achou_18250_setima = any(
        it.valor == "R$ 18.250,00" and any(f.secao == "Cláusula Sétima" for f in it.fontes)
        for it in pontos.valores
    )
    assert achou_18250_setima, "Não encontrou R$ 18.250,00 na Cláusula Sétima"

    # 2. R$ 3.650,00
    achou_3650 = any(it.valor == "R$ 3.650,00" for it in pontos.valores)
    assert achou_3650, "Não encontrou R$ 3.650,00"

    # 3. 25/11/2026 (Apêndice C)
    achou_2511_c = any(
        it.valor == "25/11/2026" and any(f.secao == "Apêndice C" for f in it.fontes)
        for it in pontos.prazos
    )
    assert achou_2511_c, "Não encontrou 25/11/2026 no Apêndice C"

    # 4. 30/03/2027
    achou_3003 = any(it.valor == "30/03/2027" for it in pontos.prazos)
    assert achou_3003, "Não encontrou 30/03/2027"

    # 5. 29/04/2027
    achou_2904 = any(it.valor == "29/04/2027" for it in pontos.prazos)
    assert achou_2904, "Não encontrou 29/04/2027"

    # 6. Multa R$ 912,50 (calculado, 5% × 18.250,00)
    achou_multa = any(
        it.valor == "R$ 912,50"
        and it.origem == "calculado"
        and "5% × 18.250,00" in (it.calculo or "")
        and any(f.secao == "Apêndice B" for f in it.fontes)
        for it in pontos.valores
    )
    assert achou_multa, "Não encontrou multa R$ 912,50 calculada com fonte no Apêndice B"

    # 7. Responsáveis GOC, GFI e GCO
    resp_siglas = {it.valor for it in pontos.responsaveis if it.valor}
    resp_titulos = " ".join(it.titulo for it in pontos.responsaveis)

    assert "GOC" in resp_siglas or "GOC" in resp_titulos, "Responsável GOC não encontrado"
    assert "GFI" in resp_siglas or "GFI" in resp_titulos, "Responsável GFI não encontrado"
    assert "GCO" in resp_siglas or "GCO" in resp_titulos, "Responsável GCO não encontrado"


def test_ng_111_extracao_e_verificacao_aceite(acervo_repo):
    """Critério de aceite para NG_111:
    - O prazo de 45 dias aparece com fonte (seção 4.3.1).
    - O ressarcimento de R$ 2.500,00 aparece com fonte (seção 4.9.3).
    """
    doc = acervo_repo.buscar("NG_111", "3.0.0")
    assert doc is not None, "NG_111 v3.0.0 não encontrado no acervo"

    pontos, cob = extrair_e_verificar(doc)
    assert cob.itens_descartados == 0
    assert cob.itens_verificados > 0

    # Prazo de 45 dias com fonte
    achou_45dias = any(
        "45" in (it.valor or "") and any(f.secao == "4.3.1" for f in it.fontes)
        for it in pontos.prazos
    )
    assert achou_45dias, "Prazo de 45 dias não encontrado na seção 4.3.1 de NG_111"

    # Ressarcimento de R$ 2.500,00 com fonte
    achou_2500 = any(
        "2.500" in (it.valor or "") and any(f.secao == "4.9.3" for f in it.fontes)
        for it in pontos.valores
    )
    assert achou_2500, "Ressarcimento de R$ 2.500,00 não encontrado na seção 4.9.3 de NG_111"


def test_zero_itens_sem_fonte_verificada_em_todo_acervo(acervo_repo):
    """Garante RNF20: zero itens sem fonte verificada em todos os 13 documentos do acervo."""
    documentos = acervo_repo.documentos
    assert len(documentos) == 13, f"Esperado 13 documentos no acervo, encontrados {len(documentos)}"

    total_verificados = 0
    for doc in documentos:
        pontos, cob = extrair_e_verificar(doc)
        assert cob.itens_descartados == 0, (
            f"Documento {doc.codigo} v{doc.versao} teve descartes inesperados: {cob.motivos_descarte}"
        )
        total_verificados += cob.itens_verificados

        # Conferir que cada item verificado possui fonte válida no documento
        secoes_ids = {s.id for s in doc.secoes}
        for cat in ["obrigacoes", "prazos", "valores", "riscos", "responsaveis", "condicoes"]:
            itens: List[ItemFicha] = getattr(pontos, cat)
            for item in itens:
                assert len(item.fontes) >= 1, f"Item {item.id} sem fonte"
                for fonte in item.fontes:
                    assert fonte.secao in secoes_ids, (
                        f"Item {item.id} referencia seção inexistente {fonte.secao}"
                    )
                    assert fonte.codigo == doc.codigo

    assert total_verificados >= 500, f"Total de itens verificados ({total_verificados}) abaixo do esperado"


def test_verificador_injecao_candidato_inexistente(acervo_repo):
    """Testa que candidatos inválidos (trecho inexistente, seção inexistente, cálculo inválido)
    são descartados, contados em cobertura.itens_descartados e que os motivos não expõem o texto do documento.
    """
    doc = acervo_repo.buscar("CTR_2026-012", "1.0.0")
    assert doc is not None

    # Candidato 1: trecho inexistente
    item_trecho_falso = ItemFicha(
        id="inj-1",
        titulo="Item com trecho falso",
        valor="R$ 999.999,00",
        origem="literal",
        fontes=[
            Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao="Cláusula Sétima",
                trecho="Texto falso que certamente não existe nesta seção",
                camada=doc.camada,
            )
        ],
    )

    # Candidato 2: seção inexistente
    item_secao_falsa = ItemFicha(
        id="inj-2",
        titulo="Item com seção falsa",
        valor="R$ 10,00",
        origem="literal",
        fontes=[
            Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao="Cláusula Fantasma",
                trecho="Qualquer texto",
                camada=doc.camada,
            )
        ],
    )

    # Candidato 3: cálculo com operando que não consta nas fontes
    item_calc_falso = ItemFicha(
        id="inj-3",
        titulo="Multa calculada inválida",
        valor="R$ 999,00",
        origem="calculado",
        calculo="99% × 888.888,00 = 999,00",
        fontes=[
            Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao="Apêndice B",
                trecho="Multa por inexecução | 5% × 18.250,00 | 912,50",
                camada=doc.camada,
            )
        ],
    )

    # Candidato 4: válido para garantir que não descarta tudo
    item_valido = ItemFicha(
        id="val-ok",
        titulo="Aluguel mensal legítimo",
        valor="R$ 3.650,00",
        origem="literal",
        fontes=[
            Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao="Cláusula Sétima",
                trecho="O aluguel mensal é de R$ 3.650,00, perfazendo o valor global de R$ 18.250,00 para os 5 meses de vigência.",
                camada=doc.camada,
            )
        ],
    )

    candidatos_dict = {
        "valores": [item_trecho_falso, item_calc_falso, item_valido],
        "obrigacoes": [item_secao_falsa],
    }

    resultado, cob = verificar_candidatos(candidatos_dict, doc)

    # Verificações de cobertura
    assert cob.itens_descartados == 3
    assert cob.itens_verificados == 1
    assert len(resultado["valores"]) == 1
    assert resultado["valores"][0].id == "val-ok"
    assert len(resultado["obrigacoes"]) == 0

    # Motivos de descarte sem vazar texto do documento
    assert len(cob.motivos_descarte) == 3
    for motivo in cob.motivos_descarte:
        assert "Texto falso" not in motivo
        assert "certamente não existe" not in motivo
        assert "Qualquer texto" not in motivo


def test_performance_documento_100_paginas():
    """Garante tempo de processamento inferior a 2 s para documento grande (~100 páginas)."""
    secoes = []
    for i in range(1, 101):
        texto = (
            f"Seção {i}. A ACME Tecnologia e Serviços estabelece que a LOCATÁRIA deve efetuar "
            f"o pagamento no valor de R$ {i * 1000},00 até o dia {min(i, 28)} de cada mês. "
            f"A GFI paga após o atesto técnico realizado pela GOC no prazo de {i} dias úteis. "
            f"A rescisão sem aviso prévio incorre em multa de 5% do valor global de R$ 50.000,00. "
            f"A vistoria deve ocorrer em 25/11/2026 com termo de entrega assinado. "
            f"Caso haja descumprimento, a inexecução sujeita a parte a penalidade.\n\n"
        ) * 8  # ~400 palavras por seção * 100 seções = ~40.000 palavras (~100 páginas)
        secoes.append(Secao(id=f"Secao-{i}", titulo=f"Cláusula {i}", texto=texto))

    doc_grande = DocumentoDetalhe(
        codigo="CTR_TESTE_100P",
        titulo="Contrato Sintético de 100 Páginas para Teste de Performance",
        tipo="CTR",
        tipo_nome="Contrato",
        versao="1.0.0",
        fase="Vigente",
        assunto="locacao",
        camada=Camada(sigla="CTR", tipo_nome="Contrato", grupo="Instrumento"),
        tema=Tema(assunto="locacao", serie=None, serie_nome=None, confirmado_por="regra"),
        secoes=secoes,
    )

    t0 = time.perf_counter()
    pontos, cob = extrair_e_verificar(doc_grande)
    duracao = time.perf_counter() - t0

    assert duracao < 2.0, f"Tempo de extração e verificação excedeu 2 s: {duracao:.3f} s"
    assert cob.itens_verificados > 0
    assert cob.itens_descartados == 0
