"""Verificador determinístico de fontes e cobertura da Ficha do Documento.

Implementa os requisitos RF51 e RF52 (Issue #46, F-03/F-05).
Reutiliza trecho_consta_na_secao de app.inteligencia.
Garante RNF20 (nada sem fonte verificada) e RNF21 (funciona sem Bedrock).
Descarta itens não verificados e registra a contagem em Cobertura sem expor texto nos motivos.
"""

from typing import List, Dict, Tuple, Optional, Union, Any, Set
from app.models import DocumentoDetalhe, Secao, Fonte
from app.ficha.modelos import ItemFicha, Cobertura, PontosFicha
from app.ficha.candidatos import extrair_candidatos, extrair_pontos_candidatos
from app.inteligencia import _tokens, trecho_consta_na_secao


def _verificar_trecho_tabela(trecho: str, texto_secao: str) -> bool:
    """Normaliza quebras de linha e separadores (|) antes de comparar trechos de tabela."""
    t_trecho = _tokens(trecho.replace("|", " ").replace("\n", " "))
    t_secao = _tokens(texto_secao.replace("|", " ").replace("\n", " "))
    if not t_trecho or not t_secao:
        return False
    return set(t_trecho) <= set(t_secao)


def _verificar_operandos_calculo(
    calculo: Optional[str],
    fontes: List[Fonte],
    doc: DocumentoDetalhe,
) -> bool:
    """Confere se os operandos da memória de cálculo constam nas fontes declaradas."""
    if not calculo or not calculo.strip():
        return False

    secoes_por_id: Dict[str, List[Secao]] = {}
    for s in doc.secoes:
        secoes_por_id.setdefault(s.id, []).append(s)

    tokens_fontes: Set[str] = set()
    for f in fontes:
        for s in secoes_por_id.get(f.secao, []):
            tokens_fontes.update(_tokens(s.texto))
        tokens_fontes.update(_tokens(f.trecho))

    tokens_calc = _tokens(calculo)
    if not tokens_calc:
        return False

    conectivos_ignorados = {"x", "de", "do", "da", "em", "para", "por", "mes", "meses", "dias", "ano", "anos"}
    for tok in tokens_calc:
        if tok not in conectivos_ignorados:
            if tok not in tokens_fontes:
                return False

    return True


def verificar_item(item: ItemFicha, doc: DocumentoDetalhe) -> Tuple[bool, Optional[str]]:
    """Verifica se um item da ficha possui todas as suas fontes comprovadas no documento.
    
    Retorna (True, None) em caso de sucesso.
    Em caso de reprovação, retorna (False, motivo) sem incluir o texto do documento no motivo.
    """
    if not item.fontes:
        return False, f"Item {item.id}: nenhuma fonte informada"

    secoes_por_id: Dict[str, List[Secao]] = {}
    for s in doc.secoes:
        secoes_por_id.setdefault(s.id, []).append(s)

    for idx, fonte in enumerate(item.fontes):
        # Validação de seção
        secoes_candidatas = secoes_por_id.get(fonte.secao)
        if not secoes_candidatas:
            return (
                False,
                f"Item {item.id}: seção '{fonte.secao}' não encontrada no documento {doc.codigo}",
            )

        # Verificação do trecho contra as seções correspondentes
        consta = any(
            trecho_consta_na_secao(fonte.trecho, secao.texto)
            or _verificar_trecho_tabela(fonte.trecho, secao.texto)
            for secao in secoes_candidatas
        )

        if not consta:
            return (
                False,
                f"Item {item.id}: trecho não consta na seção '{fonte.secao}'",
            )

    # Verificação de itens calculados
    if item.origem == "calculado":
        if not item.calculo:
            return (
                False,
                f"Item {item.id}: item com origem 'calculado' sem memória de cálculo declarada",
            )
        if not _verificar_operandos_calculo(item.calculo, item.fontes, doc):
            return (
                False,
                f"Item {item.id}: operando do cálculo não verificado nas fontes",
            )

    return True, None


def verificar_candidatos(
    candidatos: Union[Dict[str, List[ItemFicha]], PontosFicha, List[ItemFicha]],
    doc: DocumentoDetalhe,
) -> Tuple[Dict[str, List[ItemFicha]], Cobertura]:
    """Verifica uma coleção de candidatos contra as seções do documento.
    
    Descarta qualquer candidato não verificado e preenche o objeto Cobertura.
    """
    secoes_total = len(doc.secoes)
    secoes_lidas = secoes_total  # Todo o documento foi lido e submetido à verificação determinística
    itens_verificados = 0
    itens_descartados = 0
    motivos_descarte: List[str] = []

    resultado: Dict[str, List[ItemFicha]] = {
        "obrigacoes": [],
        "prazos": [],
        "valores": [],
        "riscos": [],
        "responsaveis": [],
        "condicoes": [],
    }

    if isinstance(candidatos, PontosFicha):
        mapa_entrada = {
            "obrigacoes": candidatos.obrigacoes,
            "prazos": candidatos.prazos,
            "valores": candidatos.valores,
            "riscos": candidatos.riscos,
            "responsaveis": candidatos.responsaveis,
            "condicoes": candidatos.condicoes,
        }
    elif isinstance(candidatos, dict):
        mapa_entrada = candidatos
    elif isinstance(candidatos, list):
        mapa_entrada = {"itens": candidatos}
        resultado["itens"] = []
    else:
        mapa_entrada = {}

    for cat, lista in mapa_entrada.items():
        if cat not in resultado:
            resultado[cat] = []
        for item in lista:
            valido, motivo = verificar_item(item, doc)
            if valido:
                resultado[cat].append(item)
                itens_verificados += 1
            else:
                itens_descartados += 1
                if motivo:
                    motivos_descarte.append(motivo)

    cobertura = Cobertura(
        secoes_lidas=secoes_lidas,
        secoes_total=secoes_total,
        itens_verificados=itens_verificados,
        itens_descartados=itens_descartados,
        motivos_descarte=motivos_descarte,
    )

    return resultado, cobertura


def verificar_pontos(
    pontos: PontosFicha,
    doc: DocumentoDetalhe,
) -> Tuple[PontosFicha, Cobertura]:
    """Valida um objeto PontosFicha e retorna (PontosFicha, Cobertura)."""
    dict_verificado, cobertura = verificar_candidatos(pontos, doc)
    pontos_limpos = PontosFicha(
        obrigacoes=dict_verificado.get("obrigacoes", []),
        prazos=dict_verificado.get("prazos", []),
        valores=dict_verificado.get("valores", []),
        riscos=dict_verificado.get("riscos", []),
        responsaveis=dict_verificado.get("responsaveis", []),
        condicoes=dict_verificado.get("condicoes", []),
    )
    return pontos_limpos, cobertura


def extrair_e_verificar(
    doc: DocumentoDetalhe,
) -> Tuple[PontosFicha, Cobertura]:
    """Pipeline completo determinístico: extrai candidatos e os verifica contra o documento."""
    candidatos = extrair_pontos_candidatos(doc)
    return verificar_pontos(candidatos, doc)
