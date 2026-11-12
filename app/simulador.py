"""Simulador "E se?" (Issue #8, Adendo v0.2).

Cálculo determinístico, sem IA. O arquivo de regras (data/simulador/regras.yaml)
só aponta onde cada regra está; valores, marcos, datas, faixas de alçada e trechos
são lidos do texto dos documentos vigentes do acervo.

Tipos de regra:
- prazo_dias: a seção da regra e as irmãs dela (ex.: NG_111 §4.5.x) formam a linha do
  tempo "N dias antes do início"; a data de referência vem do exemplo citado.
- alcada_valor: quadro "faixa de valor x quem aprova" (ex.: NT_2026-018 Anexo F);
  os valores sujeitos à alçada são lidos dos outros documentos vigentes do assunto.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import yaml
from fastapi import HTTPException

from app.acervo import AcervoRepository, get_acervo
from app.models import (
    DocumentoDetalhe,
    Fonte,
    ImpactoSimulado,
    MarcoSimulado,
    Regra,
    Secao,
    SimularRequest,
    SimularResponse,
)

logger = logging.getLogger(__name__)

Numero = Union[int, float]

# --- Padrões de leitura do texto normativo ------------------------------------
# "até 45 dias antes", "30 dias antes do início", "3 dias corridos antes"
DIAS_ANTES_RE = re.compile(r"(\d+)\s+dias\s+(?:(corridos|úteis)\s+)?antes", re.IGNORECASE)
# Regra de ajuste quando o dia cai em fim de semana: "...sábado, domingo... dia útil anterior"
FIM_DE_SEMANA_RE = re.compile(r"sábado|domingo", re.IGNORECASE)
DIA_UTIL_ANTERIOR_RE = re.compile(r"dia\s+útil\s+anterior", re.IGNORECASE)
DATA_BR_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
DINHEIRO_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")


# --- Utilitários ---------------------------------------------------------------

def _normalizar(texto: str) -> str:
    return " ".join(texto.split())


def _numero(x: Numero) -> Numero:
    return int(x) if float(x).is_integer() else float(x)


def _brl_para_float(valor: str) -> float:
    return float(valor.replace(".", "").replace(",", "."))


def formatar_brl(valor: float) -> str:
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def formatar_data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _primeira_data(texto: str) -> Optional[date]:
    m = DATA_BR_RE.search(texto or "")
    if not m:
        return None
    dia, mes, ano = (int(g) for g in m.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _secao(doc: DocumentoDetalhe, secao_id: str) -> Optional[Secao]:
    return next((s for s in doc.secoes if s.id == secao_id), None)


def _fonte(doc: DocumentoDetalhe, secao_id: str, trecho: str) -> Fonte:
    return Fonte(codigo=doc.codigo, versao=doc.versao, secao=secao_id, trecho=trecho, camada=doc.camada)


def trecho_em_volta(texto: str, inicio: int, fim: int, minimo: int = 40, maximo: int = 280) -> str:
    """Trecho literal (linhas inteiras) em volta de texto[inicio:fim].

    Linhas curtas (células de tabela) ganham as linhas vizinhas para dar contexto.
    Trechos longos são cortados em fronteira de palavra, marcados com "…".
    """
    linhas = texto.split("\n")
    offsets, pos = [], 0
    for linha in linhas:
        offsets.append(pos)
        pos += len(linha) + 1

    def linha_de(p: int) -> int:
        return max(i for i, o in enumerate(offsets) if o <= p)

    ini_l, fim_l = linha_de(inicio), linha_de(max(inicio, fim - 1))
    if len(_normalizar(" ".join(linhas[ini_l : fim_l + 1]))) < minimo:
        anterior = next((i for i in range(ini_l - 1, -1, -1) if linhas[i].strip()), ini_l)
        seguinte = next((i for i in range(fim_l + 1, len(linhas)) if linhas[i].strip()), fim_l)
        ini_l, fim_l = anterior, seguinte
    trecho = _normalizar(" ".join(linhas[ini_l : fim_l + 1]))
    if len(trecho) <= maximo:
        return trecho

    alvo = _normalizar(texto[inicio:fim])
    centro = trecho.find(alvo)
    centro = centro if centro >= 0 else 0
    ini = max(0, centro - (maximo - len(alvo)) // 2)
    fim_c = min(len(trecho), ini + maximo)
    if ini > 0:
        ini = trecho.find(" ", ini) + 1
    if fim_c < len(trecho):
        fim_c = trecho.rfind(" ", ini, fim_c)
    corte = trecho[ini:fim_c]
    return ("… " if ini > 0 else "") + corte + (" …" if fim_c < len(trecho) else "")


def _dia_util_anterior(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _menos_dias_uteis(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _erro_validacao(msg: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", "novo_valor"], "msg": msg, "type": "value_error"}],
    )


# --- Estruturas lidas do acervo ------------------------------------------------

@dataclass
class Marco:
    nome: str
    dias: int
    uteis: bool
    antecipa_fim_de_semana: bool
    fonte: Fonte

    def data(self, inicio: date, dias: Optional[int] = None) -> date:
        n = self.dias if dias is None else dias
        d = _menos_dias_uteis(inicio, n) if self.uteis else inicio - timedelta(days=n)
        return _dia_util_anterior(d) if self.antecipa_fim_de_semana else d


@dataclass
class Faixa:
    papel: str
    minimo: Optional[float]
    maximo: float


@dataclass
class RegraCarregada:
    config: dict
    doc: DocumentoDetalhe
    fonte: Fonte
    valor: Numero
    marcos: Optional[List[Marco]] = None
    exemplo_fonte: Optional[Fonte] = None
    inicio_exemplo: Optional[date] = None
    faixas: Optional[List[Faixa]] = None
    indice_papel: Optional[int] = None

    @property
    def id(self) -> str:
        return self.config["id"]

    @property
    def unidade(self) -> str:
        return self.config.get("unidade", "")


def ler_marcos(doc: DocumentoDetalhe, secao_regra: str) -> List[Marco]:
    """Marcos "N dias antes" da seção da regra e das seções irmãs (mesmo pai)."""
    pai = secao_regra.rsplit(".", 1)[0] if "." in secao_regra else None
    marcos = []
    for s in doc.secoes:
        irma = s.id == secao_regra or (
            pai is not None and s.id.startswith(pai + ".") and "." not in s.id[len(pai) + 1 :]
        )
        if not irma:
            continue
        texto = _normalizar(s.texto)
        m = DIAS_ANTES_RE.search(texto)
        if not m or ":" not in texto:
            continue
        nome = texto.split(":", 1)[0].strip()
        marcos.append(
            Marco(
                nome=nome,
                dias=int(m.group(1)),
                uteis=(m.group(2) or "").lower() == "úteis",
                antecipa_fim_de_semana=bool(FIM_DE_SEMANA_RE.search(texto) and DIA_UTIL_ANTERIOR_RE.search(texto)),
                fonte=_fonte(doc, s.id, texto),
            )
        )
    return marcos


def ler_faixas(texto: str) -> Tuple[List[Faixa], str]:
    """Quadro de alçadas: uma linha com valor(es) em R$ seguida da linha com quem aprova."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    faixas, usadas = [], []
    for i, linha in enumerate(linhas[:-1]):
        valores = DINHEIRO_RE.findall(linha)
        if not valores or linha.endswith(".") or len(linha) > 60:
            continue
        papel = linhas[i + 1]
        if any(ch.isdigit() for ch in papel) or len(papel.split()) > 4:
            continue
        nums = sorted(_brl_para_float(v) for v in valores)
        faixas.append(Faixa(papel=papel, minimo=nums[0] if len(nums) > 1 else None, maximo=nums[-1]))
        usadas.extend([linha, papel])
    return sorted(faixas, key=lambda f: f.maximo), " ".join(usadas)


