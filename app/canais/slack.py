"""Adaptador Slack (Bolt for Python, Socket Mode) — Issue #9.

- `/acervo <pergunta>` → `POST /api/perguntar` → cartão neutro em Block Kit.
- `/acervo radar [perspectiva]` → `GET /api/radar` → até 3 itens mais severos, com fontes.
- Botões Útil/Não útil → `POST /api/avaliacoes` com `canal: slack`.

Execução: `python -m app.canais.slack` (variáveis em `.env`, ver `.env.example`).
Tokens só por variável de ambiente: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from app.canais.base import ServicoCanais
from app.canais.cartao import BOTOES_AVALIACAO, Cartao
from app.canais.cliente_api import ErroAPI

CANAL = "slack"
COMANDO = "/acervo"
ACOES_AVALIACAO = {acao: util for acao, _, util in BOTOES_AVALIACAO}

# Mensagens de interface (estado do bot), nunca conteúdo de resposta
MSG_CONSULTANDO = "Consultando o acervo…"
MSG_USO = "Uso: `/acervo <pergunta>` ou `/acervo radar [perspectiva]`."
MSG_API_FORA = "Não consegui falar com a API do acervo agora. Tente de novo em instantes."
MSG_RECUSADO = "A API do acervo recusou o pedido: {detalhe}"
MSG_SEM_ITENS = "O radar não retornou itens para este filtro."
MSG_AVALIADO = {True: "Avaliação registrada: útil. Obrigado!", False: "Avaliação registrada: não útil. Obrigado!"}

LIMITE_TEXTO = 2900  # Slack: 3000 caracteres por bloco de texto
LIMITE_BLOCOS = 50  # Slack: máximo de blocos por mensagem

log = logging.getLogger(__name__)


def _esc(texto: str) -> str:
    """Escapa caracteres de controle do mrkdwn do Slack."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _corta(texto: str, limite: int = LIMITE_TEXTO) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _section(texto: str) -> Dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": _corta(texto)}}


def _context(texto: str) -> Dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": _corta(texto)}]}


def blocos_cartao(cartao: Cartao) -> List[Dict[str, Any]]:
    """Traduz o cartão neutro para Block Kit sem acrescentar conteúdo."""
    blocos: List[Dict[str, Any]] = []
    if cartao.titulo:
        blocos.append(_section(f"*{_esc(cartao.titulo)}*"))
    blocos.append(_section(_esc(cartao.conclusao)))

    for c in cartao.citacoes:
        selo = f"`{_esc(c.selo)}` " if c.selo else ""
        blocos.append(_section(f"{selo}*{_esc(c.referencia)}*\n> {_esc(c.trecho)}"))

    for aviso in cartao.avisos:
        blocos.append(_context(f":warning: {_esc(aviso)}"))

    if cartao.proxima_acao:
        blocos.append(_context(f":arrow_right: {_esc(cartao.proxima_acao)}"))

    elementos: List[Dict[str, Any]] = [
        {
            "type": "button",
            "action_id": b.acao,
            "text": {"type": "plain_text", "text": b.rotulo},
            "value": b.resposta_id,
        }
        for b in cartao.botoes
    ]
    if cartao.link_painel:
        elementos.append(
            {
                "type": "button",
                "action_id": "abrir_painel",
                "text": {"type": "plain_text", "text": "Abrir no painel"},
                "url": cartao.link_painel,
            }
        )
    if elementos:
        blocos.append({"type": "actions", "elements": elementos})
    return blocos


def renderizar(cartoes: List[Cartao]) -> Dict[str, Any]:
    """Payload de mensagem do Slack (`blocks` + `text` de fallback para notificações)."""
    # Respeita o limite de blocos descartando cartões inteiros, para que nenhum
    # cartão perca citações ou botões no corte.
    blocos: List[Dict[str, Any]] = []
    for i, cartao in enumerate(cartoes):
        novos = ([{"type": "divider"}] if i else []) + blocos_cartao(cartao)
        if blocos and len(blocos) + len(novos) > LIMITE_BLOCOS:
            break
        blocos.extend(novos)
    texto = (cartoes[0].titulo or cartoes[0].conclusao) if cartoes else ""
    return {"text": _corta(texto), "blocks": blocos[:LIMITE_BLOCOS]}


def _mensagem_erro(e: ErroAPI) -> str:
    """4xx → detalhe vindo da própria API; falha de rede/5xx → API indisponível."""
    if e.recusado and e.detalhe:
        return MSG_RECUSADO.format(detalhe=_esc(_corta(e.detalhe, 500)))
    return MSG_API_FORA


class SlackRenderizador:
    canal = CANAL

    def renderizar(self, cartoes: List[Cartao]) -> Dict[str, Any]:
        return renderizar(cartoes)


# ---------------------------------------------------------------------------
# Handlers (funções puras sobre ack/respond, testáveis sem Slack)
# ---------------------------------------------------------------------------

def tratar_comando(servico: ServicoCanais, ack: Callable, respond: Callable, command: Dict[str, Any]) -> None:
    texto = (command.get("text") or "").strip()
    if not texto:
        ack(MSG_USO)
        return
    # Slack exige ack em < 3 s; a consulta segue depois.
    ack(MSG_CONSULTANDO)
    try:
        cartoes = servico.receber(texto)
    except ErroAPI as e:
        log.warning("Falha na API do acervo: %s", e)
        respond(text=_mensagem_erro(e), replace_original=False)
        return
    if not cartoes:
        respond(text=MSG_SEM_ITENS, replace_original=False)
        return
    respond(**renderizar(cartoes), replace_original=False)


def tratar_avaliacao(servico: ServicoCanais, ack: Callable, respond: Callable, body: Dict[str, Any]) -> None:
    ack()
    acao = body["actions"][0]
    util = ACOES_AVALIACAO[acao["action_id"]]
    try:
        servico.avaliar(acao["value"], util, CANAL)
    except ErroAPI as e:
        log.warning("Falha ao registrar avaliação: %s", e)
        respond(text=_mensagem_erro(e), replace_original=False, response_type="ephemeral")
        return
    respond(text=MSG_AVALIADO[util], replace_original=False, response_type="ephemeral")


def registrar_handlers(app: Any, servico: ServicoCanais) -> Any:
    """Liga os handlers a um `slack_bolt.App` (ou objeto compatível)."""

    @app.command(COMANDO)
    def _comando(ack, respond, command):
        tratar_comando(servico, ack, respond, command)

    for acao in ACOES_AVALIACAO:

        @app.action(acao)
        def _avaliacao(ack, respond, body):
            tratar_avaliacao(servico, ack, respond, body)

    @app.action("abrir_painel")
    def _painel(ack):
        ack()

    return app


def _carregar_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv é opcional; variáveis do shell continuam valendo
        return
    load_dotenv()


def _exigir(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise SystemExit(f"Defina {nome} no ambiente ou no .env (ver .env.example).")
    return valor


def criar_app(servico: Optional[ServicoCanais] = None, bot_token: Optional[str] = None):
    from slack_bolt import App

    app = App(token=bot_token or _exigir("SLACK_BOT_TOKEN"))
    return registrar_handlers(app, servico or ServicoCanais())


def main() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    logging.basicConfig(level=logging.INFO)
    _carregar_env()
    app = criar_app()
    SocketModeHandler(app, _exigir("SLACK_APP_TOKEN")).start()


if __name__ == "__main__":
    main()
