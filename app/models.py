from typing import Optional, List
from pydantic import BaseModel, Field


class Camada(BaseModel):
    sigla: str = Field(..., description="Sigla do tipo documental, ex: PX, NG, CTR")
    tipo_nome: str = Field(..., description="Nome por extenso do tipo, ex: Procedimento, Norma Geral")
    grupo: str = Field(..., description="Grupo no catálogo: Normativo, Operacional, Apoio, Programa, Temporário, Instrumento, Residual")
    subordinado_a: Optional[str] = Field(None, description="Pai direto pelo campo Vinculado a")

    def rotulo(self, completo: bool = True) -> str:
        if completo:
            if self.subordinado_a:
                return f"{self.sigla} · {self.tipo_nome} · {self.grupo} · subordinado a {self.subordinado_a}"
            return f"{self.sigla} · {self.tipo_nome} · {self.grupo}"
        return f"{self.sigla} · {self.grupo}"

    def __str__(self) -> str:
        return self.rotulo()


class Tema(BaseModel):
    assunto: str = Field(..., description="Assunto ou pasta do documento (ex: ferias, inovacao, locacao)")
    serie: Optional[int] = Field(None, description="Número da série pelo catálogo §5 (ex: 1, 11) ou null se não definido")
    serie_nome: Optional[str] = Field(None, description="Nome da série (ex: Gente e Cultura) ou null")
    confirmado_por: str = Field("regra", description="Origem da confirmação do tema, ex: regra")
    observacao: Optional[str] = Field(None, description="Observação quando a série não é definida pelo catálogo")


class Fonte(BaseModel):
    codigo: str = Field(..., description="Código do documento, ex: NG_111")
    versao: str = Field(..., description="Versão do documento, ex: 3.0.0")
    secao: str = Field(..., description="ID exato da seção, ex: 4.3.1 ou Cláusula Sétima")
    trecho: str = Field(..., description="Trecho citado do documento")
    camada: Optional[Camada] = Field(None, description="Camada da norma derivada do catálogo")


class Citacao(BaseModel):
    codigo: str = Field(..., description="Código do documento, ex: PX_1111-001")
    versao: str = Field(..., description="Versão do documento, ex: 1.0.0")
    secao: str = Field(..., description="ID da seção citada")
    trecho: str = Field(..., description="Trecho citado")
    camada: Optional[Camada] = Field(None, description="Camada da norma derivada do catálogo")


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
    camada: Camada = Field(..., description="Camada da norma derivada do catálogo")
    tema: Tema = Field(..., description="Tema e série do documento derivados do catálogo")


class DocumentoDetalhe(DocumentoResumo):
    secoes: List[Secao] = Field(default_factory=list, description="Lista de seções do documento")


class SaudeResponse(BaseModel):
    status: str = "ok"
    documentos: int


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., description="Pergunta em linguagem natural sobre o acervo")
    perfil: Optional[str] = Field(None, description="Perfil do usuário: empregado, gestor, diretoria, financeiro, juridico, rh")


class PerguntaResponse(BaseModel):
    resposta_id: str = Field(..., description="Identificador único da resposta (C13)")
    resposta: str = Field(..., description="Texto da resposta extrativa estruturada conforme o perfil")
    consta: bool = Field(True, description="True se a informação consta no acervo; False em caso de abstenção")
    citacoes: List[Citacao] = Field(default_factory=list, description="Lista de citações que sustentam a resposta")
    avisos: List[str] = Field(default_factory=list, description="Avisos sobre versões substituídas ou notas")
    proxima_acao: Optional[str] = Field(None, description="Próxima ação recomendada (RF32)")


class AvaliacaoRequest(BaseModel):
    resposta_id: str = Field(..., description="Identificador da resposta avaliada (C13)")
    util: bool = Field(..., description="Indica se a resposta foi útil (True/False)")
    motivo: Optional[str] = Field(None, description="Motivo opcional da avaliação")
    comentario: Optional[str] = Field(None, max_length=200, description="Comentário livre de até 200 caracteres")
    canal: str = Field(..., pattern="^(web|slack|teams)$", description="Canal de origem: web, slack ou teams")
    perfil: Optional[str] = Field(None, description="Perfil do usuário que avaliou")


class AvaliacaoResponse(BaseModel):
    id: str = Field(..., description="Identificador único do registro de avaliação")
    registrado_em: str = Field(..., description="Data/hora ISO 8601 do registro")


class AvaliacaoResumoResponse(BaseModel):
    total: int = Field(0, description="Total de avaliações registradas")
    uteis: int = Field(0, description="Total de avaliações marcadas como úteis")
    por_canal: dict[str, int] = Field(default_factory=dict, description="Contagem de avaliações por canal")


class CodigoDecodificado(BaseModel):
    codigo: str = Field(..., description="Código do documento analisado")
    tipo: Optional[str] = Field(None, description="Sigla do tipo documental, ex: PX, NG, CTR, CT")
    tipo_nome: Optional[str] = Field(None, description="Nome por extenso do tipo documental")
    vinculado_a: Optional[str] = Field(None, description="Código do documento ao qual este se vincula")
    serie: Optional[str] = Field(None, description="Número da série do catálogo §5 em texto (ex: '1', '11') ou null")
    serie_nome: Optional[str] = Field(None, description="Nome por extenso da série no catálogo §5")
    vigencia_regra: Optional[str] = Field(None, description="Regra de vigência do tipo documental segundo o catálogo")
    existe_no_acervo: bool = Field(..., description="True se o documento existe no acervo; False caso contrário")
    observacao: Optional[str] = Field(None, description="Observações sobre ambiguidade, ausência de série ou lacunas")
    camada: Optional[Camada] = Field(None, description="Camada da norma derivada do catálogo")
    tema: Optional[Tema] = Field(None, description="Tema e série derivados do catálogo")


