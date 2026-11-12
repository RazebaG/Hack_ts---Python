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


# ==============================================================================
# Modelos de Inteligência por Perspectiva (Issue #4, C15, C17, Adendo v0.1)
# ==============================================================================

class DestaqueItem(BaseModel):
    titulo: str = Field(..., description="Título do destaque")
    valor: Optional[str] = Field(None, description="Valor textual destacado (ex: R$ 18.250,00 ou 45 dias corridos)")
    fonte: Fonte = Field(..., description="Fonte do acervo com seção e camada")
    fonte_anterior: Optional[Fonte] = Field(None, description="Fonte da versão anterior substituída (Adendo v0.1 F)")
    aviso: Optional[str] = Field(None, description="Aviso sobre versão substituída (ex: 'v2 (substituída) dizia 30 dias')")
    tema: Optional[Tema] = Field(None, description="Tema derivado do catálogo (C17)")


class ValorItem(BaseModel):
    rotulo: str = Field(..., description="Rótulo do valor financeiro")
    numero: float = Field(..., description="Valor numérico extraído")
    unidade: str = Field("BRL", description="Unidade de medida: BRL, %, dias, etc.")
    fonte: Fonte = Field(..., description="Fonte com código, versão, seção e camada")
    tema: Optional[Tema] = Field(None, description="Tema do documento ou assunto (C17)")


class PrazoItem(BaseModel):
    data: Optional[str] = Field(None, description="Data ISO 8601 (YYYY-MM-DD) quando houver")
    evento: str = Field(..., description="Descrição do prazo ou evento")
    marco: Optional[str] = Field(None, description="Marco relativo (ex: D-45, D-35) conforme Adendo v0.1 B")
    cenario: Optional[str] = Field(None, description="Cenário ou documento de exemplo (Adendo v0.1 B)")
    fonte: Fonte = Field(..., description="Fonte da seção citada")
    tema: Optional[Tema] = Field(None, description="Tema derivado (C17)")


class ResponsavelItem(BaseModel):
    papel: str = Field(..., description="Sigla ou denominação do responsável (GOC, GCO, DIRAF, GGC...)")
    responsabilidade: str = Field(..., description="Descrição da atribuição ou obrigação")
    obrigacao: Optional[str] = Field(None, description="Alias para responsabilidade / obrigação (RF09)")
    fonte: Fonte = Field(..., description="Fonte com seção e camada")
    tema: Optional[Tema] = Field(None, description="Tema do documento (C17)")


class RiscoItem(BaseModel):
    descricao: str = Field(..., description="Descrição do risco, penalidade ou conformidade")
    fonte: Fonte = Field(..., description="Fonte do trecho citado")
    tema: Optional[Tema] = Field(None, description="Tema derivado (C17)")


class PerspectivaResumo(BaseModel):
    id: str = Field(..., description="Identificador da perspectiva: juridico, financeiro, pessoas, gestao")
    nome: str = Field(..., description="Nome exibido da perspectiva")


class PerspectivaDetalhe(BaseModel):
    id: str = Field(..., description="Identificador da perspectiva")
    nome: str = Field(..., description="Nome da perspectiva")
    destaques: List[DestaqueItem] = Field(default_factory=list, description="Lista de destaques principais")
    valores: List[ValorItem] = Field(default_factory=list, description="Valores numéricos e limites")
    prazos: List[PrazoItem] = Field(default_factory=list, description="Prazos e cronograma")
    responsaveis: List[ResponsavelItem] = Field(default_factory=list, description="Matriz de responsáveis e obrigações")
    riscos: List[RiscoItem] = Field(default_factory=list, description="Riscos e alertas normativos")


class GrafoNo(BaseModel):
    id: str = Field(..., description="Identificador do nó (codigo@versao ou codigo para ausentes)")
    codigo: str = Field(..., description="Código do documento (ex: NG_111, NG_012)")
    tipo: Optional[str] = Field(None, description="Sigla do tipo documental (NG, PX, CTR...)")
    versao: Optional[str] = Field(None, description="Versão do documento (None se documento ausente no acervo)")
    substituido: bool = Field(False, description="True se for versão substituída")
    existe_no_acervo: bool = Field(True, description="True se o documento existe no acervo; False se citado mas ausente (Adendo v0.1 C)")
    titulo: Optional[str] = Field(None, description="Título do documento")
    camada: Optional[Camada] = Field(None, description="Camada derivada do catálogo (C15)")
    tema: Optional[Tema] = Field(None, description="Tema e série do catálogo (C17)")


