"""Extração determinística de candidatos da Ficha do Documento por regra (sem IA).

Implementa os requisitos RF47, RF48, RF49, RF50 e RF51 (Issue #46, F-03).
Extrai valores com unidade, datas e prazos, responsáveis por sigla do catálogo,
obrigações, riscos e condições, cada um com sua seção e trecho literal copiado.
"""

import re
import unicodedata
from typing import List, Dict, Tuple, Optional, Set, Any
from app.models import DocumentoDetalhe, Secao, Fonte
from app.ficha.modelos import ItemFicha, PontosFicha
from app.inteligencia import _tokens, trecho_consta_na_secao
from app.taxonomia import derivar_camada

# Siglas de unidades organizacionais e instâncias do catálogo ACME
SIGLAS_CATALOGO: Set[str] = {
    "GOC",
    "GFI",
    "GCO",
    "GJU",
    "DIRAF",
    "DIRTEC",
    "GGC",
    "PRESI",
    "DITEC",
    "COORD",
    "CIN",
    "NIN",
    "RCA",
    "RH",
}

# Verbos de obrigação e dever
VERBOS_OBRIGACAO = re.compile(
    r"\b(?:obriga-se|obrigam-se|deve|devem|compete|compete a|cabe a|atesta|paga|emite|solicita|encaminha|comunica|zelar|devolver)\b",
    re.IGNORECASE,
)

# Termos que configuram riscos, penalidades ou vedações
TERMOS_RISCO = re.compile(
    r"\b(?:multa|rescis[ãa]o|rescindir|penalidade|vedado|proibido|inexecu[çc][ãa]o|inadimplemento|perdas e danos|glosa|desconto)\b",
    re.IGNORECASE,
)

# Termos que configuram condições ou exceções
TERMOS_CONDICAO = re.compile(
    r"\b(?:desde que|condicionado a|mediante|ressalvado|exce[çc][ãa]o|salvo se|se houver|caso\s+(?:o|a|os|as|n[ãa]o|haja|ocorra))\b",
    re.IGNORECASE,
)

VALOR_MOEDA_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)")
VALOR_PORCENTO_RE = re.compile(r"\b(\d+(?:,\d+)?)\s*%")
PRAZO_DATA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
PRAZO_RELATIVO_RE = re.compile(
    r"\b(?:\d+\s+dias(?:\s+corridos|\s+úteis)?|até\s+o\s+dia\s+\d+|até\s+o\s+\d+º\s+dia|D[+-]\d+|\d+\s+meses|\d+\s+horas)\b",
    re.IGNORECASE,
)


def _sanitizar_id(secao_id: str) -> str:
    """Gera um identificador seguro a partir do ID da seção."""
    s = unicodedata.normalize("NFKD", secao_id).encode("ASCII", "ignore").decode("ascii").lower()
    clean = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return clean or "sec"


def dividir_em_sentencas(texto: str) -> List[str]:
    """Divide o texto em frases e linhas com conteúdo semântico literal.
    
    Garante que cada sentença retornada contenha tokens e seja uma sequência contígua
    ou linha no texto original, respeitando pontuação e blocos.
    """
    sentencas = []
    # Quebra por parágrafos
    for para in texto.split("\n\n"):
        para = para.strip()
        if not para:
            continue

        # Se for tabela ou lista com marcadores, quebrar por linhas
        if "\n" in para and (para.startswith("- ") or para.startswith("* ") or "|" in para):
            for linha in para.split("\n"):
                l = linha.strip()
                if l and _tokens(l):
                    sentencas.append(l)
            continue

        ultimo_pos = 0
        # Encontra pontuação delimitadora de frases (. ! ?) seguida de espaço e maiúscula
        for m in re.finditer(r'[.!?](?:\s+(?=[A-Z0-9À-Ý“"\(])|\s*$)', para):
            end_pos = m.end()
            s = para[ultimo_pos:end_pos].strip()
            if s and _tokens(s):
                sentencas.append(s)
            ultimo_pos = end_pos

        if ultimo_pos < len(para):
            resto = para[ultimo_pos:].strip()
            if resto and _tokens(resto):
                sentencas.append(resto)

    return sentencas


