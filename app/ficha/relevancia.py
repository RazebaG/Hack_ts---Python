"""Cálculo determinístico de relevância dos blocos da Ficha do Documento.

Implementa a fórmula descrita no PRD (seção 3.5) e requisitos RF72 a RF76 (C22).

Fórmula de Pontuação:
    pontuacao = (
        0.35 * urgencia_prazo +
        0.25 * peso_valor +
        0.20 * risco +
        0.15 * divergencia_substituicao +
        0.05 * mudanca_recente
    )

Regras dos componentes:
1. urgencia_prazo (peso 0.35):
   - Prazo <= 7 dias (ou vencido): 1.0 (motivo: 'vence em N dias' ou 'vencido há N dias')
   - Prazo <= 30 dias: 0.6 (motivo: 'vence em N dias')
   - Prazo <= 90 dias: 0.2 (motivo: 'prazo em N dias')
   - Prazo > 90 dias ou geral: 0.05
2. peso_valor (peso 0.25):
   - valor_do_bloco / maior_valor_do_documento (0.0 a 1.0)
   - ratio >= 0.95: 1.0 (motivo: 'maior valor do contrato' ou 'maior valor do documento')
   - ratio < 0.95: proporcional (motivo: 'valor expressivo' ou 'impacto financeiro')
3. risco (peso 0.20):
   - Multa, rescisão, inexecução ou desconto: 1.0 (motivo: 'risco financeiro')
   - Vedação expressa / proibição: 0.8 (motivo: 'vedação expressa')
   - Penalidade ou exceção: 0.8 (motivo: 'penalidade ou exceção')
   - Risco geral: 0.5 (motivo: 'risco identificado')
4. divergencia_substituicao (peso 0.15):
   - Referência ausente no acervo: 1.0 (motivo: 'referência ausente')
   - Versão anterior substituída: 1.0 (motivo: 'versão anterior substituída')
   - Alerta geral de governança: 0.5 (motivo: 'alerta de governança')
5. mudanca_recente (peso 0.05):
   - Mudança recente de regra / nova regra: 1.0 (motivo: 'mudança recente de regra')

Desempate:
    Em caso de empate na pontuação, prevalece a ordem padrão definida
    no template da família documental (ordem_padrao ascendente).
"""

from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from datetime import date, datetime
import re

from app.ficha.modelos import RelevanciaBloco


@dataclass
class PesosRelevancia:
    """Pesos configuráveis da fórmula de relevância (PRD 3.5)."""

    urgencia_prazo: float = 0.35
    peso_valor: float = 0.25
    risco: float = 0.20
    divergencia_substituicao: float = 0.15
    mudanca_recente: float = 0.05


VALOR_NUM_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)")
DATA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
DATA_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def parse_valor_moeda(texto: Optional[str]) -> float:
    """Converte 'R$ 18.250,00' em float (18250.0)."""
    if not texto:
        return 0.0
    m = VALOR_NUM_RE.search(texto)
    if not m:
        return 0.0
    s = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_data(texto: Optional[str]) -> Optional[date]:
    """Extrai a primeira data em formato brasileiro ou ISO."""
    if not texto:
        return None
    m_br = DATA_RE.search(texto)
    if m_br:
        try:
            return datetime.strptime(m_br.group(1), "%d/%m/%Y").date()
        except ValueError:
            pass
    m_iso = DATA_ISO_RE.search(texto)
    if m_iso:
        try:
            return date.fromisoformat(m_iso.group(1))
        except ValueError:
            pass
    return None


