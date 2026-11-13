"""Extração determinística de metadados e governança do documento (sem IA).

Implementa os requisitos RF45, RF46 e RF54 (Issue #45, F-01).
Lê governança, identidade, classificação de segurança (#interna), vigência e métricas.
"""

import os
import re
import math
from datetime import date, datetime
from typing import Optional, List, Union, Tuple, Any

from app.models import DocumentoDetalhe
from app.taxonomia import SUBORDINACAO_ACERVO
from app.ficha.modelos import (
    FonteGov,
    CampoGov,
    Governanca,
    VigenciaFicha,
    Metricas,
    VigenteEm,
    Identidade,
    Semaforo,
    FamiliaDocumento,
)

CODIGO_RE = re.compile(r"\b(?:NG|PX|PP|GU|FM|TB|FL|RG|CT|DV|CTR|NT)_[0-9]+(?:-[0-9]+)?\b")
DATA_INTERVALO_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:a|até|-)\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
DATA_ATE_RE = re.compile(r"até\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
DATA_SIMPLES_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")


def obter_data_referencia(data_ref: Optional[Union[date, str]] = None) -> date:
    """Obtém a data de referência para cálculo de dias_restantes.

    Prioridade: argumento explícito > variável DATA_REFERENCIA > data atual.
    """
    if isinstance(data_ref, date):
        return data_ref
    if isinstance(data_ref, str) and data_ref.strip():
        s = data_ref.strip()
        if "-" in s:
            return date.fromisoformat(s)
        dt = datetime.strptime(s, "%d/%m/%Y")
        return dt.date()

    env_val = os.getenv("DATA_REFERENCIA")
    if env_val and env_val.strip():
        s = env_val.strip()
        if "-" in s:
            return date.fromisoformat(s)
        dt = datetime.strptime(s, "%d/%m/%Y")
        return dt.date()

    return date.today()


def _converter_data_br_para_iso(data_br: str) -> str:
    """Converte 'DD/MM/AAAA' para 'AAAA-MM-DD'."""
    partes = data_br.strip().split("/")
    if len(partes) == 3:
        d, m, y = partes
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return data_br


def extrair_classificacao(header_text: Optional[str]) -> Optional[str]:
    """Extrai a classificação a partir de linhas com hashtag (#interna, #publica, etc.)."""
    if not header_text:
        return None
    for line in header_text.splitlines():
        line_s = line.strip()
        if line_s.startswith("#"):
            tag = line_s.lstrip("#").strip().lower()
            if tag:
                return tag
    return None


def extrair_vigencia(
    texto_vigencia: Optional[str],
    data_referencia: Optional[Union[date, str]] = None,
) -> VigenciaFicha:
    """Extrai dados estruturados de vigência a partir do texto do cabeçalho.

    Gera inicio, fim e dias_restantes em relação à data de referência.
    """
    if not texto_vigencia or not texto_vigencia.strip():
        return VigenciaFicha(texto="", inicio=None, fim=None, dias_restantes=None)

    texto = texto_vigencia.strip()
    inicio: Optional[str] = None
    fim: Optional[str] = None

    m_range = DATA_INTERVALO_RE.search(texto)
    if m_range:
        inicio = _converter_data_br_para_iso(m_range.group(1))
        fim = _converter_data_br_para_iso(m_range.group(2))
    else:
        m_ate = DATA_ATE_RE.search(texto)
        if m_ate:
            fim = _converter_data_br_para_iso(m_ate.group(1))
        else:
            m_data = DATA_SIMPLES_RE.search(texto)
            if m_data:
                inicio = _converter_data_br_para_iso(m_data.group(1))

    dias_restantes: Optional[int] = None
    if fim:
        try:
            fim_date = date.fromisoformat(fim)
            ref_date = obter_data_referencia(data_referencia)
            dias_restantes = (fim_date - ref_date).days
        except Exception:
            dias_restantes = None

    return VigenciaFicha(
        texto=texto,
        inicio=inicio,
        fim=fim,
        dias_restantes=dias_restantes,
    )


def extrair_metricas(doc: DocumentoDetalhe) -> Metricas:
    """Calcula métricas de dimensão e estimativa de leitura do documento (RF54).

    - paginas_estimadas = palavras/400 (arredondado para cima)
    - leitura_integral_min = palavras/200
    - leitura_ficha_min = 3 (tempo padrão para ficha condensada)
    """
    secoes_qtd = len(doc.secoes)
    palavras_qtd = sum(len(f"{s.titulo} {s.texto}".split()) for s in doc.secoes)

    if palavras_qtd > 0:
        paginas_estimadas = math.ceil(palavras_qtd / 400)
        leitura_integral_min = max(1, round(palavras_qtd / 200))
    else:
        paginas_estimadas = 0
        leitura_integral_min = 0

    return Metricas(
        secoes=secoes_qtd,
        palavras=palavras_qtd,
        paginas_estimadas=paginas_estimadas,
        leitura_integral_min=leitura_integral_min,
        leitura_ficha_min=3,
    )


def obter_cadeia_subordinacao(
    codigo: str,
    vinculado_a: Optional[str] = None,
    acervo: Optional[Any] = None,
) -> List[str]:
    """Reconstrói a cadeia de subordinação completa até a norma raiz."""
    cadeia = [codigo]
    curr_vinculo = (vinculado_a or "").strip() or SUBORDINACAO_ACERVO.get(codigo)
    visitados = {codigo}

    while curr_vinculo and curr_vinculo not in visitados:
        cadeia.append(curr_vinculo)
        visitados.add(curr_vinculo)
        prox_vinculo = None
        if acervo is not None:
            doc_pai = acervo.buscar(curr_vinculo)
            if doc_pai and doc_pai.vinculado_a:
                prox_vinculo = doc_pai.vinculado_a.strip()
        if not prox_vinculo:
            prox_vinculo = SUBORDINACAO_ACERVO.get(curr_vinculo)
        curr_vinculo = prox_vinculo

    return cadeia


def extrair_referencias(doc: DocumentoDetalhe) -> List[str]:
    """Identifica códigos de normas referenciadas preservando a ordem de aparição."""
    referencias: List[str] = []
    vistos = {doc.codigo}
    if doc.vinculado_a:
        vistos.add(doc.vinculado_a.strip())

    if doc.referencia:
        for cod in CODIGO_RE.findall(doc.referencia):
            if cod not in vistos:
                referencias.append(cod)
                vistos.add(cod)

    for secao in doc.secoes:
        for cod in CODIGO_RE.findall(f"{secao.titulo} {secao.texto}"):
            if cod not in vistos:
                referencias.append(cod)
                vistos.add(cod)

    return referencias


def extrair_governanca(
    doc: DocumentoDetalhe,
    header_text: Optional[str] = None,
    acervo: Optional[Any] = None,
) -> Governanca:
    """Extrai os selos de governança do cabeçalho por regra, sem IA (RF46).

    Campos ausentes recebem valor: null e fonte: null (nunca inventados).
    """
    def _montar_campo(campo_nome: str, valor: Optional[str]) -> CampoGov:
        if valor and valor.strip():
            val_limpo = valor.strip()
            return CampoGov(
                valor=val_limpo,
                fonte=FonteGov(campo=campo_nome, trecho=f"{campo_nome}: {val_limpo}"),
            )
        return CampoGov(valor=None, fonte=None)

    elaborado_por = _montar_campo("Elaborado por", doc.elaborado_por)
    aprovado_por = _montar_campo("Aprovado por", doc.aprovado_por)
    aprovado_em = _montar_campo("Aprovado em", getattr(doc, "aprovado_em", None))
    assinada_em = _montar_campo("Assinada em", getattr(doc, "assinada_em", None))
    vinculado_a = _montar_campo("Vinculado a", doc.vinculado_a)

    referencias = extrair_referencias(doc)
    cadeia = obter_cadeia_subordinacao(doc.codigo, doc.vinculado_a, acervo=acervo)

    return Governanca(
        elaborado_por=elaborado_por,
        aprovado_por=aprovado_por,
        aprovado_em=aprovado_em,
        assinada_em=assinada_em,
        vinculado_a=vinculado_a,
        referencias=referencias,
        cadeia=cadeia,
    )


from app.ficha.familias import derivar_familia


def gerar_semaforo_base(
    doc: DocumentoDetalhe,
    vigencia: Optional[VigenciaFicha] = None,
) -> Semaforo:
    """Calcula o semáforo base determinístico do documento."""
    motivos: List[str] = []
    nivel: str = "ok"

    if doc.substituido:
        nivel = "critico"
        motivos.append(f"Documento em versão anterior/substituída ({doc.versao})")

    if vigencia and vigencia.dias_restantes is not None:
        dias = vigencia.dias_restantes
        if dias < 0:
            nivel = "critico"
            motivos.append(f"Vigência encerrada há {abs(dias)} dias")
        elif dias <= 7:
            nivel = "critico"
            motivos.append(f"Vigência encerra em {dias} dias")
        elif dias <= 30:
            if nivel != "critico":
                nivel = "atencao"
            motivos.append(f"Vigência encerra em {dias} dias")
        elif dias <= 60:
            if nivel != "critico":
                nivel = "atencao"
            motivos.append(f"Vigência encerra em {dias} dias")

    if not motivos:
        nivel = "ok"
        motivos.append("Documento vigente e sem pendências cadastrais")

    return Semaforo(nivel=nivel, motivos=motivos)  # type: ignore[arg-type]


def extrair_identidade(
    doc: DocumentoDetalhe,
    header_text: Optional[str] = None,
    data_referencia: Optional[Union[date, str]] = None,
    acervo: Optional[Any] = None,
) -> Identidade:
    """Extrai a identidade completa e estruturada do documento (RF45)."""
    vigencia = extrair_vigencia(doc.vigencia, data_referencia=data_referencia)
    metricas = extrair_metricas(doc)

    classificacao = getattr(doc, "classificacao", None)
    if not classificacao:
        classificacao = extrair_classificacao(header_text or getattr(doc, "header_raw", None))

    vigente_em: Optional[VigenteEm] = None
    if doc.substituido and acervo is not None:
        doc_vigente = acervo.buscar(doc.codigo)
        if doc_vigente and doc_vigente.versao != doc.versao:
            vigente_em = VigenteEm(codigo=doc_vigente.codigo, versao=doc_vigente.versao)

    return Identidade(
        titulo=doc.titulo,
        tipo=doc.tipo,
        tipo_nome=doc.tipo_nome,
        camada=doc.camada,
        tema=doc.tema,
        fase=doc.fase,
        substituido=doc.substituido,
        vigente_em=vigente_em,
        vigencia=vigencia,
        origem=doc.origem or "acervo",
        classificacao=classificacao,
        metricas=metricas,
    )


def extrair_metadados_documento(
    doc: DocumentoDetalhe,
    header_text: Optional[str] = None,
    data_referencia: Optional[Union[date, str]] = None,
    acervo: Optional[Any] = None,
) -> Tuple[Identidade, Governanca, Semaforo, FamiliaDocumento]:
    """Função utilitária que extrai toda a camada determinística de metadados."""
    identidade = extrair_identidade(
        doc,
        header_text=header_text,
        data_referencia=data_referencia,
        acervo=acervo,
    )
    governanca = extrair_governanca(
        doc,
        header_text=header_text,
        acervo=acervo,
    )
    semaforo = gerar_semaforo_base(doc, vigencia=identidade.vigencia)
    familia = derivar_familia(doc)

    return identidade, governanca, semaforo, familia
