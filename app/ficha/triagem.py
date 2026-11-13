"""Lógica e regras determinísticas da Triagem e Lista de Atenção (C25, RF69, RF71, Issue #54).

Implementa:
- Extração de próximo prazo futuro determinístico com fonte verificada
- Resumo de marco para chip da tela inicial (ex.: 'vistoria em 13 dias', 'prazo em 19 dias')
- Sinais de multa e divergência
- Semáforo e motivo_curto por regra determinística
- Ordem por urgência determinística em 4 categorias (C25):
    (a) prazos em até 30 dias (do mais próximo ao mais distante)
    (b) regra mudou de versão
    (c) cita norma fora do acervo
    (d) demais, por próximo prazo e depois por código
- Filtros por tema, tipo, situação, sinal e paginação com limite
"""

import re
from datetime import date
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from app.acervo import AcervoRepository
from app.ficha.familias import derivar_familia
from app.ficha.metadados import obter_data_referencia
from app.ficha.modelos import (
    FamiliaDocumento,
    FichaDocumento,
    ItemTriagem,
    ProximoPrazoTriagem,
    SinaisTriagem,
    TriagemResposta,
)
from app.ficha.montagem import montar_ficha
from app.ficha.relevancia import parse_data
from app.models import DocumentoDetalhe

UNIDADES_TEMPO = {
    "dias",
    "dia",
    "meses",
    "mes",
    "horas",
    "hora",
    "úteis",
    "uteis",
    "corridos",
}


def resumir_marco(evento: str) -> str:
    """Gera o marco resumido de até 3 palavras a partir do evento do prazo.

    Se não houver palavras descritivas após a remoção de prefixos e unidades,
    retorna 'prazo'.
    Exemplos:
    - 'Último dia para a vistoria, antes da entrega' -> 'vistoria'
    - 'Vistoria e entrega' -> 'vistoria'
    - 'Prazo: 01/12/2026' -> 'prazo'
    - 'Último dia para o pedido de prorrogação' -> 'pedido de prorrogação'
    """
    s = " ".join(evento.split()).strip()
    s = re.sub(
        r"^(último dia para\s+(?:(?:a|o|as|os)\s+)?|data limite para\s+(?:(?:a|o|as|os)\s+)?|prazo para\s+(?:(?:a|o|as|os)\s+)?|prazo de\s+|prazo:\s*|início da\s+|fim da\s*)",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    s = s.lstrip(":").strip()
    s = re.split(r"[,;]|\s+antes\b|\s+após\b|\s+e\s+", s, flags=re.IGNORECASE)[0].strip()

    palavras = s.split()
    palavras_limpas: List[str] = []
    for w in palavras:
        w_clean = w.strip(":,.;()\"'").lower()
        if not w_clean:
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}$|^\d+$|^d-\d+$", w_clean):
            continue
        if w_clean in UNIDADES_TEMPO:
            continue
        palavras_limpas.append(w_clean)

    if not palavras_limpas:
        return "prazo"
    return " ".join(palavras_limpas[:3])


def extrair_proximo_prazo(
    ficha: FichaDocumento,
    data_referencia: date,
) -> Optional[ProximoPrazoTriagem]:
    """Obtém o prazo futuro mais próximo entre os itens de prazo da ficha (com fonte).

    Considera apenas prazos com data futura em relação à data de referência (dias >= 0).
    """
    candidatos = []
    for p in ficha.pontos.prazos:
        dt = parse_data(p.valor) or parse_data(p.texto) or parse_data(p.titulo)
        if dt and dt >= data_referencia:
            dias = (dt - data_referencia).days
            # Prioriza títulos específicos e informativos sobre 'Prazo: <data>'
            is_generic = p.titulo.lower().startswith("prazo: " + (p.valor or "").lower())
            candidatos.append((dias, dt, is_generic, p))

    if not candidatos:
        return None

    # Ordena por menor distância em dias, preferência por título não-genérico e ordem lexicográfica
    candidatos.sort(key=lambda x: (x[0], x[2], x[3].titulo))
    dias, dt, _, p = candidatos[0]
    fonte = p.fontes[0] if p.fontes else None

    return ProximoPrazoTriagem(
        data=dt.isoformat(),
        evento=p.titulo,
        fonte=fonte,
    )