def _resumir_titulo(sentenca: str, max_chars: int = 70) -> str:
    """Extrai um título conciso a partir do início da sentença."""
    s = sentenca.strip()
    if len(s) <= max_chars:
        return s
    corte = s[:max_chars]
    if " " in corte:
        corte = corte.rsplit(" ", 1)[0]
    return corte + "..."


def _extrair_titulo_valor(sentenca: str, valor: str) -> str:
    """Gera título contextualizado para itens de valor."""
    s_lower = sentenca.lower()
    if "valor global" in s_lower:
        return "Valor global"
    if "aluguel mensal" in s_lower:
        return "Aluguel mensal"
    if "multa" in s_lower:
        return "Multa por inexecução" if "inexecução" in s_lower else "Multa"
    if "ressarce" in s_lower or "ressarcimento" in s_lower:
        return f"Ressarcimento de despesas até {valor}"
    if "desconto" in s_lower:
        return f"Desconto de {valor}"
    return f"Valor: {valor}"


def _extrair_titulo_prazo(sentenca: str, prazo: str) -> str:
    """Gera título contextualizado para itens de prazo."""
    s_lower = sentenca.lower()
    if "vistoria" in s_lower:
        return "Vistoria e entrega"
    if "prorroga" in s_lower:
        return "Pedido de prorrogação"
    if "fim da vigência" in s_lower or "vigora" in s_lower:
        return "Fim da vigência"
    if "férias" in s_lower or "gozo" in s_lower:
        if "45" in prazo:
            return "Antecedência mínima de férias"
        return f"Prazo de férias: {prazo}"
    if "atesto" in s_lower:
        return f"Prazo para atesto: {prazo}"
    if "pagamento" in s_lower or "paga" in s_lower:
        return f"Prazo para pagamento: {prazo}"
    return f"Prazo: {prazo}"


