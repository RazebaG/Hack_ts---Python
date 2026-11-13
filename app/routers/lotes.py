"""Rotas do envio em lote e da digitalização (issue #10 · C18)."""

from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.acervo import get_acervo
from app.ingestao import MAX_BYTES_ARQUIVO, LoteInvalido, LotesService
from app.seguranca import sanitizar_nome_arquivo

router = APIRouter(prefix="/api/lotes", tags=["lotes"])

servico = LotesService(get_acervo())

_BLOCO = 1024 * 1024


class AtualizarArquivoRequest(BaseModel):
    assunto: Optional[str] = Field(None, description="Assunto escolhido (ex.: ferias, inovacao, locacao)")
    serie: Optional[int] = Field(None, description="Série do catálogo §5 (ex.: 1)")
    texto: Optional[str] = Field(None, description="Texto corrigido (foto lida ou documento digital)")
    revisado: Optional[bool] = Field(None, description="Pessoa conferiu o texto lido da foto")


class PublicarRequest(BaseModel):
    arquivos: Optional[List[str]] = Field(None, description="IDs dos arquivos a publicar; vazio = todos os prontos")


def _ler_limitado(arquivo: UploadFile) -> bytes:
    """Lê no máximo 10 MB + 1 byte: o excedente basta para marcar o erro de tamanho."""
    partes = []
    lido = 0
    while lido <= MAX_BYTES_ARQUIVO:
        bloco = arquivo.file.read(_BLOCO)
        if not bloco:
            break
        partes.append(bloco)
        lido += len(bloco)
    return b"".join(partes)


def _lote_ou_404(lote_id: str):
    lote = servico.obter(lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail=f"Lote '{lote_id}' não encontrado.")
    return lote


@router.post("", status_code=201)
def criar_lote(arquivos: List[UploadFile] = File(..., description="Arquivos .md, .pdf, .jpg ou .png")):
    """Envia 1 ou mais arquivos. Cada arquivo é validado, lido e classificado por tema.

    Rota síncrona (def): o FastAPI a executa no threadpool, então a leitura de PDF
    e a chamada ao Bedrock não bloqueiam o event loop.
    """
    if not arquivos:
        raise HTTPException(status_code=400, detail="Envie ao menos um arquivo.")
    conteudos = [(sanitizar_nome_arquivo(a.filename), _ler_limitado(a)) for a in arquivos]
    try:
        lote = servico.criar_lote(conteudos)
    except LoteInvalido as exc:
        raise HTTPException(status_code=exc.status, detail=exc.mensagem)
    return lote.para_dict()


@router.get("/{lote_id}")
def obter_lote(lote_id: str):
    return _lote_ou_404(lote_id).para_dict()


@router.patch("/{lote_id}/arquivos/{arq_id}")
def atualizar_arquivo(lote_id: str, arq_id: str, req: AtualizarArquivoRequest):
    """Corrige o tema (assunto/série), o texto lido ou marca a revisão como feita."""
    lote = _lote_ou_404(lote_id)
    arq = lote.arquivo(arq_id)
    if not arq:
        raise HTTPException(status_code=404, detail=f"Arquivo '{arq_id}' não encontrado no lote.")
    try:
        servico.atualizar_arquivo(
            lote, arq, assunto=req.assunto, serie=req.serie, texto=req.texto, revisado=req.revisado
        )
    except LoteInvalido as exc:
        raise HTTPException(status_code=exc.status, detail=exc.mensagem)
    return arq.para_dict()


@router.post("/{lote_id}/publicar")
def publicar_lote(lote_id: str, req: Optional[PublicarRequest] = None):
    """Publica os arquivos prontos (tema definido; fotos só depois da revisão)."""
    lote = _lote_ou_404(lote_id)
    return servico.publicar(lote, arquivos=req.arquivos if req else None)