def verificar_sinal_multa(ficha: FichaDocumento) -> bool:
    """Verifica se existe item de valor ou risco mencionando multa."""
    for item in ficha.pontos.valores + ficha.pontos.riscos:
        texto = f"{item.titulo} {item.valor or ''} {item.texto or ''}".lower()
        if "multa" in texto:
            return True
    return False


def verificar_sinal_divergencia(ficha: FichaDocumento) -> bool:
    """Verifica se existe alerta de versão substituída ou divergência."""
    return any(a.tipo in ("versao_substituida", "divergencia") for a in ficha.alertas)


def calcular_motivo_curto_e_categoria(
    prz: Optional[ProximoPrazoTriagem],
    data_ref: date,
    tem_versao_subst: bool,
    tem_ref_ausente: bool,
) -> Tuple[str, int, int]:
    """Calcula determinística a categoria de urgência (0 a 3) e o texto de motivo_curto.

    Categorias:
    0: prazo futuro <= 30 dias (ordena por dias crescente)
    1: regra mudou de versão
    2: referência ausente / cita norma fora do acervo
    3: demais (ordena por dias se houver prazo > 30d, senão desempate por código)
    """
    dias = None
    if prz is not None:
        dt = parse_data(prz.data)
        if dt:
            dias = (dt - data_ref).days

    if dias is not None and 0 <= dias <= 30:
        marco = resumir_marco(prz.evento)
        plur = "dias" if dias != 1 else "dia"
        motivo = f"{marco} em {dias} {plur}"
        return motivo, 0, dias
    elif tem_versao_subst:
        return "regra mudou de versão", 1, 0
    elif tem_ref_ausente:
        return "cita norma fora do acervo", 2, 0
    else:
        cat_dias = dias if dias is not None else 999999
        return "em dia", 3, cat_dias


def montar_item_triagem(
    doc: DocumentoDetalhe,
    ficha: FichaDocumento,
    data_ref: date,
) -> Tuple[ItemTriagem, Dict[str, Any]]:
    """Monta o ItemTriagem e seu dicionário de metadados para ordenação e filtro."""
    prz = extrair_proximo_prazo(ficha, data_ref)
    tem_versao_subst = verificar_sinal_divergencia(ficha)
    tem_ref_ausente = any(a.tipo == "referencia_ausente" for a in ficha.alertas)
    tem_multa = verificar_sinal_multa(ficha)

    motivo_curto, cat, cat_dias = calcular_motivo_curto_e_categoria(
        prz=prz,
        data_ref=data_ref,
        tem_versao_subst=tem_versao_subst,
        tem_ref_ausente=tem_ref_ausente,
    )

    # BLUF curto: até 140 caracteres
    bluf_curto = None
    if ficha.bluf and ficha.bluf.texto:
        txt = ficha.bluf.texto.strip()
        if len(txt) > 140:
            bluf_curto = txt[:137].rstrip() + "..."
        else:
            bluf_curto = txt

    dias_prz = None
    if prz is not None:
        dt = parse_data(prz.data)
        if dt:
            dias_prz = (dt - data_ref).days

    familia = ficha.familia or derivar_familia(doc)

    item = ItemTriagem(
        codigo=doc.codigo,
        versao=doc.versao,
        titulo=doc.titulo,
        tipo=doc.tipo,
        tema=doc.assunto,
        semaforo=ficha.semaforo,
        bluf_curto=bluf_curto,
        proximo_prazo=prz,
        alertas=len(ficha.alertas),
        leitura_integral_min=ficha.identidade.metricas.leitura_integral_min,
        leitura_ficha_min=ficha.identidade.metricas.leitura_ficha_min,
        ficha="pronta",
        sinais=SinaisTriagem(
            multa=tem_multa,
            divergencia=tem_versao_subst,
        ),
        motivo_curto=motivo_curto,
        familia=familia,
    )

    meta = {
        "cat": cat,
        "cat_dias": cat_dias,
        "dias_prz": dias_prz,
        "vigencia": doc.vigencia or "",
    }
    return item, meta


