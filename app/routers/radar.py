"""Router do Radar de Contradições (Issue #7, Adendo v0.2).

Endpoint:
- GET /api/radar
"""

from typing import Optional
from fastapi import APIRouter, Query, Header, HTTPException

from app.models import RadarResponse
from app.radar import RadarService
from app.rbac import get_rbac

router = APIRouter(prefix="/api", tags=["radar"])
radar_service = RadarService()


@router.get("/radar", response_model=RadarResponse)
def get_radar(
    perspectiva: Optional[str] = Query(
        None,
        description="Filtro opcional por perspectiva: juridico, financeiro, pessoas, gestao",
    ),
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle de acesso RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture para resolução do cargo"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Radar de contradições: versões substituídas e referências a documentos ausentes no acervo (Issue #7, Adendo v0.2, Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    if cargo_efetivo and not rbac.radar_permitido(cargo_efetivo):
        rbac.registrar_auditoria(cargo_efetivo, "/api/radar", "radar", permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: radar de contradições não acessível para o cargo '{cargo_efetivo}'.",
        )

    rbac.registrar_auditoria(cargo_efetivo, "/api/radar", "radar", permitido=True)
    return radar_service.obter_radar(perspectiva=perspectiva)
