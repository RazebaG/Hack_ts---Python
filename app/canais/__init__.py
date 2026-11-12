"""Camada comum de canais (Issue #9: RF27, RF28, RF34, RNF17).

Os canais (Slack, Teams) consomem só a API (`API_URL`) e mostram o mesmo
cartão neutro (`cartao.py`). Cada adaptador apenas traduz esse cartão para o
formato do seu canal; nenhum texto de resposta é escrito aqui.
"""

from app.canais.base import ServicoCanais, ErroAPI
from app.canais.cartao import Botao, Cartao, CitacaoCartao, montar_cartao, montar_cartoes_radar
from app.canais.cliente_api import ClienteAPI

__all__ = [
    "Botao",
    "Cartao",
    "CitacaoCartao",
    "ClienteAPI",
    "ErroAPI",
    "ServicoCanais",
    "montar_cartao",
    "montar_cartoes_radar",
]
