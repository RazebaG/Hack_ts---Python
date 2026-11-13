"""Avaliação dos sinais por seção (F-02, issue #42).

Uso:
    python -m eval.sinais              # regras atuais (app/ficha/sinais.py)
    python -m eval.sinais --prototipo  # protótipo da issue (sem níveis nem normalização), para comparar

Para cada sinal imprime o percentual de seções marcadas no acervo e o recall
contra a curadoria manual (`data/curadoria/*.yaml`): `valores` → valor,
`prazos` → prazo, `responsaveis` → obrigação, `riscos` → risco. O gabarito é o
conjunto de seções (código, versão, seção) citadas em cada lista.

Sem rede e sem IA. Imprime só identificadores de seção, nunca o texto.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

from app.acervo import AcervoRepository
from app.ficha.sinais import SINAIS, _normalizar, _texto_secao, mapa_do_documento

RAIZ = Path(__file__).resolve().parent.parent
CURADORIA = RAIZ / "data" / "curadoria"

LISTA_PARA_SINAL = {"valores": "valor", "prazos": "prazo", "responsaveis": "obrigacao", "riscos": "risco"}

Chave = Tuple[str, str, str]

# Metas do aceite da issue #42.
META_PRAZO_MAX_MARCADAS = 20.0
META_RECALL = {"prazo": 90.0, "obrigacao": 70.0, "risco": 70.0}

# Protótipo descrito na issue #42 ("antes"): um padrão por sinal, sem força nem normalização.
PROTOTIPO = {
    "valor": re.compile(r"r\$\s*\d|\d+[.,]?\d*\s*%"),
    "prazo": re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d+\s*(?:dias|meses|anos|horas)\b|ate o dia \d+|\bd-\d+\b|\bprazo"),
    "obrigacao": re.compile(r"obriga-se|\bdeve|\bcompete|\bcabe a\b|\batesta|\bpaga\b|\bemite|responsavel"),
    "risco": re.compile(
        r"multa|rescis|penalidade|vedad|inexecu|juros|sanc|descumpr|inadimpl|proibid"
    ),
}


def carregar_gabarito(pasta: Path = CURADORIA) -> Dict[str, Set[Chave]]:
    gabarito: Dict[str, Set[Chave]] = {s: set() for s in SINAIS}
    for arquivo in sorted(pasta.glob("*.yaml")):
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
        for lista, sinal in LISTA_PARA_SINAL.items():
            for item in dados.get(lista) or []:
                fonte = item.get("fonte") or {}
                if fonte.get("codigo") and fonte.get("secao"):
                    gabarito[sinal].add((fonte["codigo"], str(fonte.get("versao", "")), str(fonte["secao"])))
    return gabarito


# O parser pode repetir o id de seção dentro de um documento (listas numeradas viram
# seções "1", "2"...). Por isso o percentual conta células (seções do mapa), e o recall
# conta a seção do gabarito como achada se alguma célula com aquele id acendeu o sinal.
Marcacao = Tuple[Dict[str, int], Dict[str, Set[Chave]], int]


def marcadas_atual(acervo: AcervoRepository) -> Marcacao:
    celulas_marcadas = {s: 0 for s in SINAIS}
    chaves: Dict[str, Set[Chave]] = {s: set() for s in SINAIS}
    total = 0
    for doc in acervo.documentos:
        for celula in mapa_do_documento(doc):
            total += 1
            for sinal in SINAIS:
                if getattr(celula.sinais, sinal) > 0:
                    celulas_marcadas[sinal] += 1
                    chaves[sinal].add((doc.codigo, doc.versao, celula.secao_id))
    return celulas_marcadas, chaves, total


def marcadas_prototipo(acervo: AcervoRepository) -> Marcacao:
    celulas_marcadas = {s: 0 for s in SINAIS}
    chaves: Dict[str, Set[Chave]] = {s: set() for s in SINAIS}
    total = 0
    for doc in acervo.documentos:
        for secao in doc.secoes:
            total += 1
            texto = _normalizar(_texto_secao(secao))
            for sinal, padrao in PROTOTIPO.items():
                if padrao.search(texto):
                    celulas_marcadas[sinal] += 1
                    chaves[sinal].add((doc.codigo, doc.versao, secao.id))
    return celulas_marcadas, chaves, total


def avaliar(prototipo: bool = False, acervo: AcervoRepository | None = None) -> Dict[str, dict]:
    acervo = acervo or AcervoRepository()
    gabarito = carregar_gabarito()
    celulas, chaves, total = (marcadas_prototipo if prototipo else marcadas_atual)(acervo)
    resultado: Dict[str, dict] = {}
    for sinal in SINAIS:
        gab = gabarito[sinal]
        acertos = gab & chaves[sinal]
        resultado[sinal] = {
            "marcadas": celulas[sinal],
            "total_secoes": total,
            "pct_marcadas": 100.0 * celulas[sinal] / total if total else 0.0,
            "acertos": len(acertos),
            "gabarito": len(gab),
            "recall": 100.0 * len(acertos) / len(gab) if gab else 0.0,
            "perdidas": sorted(gab - chaves[sinal]),
        }
    return resultado


def _metas_ok(resultado: Dict[str, dict]) -> List[str]:
    falhas = []
    if resultado["prazo"]["pct_marcadas"] > META_PRAZO_MAX_MARCADAS:
        falhas.append(f"prazo marca {resultado['prazo']['pct_marcadas']:.1f}% (> {META_PRAZO_MAX_MARCADAS:.0f}%)")
    for sinal, meta in META_RECALL.items():
        if resultado[sinal]["recall"] < meta:
            falhas.append(f"{sinal}: recall {resultado[sinal]['recall']:.1f}% (< {meta:.0f}%)")
    return falhas


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia os sinais por seção contra a curadoria.")
    parser.add_argument("--prototipo", action="store_true", help="usa as regras do protótipo da issue #42")
    args = parser.parse_args(argv)

    resultado = avaliar(prototipo=args.prototipo)
    total = next(iter(resultado.values()))["total_secoes"]
    modo = "PROTÓTIPO (antes)" if args.prototipo else "REGRAS ATUAIS (app/ficha/sinais.py)"
    print("=" * 72)
    print(f"EVAL DOS SINAIS · {modo} · {total} seções")
    print("=" * 72)
    print(f"{'sinal':<10} {'marcadas':>16} {'recall':>18}")
    for sinal in SINAIS:
        r = resultado[sinal]
        print(
            f"{sinal:<10} {r['marcadas']:>4} ({r['pct_marcadas']:5.1f}%)   "
            f"{r['acertos']:>2}/{r['gabarito']:<2} ({r['recall']:5.1f}%)"
        )
    print("-" * 72)
    for sinal in SINAIS:
        for codigo, versao, secao in resultado[sinal]["perdidas"]:
            print(f"perdida · {sinal:<9} · {codigo} v{versao} · {secao}")
    falhas = _metas_ok(resultado)
    print("-" * 72)
    if falhas:
        print("METAS DA ISSUE #42 NÃO ATINGIDAS: " + "; ".join(falhas))
    else:
        print("METAS DA ISSUE #42 ATINGIDAS (prazo ≤ 20% das seções, recall prazo ≥ 90%, obrigação e risco ≥ 70%)")
    print("=" * 72)
    return 0 if args.prototipo or not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