def aprovador(faixas: List[Faixa], valor: float) -> Optional[str]:
    for f in faixas:
        if (f.minimo is None or valor >= f.minimo) and valor <= f.maximo:
            return f.papel
    return None


# --- Serviço -------------------------------------------------------------------

class SimuladorService:
    def __init__(self, acervo: Optional[AcervoRepository] = None, regras_file: Optional[Path] = None):
        self.acervo = acervo or get_acervo()
        self.regras_file = regras_file or self._descobrir_arquivo()
        self.aviso = ""
        self.regras: Dict[str, RegraCarregada] = {}
        self.carregar()

    @staticmethod
    def _descobrir_arquivo() -> Path:
        env = os.getenv("SIMULADOR_REGRAS")
        if env:
            return Path(env)
        return Path(__file__).resolve().parent.parent / "data" / "simulador" / "regras.yaml"

    def carregar(self) -> None:
        self.regras.clear()
        if not self.regras_file.exists():
            logger.warning("Arquivo de regras do simulador não encontrado: %s", self.regras_file)
            return
        with open(self.regras_file, "r", encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}
        self.aviso = dados.get("aviso", "")
        for cfg in dados.get("regras", []):
            try:
                regra = self._carregar_regra(cfg)
            except ValueError as e:
                logger.warning("Regra %s ignorada: %s", cfg.get("id"), e)
                continue
            self.regras[regra.id] = regra

    def _carregar_regra(self, cfg: dict) -> RegraCarregada:
        ref = cfg["fonte"]
        doc = self.acervo.buscar(ref["codigo"])
        if doc is None or doc.substituido:
            raise ValueError(f"{ref['codigo']} não tem versão vigente no acervo")
        secao = _secao(doc, ref["secao"])
        if secao is None:
            raise ValueError(f"seção {ref['secao']} não existe em {doc.codigo}@{doc.versao}")

        if cfg["tipo"] == "prazo_dias":
            marcos = ler_marcos(doc, secao.id)
            principal = next((m for m in marcos if m.fonte.secao == secao.id), None)
            if principal is None:
                raise ValueError(f"§{secao.id} não fixa um prazo em dias")
            ex_ref = cfg.get("exemplo") or {}
            ex_doc = self.acervo.buscar(ex_ref.get("codigo", "")) if ex_ref else None
            ex_sec = _secao(ex_doc, ex_ref["secao"]) if ex_doc else None
            inicio = _primeira_data(ex_sec.texto) if ex_sec else None
            ex_fonte = None
            if ex_sec and inicio:
                m = DATA_BR_RE.search(ex_sec.texto)
                ex_fonte = _fonte(ex_doc, ex_sec.id, trecho_em_volta(ex_sec.texto, m.start(), m.end()))
            return RegraCarregada(
                config=cfg, doc=doc, fonte=principal.fonte, valor=principal.dias,
                marcos=marcos, exemplo_fonte=ex_fonte, inicio_exemplo=inicio,
            )

        if cfg["tipo"] == "alcada_valor":
            faixas, trecho = ler_faixas(secao.texto)
            papel = cfg["papel"].lower()
            idx = next((i for i, f in enumerate(faixas) if f.papel.lower() == papel), None)
            if idx is None:
                raise ValueError(f"papel {cfg['papel']} não consta do quadro de §{secao.id}")
            return RegraCarregada(
                config=cfg, doc=doc, fonte=_fonte(doc, secao.id, trecho),
                valor=_numero(faixas[idx].maximo), faixas=faixas, indice_papel=idx,
            )

        raise ValueError(f"tipo de regra desconhecido: {cfg['tipo']}")

    # --- API -----------------------------------------------------------------

    def listar_regras(self) -> List[Regra]:
        return [
            Regra(id=r.id, rotulo=r.config["rotulo"], valor=r.valor, unidade=r.unidade, fonte=r.fonte)
            for r in self.regras.values()
        ]

    def simular(self, req: SimularRequest) -> SimularResponse:
        regra = self.regras.get(req.regra)
        if regra is None:
            raise HTTPException(status_code=404, detail=f"Regra '{req.regra}' não encontrada.")
        limites = regra.config.get("limites", {})
        lo, hi = limites.get("min"), limites.get("max")
        if (lo is not None and req.novo_valor < lo) or (hi is not None and req.novo_valor > hi):
            raise _erro_validacao(f"novo_valor deve estar entre {lo} e {hi} {regra.unidade}.")
        if regra.config["tipo"] == "prazo_dias":
            if not float(req.novo_valor).is_integer():
                raise _erro_validacao("novo_valor deve ser um número inteiro de dias.")
            return self._simular_prazo(regra, int(req.novo_valor), req.cenario)
        return self._simular_alcada(regra, float(req.novo_valor), req.cenario)

    # --- Citações do valor vigente em documentos vigentes do mesmo assunto -----

    def _documentos_relacionados(self, regra: RegraCarregada) -> List[DocumentoDetalhe]:
        return [d for d in self.acervo.documentos if not d.substituido and d.assunto == regra.doc.assunto]

    def _revisar_documentos(
        self, regra: RegraCarregada, padroes: List[Tuple[str, re.Pattern]]
    ) -> List[ImpactoSimulado]:
        impactos = []
        for doc in self._documentos_relacionados(regra):
            fontes, citados = [], []
            for s in doc.secoes:
                achados = [(rot, m) for rot, p in padroes for m in [p.search(s.texto)] if m]
                if not achados:
                    continue
                primeiro = min(achados, key=lambda a: a[1].start())[1]
                fontes.append(_fonte(doc, s.id, trecho_em_volta(s.texto, primeiro.start(), primeiro.end())))
                citados.extend(rot for rot, _ in achados if rot not in citados)
            if fontes:
                impactos.append(
                    ImpactoSimulado(
                        tipo="revisar_documento", codigo=doc.codigo, versao=doc.versao,
                        descricao="Cita " + " e ".join(f"“{c}”" for c in citados),
                        fontes=fontes,
                    )
                )
        return impactos

    # --- prazo_dias ------------------------------------------------------------

    def _simular_prazo(self, regra: RegraCarregada, novo: int, cenario: Optional[str]) -> SimularResponse:
        atual = int(regra.valor)
        inicio = _primeira_data(cenario) if cenario else None
        inicio = inicio or regra.inicio_exemplo
        if inicio is None:
            raise HTTPException(status_code=422, detail="Não há data de início no cenário nem no exemplo do acervo.")
        if not cenario and regra.exemplo_fonte:
            ex = regra.exemplo_fonte
            cenario = f"Exemplo {ex.codigo} {ex.secao}: início em {formatar_data_br(inicio)}"

        principal = next(m for m in regra.marcos if m.fonte.secao == regra.fonte.secao)
        linha = []
        for m in regra.marcos:
            dias_depois = novo if m is principal else m.dias
            antes, depois = m.data(inicio), m.data(inicio, dias_depois)
            linha.append(
                MarcoSimulado(
                    marco=m.nome, antes=antes.isoformat(), depois=depois.isoformat(), muda=antes != depois,
                    d_antes=m.dias, d_depois=dias_depois, fonte=m.fonte,
                )
            )

        impactos: List[ImpactoSimulado] = []
        conflitantes: List[Marco] = []
        if novo != atual:
            for m in regra.marcos:
                if m is principal:
                    continue
                vinha_depois = atual > m.dias  # D-maior acontece antes
                inverte = (vinha_depois and novo <= m.dias) or (not vinha_depois and novo >= m.dias)
                if not inverte:
                    continue
                conflitantes.append(m)
                if novo == m.dias:
                    relacao = "cairia no mesmo dia do"
                elif vinha_depois:
                    relacao = "ficaria antes do"
                else:
                    relacao = "ficaria depois do"
                impactos.append(
                    ImpactoSimulado(
                        tipo="conflito_interno",
                        descricao=(
                            f"{m.nome} (D-{m.dias}) {relacao} fim do prazo de "
                            f"{principal.nome.lower()} (D-{novo})."
                        ),
                        fontes=[m.fonte],
                    )
                )
            padroes = [
                (f"{atual} {regra.unidade}", re.compile(rf"\b{atual}[\s|]+{re.escape(regra.unidade)}\b")),
                (f"D-{atual}", re.compile(rf"\bD-{atual}\b")),
            ]
            impactos.extend(self._revisar_documentos(regra, padroes))

        principal_depois = principal.data(inicio, novo)
        if novo == atual:
            resumo = [f"Nada muda: o valor vigente já é {atual} {regra.unidade} ({regra.fonte.codigo} §{regra.fonte.secao})."]
        else:
            resumo = [
                f"{principal.nome} passa de D-{atual} para D-{novo} "
                f"({formatar_data_br(principal_depois)} no exemplo)."
            ]
            if conflitantes:
                resumo.append(
                    "Ficam incompatíveis: " + ", ".join(f"{m.nome} (D-{m.dias})" for m in conflitantes) + "."
                )
            revisar = [i.codigo for i in impactos if i.tipo == "revisar_documento"]
            if revisar:
                resumo.append(
                    f"{len(revisar)} documento(s) vigente(s) citam {atual} {regra.unidade} e exigiriam revisão: "
                    + ", ".join(revisar) + "."
                )

        return SimularResponse(
            regra=regra.id, valor_atual=atual, novo_valor=novo, unidade=regra.unidade,
            cenario=cenario, inicio_gozo=inicio.isoformat(),
            linha_do_tempo=linha, impactos=impactos, resumo=resumo, aviso=self.aviso,
        )

    # --- alcada_valor ----------------------------------------------------------

    def _simular_alcada(self, regra: RegraCarregada, novo: float, cenario: Optional[str]) -> SimularResponse:
        atual = float(regra.valor)
        idx = regra.indice_papel
        papel = regra.faixas[idx].papel
        faixas_novas = [Faixa(f.papel, f.minimo, f.maximo) for f in regra.faixas]
        faixas_novas[idx].maximo = novo
        if idx + 1 < len(faixas_novas):
            faixas_novas[idx + 1].minimo = round(novo + 0.01, 2)

        impactos: List[ImpactoSimulado] = []
        resumo: List[str] = []
        if novo == atual:
            resumo.append(f"Nada muda: o valor vigente já é {formatar_brl(atual)} ({regra.fonte.codigo} §{regra.fonte.secao}).")
        else:
            resumo.append(f"A alçada de {papel} passa de {formatar_brl(atual)} para {formatar_brl(novo)}.")
            seguinte = regra.faixas[idx + 1] if idx + 1 < len(regra.faixas) else None
            if seguinte and novo >= seguinte.maximo:
                impactos.append(
                    ImpactoSimulado(
                        tipo="conflito_interno",
                        descricao=(
                            f"A alçada de {papel} ({formatar_brl(novo)}) alcançaria o teto de "
                            f"{seguinte.papel} ({formatar_brl(seguinte.maximo)})."
                        ),
                        fontes=[regra.fonte],
                    )
                )
            impactos.extend(self._mudancas_de_aprovador(regra, faixas_novas, resumo))
            padroes = [(formatar_brl(atual), re.compile(re.escape(formatar_brl(atual)).replace(r"\ ", r"\s*")))]
            if seguinte and seguinte.minimo is not None:
                limite = formatar_brl(seguinte.minimo)
                padroes.append((limite, re.compile(re.escape(limite).replace(r"\ ", r"\s*"))))
            revisar = self._revisar_documentos(regra, padroes)
            impactos.extend(revisar)
            if revisar:
                resumo.append(
                    f"{len(revisar)} documento(s) vigente(s) citam {formatar_brl(atual)} e exigiriam revisão: "
                    + ", ".join(i.codigo for i in revisar) + "."
                )

        return SimularResponse(
            regra=regra.id, valor_atual=_numero(atual), novo_valor=_numero(novo), unidade=regra.unidade,
            cenario=cenario, impactos=impactos, resumo=resumo, aviso=self.aviso,
        )

    def _mudancas_de_aprovador(
        self, regra: RegraCarregada, faixas_novas: List[Faixa], resumo: List[str]
    ) -> List[ImpactoSimulado]:
        termo = regra.config.get("valor_alvo")
        if not termo:
            return []
        alvo_re = re.compile(
            r"\s+".join(map(re.escape, termo.split())) + r"\W+(?:\w+\W+){0,2}?" + DINHEIRO_RE.pattern,
            re.IGNORECASE,
        )
        impactos = []
        for doc in self._documentos_relacionados(regra):
            if doc.codigo == regra.doc.codigo:
                continue  # o próprio documento da regra entra em revisar_documento
            achado = next(((s, m) for s in doc.secoes for m in [alvo_re.search(s.texto)] if m), None)
            if not achado:
                continue
            s, m = achado
            valor = _brl_para_float(m.group(1))
            antes, depois = aprovador(regra.faixas, valor), aprovador(faixas_novas, valor)
            if antes == depois:
                continue
            impactos.append(
                ImpactoSimulado(
                    tipo="muda_aprovador", codigo=doc.codigo, versao=doc.versao, antes=antes, depois=depois,
                    descricao=f"{termo.capitalize()} de {formatar_brl(valor)}: a aprovação passa de {antes} para {depois}.",
                    fontes=[_fonte(doc, s.id, trecho_em_volta(s.texto, m.start(), m.end())), regra.fonte],
                )
            )
            resumo.append(f"{doc.codigo} ({formatar_brl(valor)}) deixa de exigir {antes} e passa a {depois}.")
        return impactos
