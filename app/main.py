from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    DocumentoResumo,
    DocumentoDetalhe,
    SaudeResponse,
    PerguntaRequest,
    PerguntaResponse,
    AvaliacaoRequest,
    AvaliacaoResponse,
    AvaliacaoResumoResponse,
    CodigoDecodificado,
)
from app.acervo import AcervoRepository, get_acervo
from app.perguntar import PerguntarService
from app.avaliacoes import AvaliacoesRepository
from app.routers.inteligencia import router as inteligencia_router
from app.routers.radar import router as radar_router
from app.routers.simulador import router as simulador_router
from app.routers.lotes import router as lotes_router, servico as lotes_servico
from app.codigo import decodificar_codigo
from app.bedrock import get_ia_status
from app.rbac import get_rbac

app = FastAPI(
    title="Assistente do Arquivo Central de Normas - API",
    description="Backend de inteligência sobre o acervo normativo da ACME (HACKA/TS 2026)",
    version="0.1.0",
)

# Configuração de CORS para o frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Roteadores (Issues #4, #7, #8 e #10)
app.include_router(inteligencia_router)
app.include_router(radar_router)
app.include_router(simulador_router)
app.include_router(lotes_router)

# Inicialização dos repositórios e serviços em memória
acervo = get_acervo()
perguntar_service = PerguntarService(acervo)
avaliacoes_repo = AvaliacoesRepository()

# Documento publicado por lote entra no índice híbrido de /api/perguntar
# (BM25 + embeddings das seções novas). O radar lê o acervo a cada consulta.
lotes_servico.registrar_ao_publicar(perguntar_service.buscador.reindexar)


@app.get("/api/saude", response_model=SaudeResponse)
def get_saude():
    """Retorna o status da API, total de documentos e status do provedor de IA."""
    return SaudeResponse(
        status="ok",
        documentos=acervo.total(),
        ia=get_ia_status(),
    )


@app.get("/api/documentos", response_model=List[DocumentoResumo])
def listar_documentos(
    assunto: Optional[str] = Query(None, description="Filtrar por assunto (ex: ferias, inovacao, locacao)"),
    substituido: Optional[bool] = Query(None, description="Filtrar por vigência (True para versões anteriores)"),
    serie: Optional[int] = Query(None, description="Filtrar por série da norma (ex: 1 para Gente e Cultura)"),
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle de acesso RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture para resolução do cargo no RBAC"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Lista documentos do acervo filtrados por assunto, vigência e cargo RBAC (Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    docs = acervo.listar(assunto=assunto, substituido=substituido, serie=serie)
    if cargo_efetivo:
        docs = [d for d in docs if rbac.documento_permitido(cargo_efetivo, d)]
        rbac.registrar_auditoria(cargo_efetivo, "/api/documentos", f"total={len(docs)}", permitido=True)
    return docs


@app.get("/api/documentos/{codigo}", response_model=DocumentoDetalhe)
def obter_documento(
    codigo: str,
    versao: Optional[str] = Query(None, description="Versão específica (se omitido, retorna a vigente)"),
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle de acesso RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture para resolução do cargo no RBAC"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Retorna detalhes e seções de um documento com verificação de alçada RBAC (Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(cargo=cargo, x_cargo=x_cargo, x_user_email=x_user_email, email=email)
    if cargo_efetivo and not rbac.documento_permitido(cargo_efetivo, codigo):
        rbac.registrar_auditoria(cargo_efetivo, f"/api/documentos/{codigo}", codigo, permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: documento '{codigo}' não acessível para o cargo '{cargo_efetivo}'.",
        )

    doc = acervo.buscar(codigo=codigo, versao=versao)
    if not doc:
        versao_info = f" na versão {versao}" if versao else ""
        raise HTTPException(
            status_code=404,
            detail=f"Documento '{codigo}'{versao_info} não encontrado no acervo.",
        )

    if cargo_efetivo and not rbac.documento_permitido(cargo_efetivo, doc):
        rbac.registrar_auditoria(cargo_efetivo, f"/api/documentos/{codigo}", codigo, permitido=False)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: versão ou tipo do documento '{codigo}' não acessível para o cargo '{cargo_efetivo}'.",
        )

    if cargo_efetivo:
        rbac.registrar_auditoria(cargo_efetivo, f"/api/documentos/{codigo}", codigo, permitido=True)
    return doc


@app.get("/api/acervo/estatisticas")
def get_estatisticas():
    """Retorna contadores consolidados do acervo por vigência, tipo e assunto."""
    return acervo.estatisticas()


@app.get("/api/codigo/{codigo:path}", response_model=CodigoDecodificado)
def decodificar_documento(codigo: str):
    """Decodifica a estrutura de um código de documento conforme regras do catálogo (C15, C17, RF16)."""
    return decodificar_codigo(codigo, acervo=acervo)



@app.post("/api/perguntar", response_model=PerguntaResponse)
def post_perguntar(
    req: PerguntaRequest,
    cargo: Optional[str] = Query(None, description="Cargo do usuário para controle RBAC"),
    email: Optional[str] = Query(None, description="E-mail de fixture para resolução do cargo no RBAC"),
    x_cargo: Optional[str] = Header(None, alias="X-Cargo"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
):
    """Responde perguntas sobre o acervo com citação, versão vigente, abstenção e filtro RBAC (C13, C15, RF02, Issue #22)."""
    rbac = get_rbac()
    cargo_efetivo = rbac.resolver_cargo(
        cargo=getattr(req, "cargo", None) or cargo,
        x_cargo=x_cargo,
        x_user_email=x_user_email,
        email=getattr(req, "email", None) or email,
        perfil=req.perfil,
    )
    return perguntar_service.responder(req, cargo=cargo_efetivo)


@app.get("/api/rbac/usuarios")
def listar_usuarios_rbac():
    """Retorna os usuários de fixture configurados para demonstração do RBAC (Issue #22)."""
    rbac = get_rbac()
    return [
        {
            "email": u.email,
            "nome": u.nome,
            "cargo": u.cargo,
            "descricao": u.descricao,
        }
        for u in rbac.usuarios_por_email.values()
    ]


@app.get("/api/rbac/matriz")
def obter_matriz_rbac():
    """Retorna a matriz de permissões RBAC por cargo (Issue #22)."""
    rbac = get_rbac()
    return {
        cargo_id: {
            "cargo": r.cargo,
            "descricao": r.descricao,
            "assuntos_permitidos": r.assuntos_permitidos,
            "tipos_permitidos": r.tipos_permitidos,
            "documentos_proibidos": r.documentos_proibidos,
            "perspectivas_permitidas": r.perspectivas_permitidas,
            "ver_radar": r.ver_radar,
            "ver_substituidos": r.ver_substituidos,
            "ver_grafo": r.ver_grafo,
            "ver_relatorio": r.ver_relatorio,
        }
        for cargo_id, r in rbac.cargos.items()
    }


@app.post("/api/avaliacoes", response_model=AvaliacaoResponse, status_code=201)
def registrar_avaliacao(req: AvaliacaoRequest):
    """Registra uma avaliação de resposta (C14, RF39, RNF16)."""
    return avaliacoes_repo.registrar(req)


@app.get("/api/avaliacoes/resumo", response_model=AvaliacaoResumoResponse)
def get_avaliacoes_resumo():
    """Retorna resumo consolidado de avaliações: total, úteis e por canal (C14, RF39)."""
    return avaliacoes_repo.resumo()

