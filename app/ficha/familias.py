"""Tabela de famílias e blocos da Ficha do Documento (RF72 a RF76, C22).

Implementa a taxonomia de famílias, mapeamento de blocos por família
e regras de preenchimento determinístico (sem IA).
"""

from typing import List, Dict, Optional, Literal
from dataclasses import dataclass
from app.models import DocumentoDetalhe
from app.ficha.modelos import FamiliaDocumento, ItemFicha
from app.ficha.candidatos import extrair_candidatos

SinalBloco = Literal["valor", "prazo", "responsavel", "risco", "regra", "alerta"]


@dataclass(frozen=True)
class BlocoTemplate:
    """Definição do template de um bloco por família documental."""

    id: str
    titulo: str
    sinal: SinalBloco
    ordem_padrao: int
    tipo_conteudo: str


# ==============================================================================
# Tabela FAMILIA_BLOCOS (PRD 3.5 e Revisão 13/11)
# ==============================================================================
# Contrato: Quanto custa · Até quando · Quem faz o quê · Onde pode doer · Regras que valem · Falta no acervo
# Norma: O que muda para você · Prazos que valem · Quem faz o quê · Limites e valores · Penalidades e exceções · Versão em vigor e o que mudou · Documentos ligados
# Procedimento e Nota Técnica: Prazos · Valores · Quem faz o quê · Riscos
FAMILIA_BLOCOS: Dict[FamiliaDocumento, List[BlocoTemplate]] = {
    "contrato": [
        BlocoTemplate(
            id="b-custo",
            titulo="Quanto custa",
            sinal="valor",
            ordem_padrao=1,
            tipo_conteudo="valor",
        ),
        BlocoTemplate(
            id="b-prazo",
            titulo="Até quando",
            sinal="prazo",
            ordem_padrao=2,
            tipo_conteudo="prazo",
        ),
        BlocoTemplate(
            id="b-quem",
            titulo="Quem faz o quê",
            sinal="responsavel",
            ordem_padrao=3,
            tipo_conteudo="responsavel",
        ),
        BlocoTemplate(
            id="b-risco",
            titulo="Onde pode doer",
            sinal="risco",
            ordem_padrao=4,
            tipo_conteudo="risco",
        ),
        BlocoTemplate(
            id="b-regras",
            titulo="Regras que valem",
            sinal="regra",
            ordem_padrao=5,
            tipo_conteudo="regra",
        ),
        BlocoTemplate(
            id="b-falta",
            titulo="Falta no acervo",
            sinal="alerta",
            ordem_padrao=6,
            tipo_conteudo="falta_acervo",
        ),
    ],
    "norma": [
        BlocoTemplate(
            id="b-muda",
            titulo="O que muda para você",
            sinal="regra",
            ordem_padrao=1,
            tipo_conteudo="o_que_muda",
        ),
        BlocoTemplate(
            id="b-prazos",
            titulo="Prazos que valem",
            sinal="prazo",
            ordem_padrao=2,
            tipo_conteudo="prazo",
        ),
        BlocoTemplate(
            id="b-quem",
            titulo="Quem faz o quê",
            sinal="responsavel",
            ordem_padrao=3,
            tipo_conteudo="responsavel",
        ),
        BlocoTemplate(
            id="b-valores",
            titulo="Limites e valores",
            sinal="valor",
            ordem_padrao=4,
            tipo_conteudo="valor",
        ),
        BlocoTemplate(
            id="b-penalidades",
            titulo="Penalidades e exceções",
            sinal="risco",
            ordem_padrao=5,
            tipo_conteudo="risco",
        ),
        BlocoTemplate(
            id="b-versao",
            titulo="Versão em vigor e o que mudou",
            sinal="alerta",
            ordem_padrao=6,
            tipo_conteudo="versao_vigor",
        ),
        BlocoTemplate(
            id="b-ligados",
            titulo="Documentos ligados",
            sinal="regra",
            ordem_padrao=7,
            tipo_conteudo="documentos_ligados",
        ),
    ],
    "procedimento": [
        BlocoTemplate(
            id="b-prazos",
            titulo="Prazos",
            sinal="prazo",
            ordem_padrao=1,
            tipo_conteudo="prazo",
        ),
        BlocoTemplate(
            id="b-valores",
            titulo="Valores",
            sinal="valor",
            ordem_padrao=2,
            tipo_conteudo="valor",
        ),
        BlocoTemplate(
            id="b-quem",
            titulo="Quem faz o quê",
            sinal="responsavel",
            ordem_padrao=3,
            tipo_conteudo="responsavel",
        ),
        BlocoTemplate(
            id="b-riscos",
            titulo="Riscos",
            sinal="risco",
            ordem_padrao=4,
            tipo_conteudo="risco",
        ),
    ],
    "nota_tecnica": [
        BlocoTemplate(
            id="b-prazos",
            titulo="Prazos",
            sinal="prazo",
            ordem_padrao=1,
            tipo_conteudo="prazo",
        ),
        BlocoTemplate(
            id="b-valores",
            titulo="Valores",
            sinal="valor",
            ordem_padrao=2,
            tipo_conteudo="valor",
        ),
        BlocoTemplate(
            id="b-quem",
            titulo="Quem faz o quê",
            sinal="responsavel",
            ordem_padrao=3,
            tipo_conteudo="responsavel",
        ),
        BlocoTemplate(
            id="b-riscos",
            titulo="Riscos",
            sinal="risco",
            ordem_padrao=4,
            tipo_conteudo="risco",
        ),
    ],
}


def derivar_familia(
    doc: DocumentoDetalhe,
    candidatos: Optional[Dict[str, List[ItemFicha]]] = None,
) -> FamiliaDocumento:
    """Deriva a família do documento a partir de camada.sigla / camada.grupo (Revisão 13/11).

    Regras da taxonomia e do contrato C22:
    - CTR e NT com valor e prazo -> 'contrato'
    - NG e RG -> 'norma'
    - PX, GU, FL, FM, TB, PP -> 'procedimento'
    - NT e CT sem valor -> 'nota_tecnica'
    """
    sigla = doc.camada.sigla if doc.camada else (doc.codigo.split("_")[0] if "_" in doc.codigo else "")
    sigla = sigla.upper()

    if sigla == "CTR":
        return "contrato"

    if sigla in ("NG", "RG"):
        return "norma"

    if sigla in ("PX", "PP", "GU", "FL", "FM", "TB"):
        return "procedimento"

    if sigla in ("NT", "CT", "DV"):
        if sigla == "NT":
            if candidatos is None:
                cands = extrair_candidatos(doc)
            else:
                cands = candidatos
            tem_valor = bool(cands.get("valores"))
            tem_prazo = bool(cands.get("prazos"))
            if tem_valor and tem_prazo:
                return "contrato"
            return "nota_tecnica"
        return "nota_tecnica"

    # Fallback por grupo de camada no catálogo ACME
    grupo = doc.camada.grupo if doc.camada else ""
    if grupo == "Instrumento":
        return "contrato"
    if grupo in ("Normativo", "Programa"):
        return "norma"
    if grupo in ("Apoio", "Operacional"):
        return "procedimento"

    return "norma"
