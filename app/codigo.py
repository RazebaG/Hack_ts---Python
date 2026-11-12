"""Módulo decodificador de código de documento do Arquivo Central de Normas (ACME).

Decodifica a estrutura de códigos conforme o Catálogo (CATALOGO__INSTRUCOES_SOBRE_O_ACERVO.md, seções 2, 3 e 5).
Regras do catálogo:
- Siglas e categorias (12 categorias + documentos fundacionais)
- Herança de número (NG_111 gera PX_1111-001)
- Séries 0–14 por faixa de numeração
- Vigências por categoria documental
- Formatos próprios de CT, CTR e NT
- Resolução de ambiguidade com suporte do acervo
- Inclusão dos objetos camada e tema (C15, C17, Issue #13)

Especificação: docs/CONTRATO-API.md, docs/PRD.md, docs/requisitos/REQUISITOS-v2.md (RF16), Issue #3.
"""

import re
from typing import Optional, Dict, Tuple

from app.models import Camada, Tema, CodigoDecodificado
from app.taxonomia import (
    CATEGORIAS_CATALOGO,
    SERIES_CATALOGO,
    FAIXAS_SERIES,
    derivar_camada,
    derivar_tema,
    inferir_norma_raiz,
)
from app.acervo import AcervoRepository


# Vigências por categoria documental (Catálogo §2 e §6)
VIGENCIA_REGRAS: Dict[str, str] = {
    "NG": "18 meses a partir da aprovação",
    "PX": "18 meses a partir da aprovação",
    "GU": "18 meses a partir da aprovação",
    "CT": "No máximo 150 dias",
    "RG": "Por edição do programa",
    "CTR": "A do próprio instrumento",
    "NT": "Vale para a decisão a que se refere",
    "PP": "Revisão conforme a necessidade",
    "FM": "Revisão conforme a necessidade",
    "TB": "Revisão conforme a necessidade",
    "FL": "Revisão conforme a necessidade",
    "DV": "Revisão conforme a necessidade",
    "CAS": "Revisão conforme a necessidade",
    "RCA": "Revisão conforme a necessidade",
}


CATEGORIAS_COMPLETAS: Dict[str, Tuple[str, str]] = {
    **CATEGORIAS_CATALOGO,
    "CAS": ("Carta Social", "Fundacional"),
    "RCA": ("Regimento do Conselho e da Diretoria", "Fundacional"),
}


def extrair_sigla(codigo: str) -> Optional[str]:
    """Extrai a sigla da categoria a partir do código do documento."""
    clean = (codigo or "").strip()
    if not clean:
        return None

    up = clean.upper()
    if up in CATEGORIAS_COMPLETAS:
        return up

    # Formatos especiais de instrumentos / comunicados
    if re.match(r"^CTR[_\s\-–—]", clean, re.IGNORECASE):
        return "CTR"
    if re.match(r"^NT[_\s\-–—]", clean, re.IGNORECASE):
        return "NT"
    if re.match(r"^CT[_\s\-–—]", clean, re.IGNORECASE):
        return "CT"

    # Padrão canônico com sublinhado ou separador: SIGLA_...
    m = re.match(r"^([A-Za-z]{2,3})[_\s\-–—]", clean)
    if m:
        cand = m.group(1).upper()
        if cand in CATEGORIAS_COMPLETAS:
            return cand

    return None



def buscar_no_acervo(codigo: str, acervo: Optional[AcervoRepository]):
    """Busca o documento no acervo, aceitando variações de caixa e separadores."""
    if not acervo:
        return None

    # 1. Busca exata
    doc = acervo.buscar(codigo)
    if doc:
        return doc

    # 2. Busca em caixa alta
    up = codigo.strip().upper()
    doc = acervo.buscar(up)
    if doc:
        return doc

    # 3. Busca normalizada por separadores (espaços, traços, sublinhados)
    codigo_norm = re.sub(r"[\s\-_–—]+", "", up)
    for d in acervo.documentos:
        d_norm = re.sub(r"[\s\-_–—]+", "", d.codigo.upper())
        if d_norm == codigo_norm:
            return d

    return None


def detectar_ambiguidade(
    codigo: str, sigla: str, doc_vinculado_a: Optional[str]
) -> Optional[str]:
    """Detecta se o número do código é ambíguo conforme Catálogo §3.

    Exemplo clássico do Catálogo §3: PX_1111-001 tem número 1111, que pode indicar:
    - NG_111 (Série 1 · Gente e Cultura) com sequencial de processo 1
    - NG_1111 (Série 11 · Programas Institucionais)
    """
    m = re.search(r"(\d{4})", codigo)
    if not m:
        return None

    num_str = m.group(1)
    if num_str == "1111" or (
        num_str.startswith("111")
        and sigla in ("PX", "PP", "GU", "FM", "TB", "FL", "DV")
    ):
        if doc_vinculado_a:
            return (
                f"Número ambíguo: {num_str} pode referenciar NG_111 (Série 1 · Gente e Cultura) "
                f"ou NG_1111 (Série 11 · Programas Institucionais); confirmado no acervo como vinculado a {doc_vinculado_a}."
            )
        else:
            return (
                f"Número ambíguo: {num_str} pode referenciar NG_111 (Série 1 · Gente e Cultura) "
                f"ou NG_1111 (Série 11 · Programas Institucionais); confirme no campo vinculado_a do cabeçalho."
            )

    return None


