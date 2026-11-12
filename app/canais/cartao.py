"""Cartão neutro, comum a todos os canais (RF27, RF28, RF34).

Função única que transforma a saída da API em um cartão independente de canal:
conclusão, até 3 citações com selo curto de camada (`SIGLA · Grupo`), avisos,
próxima ação, link para o painel e botões Útil/Não útil.

Todo o conteúdo vem da API; aqui só se seleciona e organiza.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_CITACOES = 3
MAX_ITENS_RADAR = 3
ORDEM_SEVERIDADE = {"alta": 0, "media": 1, "baixa": 2}

# Rótulos de interface (não são respostas): ação → (rótulo, util)
BOTOES_AVALIACAO = (("avaliacao_util", "Útil", True), ("avaliacao_nao_util", "Não útil", False))


@dataclass(frozen=True)
class CitacaoCartao:
    codigo: str
    versao: str
    secao: str
    trecho: str
    selo: Optional[str] = None  # camada curta, ex.: "PX · Normativo"

    @property
    def referencia(self) -> str:
        return f"{self.codigo} · v{self.versao} · {self.secao}"


@dataclass(frozen=True)
class Botao:
    acao: str
    rotulo: str
    util: bool
    resposta_id: str


@dataclass(frozen=True)
class Cartao:
    conclusao: str
    consta: bool = True
    titulo: Optional[str] = None
    citacoes: List[CitacaoCartao] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    proxima_acao: Optional[str] = None
    link_painel: Optional[str] = None
    resposta_id: Optional[str] = None
    botoes: List[Botao] = field(default_factory=list)


def selo_camada(camada: Optional[Dict[str, Any]]) -> Optional[str]:
    """Formato curto de canal (Adendo v0.3, RNF14): `SIGLA · Grupo`."""
    if not camada or not camada.get("sigla") or not camada.get("grupo"):
        return None
    return f"{camada['sigla']} · {camada['grupo']}"


def _citacao(dado: Dict[str, Any]) -> CitacaoCartao:
    return CitacaoCartao(
        codigo=dado["codigo"],
        versao=dado["versao"],
        secao=dado["secao"],
        trecho=dado.get("trecho", ""),
        selo=selo_camada(dado.get("camada")),
    )


def _painel(painel_url: Optional[str]) -> Optional[str]:
    url = painel_url if painel_url is not None else os.getenv("PAINEL_URL")
    return url or None


def montar_cartao(resposta: Dict[str, Any], painel_url: Optional[str] = None) -> Cartao:
    """Cartão neutro de uma resposta de `POST /api/perguntar`."""
    consta = bool(resposta.get("consta", True))
    resposta_id = resposta.get("resposta_id")
    citacoes = [_citacao(c) for c in resposta.get("citacoes", [])[:MAX_CITACOES]] if consta else []
    botoes = (
        [Botao(acao=a, rotulo=r, util=u, resposta_id=resposta_id) for a, r, u in BOTOES_AVALIACAO]
        if resposta_id
        else []
    )
    return Cartao(
        conclusao=resposta.get("resposta", ""),
        consta=consta,
        citacoes=citacoes,
        avisos=list(resposta.get("avisos", [])),
        proxima_acao=resposta.get("proxima_acao"),
        link_painel=_painel(painel_url),
        resposta_id=resposta_id,
        botoes=botoes,
    )


def montar_cartoes_radar(radar: Dict[str, Any], painel_url: Optional[str] = None) -> List[Cartao]:
    """Os 3 itens mais severos de `GET /api/radar`, cada um como cartão com suas fontes."""
    itens = sorted(radar.get("itens", []), key=lambda i: ORDEM_SEVERIDADE.get(i.get("severidade", "media"), 1))
    link = _painel(painel_url)
    return [
        Cartao(
            titulo=item.get("titulo"),
            conclusao=item.get("explicacao", ""),
            citacoes=[_citacao(f) for f in item.get("fontes", [])[:MAX_CITACOES]],
            link_painel=link,
        )
        for item in itens[:MAX_ITENS_RADAR]
    ]