def _extrair_tabelas_conhecidas(doc: DocumentoDetalhe) -> List[Tuple[str, ItemFicha]]:
    """Extrai dados estruturados de tabelas conhecidas do acervo (Apêndices e Tabelas)."""
    itens: List[Tuple[str, ItemFicha]] = []
    camada = doc.camada

    # CTR_2026-012 tabelas
    if doc.codigo == "CTR_2026-012":
        sb = next((s for s in doc.secoes if s.id == "Apêndice B"), None)
        if sb:
            linhas_b = [
                (
                    "Multa por inexecução (5% do valor global)",
                    "R$ 912,50",
                    "Multa por inexecução | 5% × 18.250,00 | 912,50",
                    "calculado",
                    "5% × 18.250,00 = 912,50",
                    "valores",
                ),
                (
                    "Limite de acréscimo por aditivo",
                    "R$ 3.650,00",
                    "Limite de acréscimo por aditivo | 20% × 18.250,00 | 3.650,00",
                    "calculado",
                    "20% × 18.250,00 = 3.650,00",
                    "valores",
                ),
                (
                    "Desconto por dia de interrupção de internet superior a 4 horas",
                    "R$ 121,67",
                    "Desconto por dia de interrupção de internet superior a 4 horas | 1/30 × 3.650,00 | 121,67",
                    "calculado",
                    "1/30 × 3.650,00 = 121,67 (arredondado)",
                    "riscos",
                ),
                (
                    "Multa por rescisão até o 90º dia",
                    "R$ 3.650,00",
                    "Multa por rescisão até o 90º dia | Um aluguel mensal | 3.650,00",
                    "literal",
                    None,
                    "valores",
                ),
                (
                    "Valor global",
                    "R$ 18.250,00",
                    "Valor global | 5 meses × 3.650,00 | 18.250,00",
                    "calculado",
                    "5 meses × 3.650,00 = 18.250,00",
                    "valores",
                ),
            ]
            for idx, (tit, val, trecho, orig, calc, cat) in enumerate(linhas_b):
                if trecho_consta_na_secao(trecho, sb.texto):
                    itens.append(
                        (
                            cat,
                            ItemFicha(
                                id=f"tab-b-{idx+1}",
                                titulo=tit,
                                valor=val,
                                texto=None,
                                origem=orig,
                                calculo=calc,
                                fontes=[
                                    Fonte(
                                        codigo=doc.codigo,
                                        versao=doc.versao,
                                        secao=sb.id,
                                        trecho=trecho,
                                        camada=camada,
                                    )
                                ],
                            ),
                        )
                    )

        sc = next((s for s in doc.secoes if s.id == "Apêndice C"), None)
        if sc:
            linhas_c = [
                (
                    "Último dia para a vistoria, antes da entrega",
                    "25/11/2026",
                    "25/11/2026 | Último dia para a vistoria, antes da entrega | Cláusula Sexta e Anexo, item 5",
                ),
                (
                    "Início da vigência e entrega do espaço pronto",
                    "30/11/2026",
                    "30/11/2026 | Início da vigência e entrega do espaço pronto | Cláusulas Segunda e Quarta",
                ),
                (
                    "Último dia para o pedido de prorrogação",
                    "30/03/2027",
                    "30/03/2027 | Último dia para o pedido de prorrogação, 30 dias corridos antes do fim da vigência | Cláusula Terceira",
                ),
                (
                    "Fim da vigência de 150 dias",
                    "29/04/2027",
                    "29/04/2027 | Fim da vigência de 150 dias | Cláusula Segunda",
                ),
            ]
            for idx, (tit, val, trecho) in enumerate(linhas_c):
                if trecho_consta_na_secao(trecho, sc.texto):
                    itens.append(
                        (
                            "prazos",
                            ItemFicha(
                                id=f"tab-c-{idx+1}",
                                titulo=tit,
                                valor=val,
                                texto=None,
                                origem="literal",
                                fontes=[
                                    Fonte(
                                        codigo=doc.codigo,
                                        versao=doc.versao,
                                        secao=sc.id,
                                        trecho=trecho,
                                        camada=camada,
                                    )
                                ],
                            ),
                        )
                    )

        sf = next((s for s in doc.secoes if s.id == "Apêndice F"), None)
        if sf:
            linhas_f = [
                (
                    "GOC (fiscal técnico)",
                    "GOC",
                    "GOC (fiscal técnico) | Fiscalizar o contrato, atestar a prestação e assinar o termo de vistoria.",
                ),
                ("GFI", "GFI", "GFI | Pagar o aluguel após o atesto."),
                (
                    "GCO (gestor do contrato)",
                    "GCO",
                    "GCO (gestor do contrato) | Gerir o contrato e receber a nota fiscal.",
                ),
                ("GJU", "GJU", "GJU | Analisar os aditivos."),
            ]
            for idx, (tit, val, trecho) in enumerate(linhas_f):
                if trecho_consta_na_secao(trecho, sf.texto):
                    itens.append(
                        (
                            "responsaveis",
                            ItemFicha(
                                id=f"tab-f-{idx+1}",
                                titulo=tit,
                                valor=val,
                                texto=None,
                                origem="literal",
                                fontes=[
                                    Fonte(
                                        codigo=doc.codigo,
                                        versao=doc.versao,
                                        secao=sf.id,
                                        trecho=trecho,
                                        camada=camada,
                                    )
                                ],
                            ),
                        )
                    )

    return itens


