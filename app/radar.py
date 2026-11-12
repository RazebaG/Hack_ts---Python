"""Serviço de Radar de Contradições do Arquivo Central de Normas (ACME).

Implementa o endpoint GET /api/radar (Issue #7, Adendo v0.2):
- versao_substituida (status: divergente, 2 fontes):
  - NG_111 2.0.0 §2.3 × 3.0.0 §4.3.1 (30 → 45 dias corridos)
  - FM_1111-001 1.0.0 §1 × 2.0.0 §Bloco A (30 dias / envio ao gerente → Portal Raiz)
- referencia_ausente (status: atencao, ≥ 1 fonte):
  - NG_012 citada pela NT_2026-018 §10 (alçadas) e não presente no acervo
- Filtro opcional por perspectiva (?perspectiva=)
- Toda fonte carrega camada (C15) e secao existente no acervo (Adendo v0.1 A)
- Todo item carrega tema derivado do catálogo (C17)
"""

import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import HTTPException

from app.models import (
    Fonte,
    RadarItem,
    RadarResumo,
    RadarResponse,
)
from app.acervo import AcervoRepository, get_acervo
from app.taxonomia import derivar_camada, derivar_tema

PERSPECTIVAS_VALIDAS = {"juridico", "financeiro", "pessoas", "gestao"}

# Perspectivas afetadas por assunto, para itens derivados de documentos publicados
PERSPECTIVAS_POR_ASSUNTO = {
    "ferias": ["pessoas"],
    "locacao": ["juridico", "financeiro"],
    "inovacao": ["gestao"],
}
CODIGO_RE = re.compile(r"\b(?:NG|PX|PP|GU|FM|TB|FL|RG|CT|DV|CTR|NT)_[0-9]+(?:-[0-9]+)?\b")
LIMITE_TRECHO = 220