def calcular_relevancia_bloco(
    id_bloco: str,
    titulo: str,
    sinal: str,
    destaque: str,
    apoio: Optional[str],
    maior_valor_doc: float,
    data_referencia: date,
    pesos: Optional[PesosRelevancia] = None,
    familia: str = "contrato",
) -> Tuple[float, str]:
    """Calcula determinística a pontuação e o motivo para um bloco exclusivamente
    a partir da fórmula do PRD (seção 3.5), sem constantes ajustadas ou literais de documentos.

    Retorna (pontuacao, motivo).
    """
    if pesos is None:
        pesos = PesosRelevancia()

    apoio_txt = apoio or ""
    texto_total = f"{destaque} {apoio_txt}".lower()
    scores: Dict[str, float] = {
        "urgencia_prazo": 0.0,
        "peso_valor": 0.0,
        "risco": 0.0,
        "divergencia_substituicao": 0.0,
        "mudanca_recente": 0.0,
    }
    motivos: Dict[str, str] = {}

    # 1. Urgência de prazo (peso 0.35)
    dt = parse_data(destaque) or parse_data(apoio)
    if dt:
        dias = (dt - data_referencia).days
        if dias < 0:
            scores["urgencia_prazo"] = 1.0
            motivos["urgencia_prazo"] = f"vencido há {abs(dias)} dias"
        elif dias <= 7:
            scores["urgencia_prazo"] = 1.0
            motivos["urgencia_prazo"] = f"vence em {dias} dias"
        elif dias <= 30:
            scores["urgencia_prazo"] = 0.6
            motivos["urgencia_prazo"] = f"vence em {dias} dias"
        elif dias <= 90:
            scores["urgencia_prazo"] = 0.2
            motivos["urgencia_prazo"] = f"prazo em {dias} dias"
        else:
            scores["urgencia_prazo"] = 0.05
            motivos["urgencia_prazo"] = f"prazo em {dias} dias"
    elif sinal == "prazo" or "dias" in texto_total:
        m_dias = re.search(r"(\d+)\s+dias", texto_total)
        if m_dias:
            n_dias = int(m_dias.group(1))
            if n_dias <= 7:
                scores["urgencia_prazo"] = 1.0
                motivos["urgencia_prazo"] = f"prazo de {n_dias} dias"
            elif n_dias <= 30:
                scores["urgencia_prazo"] = 0.6
                motivos["urgencia_prazo"] = f"prazo de {n_dias} dias"
            elif n_dias <= 90:
                scores["urgencia_prazo"] = 0.2
                motivos["urgencia_prazo"] = f"prazo de {n_dias} dias"
            else:
                scores["urgencia_prazo"] = 0.05
                motivos["urgencia_prazo"] = f"prazo de {n_dias} dias"

    # 2. Peso do valor (peso 0.25)
    val = parse_valor_moeda(destaque)
    if val == 0.0:
        val = parse_valor_moeda(apoio)
    if val > 0.0 and maior_valor_doc > 0.0:
        ratio = min(1.0, val / maior_valor_doc)
        scores["peso_valor"] = ratio
        if ratio >= 0.95:
            motivos["peso_valor"] = "maior valor do contrato" if familia == "contrato" else "maior valor do documento"
        elif ratio >= 0.4:
            motivos["peso_valor"] = "valor expressivo"
        else:
            motivos["peso_valor"] = "impacto financeiro"

    # 3. Risco (peso 0.20)
    if any(k in texto_total for k in ("multa", "rescis", "inexecu", "desconto")):
        scores["risco"] = 1.0
        motivos["risco"] = "risco financeiro"
    elif any(k in texto_total for k in ("vedad", "proibid")):
        scores["risco"] = 0.8
        motivos["risco"] = "vedação expressa"
    elif any(k in texto_total for k in ("penalid", "exce")):
        scores["risco"] = 0.8
        motivos["risco"] = "penalidade ou exceção"
    elif sinal == "risco":
        scores["risco"] = 0.5
        motivos["risco"] = "risco identificado"

    # 4. Divergência ou Substituição / Referência Ausente (peso 0.15)
    if any(k in texto_total for k in ("falta no acervo", "não consta no acervo", "referência ausente", "ausente")):
        scores["divergencia_substituicao"] = 1.0
        motivos["divergencia_substituicao"] = "referência ausente"
    elif "substitu" in texto_total or "revogad" in texto_total:
        scores["divergencia_substituicao"] = 1.0
        motivos["divergencia_substituicao"] = "versão anterior substituída"
    elif sinal == "alerta":
        scores["divergencia_substituicao"] = 0.5
        motivos["divergencia_substituicao"] = "alerta de governança"

    # 5. Mudança recente / Nova regra (peso 0.05)
    if "o que muda" in titulo.lower() or "o que mudou" in titulo.lower():
        scores["mudanca_recente"] = 1.0
        motivos["mudanca_recente"] = "mudança recente de regra"

    # Contribuições ponderadas estritamente pelos pesos da fórmula do PRD (seção 3.5)
    contrib_prazo = pesos.urgencia_prazo * scores["urgencia_prazo"]
    contrib_valor = pesos.peso_valor * scores["peso_valor"]
    contrib_risco = pesos.risco * scores["risco"]
    contrib_alerta = pesos.divergencia_substituicao * scores["divergencia_substituicao"]
    contrib_mudanca = pesos.mudanca_recente * scores["mudanca_recente"]

    pontuacao_bruta = (
        contrib_prazo +
        contrib_valor +
        contrib_risco +
        contrib_alerta +
        contrib_mudanca
    )
    pontuacao = round(min(1.0, max(0.0, pontuacao_bruta)), 2)

    # Identifica o fato que mais pesou
    fatores = [
        (contrib_valor, motivos.get("peso_valor")),
        (contrib_prazo, motivos.get("urgencia_prazo")),
        (contrib_risco, motivos.get("risco")),
        (contrib_alerta, motivos.get("divergencia_substituicao")),
        (contrib_mudanca, motivos.get("mudanca_recente")),
    ]
    fatores_positivos = [(score, mot) for score, mot in fatores if mot and score > 0.0]
    if fatores_positivos:
        fatores_positivos.sort(key=lambda x: x[0], reverse=True)
        motivo_final = fatores_positivos[0][1]
    else:
        # Quando nenhum componente pontuou (ex: "Quem faz o quê", bloco informativo)
        if sinal == "responsavel":
            motivo_final = "atribuição de responsabilidades"
        elif sinal == "regra":
            motivo_final = "regras e diretrizes aplicáveis"
        elif sinal == "prazo":
            motivo_final = "prazos estabelecidos"
        elif sinal == "valor":
            motivo_final = "valores definidos"
        elif sinal == "risco":
            motivo_final = "condições e riscos"
        elif sinal == "alerta":
            motivo_final = "alerta de governança"
        else:
            motivo_final = "item informativo do documento"

    return pontuacao, motivo_final  # type: ignore[return-value]
