"""Router da Ficha do Documento (C22–C27, Adendo v0.4, Issue #48).

Expõe o endpoint GET /api/documentos/{codigo}/ficha em modo extrativo
determinístico, com montagem a partir dos módulos de app/ficha/, cache em memória
por hash do conteúdo, validação de perfil e linguagem, e suporte a ETag / 304.
"""

import hashlib
import threading
from typing import Dict, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.acervo import AcervoRepository, get_acervo
from app.ficha.modelos import FichaDocumento, TriagemResposta
from app.ficha.montagem import montar_ficha
from app.ficha.triagem import executar_triagem
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


def aquecer_cache_fichas(acervo: Optional[AcervoRepository] = None) -> int:
    """Pré-calcula e armazena em cache as fichas de todos os documentos do acervo (Issue #56)."""
    if acervo is None:
        acervo = get_acervo()
    count = 0
    for doc in acervo.documentos:
        conteudo_hash = calcular_hash_conteudo(doc)
        cache_key = (doc.codigo, doc.versao, conteudo_hash, None, "original")
        with _lock_cache:
            if cache_key in _cache_fichas:
                count += 1
                continue
        ficha = montar_ficha(doc=doc, acervo=acervo, perfil=None, linguagem="original")
        with _lock_cache:
            _cache_fichas[cache_key] = ficha
        count += 1
    return count


def obter_ficha_cache_ou_montar(
    doc: DocumentoDetalhe,
    acervo: AcervoRepository,
    perfil: Optional[str] = None,
    linguagem: str = "original",
) -> FichaDocumento:
    """Recupera a ficha em memória pelo hash de conteúdo ou monta deterministicamente."""
    conteudo_hash = calcular_hash_conteudo(doc)
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


@router.get("/ficha/triagem", response_model=TriagemResposta)
def obter_triagem(
    limite: Optional[int] = Query(None, ge=1, le=20, description="Limita o número de itens retornados (1 a 20)"),
    perfil: Optional[str] = Query(None, description="Perfil do usuário (aceito e ignorado no MVP)"),
    tema: Optional[str] = Query(None, description="Filtrar por tema/assunto (ex: ferias, locacao)"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo documental (ex: CTR, NG, PX)"),
    situacao: Optional[Literal["ok", "atencao", "critico"]] = Query(None, description="Filtrar por situação do semáforo"),
    sinal: Optional[Literal["prazo_30d", "multa", "divergencia"]] = Query(None, description="Filtrar por sinal"),
    ordenar: Literal["urgencia", "vigencia", "tema", "tipo"] = Query("urgencia", description="Critério de ordenação"),
    pagina: int = Query(1, ge=1, description="Número da página (padrão 1)"),
    tamanho: int = Query(50, ge=1, le=100, description="Quantidade de itens por página (padrão 50, máx. 100)"),
    data_referencia: Optional[str] = Query(None, description="Data de referência para cálculo de prazos (AAAA-MM-DD)"),
):
    """Fila e lista de atenção para triagem (C25, RF69, RF71, Issue #54).

    - Retorna a lista de atenção de documentos vigentes ordenada por urgência (padrão)
    - Suporta filtros por tema, tipo, situação (ok/atencao/critico) e sinal (prazo_30d/multa/divergencia)
    - Paginação e suporte a ?limite= (1 a 20) para uso na tela inicial (Mesa e chips)
    - Determinístico, sem IA e sem rede, com reaproveitamento de cache em memória
    """
    if perfil is not None and perfil not in PERFIS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Perfil '{perfil}' inválido. Valores permitidos: {', '.join(sorted(PERFIS_VALIDOS))}.",
        )

    acervo = get_acervo()
    return executar_triagem(
        acervo=acervo,
        obter_ficha_fn=obter_ficha_cache_ou_montar,
        limite=limite,
        perfil=perfil,
        tema=tema,
        tipo=tipo,
        situacao=situacao,
        sinal=sinal,
        ordenar=ordenar,
        pagina=pagina,
        tamanho=tamanho,
        data_referencia=data_referencia,
    )


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

    return obter_ficha_cache_ou_montar(
        doc=doc,
        acervo=acervo,
        perfil=perfil,
        linguagem=linguagem or "original",
    )
