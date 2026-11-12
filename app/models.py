from typing import Optional, List
from pydantic import BaseModel, Field


class Secao(BaseModel):
    id: str = Field(..., description="Identificador da seção, ex: 1, 2.1, CLÁUSULA SÉTIMA, Anexo A, Tabela 1")
    titulo: str = Field(..., description="Título da seção")
    texto: str = Field(..., description="Conteúdo textual da seção")


class DocumentoResumo(BaseModel):
    codigo: str = Field(..., description="Sigla e número do documento, ex: NG_111")
    titulo: str = Field(..., description="Título do documento")
    tipo: str = Field(..., description="Sigla do tipo documental, ex: NG, PX, CTR")
    tipo_nome: str = Field(..., description="Nome por extenso do tipo, ex: Norma Geral, Contrato")
    versao: str = Field(..., description="Versão semântica do documento, ex: 3.0.0")
    fase: str = Field(..., description="Fase de vigência, ex: Vigente ou Versão anterior")
    vigencia: Optional[str] = Field(None, description="Período ou data de vigência/aprovação/assinatura")
    vinculado_a: Optional[str] = Field(None, description="Código da norma/documento ao qual este se vincula")
    referencia: Optional[str] = Field(None, description="Código de documento de referência")
    assunto: str = Field(..., description="Assunto / pasta de origem (ferias, inovacao, locacao)")
    substituido: bool = Field(False, description="True se for versão anterior/substituída")
    elaborado_por: Optional[str] = Field(None, description="Unidade que elaborou o documento")
    aprovado_por: Optional[str] = Field(None, description="Instância que aprovou o documento")


class DocumentoDetalhe(DocumentoResumo):
    secoes: List[Secao] = Field(default_factory=list, description="Lista de seções do documento")


class SaudeResponse(BaseModel):
    status: str = "ok"
    documentos: int