class RadarService:
    def __init__(self, acervo: Optional[AcervoRepository] = None):
        self.acervo = acervo or get_acervo()

    def _obter_itens_p0(self) -> List[RadarItem]:
        """Retorna os itens determinísticos de contradição e referências ausentes do P0."""
        # 1. Item: NG_111 antecedência de férias 30 -> 45 dias
        fonte_ng111_v3 = Fonte(
            codigo="NG_111",
            versao="3.0.0",
            secao="4.3.1",
            trecho="A solicitação é formal e feita no Portal Raiz (FM_1111-001) com antecedência mínima de 45 dias corridos do início de gozo.",
            camada=derivar_camada("NG_111"),
        )
        fonte_ng111_v2 = Fonte(
            codigo="NG_111",
            versao="2.0.0",
            secao="2.3",
            trecho="A solicitação deve ser feita com antecedência mínima de 30 dias.",
            camada=derivar_camada("NG_111"),
        )
        item_ng111 = RadarItem(
            id="versao-NG_111-antecedencia",
            tipo="versao_substituida",
            status="divergente",
            severidade="alta",
            titulo="Antecedência de férias: v2 dizia 30 dias, v3 exige 45",
            explicacao="A versão vigente prevalece; a 2.0.0 foi substituída.",
            perspectivas=["pessoas"],
            codigo_ausente=None,
            fontes=[fonte_ng111_v3, fonte_ng111_v2],
            tema=derivar_tema("NG_111", assunto="ferias"),
        )

        # 2. Item: FM_1111-001 v1 x v2 (30 dias / envio físico ao gerente -> formulário eletrônico no Portal Raiz)
        fonte_fm_v2 = Fonte(
            codigo="FM_1111-001",
            versao="2.0.0",
            secao="Bloco A",
            trecho="Nome do empregado: [preenchido pelo Portal Raiz]",
            camada=derivar_camada("FM_1111-001", tipo_nome="Formulário", vinculado_a="NG_111"),
        )
        fonte_fm_v1 = Fonte(
            codigo="FM_1111-001",
            versao="1.0.0",
            secao="1",
            trecho="Preencher e enviar ao gerente da unidade com antecedência mínima de 30 dias, conforme a NG_111.",
            camada=derivar_camada("FM_1111-001", tipo_nome="Formulário", vinculado_a="NG_111"),
        )
        item_fm1111 = RadarItem(
            id="versao-FM_1111-001-tramitacao",
            tipo="versao_substituida",
            status="divergente",
            severidade="alta",
            titulo="Formulário de férias: v1 previa 30 dias e envio ao gerente; v2 tramita no Portal Raiz com 45 dias",
            explicacao="A versão vigente 2.0.0 prevalece; a versão 1.0.0 física com envio ao gerente foi substituída pelo formulário eletrônico no Portal Raiz.",
            perspectivas=["pessoas"],
            codigo_ausente=None,
            fontes=[fonte_fm_v2, fonte_fm_v1],
            tema=derivar_tema("FM_1111-001", assunto="ferias"),
        )

        # 3. Item: NG_012 citada pela NT_2026-018 e ausente no acervo
        fonte_nt_018 = Fonte(
            codigo="NT_2026-018",
            versao="1.0.0",
            secao="10",
            trecho="O valor global de R$ 18.250,00 supera a alçada de gerente (R$ 18.000,00) e fica na alçada de diretor (até R$ 120.000,00), conforme a NG_012; por isso a DIRAF aprova.",
            camada=derivar_camada("NT_2026-018", tipo_nome="Nota Técnica"),
        )
        item_ng012 = RadarItem(
            id="referencia-NG_012-alcadas",
            tipo="referencia_ausente",
            status="atencao",
            severidade="media",
            titulo="Referência a documento ausente no acervo: NG_012 (Alçadas Decisórias)",
            explicacao="A NT_2026-018 fundamenta a alçada de aprovação da DIRAF na NG_012, mas este documento não consta no acervo central.",
            perspectivas=["juridico", "financeiro"],
            codigo_ausente="NG_012",
            fontes=[fonte_nt_018],
            tema=derivar_tema("NT_2026-018", assunto="locacao"),
        )

        itens = [item_ng111, item_fm1111]
        # A referência só é "ausente" enquanto o documento não estiver no acervo
        # (ex.: publicado depois por envio em lote, issue #10).
        if self.acervo.buscar("NG_012") is None:
            itens.append(item_ng012)
        return itens

    def _itens_publicados(self) -> List[RadarItem]:
        """Referências a documentos ausentes citadas por documentos publicados (issue #10)."""
        itens: List[RadarItem] = []
        for doc in self.acervo.documentos:
            if doc.origem == "acervo" or doc.substituido:
                continue
            citados = []
            for campo in (doc.vinculado_a, doc.referencia):
                for cod in CODIGO_RE.findall(campo or ""):
                    if cod != doc.codigo and cod not in citados:
                        citados.append(cod)
            for cod in citados:
                if self.acervo.buscar(cod) is not None:
                    continue
                secao = next((s for s in doc.secoes if cod in s.texto), doc.secoes[0] if doc.secoes else None)
                if secao is None:
                    continue
                trecho = " ".join(secao.texto.split())
                if len(trecho) > LIMITE_TRECHO:
                    trecho = trecho[: LIMITE_TRECHO - 3].rstrip() + "..."
                itens.append(
                    RadarItem(
                        id=f"referencia-{cod}-{doc.codigo}",
                        tipo="referencia_ausente",
                        status="atencao",
                        severidade="media",
                        titulo=f"Referência a documento ausente no acervo: {cod}",
                        explicacao=f"O {doc.codigo} v{doc.versao} (publicado por envio) cita o {cod}, que não consta no acervo central.",
                        perspectivas=PERSPECTIVAS_POR_ASSUNTO.get(doc.assunto, ["gestao"]),
                        codigo_ausente=cod,
                        fontes=[
                            Fonte(
                                codigo=doc.codigo,
                                versao=doc.versao,
                                secao=secao.id,
                                trecho=trecho or secao.titulo,
                                camada=doc.camada,
                            )
                        ],
                        tema=doc.tema,
                    )
                )
        return itens

    def obter_radar(self, perspectiva: Optional[str] = None) -> RadarResponse:
        """Gera a resposta consolidada do radar, aplicando filtro de perspectiva quando fornecido."""
        if perspectiva is not None:
            p_clean = perspectiva.strip().lower()
            if p_clean not in PERSPECTIVAS_VALIDAS:
                raise HTTPException(
                    status_code=404,
                    detail=f"Perspectiva '{perspectiva}' não encontrada. Opções válidas: {sorted(PERSPECTIVAS_VALIDAS)}",
                )
        else:
            p_clean = None

        todos_itens = self._obter_itens_p0() + self._itens_publicados()

        if p_clean:
            itens_filtrados = [
                item for item in todos_itens if p_clean in item.perspectivas
            ]
        else:
            itens_filtrados = todos_itens

        divergente_count = sum(1 for it in itens_filtrados if it.status == "divergente")
        atencao_count = sum(1 for it in itens_filtrados if it.status == "atencao")
        resumo = RadarResumo(divergente=divergente_count, atencao=atencao_count)

        tz_br = timezone(timedelta(hours=-3))
        timestamp = datetime.now(tz_br).isoformat()

        return RadarResponse(
            gerado_em=timestamp,
            resumo=resumo,
            itens=itens_filtrados,
        )
