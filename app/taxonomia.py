"""Módulo de taxonomia do Arquivo Central de Normas (ACME).

Deriva camada e tema a partir do catálogo (CATALOGO__INSTRUCOES_SOBRE_O_ACERVO.md, seções 2, 5 e 6).
Especificação: docs/PRD.md, docs/requisitos/REQUISITOS-v2.md, REQUISITOS-v3.md, FLUXO-DE-TELAS-v2.md §7.
Reutilizado por #2, #4, #7, #10, #9.
"""

import re
from typing import Optional, Dict, Tuple, Any
from app.models import Camada, Tema, Fonte, Citacao

# ==============================================================================
# Catálogo Seção 2: Categorias de Documentos e Grupos
# ==============================================================================

CATEGORIAS_CATALOGO: Dict[str, Tuple[str, str]] = {
    "NG": ("Norma Geral", "Normativo"),
    "PX": ("Procedimento", "Normativo"),
    "PP": ("Padrão Operacional", "Operacional"),
    "GU": ("Guia", "Apoio"),
    "FM": ("Formulário", "Apoio"),
    "TB": ("Tabela", "Apoio"),
    "FL": ("Fluxo", "Apoio"),
    "RG": ("Regulamento de Programa", "Programa"),
    "CT": ("Comunicado Temporário", "Temporário"),
    "DV": ("Documento Diverso", "Residual"),
    "CTR": ("Contrato", "Instrumento"),
    "NT": ("Nota Técnica", "Instrumento"),
}

TIPO_NOME_PARA_SIGLA: Dict[str, str] = {
    "norma geral": "NG",
    "procedimento": "PX",
    "padrão operacional": "PP",
    "padrao operacional": "PP",
    "guia": "GU",
    "formulário": "FM",
    "formulario": "FM",
    "formulário de solicitação de férias": "FM",
    "tabela": "TB",
    "tabelas": "TB",
    "fluxo": "FL",
    "fluxograma": "FL",
    "regulamento de programa": "RG",
    "regulamento do programa": "RG",
    "comunicado temporário": "CT",
    "comunicado temporario": "CT",
    "documento diverso": "DV",
    "contrato": "CTR",
    "contrato de locação": "CTR",
    "contrato de locação de espaço": "CTR",
    "nota técnica": "NT",
    "nota tecnica": "NT",
}

# Subordinação direta conhecida no acervo padrão
SUBORDINACAO_ACERVO: Dict[str, str] = {
    "FL_1111-001": "PX_1111-001",
    "FM_1111-001": "NG_111",
    "PX_1111-001": "NG_111",
    "TB_1111-001": "NG_111",
    "PX_1130-001": "NG_1130",
    "RG_1100": "NG_1130",
}

# ==============================================================================
# Catálogo Seção 5: Séries de Numeração
# ==============================================================================

SERIES_CATALOGO: Dict[int, str] = {
    0: "Estratégia e Planejamento",
    1: "Gente e Cultura",
    2: "Finanças e Contabilidade",
    3: "Operações de Campo",
    4: "Compras e Contratos",
    5: "Relacionamento com Clientes",
    6: "Tecnologia da Informação",
    7: "Assuntos Jurídicos",
    8: "Auditoria",
    9: "Riscos e Conformidade",
    11: "Programas Institucionais",
    12: "Segurança da Informação",
    14: "Parcerias e Canais Externos",
}

FAIXAS_SERIES = [
    (0, 99, 0, "Estratégia e Planejamento"),
    (100, 199, 1, "Gente e Cultura"),
    (200, 299, 2, "Finanças e Contabilidade"),
    (300, 399, 3, "Operações de Campo"),
    (400, 499, 4, "Compras e Contratos"),
    (500, 599, 5, "Relacionamento com Clientes"),
    (600, 699, 6, "Tecnologia da Informação"),
    (700, 799, 7, "Assuntos Jurídicos"),
    (800, 899, 8, "Auditoria"),
    (900, 999, 9, "Riscos e Conformidade"),
    (1100, 1199, 11, "Programas Institucionais"),
    (1200, 1299, 12, "Segurança da Informação"),
    (1400, 1899, 14, "Parcerias e Canais Externos"),
]


