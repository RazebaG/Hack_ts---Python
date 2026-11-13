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
    CelulaMapa,
    Alerta,
    Cobertura,
    PontosFicha,
)
from app.ficha.metadados import (
    extrair_metadados_documento,
    extrair_governanca,
    extrair_identidade,
    extrair_metricas,
    extrair_vigencia,
    derivar_familia,
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

__all__ = [
    "FichaDocumento",
    "Identidade",
    "Governanca",
    "Semaforo",
    "ItemFicha",
    "Acao",
    "Bloco",
    "CelulaMapa",
    "Alerta",
    "Cobertura",
    "PontosFicha",
    "extrair_metadados_documento",
    "extrair_governanca",
    "extrair_identidade",
    "extrair_metricas",
    "extrair_vigencia",
    "derivar_familia",
    "gerar_semaforo_base",
    "extrair_candidatos",
    "extrair_pontos_candidatos",
    "extrair_candidatos_por_categoria",
    "verificar_item",
    "verificar_candidatos",
    "verificar_pontos",
    "extrair_e_verificar",
]
