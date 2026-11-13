"""Router de inteligência por perspectiva (Issue #4).

Endpoints:
- GET /api/perspectivas
- GET /api/perspectivas/{id}
- GET /api/grafo
- GET /api/comparar
- GET /api/relatorio
"""

from typing import List, Optional
from fastapi import APIRouter, Query, Header, HTTPException
from app.models import (
    PerspectivaResumo,
    PerspectivaDetalhe,
    GrafoResponse,
    CompararResponse,
    RelatorioResponse,
)
from app.inteligencia import InteligenciaService
from app.rbac import get_rbac

router = APIRouter(prefix="/api", tags=["inteligencia"])
inteligencia_service = InteligenciaService()


@router.get("/perspectivas", response_model=List[PerspectivaResumo])
def listar_perspectivas(
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture do usuário"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Lista as perspectivas disponíveis filtradas pelo cargo (juridico, financeiro, pessoas, gestao)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    persps = inteligencia_service.listar_perspectivas()
    if cargo_efetivo:
        persps = [p for p in persps if rbac.perspectiva_permitida(cargo_efetivo, p.id)]
    return persps


@router.get("/perspectivas/{id}", response_model=PerspectivaDetalhe)
def obter_perspectiva(
    id: str,
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture do usuário"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Retorna os dados detalhados de uma perspectiva com controle RBAC (Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    if cargo_efetivo and not rbac.perspectiva_permitida(cargo_efetivo, id):
        rbac.registrar_auditoria(cargo_efetivo, f"/api/perspectivas/{id}", id, permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: perspectiva '{id}' não acessível para o cargo '{cargo_efetivo}'.",
        )
    rbac.registrar_auditoria(cargo_efetivo, f"/api/perspectivas/{id}", id, permitido=True)
    return inteligencia_service.obter_perspectiva(id)


@router.get("/grafo", response_model=GrafoResponse)
def get_grafo(
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture do usuário"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Retorna o grafo de documentos do acervo filtrado pelo cargo."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    grafo = inteligencia_service.gerar_grafo()
    if cargo_efetivo:
        nos_permitidos = {n.id for n in grafo.nos if rbac.documento_permitido(cargo_efetivo, n.id.split("@")[0])}
        nos_filtrados = [n for n in grafo.nos if n.id in nos_permitidos]
        arestas_filtradas = [
            a for a in grafo.arestas if a.de in nos_permitidos and a.para in nos_permitidos
        ]
        return GrafoResponse(
            nos=nos_filtrados,
            arestas=arestas_filtradas,
        )
    return grafo


@router.get("/comparar", response_model=CompararResponse)
def comparar_documento(
    codigo: str = Query(..., description="Código do documento (ex: NG_111)"),
    de: str = Query(..., description="Versão de origem (ex: 2.0.0)"),
    para: str = Query(..., description="Versão de destino (ex: 3.0.0)"),
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture do usuário"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Compara duas versões do mesmo documento seção a seção com controle RBAC (Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    if cargo_efetivo and not rbac.documento_permitido(cargo_efetivo, codigo):
        rbac.registrar_auditoria(cargo_efetivo, "/api/comparar", codigo, permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: comparação do documento '{codigo}' não acessível para o cargo '{cargo_efetivo}'.",
        )
    rbac.registrar_auditoria(cargo_efetivo, "/api/comparar", codigo, permitido=True)
    return inteligencia_service.comparar_versoes(codigo=codigo, de=de, para=para)


@router.get("/relatorio", response_model=RelatorioResponse)
def get_relatorio(
    perspectiva: Optional[str] = Query(None, description="Perspectiva do relatório (ex: juridico, financeiro, pessoas, gestao)"),
    codigo: Optional[str] = Query(None, description="Código de documento para relatório executivo (ex: CTR_2026-012)"),
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture do usuário"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Gera relatório executivo consolidado com fontes estruturadas e controle RBAC (Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    if cargo_efetivo and not rbac.relatorio_permitido(cargo_efetivo, perspectiva=perspectiva, codigo=codigo):
        rbac.registrar_auditoria(cargo_efetivo, "/api/relatorio", f"persp={perspectiva}/doc={codigo}", permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: relatório executivo não acessível para o cargo '{cargo_efetivo}'.",
        )
    rbac.registrar_auditoria(cargo_efetivo, "/api/relatorio", f"persp={perspectiva}/doc={codigo}", permitido=True)
    return inteligencia_service.gerar_relatorio(perspectiva=perspectiva, codigo=codigo)