def inferir_norma_raiz(codigo: str, vinculado_a: Optional[str] = None) -> Optional[str]:
    """Descobre a norma geral (NG) ou raiz à qual o documento se conecta."""
    if vinculado_a and vinculado_a.strip():
        v = vinculado_a.strip()
        if v.startswith("NG_"):
            return v
        if v in SUBORDINACAO_ACERVO:
            return inferir_norma_raiz(v, SUBORDINACAO_ACERVO[v])

    clean = (codigo or "").strip()
    if clean.startswith("NG_"):
        return clean
    if clean in SUBORDINACAO_ACERVO:
        return inferir_norma_raiz(clean, SUBORDINACAO_ACERVO[clean])

    # Tentar inferir de padrões como PX_1111-001 -> NG_111
    m = re.match(r"^[A-Z]{2}_(\d+)(?:-\d+)?$", clean)
    if m:
        num_str = m.group(1)
        # Se for 4 dígitos terminando com sequencial de processo (ex: 1111 -> 111)
        if len(num_str) == 4 and num_str.startswith("111"):
            return "NG_111"
        if len(num_str) == 4 and num_str == "1130":
            return "NG_1130"
        return f"NG_{num_str}"

    return None


def derivar_camada(
    codigo: str,
    tipo_nome: Optional[str] = None,
    vinculado_a: Optional[str] = None,
) -> Camada:
    """Deriva o objeto camada = {sigla, tipo_nome, grupo, subordinado_a} a partir do catálogo.

    Grupos do catálogo:
    - Normativo: NG, PX
    - Operacional: PP
    - Apoio: GU, FM, TB, FL
    - Programa: RG
    - Temporário: CT
    - Instrumento: CTR, NT
    - Residual: DV

    subordinado_a = pai direto pelo campo 'Vinculado a' (ex.: FL_1111-001 → PX_1111-001).
    """
    codigo_clean = (codigo or "").strip()

    # 1. Identificar sigla
    sigla = None
    if "_" in codigo_clean:
        cand = codigo_clean.split("_")[0].upper()
        if cand in CATEGORIAS_CATALOGO:
            sigla = cand

    if not sigla and tipo_nome:
        sigla = TIPO_NOME_PARA_SIGLA.get(tipo_nome.strip().lower())

    if not sigla:
        sigla = codigo_clean.split("_")[0].upper() if "_" in codigo_clean else "DV"

    # 2. Obter nome padrão e grupo do catálogo
    tipo_padrao, grupo_padrao = CATEGORIAS_CATALOGO.get(
        sigla, ("Documento Diverso", "Residual")
    )
    final_tipo_nome = tipo_padrao

    # 3. Determinar pai direto (subordinado_a)
    subordinado_a: Optional[str] = None
    if vinculado_a and vinculado_a.strip():
        subordinado_a = vinculado_a.strip()
    elif codigo_clean in SUBORDINACAO_ACERVO:
        subordinado_a = SUBORDINACAO_ACERVO[codigo_clean]
    elif sigla in ("PX", "PP", "GU", "FM", "TB", "FL", "DV"):
        raiz = inferir_norma_raiz(codigo_clean)
        if raiz and raiz != codigo_clean:
            subordinado_a = raiz

    # Documentos que são raiz por natureza e não têm pai
    if sigla in ("NG", "CTR", "NT", "CT") and not vinculado_a:
        subordinado_a = None

    return Camada(
        sigla=sigla,
        tipo_nome=final_tipo_nome,
        grupo=grupo_padrao,
        subordinado_a=subordinado_a,
    )