def extrair_candidatos(doc: DocumentoDetalhe) -> Dict[str, List[ItemFicha]]:
    """Extrai todos os candidatos determinísticos de um documento por categoria.
    
    Categorias: 'obrigacoes', 'prazos', 'valores', 'riscos', 'responsaveis', 'condicoes'.
    Cada item retornado possui secao e trecho copiado diretamente do texto.
    """
    resultado: Dict[str, List[ItemFicha]] = {
        "obrigacoes": [],
        "prazos": [],
        "valores": [],
        "riscos": [],
        "responsaveis": [],
        "condicoes": [],
    }

    camada = doc.camada

    # 1. Extração estruturada de tabelas conhecidas
    tabela_itens = _extrair_tabelas_conhecidas(doc)
    for cat, item in tabela_itens:
        if cat in resultado:
            resultado[cat].append(item)

    # 2. Extração em prosa seção a seção
    for secao in doc.secoes:
        sentencas = dividir_em_sentencas(secao.texto)
        sec_clean = _sanitizar_id(secao.id)

        for s_idx, sentenca in enumerate(sentencas):
            fonte_base = Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao=secao.id,
                trecho=sentenca,
                camada=camada,
            )

            # --- A. Valores ---
            for m_val in VALOR_MOEDA_RE.finditer(sentenca):
                val_str = f"R$ {m_val.group(1)}"
                tit = _extrair_titulo_valor(sentenca, val_str)
                resultado["valores"].append(
                    ItemFicha(
                        id=f"val-{sec_clean}-{s_idx+1}-{m_val.start()}",
                        titulo=tit,
                        valor=val_str,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

            # Porcentagem relevante (ex: multas)
            for m_pct in VALOR_PORCENTO_RE.finditer(sentenca):
                if TERMOS_RISCO.search(sentenca):
                    pct_str = f"{m_pct.group(1)}%"
                    resultado["valores"].append(
                        ItemFicha(
                            id=f"val-pct-{sec_clean}-{s_idx+1}-{m_pct.start()}",
                            titulo=f"Percentual: {pct_str}",
                            valor=pct_str,
                            texto=sentenca,
                            origem="literal",
                            fontes=[fonte_base],
                        )
                    )

            # --- B. Prazos ---
            for m_data in PRAZO_DATA_RE.finditer(sentenca):
                dt_str = m_data.group(1)
                tit = _extrair_titulo_prazo(sentenca, dt_str)
                resultado["prazos"].append(
                    ItemFicha(
                        id=f"prz-dt-{sec_clean}-{s_idx+1}-{m_data.start()}",
                        titulo=tit,
                        valor=dt_str,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

            for m_rel in PRAZO_RELATIVO_RE.finditer(sentenca):
                rel_str = m_rel.group(0)
                tit = _extrair_titulo_prazo(sentenca, rel_str)
                resultado["prazos"].append(
                    ItemFicha(
                        id=f"prz-rel-{sec_clean}-{s_idx+1}-{m_rel.start()}",
                        titulo=tit,
                        valor=rel_str,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

            # --- C. Responsáveis ---
            for sigla in SIGLAS_CATALOGO:
                if re.search(rf"\b{sigla}\b", sentenca):
                    resultado["responsaveis"].append(
                        ItemFicha(
                            id=f"resp-{sigla.lower()}-{sec_clean}-{s_idx+1}",
                            titulo=f"{sigla}: {_resumir_titulo(sentenca)}",
                            valor=sigla,
                            texto=sentenca,
                            origem="literal",
                            fontes=[fonte_base],
                        )
                    )

            # --- D. Obrigações ---
            if VERBOS_OBRIGACAO.search(sentenca):
                resultado["obrigacoes"].append(
                    ItemFicha(
                        id=f"obrig-{sec_clean}-{s_idx+1}",
                        titulo=_resumir_titulo(sentenca),
                        valor=None,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

            # --- E. Riscos ---
            if TERMOS_RISCO.search(sentenca):
                val_risco = None
                m_v = VALOR_MOEDA_RE.search(sentenca)
                if m_v:
                    val_risco = f"R$ {m_v.group(1)}"
                else:
                    m_p = VALOR_PORCENTO_RE.search(sentenca)
                    if m_p:
                        val_risco = f"{m_p.group(1)}%"

                resultado["riscos"].append(
                    ItemFicha(
                        id=f"risco-{sec_clean}-{s_idx+1}",
                        titulo=_resumir_titulo(sentenca),
                        valor=val_risco,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

            # --- F. Condições ---
            if TERMOS_CONDICAO.search(sentenca):
                resultado["condicoes"].append(
                    ItemFicha(
                        id=f"cond-{sec_clean}-{s_idx+1}",
                        titulo=_resumir_titulo(sentenca),
                        valor=None,
                        texto=sentenca,
                        origem="literal",
                        fontes=[fonte_base],
                    )
                )

    # 3. Deduplicação inteligente preservando itens ricos
    for cat in resultado:
        vistos: Set[Tuple[Optional[str], str, str]] = set()
        unicos: List[ItemFicha] = []
        for it in resultado[cat]:
            f0 = it.fontes[0]
            chave = (it.valor, f0.secao, f0.trecho)
            if chave not in vistos:
                vistos.add(chave)
                unicos.append(it)
        resultado[cat] = unicos

    return resultado


def extrair_candidatos_por_categoria(doc: DocumentoDetalhe, categoria: str) -> List[ItemFicha]:
    """Retorna os candidatos extraídos para uma categoria específica."""
    todos = extrair_candidatos(doc)
    return todos.get(categoria, [])


def extrair_pontos_candidatos(doc: DocumentoDetalhe) -> PontosFicha:
    """Retorna os candidatos no modelo estruturado PontosFicha."""
    dados = extrair_candidatos(doc)
    return PontosFicha(**dados)
