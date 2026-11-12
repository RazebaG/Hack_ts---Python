from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
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
from app.codigo import decodificar_codigo
from app.bedrock import get_ia_status

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

# Roteadores (Issues #4 e #7)
app.include_router(inteligencia_router)
app.include_router(radar_router)

# Inicialização dos repositórios e serviços em memória
acervo = get_acervo()
perguntar_service = PerguntarService(acervo)
avaliacoes_repo = AvaliacoesRepository()


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
):
    """Lista todos os documentos do acervo (vigentes e substituídos)."""
    return acervo.listar(assunto=assunto, substituido=substituido, serie=serie)


@app.get("/api/documentos/{codigo}", response_model=DocumentoDetalhe)
def obter_documento(
    codigo: str,
    versao: Optional[str] = Query(None, description="Versão específica (se omitido, retorna a vigente)"),
):
    """Retorna detalhes e seções de um documento. Sem versão -> retorna a versão vigente."""
    doc = acervo.buscar(codigo=codigo, versao=versao)
    if not doc:
        versao_info = f" na versão {versao}" if versao else ""
        raise HTTPException(
            status_code=404,
            detail=f"Documento '{codigo}'{versao_info} não encontrado no acervo.",
        )
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
def post_perguntar(req: PerguntaRequest):
    """Responde perguntas sobre o acervo com citação, versão vigente e abstenção (C13, C15, RF02)."""
    return perguntar_service.responder(req)


@app.post("/api/avaliacoes", response_model=AvaliacaoResponse, status_code=201)
def registrar_avaliacao(req: AvaliacaoRequest):
    """Registra uma avaliação de resposta (C14, RF39, RNF16)."""
    return avaliacoes_repo.registrar(req)


@app.get("/api/avaliacoes/resumo", response_model=AvaliacaoResumoResponse)
def get_avaliacoes_resumo():
    """Retorna resumo consolidado de avaliações: total, úteis e por canal (C14, RF39)."""
    return avaliacoes_repo.resumo()