def executar_triagem(
    acervo: AcervoRepository,
    obter_ficha_fn: Callable[[DocumentoDetalhe, AcervoRepository, Optional[str]], FichaDocumento],
    limite: Optional[int] = None,
    perfil: Optional[str] = None,
    tema: Optional[str] = None,
    tipo: Optional[str] = None,
    situacao: Optional[Literal["ok", "atencao", "critico"]] = None,
    sinal: Optional[Literal["prazo_30d", "multa", "divergencia"]] = None,
    ordenar: Literal["urgencia", "vigencia", "tema", "tipo"] = "urgencia",
    pagina: int = 1,
    tamanho: int = 50,
    data_referencia: Optional[Union[date, str]] = None,
) -> TriagemResposta:
    """Executa a triagem completa sobre documentos vigentes (substituido = False)."""
    data_ref = obter_data_referencia(data_referencia)

    # Documentos vigentes apenas
    docs_vigentes = [d for d in acervo.documentos if not d.substituido]

    itens_candidatos: List[Tuple[ItemTriagem, Dict[str, Any]]] = []

    for doc in docs_vigentes:
        # Filtro rápido por tema e tipo antes de montar ficha
        if tema is not None and doc.assunto.lower() != tema.strip().lower():
            continue
        if tipo is not None and doc.tipo.upper() != tipo.strip().upper():
            continue

        ficha = obter_ficha_fn(doc, acervo, perfil)
        item, meta = montar_item_triagem(doc, ficha, data_ref=data_ref)

        # Filtro por situação do semáforo
        if situacao is not None and item.semaforo.nivel != situacao:
            continue

        # Filtro por sinal
        if sinal is not None:
            if sinal == "prazo_30d":
                if not (item.proximo_prazo and meta["dias_prz"] is not None and 0 <= meta["dias_prz"] <= 30):
                    continue
            elif sinal == "multa":
                if not item.sinais.multa:
                    continue
            elif sinal == "divergencia":
                if not item.sinais.divergencia:
                    continue

        itens_candidatos.append((item, meta))

    # Ordenação determinística
    if ordenar == "urgencia":
        itens_candidatos.sort(key=lambda x: (x[1]["cat"], x[1]["cat_dias"], x[0].codigo))
    elif ordenar == "vigencia":
        itens_candidatos.sort(key=lambda x: (x[1]["vigencia"], x[0].codigo))
    elif ordenar == "tema":
        itens_candidatos.sort(key=lambda x: (x[0].tema.lower(), x[0].codigo))
    elif ordenar == "tipo":
        itens_candidatos.sort(key=lambda x: (x[0].tipo.lower(), x[0].codigo))

    total = len(itens_candidatos)
    pedem_acao = sum(1 for it, _ in itens_candidatos if it.semaforo.nivel != "ok")

    if limite is not None:
        itens_paginados = [it for it, _ in itens_candidatos[:limite]]
        tamanho_resposta = limite
        pagina_resposta = 1
    else:
        inicio = (pagina - 1) * tamanho
        fim = inicio + tamanho
        itens_paginados = [it for it, _ in itens_candidatos[inicio:fim]]
        tamanho_resposta = tamanho
        pagina_resposta = pagina

    return TriagemResposta(
        total=total,
        pagina=pagina_resposta,
        tamanho=tamanho_resposta,
        pedem_acao=pedem_acao,
        itens=itens_paginados,
    )
