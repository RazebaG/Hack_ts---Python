"""Router da Ficha do Documento (C22–C27, Adendo v0.4).

Módulos da Ficha em app/ficha/ e rotas da API em app/routers/ficha.py.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["ficha"])