class GrafoAresta(BaseModel):
    de: str = Field(..., description="ID do nó de origem")
    para: str = Field(..., description="ID do nó de destino")
    tipo: str = Field(..., description="Tipo da relação: vinculado_a, referencia, substitui")


class GrafoResponse(BaseModel):
    nos: List[GrafoNo] = Field(default_factory=list, description="Nós do grafo de documentos")
    arestas: List[GrafoAresta] = Field(default_factory=list, description="Arestas de interligação")


class MudancaSecao(BaseModel):
    secao: str = Field(..., description="Identificador da seção")
    tipo: str = Field(..., description="Tipo de mudança: alterado, incluido, removido")
    antes: Optional[str] = Field(None, description="Conteúdo da seção na versão 'de'")
    depois: Optional[str] = Field(None, description="Conteúdo da seção na versão 'para'")


class CompararResponse(BaseModel):
    codigo: str = Field(..., description="Código do documento comparado")
    de: str = Field(..., description="Versão de origem")
    para: str = Field(..., description="Versão de destino")
    mudancas: List[MudancaSecao] = Field(default_factory=list, description="Diferenças encontradas por seção")
    resumo: List[str] = Field(default_factory=list, description="Frases curtas de resumo das mudanças")


class RelatorioItem(BaseModel):
    texto: str = Field(..., description="Texto do item do relatório")
    fonte: Fonte = Field(..., description="Fonte comprobatória com camada")


class RelatorioSecao(BaseModel):
    titulo: str = Field(..., description="Título da seção do relatório")
    itens: List[RelatorioItem] = Field(default_factory=list, description="Itens da seção")


class RelatorioResponse(BaseModel):
    titulo: str = Field(..., description="Título do relatório executivo")
    gerado_em: str = Field(..., description="Timestamp ISO 8601 da geração")
    perspectiva: Optional[str] = Field(None, description="Perspectiva de origem se aplicável")
    codigo: Optional[str] = Field(None, description="Código do documento se aplicável")
    secoes: List[RelatorioSecao] = Field(default_factory=list, description="Seções do relatório")


# ==============================================================================
# Modelos do Radar de Contradições (Issue #7, Adendo v0.2, C15, C17)
# ==============================================================================

class RadarResumo(BaseModel):
    divergente: int = Field(0, description="Total de itens divergentes (versões substituídas / conflitos)")
    atencao: int = Field(0, description="Total de itens de atenção (referências ausentes)")


class RadarItem(BaseModel):
    id: str = Field(..., description="Identificador único do item no radar")
    tipo: str = Field(..., description="Tipo do item: versao_substituida ou referencia_ausente")
    status: str = Field(..., description="Status do item: divergente ou atencao")
    severidade: str = Field("media", description="Severidade do item: alta, media ou baixa")
    titulo: str = Field(..., description="Título descritivo da contradição ou ausência")
    explicacao: str = Field(..., description="Explicação da divergência ou regra aplicável")
    perspectivas: List[str] = Field(default_factory=list, description="Lista de perspectivas afetadas (pessoas, juridico, financeiro, gestao)")
    codigo_ausente: Optional[str] = Field(None, description="Código do documento ausente no acervo quando aplicável")
    fontes: List[Fonte] = Field(default_factory=list, description="Lista de fontes que fundamentam o item com camada")
    tema: Optional[Tema] = Field(None, description="Tema derivado do catálogo (C17)")


class RadarResponse(BaseModel):
    gerado_em: str = Field(..., description="Timestamp ISO 8601 da geração")
    resumo: RadarResumo = Field(..., description="Contagem consolidada por status")
    itens: List[RadarItem] = Field(default_factory=list, description="Lista de itens identificados pelo radar")