def derivar_tema(
    codigo: str,
    assunto: str = "",
    vinculado_a: Optional[str] = None,
    referencia: Optional[str] = None,
) -> Tema:
    """Deriva o objeto tema = {assunto, serie, serie_nome, confirmado_por: 'regra'}.

    - assunto = pasta (ferias, inovacao, locacao)
    - série pela faixa de numeração do catálogo §5
    - quando o catálogo não define a série (ex.: NG_1130), serie = null com observacao
    """
    codigo_clean = (codigo or "").strip()
    final_assunto = (assunto or "").strip().lower()

    # Se assunto não veio preenchido, deduzir do acervo conhecido
    if not final_assunto:
        if any(k in codigo_clean for k in ("111", "FERIAS")):
            final_assunto = "ferias"
        elif any(k in codigo_clean for k in ("1130", "1100", "021")):
            final_assunto = "inovacao"
        elif any(k in codigo_clean for k in ("012", "018", "COWORKING")):
            final_assunto = "locacao"
        else:
            final_assunto = "geral"

    # Caso especial: RG_1100
    # Conforme Catálogo §2: "o número vem da série do assunto (RG_1100 na Série 11)"
    # Não herda de NG_1130
    if codigo_clean.startswith("RG_1100") or codigo_clean == "RG_1100":
        return Tema(
            assunto=final_assunto,
            serie=11,
            serie_nome=SERIES_CATALOGO.get(11, "Programas Institucionais"),
            confirmado_por="regra",
            observacao=None,
        )

    # Caso especial: NG_1130 e documentos vinculados a ela (ex: PX_1130-001)
    # Conforme PRD e REQUISITOS-v3.md L-f e a issue 13:
    # "quando o catálogo não define a série (ex.: NG_1130), serie = null com observacao."
    if codigo_clean == "NG_1130":
        return Tema(
            assunto=final_assunto,
            serie=None,
            serie_nome=None,
            confirmado_por="regra",
            observacao="Catálogo §5 não define explicitamente a série para NG_1130 (lacuna L-f)",
        )

    if vinculado_a == "NG_1130" or codigo_clean == "PX_1130-001":
        return Tema(
            assunto=final_assunto,
            serie=None,
            serie_nome=None,
            confirmado_por="regra",
            observacao="Documento subordinado a NG_1130 (sem série definida no Catálogo §5)",
        )

    # Instrumentos e comunicados com numeração própria (ano e sequencial)
    if (
        codigo_clean.startswith("CTR_")
        or codigo_clean.startswith("NT_")
        or codigo_clean.startswith("CT_")
    ):
        return Tema(
            assunto=final_assunto,
            serie=None,
            serie_nome=None,
            confirmado_por="regra",
            observacao="Documento com numeração própria (ano/sequencial), sem série no catálogo",
        )

    # Buscar raiz para determinar a faixa de série
    norma_raiz = inferir_norma_raiz(codigo_clean, vinculado_a)
    numero_norma = None

    if norma_raiz:
        m = re.search(r"NG_(\d+)", norma_raiz)
        if m:
            numero_norma = int(m.group(1))
    else:
        m = re.search(r"\d+", codigo_clean)
        if m:
            numero_norma = int(m.group(0))

    if numero_norma is not None:
        for min_num, max_num, s_num, s_nome in FAIXAS_SERIES:
            if min_num <= numero_norma <= max_num:
                return Tema(
                    assunto=final_assunto,
                    serie=s_num,
                    serie_nome=s_nome,
                    confirmado_por="regra",
                    observacao=None,
                )

    # Se não couber em nenhuma faixa do catálogo
    return Tema(
        assunto=final_assunto,
        serie=None,
        serie_nome=None,
        confirmado_por="regra",
        observacao=f"Número {numero_norma} fora das faixas do catálogo §5",
    )


def obter_camada(
    codigo: str,
    tipo_nome: Optional[str] = None,
    vinculado_a: Optional[str] = None,
) -> Camada:
    """Atalho para derivar_camada."""
    return derivar_camada(codigo, tipo_nome=tipo_nome, vinculado_a=vinculado_a)


def obter_tema(
    codigo: str,
    assunto: str = "",
    vinculado_a: Optional[str] = None,
    referencia: Optional[str] = None,
) -> Tema:
    """Atalho para derivar_tema."""
    return derivar_tema(
        codigo, assunto=assunto, vinculado_a=vinculado_a, referencia=referencia
    )


def formatar_camada(camada: Camada, formato: str = "completo") -> str:
    """Formata o selo de camada da norma para exibição.

    - formato='completo' (web/T8/relatório): 'SIGLA · Tipo · Grupo · subordinado a PAI'
      Exemplo: 'PX · Procedimento · Normativo · subordinado a NG_111'
      Exemplo: 'CTR · Contrato · Instrumento'
    - formato='curto' (canais C0/Slack/Teams): 'SIGLA · Grupo'
      Exemplo: 'PX · Normativo'
      Exemplo: 'CTR · Instrumento'
    """
    if formato == "curto":
        return f"{camada.sigla} · {camada.grupo}"
    return camada.rotulo(completo=True)


def enriquecer_citacao(citacao: Any) -> Any:
    """Enriquece uma citação ou fonte com sua camada derivada do catálogo.

    Suporta instâncias de Citacao, Fonte ou dicts contendo a chave 'codigo'.
    """
    if isinstance(citacao, dict):
        codigo = citacao.get("codigo", "")
        camada = derivar_camada(codigo)
        citacao["camada"] = camada.model_dump()
        return citacao
    elif isinstance(citacao, (Citacao, Fonte)):
        if citacao.camada is None:
            citacao.camada = derivar_camada(citacao.codigo)
        return citacao
    return citacao


def enriquecer_fonte(fonte: Any) -> Any:
    """Enriquece um objeto de fonte com a camada correspondente."""
    return enriquecer_citacao(fonte)
