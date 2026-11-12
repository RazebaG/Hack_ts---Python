"""Router do simulador "E se?" (Issue #8, Adendo v0.2).

Endpoints:
- GET /api/regras
- POST /api/simular
"""

from typing import List
from fastapi import APIRouter

from app.models import Regra, SimularRequest, SimularResponse
from app.simulador import SimuladorService

router = APIRouter(prefix="/api", tags=["simulador"])
simulador_service = SimuladorService()


@router.get("/regras", response_model=List[Regra])
def listar_regras():
    """Regras simuláveis com o valor vigente e a fonte lidos do acervo."""
    return simulador_service.listar_regras()


@router.post("/simular", response_model=SimularResponse)
def simular(req: SimularRequest):
    """Simulação hipotética e determinística (sem IA) da mudança de uma regra."""
    return simulador_service.simular(req)
