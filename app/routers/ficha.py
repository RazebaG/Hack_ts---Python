"""Router da Ficha do Documento (C22–C27, Adendo v0.4, Issue #48).

Expõe o endpoint GET /api/documentos/{codigo}/ficha em modo extrativo
determinístico, com montagem a partir dos módulos de app/ficha/, cache em memória
por hash do conteúdo, validação de perfil e linguagem, e suporte a ETag / 304.
"""

import hashlib
import threading
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.acervo import get_acervo
from app.ficha.modelos import FichaDocumento
from app.ficha.montagem import montar_ficha
from app.models import DocumentoDetalhe

router = APIRouter(prefix="/api", tags=["ficha"])

# Perfis e linguagens válidos conforme o Adendo v0.4 (C22)
PERFIS_VALIDOS = {"empregado", "gestor", "diretoria", "financeiro", "juridico", "rh"}
LINGUAGENS_VALIDAS = {"original", "simples"}

# Cache em memória por hash de conteúdo (F-07)
# Chave: (codigo, versao, hash_conteudo, perfil, linguagem)
_cache_fichas: Dict[Tuple[str, str, str, Optional[str], str], FichaDocumento] = {}
_lock_cache = threading.Lock()


def calcular_hash_conteudo(doc: DocumentoDetalhe) -> str:
    """Calcula o hash SHA-256 do conteúdo do documento para cache e ETag."""
    hasher = hashlib.sha256()
    hasher.update(doc.codigo.encode("utf-8"))
    hasher.update(doc.versao.encode("utf-8"))
    hasher.update((doc.titulo or "").encode("utf-8"))
    hasher.update((doc.fase or "").encode("utf-8"))
    hasher.update((doc.vigencia or "").encode("utf-8"))
    hasher.update((doc.header_raw or "").encode("utf-8"))
    for s in doc.secoes:
        hasher.update(s.id.encode("utf-8"))
        hasher.update((s.titulo or "").encode("utf-8"))
        hasher.update(s.texto.encode("utf-8"))
    return hasher.hexdigest()


def obter_total_fichas_prontas() -> int:
    """Retorna a contagem de documentos únicos com ficha gerada e pronta em memória."""
    with _lock_cache:
        docs_unicos = {(k[0], k[1]) for k in _cache_fichas.keys()}
        return len(docs_unicos)


def limpar_cache_fichas() -> None:
    """Limpa o cache em memória (utilizado em testes)."""
    with _lock_cache:
        _cache_fichas.clear()


@router.get("/documentos/{codigo}/ficha", response_model=FichaDocumento)
def obter_ficha(
    codigo: str,
    request: Request,
    response: Response,
    versao: Optional[str] = Query(None, description="Versão do documento (se omitido, usa a vigente)"),
    perfil: Optional[str] = Query(None, description="Perfil do usuário: empregado, gestor, diretoria, financeiro, juridico, rh"),
    linguagem: Optional[str] = Query("original", description="Linguagem do conteúdo: original ou simples"),
):
    """Retorna a Ficha do Documento por Regra (C22, RF44 a RF57, Issue #48).

    - Modo extrativo e estado 'pronta'
    - Cálculo determinístico por hash de conteúdo mantido em memória
    - Suporte a ETag e validação condicional HTTP 304 Not Modified
    - Validação de perfil e linguagem (HTTP 422) e documento inexistente (HTTP 404)
    """
    if perfil is not None and perfil not in PERFIS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Perfil '{perfil}' inválido. Valores permitidos: {', '.join(sorted(PERFIS_VALIDOS))}.",
        )
    if linguagem is not None and linguagem not in LINGUAGENS_VALIDAS:
        raise HTTPException(
            status_code=422,
            detail=f"Linguagem '{linguagem}' inválida. Valores permitidos: {', '.join(sorted(LINGUAGENS_VALIDAS))}.",
        )

    acervo = get_acervo()
    doc = acervo.buscar(codigo=codigo, versao=versao)
    if not doc:
        versao_info = f" na versão {versao}" if versao else ""
        raise HTTPException(
            status_code=404,
            detail=f"Documento '{codigo}'{versao_info} não encontrado no acervo.",
        )

    conteudo_hash = calcular_hash_conteudo(doc)
    etag = f'"{conteudo_hash}"'
    response.headers["ETag"] = etag

    # Validação condicional com cabeçalho If-None-Match
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    ling = linguagem or "original"
    cache_key = (doc.codigo, doc.versao, conteudo_hash, perfil, ling)

    with _lock_cache:
        ficha = _cache_fichas.get(cache_key)

    if ficha is None:
        ficha = montar_ficha(
            doc=doc,
            acervo=acervo,
            perfil=perfil,
            linguagem=ling,
        )
        with _lock_cache:
            _cache_fichas[cache_key] = ficha

    return ficha
