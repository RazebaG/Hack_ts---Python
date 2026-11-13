"""Modelos Pydantic da Ficha do Documento (Contrato C22, C22b e Adendo v0.4).

Especificação: CONTRATO-API-ADENDO-v0.4.md, PRD-FICHA-DO-DOCUMENTO.md e mock-ficha-CTR_2026-012.json.
Reutiliza Fonte e Camada de app.models conforme exigido.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from app.models import Fonte, Camada, Tema

FamiliaDocumento = Literal["contrato", "norma", "procedimento", "nota_tecnica"]


class FonteGov(BaseModel):
    campo: str = Field(..., description="Nome do campo no cabeçalho")
    trecho: str = Field(..., description="Trecho literal extraído do cabeçalho")


class CampoGov(BaseModel):
    valor: Optional[str] = Field(None, description="Valor do campo ou null se não constar")
    fonte: Optional[FonteGov] = Field(None, description="Fonte da governança ou null se campo ausente")


class Governanca(BaseModel):
    elaborado_por: CampoGov = Field(default_factory=CampoGov, description="Unidade elaboradora")
    aprovado_por: CampoGov = Field(default_factory=CampoGov, description="Instância aprovadora")
    aprovado_em: CampoGov = Field(default_factory=CampoGov, description="Data de aprovação")
    assinada_em: CampoGov = Field(default_factory=CampoGov, description="Data de assinatura")
    vinculado_a: CampoGov = Field(default_factory=CampoGov, description="Documento pai direto")
    referencias: List[str] = Field(default_factory=list, description="Lista de códigos de normas referenciadas")
    cadeia: List[str] = Field(default_factory=list, description="Cadeia de subordinação completa até a norma raiz")


class VigenciaFicha(BaseModel):
    texto: str = Field(..., description="Texto da vigência conforme documento")
    inicio: Optional[str] = Field(None, description="Data de início no formato AAAA-MM-DD")
    fim: Optional[str] = Field(None, description="Data de término no formato AAAA-MM-DD")
    dias_restantes: Optional[int] = Field(None, description="Dias restantes até o fim da vigência")


class Metricas(BaseModel):
    secoes: int = Field(..., description="Total de seções do documento")
    palavras: int = Field(..., description="Total de palavras no documento")
    paginas_estimadas: int = Field(..., description="Páginas estimadas (palavras/400 arredondado para cima)")
    leitura_integral_min: int = Field(..., description="Tempo de leitura integral em minutos (palavras/200)")
    leitura_ficha_min: int = Field(3, description="Tempo estimado de leitura da ficha em minutos")


class VigenteEm(BaseModel):
    codigo: str = Field(..., description="Código do documento vigente")
    versao: str = Field(..., description="Versão do documento vigente")


class Identidade(BaseModel):
    titulo: str = Field(..., description="Título do documento")
    tipo: str = Field(..., description="Sigla do tipo documental, ex: CTR, NG, PX")
    tipo_nome: str = Field(..., description="Nome do tipo por extenso, ex: Contrato, Norma Geral")
    camada: Camada = Field(..., description="Camada da norma derivada do catálogo")
    tema: Tema = Field(..., description="Tema e série do documento")
    fase: str = Field(..., description="Fase de vigência, ex: Vigente ou Versão anterior")
    substituido: bool = Field(False, description="True se for versão anterior/substituída")
    vigente_em: Optional[VigenteEm] = Field(None, description="Documento e versão vigente caso substituído")
    vigencia: VigenciaFicha = Field(..., description="Dados estruturados de vigência")
    origem: str = Field("acervo", description="Origem do documento: acervo, upload ou digitalizado")
    classificacao: Optional[str] = Field(None, description="Classificação lida do cabeçalho, ex: interna")
    metricas: Metricas = Field(..., description="Métricas de dimensão e tempo")


class Semaforo(BaseModel):
    nivel: Literal["ok", "atencao", "critico"] = Field(..., description="Nível de atenção do documento")
    motivos: List[str] = Field(default_factory=list, description="Lista de motivos em linguagem simples")


class ModoFicha(BaseModel):
    ia: Literal["bedrock", "extrativo"] = Field("bedrock", description="Modo de geração da ficha")
    modelo: Optional[str] = Field(None, description="Identificador do modelo LLM utilizado")


class ProgressoFicha(BaseModel):
    etapa: str = Field(..., description="Etapa atual da geração")
    feito: int = Field(..., description="Quantidade de etapas concluídas")
    total: int = Field(..., description="Total de etapas")


class ItemFicha(BaseModel):
    id: str = Field(..., description="Identificador único do item")
    titulo: str = Field(..., description="Título do item")
    valor: Optional[str] = Field(None, description="Valor literal ou calculado")
    texto: Optional[str] = Field(None, description="Texto explicativo ou de apoio")
    origem: Literal["literal", "resumo", "calculado"] = Field(..., description="Origem da extração")
    fontes: List[Fonte] = Field(..., min_length=1, description="Fontes verificadas (mínimo 1)")
    calculo: Optional[str] = Field(None, description="Memória de cálculo quando origem=calculado")


class PrazoAcao(BaseModel):
    data: Optional[str] = Field(None, description="Data limite no formato AAAA-MM-DD")
    regra: Optional[str] = Field(None, description="Regra de prazo descrita no documento")


class Acao(BaseModel):
    id: str = Field(..., description="Identificador da ação")
    acao: str = Field(..., description="Descrição da ação exigida")
    quem: Optional[str] = Field(None, description="Responsável pela ação")
    prazo: Optional[PrazoAcao] = Field(None, description="Prazo estruturado da ação")
    consequencia: Optional[str] = Field(None, description="Consequência do não cumprimento")
    urgencia: Literal["alta", "media", "baixa"] = Field(..., description="Nível de urgência da ação")
    origem: Literal["literal", "resumo", "calculado"] = Field("resumo", description="Origem da extração")
    fontes: List[Fonte] = Field(default_factory=list, description="Fontes verificadas que embasam a ação")


class RelevanciaBloco(BaseModel):
    posicao: int = Field(..., description="Posição de exibição ordinal (começa em 1)")
    motivo: str = Field(..., description="Motivo da relevância em palavras simples")
    pontuacao: float = Field(..., description="Pontuação calculada por regra (0..1)")


class Bloco(BaseModel):
    id: str = Field(..., description="ID do bloco, ex: b-custo")
    titulo: str = Field(..., description="Título do bloco, ex: Quanto custa")
    destaque: str = Field(..., description="Destaque numérico ou frase curta")
    apoio: Optional[str] = Field(None, description="Texto de apoio de até 2 linhas")
    relevancia: RelevanciaBloco = Field(..., description="Relevância calculada por regra")
    sinal: Literal["valor", "prazo", "responsavel", "risco", "regra", "alerta"] = Field(..., description="Tipo de sinal")
    secoes_mapa: List[str] = Field(default_factory=list, description="IDs das seções acesas no mapa")
    itens: List[str] = Field(default_factory=list, description="IDs de ItemFicha/Acao referenciados")
    alerta: Optional[int] = Field(None, description="Índice em alertas[] quando aplicável")


class PontosFicha(BaseModel):
    obrigacoes: List[ItemFicha] = Field(default_factory=list)
    prazos: List[ItemFicha] = Field(default_factory=list)
    valores: List[ItemFicha] = Field(default_factory=list)
    riscos: List[ItemFicha] = Field(default_factory=list)
    responsaveis: List[ItemFicha] = Field(default_factory=list)
    condicoes: List[ItemFicha] = Field(default_factory=list)


class SinaisCelula(BaseModel):
    prazo: int = Field(0, description="Contagem de sinais de prazo")
    valor: int = Field(0, description="Contagem de sinais de valor")
    obrigacao: int = Field(0, description="Contagem de sinais de obrigação")
    risco: int = Field(0, description="Contagem de sinais de risco")


class CelulaMapa(BaseModel):
    secao_id: str = Field(..., description="ID da seção correspondente")
    titulo: str = Field(..., description="Título da seção")
    ordem: int = Field(..., description="Ordem sequencial da seção")
    peso: float = Field(..., description="Peso relativo ao tamanho do texto (0..1)")
    sinais: SinaisCelula = Field(default_factory=SinaisCelula, description="Contagens de sinais por regra")
    intensidade: float = Field(..., description="Intensidade ponderada da célula (0..1)")


class Alerta(BaseModel):
    tipo: Literal["versao_substituida", "referencia_ausente", "divergencia", "vigencia_proxima"] = Field(..., description="Tipo do alerta")
    titulo: str = Field(..., description="Título do alerta")
    explicacao: str = Field(..., description="Explicação detalhada")
    radar_id: Optional[str] = Field(None, description="ID do item no Radar se aplicável")
    fontes: List[Fonte] = Field(default_factory=list, description="Fontes do documento que embasam o alerta")


class Cobertura(BaseModel):
    secoes_lidas: int = Field(..., description="Quantidade de seções processadas")
    secoes_total: int = Field(..., description="Total de seções do documento")
    itens_verificados: int = Field(..., description="Quantidade de itens com fonte verificada")
    itens_descartados: int = Field(0, description="Quantidade de itens descartados por falha na fonte")
    motivos_descarte: List[str] = Field(default_factory=list, description="Motivos dos descartes realizados")


class DeltaFicha(BaseModel):
    de: str = Field(..., description="Versão de origem")
    para: str = Field(..., description="Versão de destino")
    resumo: List[str] = Field(default_factory=list, description="Resumo das mudanças entre as versões")
    mudancas: int = Field(0, description="Quantidade de alterações identificadas")


class FichaDocumento(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(..., description="Código do documento")
    versao: str = Field(..., description="Versão do documento")
    gerada_em: str = Field(..., description="Timestamp ISO 8601 de geração")
    perfil: Optional[str] = Field(None, description="Perfil do usuário se aplicável")
    linguagem: str = Field("original", description="Linguagem: original ou simples")
    estado: Literal["gerando", "parcial", "pronta", "erro"] = Field(..., description="Estado da ficha")
    progresso: Optional[ProgressoFicha] = Field(None, description="Progresso da geração quando gerando/parcial")
    modo: ModoFicha = Field(default_factory=ModoFicha, description="Modo e modelo de IA")
    identidade: Identidade = Field(..., description="Identidade e metadados estruturados")
    semaforo: Semaforo = Field(..., description="Semáforo de atenção")
    governanca: Governanca = Field(..., description="Selos de governança")
    familia: Optional[FamiliaDocumento] = Field(None, description="Família documental")
    blocos: List[Bloco] = Field(default_factory=list, description="Blocos da mesa de decisão")
    bluf: Optional[ItemFicha] = Field(None, description="Resumo BLUF em uma frase")
    numeros: List[ItemFicha] = Field(default_factory=list, description="Números principais (compatibilidade)")
    acoes: List[Acao] = Field(default_factory=list, description="Ações extraídas")
    pontos: PontosFicha = Field(default_factory=PontosFicha, description="Pontos-chave por tema")
    mapa_calor: List[CelulaMapa] = Field(default_factory=list, description="Células do mapa de calor")
    alertas: List[Alerta] = Field(default_factory=list, description="Alertas identificados")
    perguntas_sugeridas: List[str] = Field(default_factory=list, description="Perguntas sugeridas")
    cobertura: Cobertura = Field(..., description="Métricas de cobertura e verificação")
    delta: Optional[DeltaFicha] = Field(None, description="Delta em relação a versão anterior")
