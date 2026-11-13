"""Módulo da Ficha do Documento (C22–C27).

Contrato C22, C22b e adendo v0.4 ao CONTRATO-API.md.
"""

from app.ficha.modelos import (
    FichaDocumento,
    Identidade,
    Governanca,
    Semaforo,
    ItemFicha,
    Acao,
    Bloco,
    RelevanciaBloco,
    CelulaMapa,
    Alerta,
    Cobertura,
    PontosFicha,
    FamiliaDocumento,
    SinaisTriagem,
    ProximoPrazoTriagem,
    ItemTriagem,
    TriagemResposta,
)
from app.ficha.metadados import (
    extrair_metadados_documento,
    extrair_governanca,
    extrair_identidade,
    extrair_metricas,
    extrair_vigencia,
    gerar_semaforo_base,
)
from app.ficha.candidatos import (
    extrair_candidatos,
    extrair_pontos_candidatos,
    extrair_candidatos_por_categoria,
)
from app.ficha.verificador import (
    verificar_item,
    verificar_candidatos,
    verificar_pontos,
    extrair_e_verificar,
)
from app.ficha.familias import (
    FAMILIA_BLOCOS,
    BlocoTemplate,
    derivar_familia,
)
from app.ficha.relevancia import (
    PesosRelevancia,
    calcular_relevancia_bloco,
)
from app.ficha.montagem import (
    montar_ficha,
)

__all__ = [
    "FichaDocumento",
    "Identidade",
    "Governanca",
    "Semaforo",
    "ItemFicha",
    "Acao",
    "Bloco",
    "RelevanciaBloco",
    "CelulaMapa",
    "Alerta",
    "Cobertura",
    "PontosFicha",
    "FamiliaDocumento",
    "SinaisTriagem",
    "ProximoPrazoTriagem",
    "ItemTriagem",
    "TriagemResposta",
    "extrair_metadados_documento",
    "extrair_governanca",
    "extrair_identidade",
    "extrair_metricas",
    "extrair_vigencia",
    "gerar_semaforo_base",
    "extrair_candidatos",
    "extrair_pontos_candidatos",
    "extrair_candidatos_por_categoria",
    "verificar_item",
    "verificar_candidatos",
    "verificar_pontos",
    "extrair_e_verificar",
    "FAMILIA_BLOCOS",
    "BlocoTemplate",
    "derivar_familia",
    "PesosRelevancia",
    "calcular_relevancia_bloco",
    "montar_ficha",
]
