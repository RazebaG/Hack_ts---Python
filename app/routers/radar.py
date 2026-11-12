"""Router do Radar de Contradições (Issue #7, Adendo v0.2).

Endpoint:
- GET /api/radar
"""

from typing import Optional
from fastapi import APIRouter, Query

from app.models import RadarResponse
from app.radar import RadarService

router = APIRouter(prefix="/api", tags=["radar"])
radar_service = RadarService()


@router.get("/radar", response_model=RadarResponse)
def get_radar(
    perspectiva: Optional[str] = Query(
        None,
        description="Filtro opcional por perspectiva: juridico, financeiro, pessoas, gestao",
    ),
):
    """Radar de contradições: versões substituídas e referências a documentos ausentes no acervo (Issue #7, Adendo v0.2)."""
    return radar_service.obter_radar(perspectiva=perspectiva)
