"""Router de inteligência por perspectiva (Issue #4).

Endpoints:
- GET /api/perspectivas
- GET /api/perspectivas/{id}
- GET /api/grafo
- GET /api/comparar
- GET /api/relatorio
"""

from typing import List, Optional
from fastapi import APIRouter, Query
from app.models import (
    PerspectivaResumo,
    PerspectivaDetalhe,
    GrafoResponse,
    CompararResponse,
    RelatorioResponse,
)
from app.inteligencia import InteligenciaService

router = APIRouter(prefix="/api", tags=["inteligencia"])
inteligencia_service = InteligenciaService()


@router.get("/perspectivas", response_model=List[PerspectivaResumo])
def listar_perspectivas():
    """Lista as perspectivas disponíveis (juridico, financeiro, pessoas, gestao)."""
    return inteligencia_service.listar_perspectivas()


@router.get("/perspectivas/{id}", response_model=PerspectivaDetalhe)
def obter_perspectiva(id: str):
    """Retorna os dados detalhados de uma perspectiva (destaques, valores, prazos, responsaveis, riscos)."""
    return inteligencia_service.obter_perspectiva(id)


@router.get("/grafo", response_model=GrafoResponse)
def get_grafo():
    """Retorna o grafo de documentos do acervo com nós, relações e documentos ausentes citados."""
    return inteligencia_service.gerar_grafo()


@router.get("/comparar", response_model=CompararResponse)
def comparar_documento(
    codigo: str = Query(..., description="Código do documento (ex: NG_111)"),
    de: str = Query(..., description="Versão de origem (ex: 2.0.0)"),
    para: str = Query(..., description="Versão de destino (ex: 3.0.0)"),
):
    """Compara duas versões do mesmo documento seção a seção com resumo."""
    return inteligencia_service.comparar_versoes(codigo=codigo, de=de, para=para)


@router.get("/relatorio", response_model=RelatorioResponse)
def get_relatorio(
    perspectiva: Optional[str] = Query(None, description="Perspectiva do relatório (ex: juridico, financeiro, pessoas, gestao)"),
    codigo: Optional[str] = Query(None, description="Código de documento para relatório executivo (ex: CTR_2026-012)"),
):
    """Gera relatório executivo consolidado com fontes estruturadas."""
    return inteligencia_service.gerar_relatorio(perspectiva=perspectiva, codigo=codigo)
