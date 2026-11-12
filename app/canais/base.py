"""Interface comum dos canais: receber mensagem → chamar a API → cartão neutro.

Os adaptadores (Slack, Teams) usam `ServicoCanais` e só renderizam o `Cartao`.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol

from app.canais.cartao import Cartao, montar_cartao, montar_cartoes_radar
from app.canais.cliente_api import ClienteAPI, ErroAPI

__all__ = ["Comando", "ServicoCanais", "Renderizador", "interpretar", "ErroAPI"]

_RADAR = re.compile(r"^radar\b\s*(.*)$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class Comando:
    tipo: str  # "perguntar" | "radar" | "vazio"
    texto: str = ""


def interpretar(texto: Optional[str]) -> Comando:
    """`radar [tema]` → radar; qualquer outro texto → pergunta."""
    texto = (texto or "").strip()
    if not texto:
        return Comando("vazio")
    m = _RADAR.match(texto)
    if m:
        return Comando("radar", m.group(1).strip())
    return Comando("perguntar", texto)


class Renderizador(Protocol):
    """O que cada canal implementa: transformar cartões no payload do canal."""

    canal: str

    def renderizar(self, cartoes: List[Cartao]) -> object: ...


class ServicoCanais:
    def __init__(self, api: Optional[ClienteAPI] = None, painel_url: Optional[str] = None):
        self.api = api or ClienteAPI()
        self.painel_url = painel_url

    def perguntar(self, pergunta: str, perfil: Optional[str] = None) -> Cartao:
        return montar_cartao(self.api.perguntar(pergunta, perfil), self.painel_url)

    def radar(self, tema: Optional[str] = None) -> List[Cartao]:
        return montar_cartoes_radar(self.api.radar(tema or None), self.painel_url)

    def receber(self, texto: Optional[str], perfil: Optional[str] = None) -> List[Cartao]:
        """Ponto de entrada único dos canais. Levanta `ErroAPI` se a API falhar."""
        cmd = interpretar(texto)
        if cmd.tipo == "radar":
            return self.radar(cmd.texto)
        if cmd.tipo == "perguntar":
            return [self.perguntar(cmd.texto, perfil)]
        return []

    def avaliar(self, resposta_id: str, util: bool, canal: str) -> dict:
        return self.api.avaliar(resposta_id, util, canal)