def decodificar_codigo(
    codigo: str, acervo: Optional[AcervoRepository] = None
) -> CodigoDecodificado:
    """Decodifica a estrutura de um código de documento do acervo da ACME.

    Retorna tipo, tipo_nome, vinculado_a, serie, serie_nome, vigencia_regra,
    existe_no_acervo, observacao, camada e tema.
    """
    codigo_original = (codigo or "").strip()
    doc = buscar_no_acervo(codigo_original, acervo)
    existe_no_acervo = doc is not None

    sigla = None
    if doc:
        sigla = doc.tipo
    if not sigla:
        sigla = extrair_sigla(codigo_original)

    # Caso 1: Sigla não reconhecida e documento inexistente no acervo
    if not sigla and not existe_no_acervo:
        return CodigoDecodificado(
            codigo=codigo_original,
            tipo=None,
            tipo_nome=None,
            vinculado_a=None,
            serie=None,
            serie_nome=None,
            vigencia_regra=None,
            existe_no_acervo=False,
            observacao="Código não reconhecido pelo catálogo e não encontrado no acervo.",
            camada=None,
            tema=None,
        )

    # Sigla reconhecida
    tipo_padrao, grupo_padrao = CATEGORIAS_COMPLETAS.get(
        sigla, ("Documento Diverso", "Residual")
    )
    tipo_nome = tipo_padrao
    vigencia_regra = VIGENCIA_REGRAS.get(sigla, "Revisão conforme a necessidade")

    # Determinar vinculado_a
    vinculado_a: Optional[str] = None
    if doc and doc.vinculado_a:
        vinculado_a = doc.vinculado_a
    elif not doc:
        if sigla in ("PX", "PP", "GU", "FM", "TB", "FL", "DV"):
            vinculado_a = inferir_norma_raiz(codigo_original)
        else:
            vinculado_a = None

    # Detectar ambiguidade no número
    obs_ambiguidade = detectar_ambiguidade(codigo_original, sigla, vinculado_a)

    # Determinar camada
    if doc:
        camada = doc.camada
    else:
        camada = derivar_camada(
            codigo_original, tipo_nome=tipo_nome, vinculado_a=vinculado_a
        )

    # Determinar tema, série, serie_nome e observação
    serie: Optional[str] = None
    serie_nome: Optional[str] = None
    observacao: Optional[str] = None
    tema: Optional[Tema] = None

    # Tratamento por categoria específica do Catálogo
    if sigla in ("CTR", "NT"):
        # Contratos e notas técnicas têm numeração própria (ano/sequencial), sem série
        tema = doc.tema if doc else derivar_tema(codigo_original, vinculado_a=vinculado_a)
        serie = None
        serie_nome = None
        observacao = (
            "Documento com numeração própria (ano/sequencial), sem série no catálogo"
        )

    elif sigla == "CT":
        # Comunicados temporários têm formato próprio (diretoria/ano/sequencial)
        serie = None
        serie_nome = None
        if existe_no_acervo:
            observacao = (
                "Documento com numeração própria (diretoria/ano/sequencial), sem série no catálogo"
            )
        else:
            observacao = (
                "Documento do acervo anterior com numeração própria (diretoria/ano/sequencial), "
                "sem série no catálogo"
            )
        tema = Tema(
            assunto="geral",
            serie=None,
            serie_nome=None,
            confirmado_por="regra",
            observacao=observacao,
        )

    elif sigla == "RG":
        # Regulamento de programa: número vem da série do assunto (RG_1100 -> Série 11)
        tema = doc.tema if doc else derivar_tema(codigo_original, vinculado_a=vinculado_a)
        serie = str(tema.serie) if tema.serie is not None else "11"
        serie_nome = tema.serie_nome or "Programas Institucionais"
        observacao = (
            "Não herda número de NG: o número vem da série do assunto (Série 11 · Programas Institucionais)"
        )

    elif codigo_original in ("NG_1130", "PX_1130-001") or vinculado_a == "NG_1130":
        # Caso especial NG_1130 (lacuna L-f)
        tema = doc.tema if doc else derivar_tema(codigo_original, vinculado_a=vinculado_a)
        serie = None
        serie_nome = None
        if codigo_original == "NG_1130":
            observacao = (
                "Catálogo §5 não define explicitamente a série para NG_1130 (lacuna L-f)"
            )
        else:
            observacao = (
                "Documento subordinado a NG_1130 (sem série definida no Catálogo §5)"
            )

    else:
        # Casos gerais (NG, PX, PP, GU, FM, TB, FL, DV)
        if doc:
            tema = doc.tema
            serie = str(tema.serie) if tema.serie is not None else None
            serie_nome = tema.serie_nome
            observacao = obs_ambiguidade or tema.observacao
        else:
            tema = derivar_tema(codigo_original, vinculado_a=vinculado_a)
            serie = str(tema.serie) if tema.serie is not None else None
            serie_nome = tema.serie_nome
            observacao = (
                obs_ambiguidade
                or tema.observacao
                or ("Documento não cadastrado no acervo." if not existe_no_acervo else None)
            )

    return CodigoDecodificado(
        codigo=codigo_original,
        tipo=sigla,
        tipo_nome=tipo_nome,
        vinculado_a=vinculado_a,
        serie=serie,
        serie_nome=serie_nome,
        vigencia_regra=vigencia_regra,
        existe_no_acervo=existe_no_acervo,
        observacao=observacao,
        camada=camada,
        tema=tema,
    )
