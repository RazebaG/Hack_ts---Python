"""Sinais por seção e mapa de posição do documento (F-02, issue #42).

Por regra e sem IA: cada seção recebe contagens de quatro sinais (prazo, valor,
obrigação, risco) e uma intensidade de 0 a 1, que formam o `mapa_calor` do
contrato C22 (RF53). Cada célula leva o `secao_id`, que liga o mapa às seções
de onde os blocos vieram (RF75).

Como funciona:
1. Cada padrão tem uma força: forte (3), médio (2) ou fraco (1). Exemplos:
   `R$ 3.650,00` e `25/11/2026` são fortes; `30 dias` é médio; "prazo" ou
   "deve" soltos são fracos.
2. A pontuação de um sinal numa seção é a soma das forças dos padrões achados.
3. Normalização por documento: um padrão forte acende o sinal; um padrão
   médio acende só se a pontuação passa do limiar do documento (acima do 3º
   quartil das seções em que o sinal aparece); padrões fracos sozinhos nunca
   acendem, só reforçam a pontuação. Assim o mapa não acende um terço das
   seções por causa de palavras soltas.
4. `intensidade` = soma das pontuações dos sinais acesos, dividida pela maior
   soma do documento. `peso` = palavras da seção / palavras do documento.

Determinístico: o mesmo texto gera sempre o mesmo mapa. Nada é registrado em
log (o texto do documento nunca vai para log).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Pattern, Sequence, Tuple

from app.ficha.metadados import extrair_metricas
from app.ficha.modelos import CelulaMapa, Metricas, SinaisCelula
from app.models import DocumentoDetalhe, Secao

FORTE, MEDIO, FRACO = 3, 2, 1
SINAIS: Tuple[str, ...] = ("prazo", "valor", "obrigacao", "risco")

# Quartil superior: o limiar é o percentil 75 das pontuações positivas do sinal no documento.
PERCENTIL_LIMIAR = 0.75


@dataclass(frozen=True)
class Regra:
    sinal: str
    forca: int
    padrao: Pattern[str]


def _r(expr: str) -> Pattern[str]:
    return re.compile(expr)


# Os padrões rodam sobre o texto normalizado: minúsculo e sem acento (ver _normalizar).
REGRAS: Tuple[Regra, ...] = (
    # --- valor --------------------------------------------------------------
    Regra("valor", FORTE, _r(r"r\$\s*\d")),
    # Valor monetário sem "R$" (tabelas com "(R$)" no cabeçalho): 18.250,00 · 912,50.
    # Os lookbehinds evitam contar de novo o que já veio com "R$" e pedaços como "650,00" de "3.650,00".
    Regra("valor", FORTE, _r(r"(?<!r\$ )(?<!r\$)(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\b")),
    # Valor expresso em aluguéis ou salários: "multa equivalente a um aluguel mensal"
    Regra("valor", FORTE, _r(r"\b(?:um|uma|dois|duas|tres|\d+)\s+(?:alugue(?:l|is)|salarios?)\b")),
    Regra("valor", MEDIO, _r(r"\b\d+(?:[.,]\d+)?\s*%")),
    Regra("valor", FRACO, _r(r"\b(?:valor(?:es)? global|orcamento|reajuste|aluguel mensal)\b")),
    # --- prazo --------------------------------------------------------------
    Regra("prazo", FORTE, _r(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    Regra("prazo", FORTE, _r(r"\bd-\d+\b")),
    Regra("prazo", FORTE, _r(r"\bate o dia \d+")),
    # Marco por dia ordinal: "até o 90º dia de vigência", "a partir do 91º dia"
    Regra("prazo", FORTE, _r(r"\b(?:ate o|a partir do|no|do) \d+\s*[o\u00ba\u00b0] dia\b")),
    Regra("prazo", MEDIO, _r(r"\b\d+\s*(?:dias?|mes(?:es)?|anos?|horas?|semanas?)\b")),
    Regra("prazo", FRACO, _r(r"\b(?:prazos?|antecedencia|vencimento|prorroga\w*)\b")),
    # --- obrigação ----------------------------------------------------------
    Regra("obrigacao", FORTE, _r(r"\b(?:obriga-se|obrigam-se|compete (?:a|ao|aos|as)\b)")),
    Regra("obrigacao", FORTE, _r(r"\bcabe (?:a|ao|aos|as)\b")),
    Regra("obrigacao", FORTE, _r(r"\b(?:e|sao) responsave(?:l|is)\b")),
    # Atribuição explícita a quem executa: "o fiscal atesta", "a DIRAF aprova", "quem aprova"
    Regra("obrigacao", FORTE, _r(r"\b(?:atesta|aprova|aprovam|e aprovad[oa]|quem aprova|decide)\b")),
    # Faixa de alçada seguida do cargo: "Gasto entre R$ 18.000,01 e R$ 120.000,00: diretor da DIRTEC"
    Regra("obrigacao", FORTE, _r(r":\s*(?:o |a )?(?:diretor|gerente|comite|presidente|conselho)\b")),
    Regra("obrigacao", MEDIO, _r(r"\b(?:emite|paga|notifica|assina|verificou|verifica|registra|encaminha|providencia)\b")),
    Regra("obrigacao", FRACO, _r(r"\b(?:deve|devem|devera|responsave(?:l|is))\b")),
    Regra("obrigacao", FRACO, _r(r"\b(?:diretor|gerente|comite)\b")),
    # --- risco --------------------------------------------------------------
    Regra("risco", FORTE, _r(r"\b(?:multas?|penalidades?|rescis\w*|sanc(?:ao|oes)|juros|inadimpl\w*|inexecu\w*)\b")),
    Regra("risco", MEDIO, _r(r"\b(?:vedad\w*|proibid\w*|descumpr\w*|recus\w*|fracionamento)\b")),
    # Alçada: aprovar fora dela é o risco ("fica na alçada de", "respeitam as alçadas")
    Regra("risco", FORTE, _r(r"\balcadas?\b")),
    Regra("risco", MEDIO, _r(r"\b(?:supera|nao ha pagamento|antecedencia minima|no minimo|prazo minimo)\b")),
    Regra("risco", FRACO, _r(r"\b(?:limite|minim[oa]|maxim[oa]|acima de|abaixo de|somente|apenas)\b")),
)


def _normalizar(texto: str) -> str:
    """Minúsculo e sem acento, para os padrões não dependerem de grafia."""
    sem_acento = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return sem_acento.lower()


def _texto_secao(secao: Secao) -> str:
    """Título + texto; o parser costuma repetir o título na primeira linha, e aí não duplica."""
    titulo = (secao.titulo or "").strip()
    texto = secao.texto or ""
    if titulo and texto.lstrip().startswith(titulo):
        return texto
    return f"{titulo}\n{texto}"


def _palavras(secao: Secao) -> int:
    # Mesma contagem de extrair_metricas (F-01), para peso e métricas baterem.
    return len(f"{secao.titulo} {secao.texto}".split())


def _sem_sinal() -> Dict[str, bool]:
    return {s: False for s in SINAIS}


@dataclass
class PontuacaoSecao:
    """Por sinal: quantos padrões achados, pontos (soma das forças) e se houve padrão forte/médio."""

    contagens: Dict[str, int]
    pontos: Dict[str, int]
    tem_forte: Dict[str, bool]
    tem_medio: Dict[str, bool] = field(default_factory=_sem_sinal)


def pontuar_texto(texto: str) -> PontuacaoSecao:
    """Pontua um texto (uma seção) em cada sinal."""
    norm = _normalizar(texto)
    contagens = {s: 0 for s in SINAIS}
    pontos = {s: 0 for s in SINAIS}
    tem_forte = {s: False for s in SINAIS}
    tem_medio = {s: False for s in SINAIS}
    for regra in REGRAS:
        achados = len(regra.padrao.findall(norm))
        if not achados:
            continue
        contagens[regra.sinal] += achados
        pontos[regra.sinal] += achados * regra.forca
        if regra.forca == FORTE:
            tem_forte[regra.sinal] = True
        elif regra.forca == MEDIO:
            tem_medio[regra.sinal] = True
    return PontuacaoSecao(contagens=contagens, pontos=pontos, tem_forte=tem_forte, tem_medio=tem_medio)


def _percentil(valores: Sequence[int], p: float) -> float:
    """Percentil pelo método do posto mais próximo (determinístico, sem interpolação)."""
    ordenados = sorted(valores)
    posto = max(1, math.ceil(p * len(ordenados)))
    return float(ordenados[posto - 1])


def limiares_do_documento(pontuacoes: Sequence[PontuacaoSecao]) -> Dict[str, float]:
    """Limiar de cada sinal: percentil 75 das pontuações positivas no documento."""
    limiares: Dict[str, float] = {}
    for sinal in SINAIS:
        positivos = [p.pontos[sinal] for p in pontuacoes if p.pontos[sinal] > 0]
        limiares[sinal] = _percentil(positivos, PERCENTIL_LIMIAR) if positivos else math.inf
    return limiares


def _aceso(p: PontuacaoSecao, sinal: str, limiar: float) -> bool:
    """Forte acende sempre; médio acende se passa do limiar; só fraco (palavra solta) não acende.

    "Passa" é estrito: com muitos empates no 3º quartil, `>=` acenderia quase metade das
    seções que têm o sinal (medido no acervo: prazo em 20,5% das seções contra 14,8%).
    """
    if p.tem_forte[sinal]:
        return True
    return p.tem_medio[sinal] and p.pontos[sinal] > limiar


def mapa_do_documento(doc: DocumentoDetalhe) -> List[CelulaMapa]:
    """`mapa_calor` do C22: uma célula por seção, na ordem do documento."""
    secoes = list(doc.secoes)
    if not secoes:
        return []

    pontuacoes = [pontuar_texto(_texto_secao(s)) for s in secoes]
    limiares = limiares_do_documento(pontuacoes)

    palavras = [_palavras(s) for s in secoes]
    total_palavras = sum(palavras)

    acesos: List[Dict[str, bool]] = [
        {sinal: _aceso(p, sinal, limiares[sinal]) for sinal in SINAIS} for p in pontuacoes
    ]
    brutos = [
        sum(p.pontos[s] for s in SINAIS if a[s]) for p, a in zip(pontuacoes, acesos)
    ]
    maior = max(brutos) if brutos else 0

    celulas: List[CelulaMapa] = []
    for ordem, (secao, p, a, bruto, n) in enumerate(
        zip(secoes, pontuacoes, acesos, brutos, palavras), start=1
    ):
        celulas.append(
            CelulaMapa(
                secao_id=secao.id,
                titulo=secao.titulo,
                ordem=ordem,
                peso=round(n / total_palavras, 4) if total_palavras else round(1 / len(secoes), 4),
                sinais=SinaisCelula(**{s: (p.contagens[s] if a[s] else 0) for s in SINAIS}),
                intensidade=round(bruto / maior, 2) if maior else 0.0,
            )
        )
    return celulas


def metricas_do_documento(doc: DocumentoDetalhe) -> Metricas:
    """Métricas do C22 (`secoes`, `palavras`, `paginas_estimadas`, `leitura_integral_min`).

    Reaproveita a regra da F-01 (`extrair_metricas`) para não haver duas contas diferentes.
    """
    return extrair_metricas(doc)
