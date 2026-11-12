"""Router do Simulador de Cenários "E se?" (Issue #8, Adendo v0.2).

Endpoints:
- GET /api/regras: lista regras paramétricas para simulação
- POST /api/simular: executa simulação hipotética determinística
"""

from typing import List
from fastapi import APIRouter

from app.models import RegraSimulacao, SimulacaoRequest, SimulacaoResponse
from app.simulador import SimuladorService

router = APIRouter(prefix="/api", tags=["simulador"])
simulador_service = SimuladorService()


@router.get("/regras", response_model=List[RegraSimulacao])
def get_regras():
    """Retorna as regras normativas disponíveis para simulação hipotética (Issue #8, Adendo v0.2)."""
    return simulador_service.listar_regras()


@router.post("/simular", response_model=SimulacaoResponse)
def post_simular(req: SimulacaoRequest):
    """Executa simulação de impacto para uma regra paramétrica (Issue #8, Adendo v0.2)."""
    return simulador_service.simular(req)
