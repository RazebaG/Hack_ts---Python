"""Router da Ficha do Documento (C22–C27, Adendo v0.4).

Módulos da Ficha em app/ficha/ e rotas da API em app/routers/ficha.py.
Implementa:
- GET /api/documentos/{codigo}/ficha (C22)
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends

from app.acervo import AcervoRepository, get_acervo
from app.ficha.modelos import FichaDocumento
from app.ficha.montagem import montar_ficha

PERFIS_VALIDOS = {"empregado", "gestor", "diretoria", "financeiro", "juridico", "rh"}

router = APIRouter(prefix="/api", tags=["ficha"])


@router.get(
    "/documentos/{codigo}/ficha",
    response_model=FichaDocumento,
    summary="Obter ficha estruturada do documento",
    description="Retorna a Ficha do Documento (C22) com identidade, governança, mesa de decisão, blocos por família e relevância determinística.",
)
def obter_ficha_documento(
    codigo: str,
    versao: Optional[str] = Query(None, description="Versão do documento (padrão: vigente)"),
    perfil: Optional[str] = Query(None, description="Perfil do usuário (P1)"),
    linguagem: str = Query("original", description="Linguagem: original ou simples (P1)"),
    acervo: AcervoRepository = Depends(get_acervo),
) -> FichaDocumento:
    if perfil is not None and perfil.lower() not in PERFIS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Perfil '{perfil}' inválido. Opções válidas: {sorted(PERFIS_VALIDOS)}",
        )

    doc = acervo.buscar(codigo, versao)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Documento '{codigo}'{' versão ' + versao if versao else ''} não encontrado no acervo.",
        )

    ficha = montar_ficha(
        doc=doc,
        acervo=acervo,
        perfil=perfil,
        linguagem=linguagem,
    )
    return ficha
