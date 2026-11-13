"""Agente do Teams (S2, RF33) com o Microsoft 365 Agents SDK.

O canal é só apresentação: o texto, as citações, os avisos e a próxima ação
vêm de ``POST /api/perguntar``, viram o cartão neutro de ``canais/cartao.py``
(o mesmo do Slack) e o adaptador apenas converte esse cartão em Adaptive Card.
Os botões Útil / Não útil gravam em ``POST /api/avaliacoes`` com ``canal: teams``.

Rodar localmente (modo anônimo, para o Microsoft 365 Agents Playground):

    python -m app.canais.teams      # escuta em http://localhost:3978/api/messages

Configuração só por variável de ambiente (ver ``.env.example``):
``API_URL``, ``PAINEL_URL``, ``TEAMS_PORTA``, ``TEAMS_PERFIL`` e, para publicar
no tenant (plano de 6 meses), ``CLIENT_ID``, ``CLIENT_SECRET``, ``TENANT_ID``.
Sem ``CLIENT_ID`` o agente aceita requisições anônimas (Playground).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx

from app.canais.cartao import (
    MAX_ITENS_RADAR,
    ORDEM_SEVERIDADE,
    Cartao,
    CitacaoCartao,
    montar_cartao,
    montar_cartoes_radar,
)
from app.canais.cliente_api import ErroAPI, cabecalhos_api

logger = logging.getLogger(__name__)

CANAL = "teams"
ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
ADAPTIVE_CARD_VERSION = "1.5"
MAX_TRECHO = 200

# Textos de estado da camada de canais (FLUXO-DE-TELAS-v2 §3). Não são respostas:
# o conteúdo das respostas vem sempre da API.
TEXTO_RESPONDENDO = "Consultando o acervo…"
TEXTO_AVALIACAO_REGISTRADA = "Obrigado. Sua avaliação ajuda a melhorar as respostas."
TEXTO_API_FORA = (
    "Não consegui consultar o acervo agora. Tente de novo em alguns segundos "
    "ou use o painel: {painel_url}."
)
TEXTO_PERGUNTA_RECUSADA = (
    "A API do acervo não aceitou esta pergunta. Reformule de forma mais curta e "
    "objetiva e envie de novo."
)
TEXTO_AVALIACAO_RECUSADA = "Não consegui registrar esta avaliação. Ela pode já ter expirado."
TEXTO_RADAR_VAZIO = "O radar não tem itens para o tema “{tema}”."
TEXTO_RADAR_VAZIO_GERAL = "O radar não tem itens no momento."
TEXTO_AJUDA = (
    "Envie sua pergunta direto, ou use `acervo <pergunta>` ou `acervo radar [tema]`."
)


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Config:
    api_url: str = "http://localhost:8000"
    painel_url: str = "http://localhost:5173"
    porta: int = 3978
    perfil: Optional[str] = None
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""

    @classmethod
    def do_ambiente(cls, env: Optional[Dict[str, str]] = None) -> "Config":
        env = os.environ if env is None else env
        padrao = cls()
        return cls(
            api_url=(env.get("API_URL") or padrao.api_url).rstrip("/"),
            painel_url=(env.get("PAINEL_URL") or padrao.painel_url).rstrip("/"),
            porta=int(env.get("TEAMS_PORTA") or padrao.porta),
            perfil=env.get("TEAMS_PERFIL") or None,
            client_id=env.get("CLIENT_ID", ""),
            client_secret=env.get("CLIENT_SECRET", ""),
            tenant_id=env.get("TENANT_ID", ""),
        )

    @property
    def anonimo(self) -> bool:
        return not self.client_id


# --------------------------------------------------------------------------- #
# Interpretação da mensagem
# --------------------------------------------------------------------------- #

_PREFIXO = re.compile(r"^\s*/?acervo\b[\s:,-]*", re.IGNORECASE)
_MENCAO = re.compile(r"<at>.*?</at>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class Comando:
    tipo: str  # "perguntar" | "radar" | "ajuda"
    argumento: str = ""


def interpretar(texto: Optional[str]) -> Comando:
    """`acervo <pergunta>`, `acervo radar [tema]`, `acervo ajuda` ou a pergunta direta."""
    limpo = _MENCAO.sub(" ", texto or "").strip()
    limpo = _PREFIXO.sub("", limpo, count=1).strip()
    if not limpo or limpo.lower() == "ajuda":
        return Comando("ajuda")
    partes = limpo.split(maxsplit=1)
    if partes[0].lower() == "radar":
        return Comando("radar", partes[1].strip() if len(partes) > 1 else "")
    return Comando("perguntar", limpo)


# --------------------------------------------------------------------------- #
# Cliente da API do acervo
# --------------------------------------------------------------------------- #


def api_fora(erro: ErroAPI) -> bool:
    """Sem status (conexão/timeout) ou 5xx: a API está fora. 4xx: o pedido foi recusado."""
    return erro.status is None or erro.status >= 500


class ClienteAcervo:
    """Chama a API FastAPI do acervo. O ``transport`` permite testes sem rede.

    Falhas viram ``ErroAPI`` (o mesmo da camada comum); ``status`` é ``None``
    quando a API não respondeu.
    """

    def __init__(self, api_url: str, transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 10.0):
        self._api_url = api_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api_url, transport=self._transport, timeout=self._timeout, headers=cabecalhos_api()
        )

    async def _requisitar(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        try:
            async with self._cliente() as cliente:
                resp = await cliente.request(metodo, caminho, **kwargs)
        except httpx.HTTPError as exc:
            raise ErroAPI(f"API indisponível em {self._api_url}: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ErroAPI(f"{metodo} {caminho} → {resp.status_code}: {resp.text[:300]}", status=resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            raise ErroAPI(f"{metodo} {caminho} → resposta sem JSON", status=502) from exc

    async def perguntar(self, pergunta: str, perfil: Optional[str]) -> Dict[str, Any]:
        return await self._requisitar("POST", "/api/perguntar", json={"pergunta": pergunta, "perfil": perfil})

    async def avaliar(self, resposta_id: str, util: bool, perfil: Optional[str]) -> Dict[str, Any]:
        corpo = {"resposta_id": resposta_id, "util": util, "canal": CANAL, "perfil": perfil}
        return await self._requisitar("POST", "/api/avaliacoes", json=corpo)

    async def radar(self) -> List[Dict[str, Any]]:
        """Itens de ``GET /api/radar`` (``RadarResponse.itens``)."""
        dados = await self._requisitar("GET", "/api/radar")
        if isinstance(dados, dict):
            dados = dados.get("itens", [])
        return list(dados or [])


# --------------------------------------------------------------------------- #
# Adaptive Cards
# --------------------------------------------------------------------------- #


def _cortar(texto: str, limite: int = MAX_TRECHO) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def rotulo_citacao(c: CitacaoCartao) -> str:
    """``NG_111 · v3.0.0 · Anexo C`` (RNF14)."""
    return c.referencia


def link_pergunta(painel_url: str, pergunta: str) -> str:
    return f"{painel_url}/perguntar?{urlencode({'q': pergunta})}"


def link_documento(painel_url: str, c: CitacaoCartao) -> str:
    codigo = quote(c.codigo, safe="")
    versao = urlencode({"versao": c.versao})
    secao = quote(c.secao, safe="")
    return f"{painel_url}/documento/{codigo}?{versao}#secao-{secao}"


def link_radar(painel_url: str, tema: str = "", item_id: Optional[str] = None) -> str:
    if item_id:
        return f"{painel_url}/radar?{urlencode({'item': item_id})}"
    return f"{painel_url}/radar" + (f"?{urlencode({'tema': tema})}" if tema else "")


def _card(corpo: List[Dict[str, Any]], acoes: List[Dict[str, Any]]) -> Dict[str, Any]:
    card: Dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": ADAPTIVE_CARD_VERSION,
        "body": corpo,
    }
    if acoes:
        card["actions"] = acoes
    return card


def _texto(texto: str, **extra: Any) -> Dict[str, Any]:
    return {"type": "TextBlock", "text": texto, "wrap": True, **extra}


def _bloco_citacao(c: CitacaoCartao, painel_url: str) -> Dict[str, Any]:
    itens = [_texto(f"[{rotulo_citacao(c)}]({link_documento(painel_url, c)})", weight="Bolder", spacing="None")]
    if c.selo:
        itens.append(_texto(c.selo, isSubtle=True, size="Small", spacing="None"))
    if c.trecho:
        itens.append(_texto(_cortar(c.trecho), size="Small", spacing="None"))
    return {"type": "Container", "style": "emphasis", "spacing": "Medium", "items": itens}


def adaptive_card(cartao: Cartao, pergunta: str, painel_url: str, perfil: Optional[str] = None) -> Dict[str, Any]:
    """Traduz o cartão neutro (``canais/cartao.py``) em Adaptive Card, sem acrescentar conteúdo."""
    corpo: List[Dict[str, Any]] = [
        # 1. Conclusão
        _texto(cartao.conclusao, weight="Bolder", size="Medium"),
    ]
    # 2. Citações (o cartão neutro já limita a 3; trecho ≤ 200 caracteres no Teams)
    corpo.extend(_bloco_citacao(c, painel_url) for c in cartao.citacoes)
    # 3. Avisos
    corpo.extend(_texto(f"⚠️ {aviso}", color="Warning") for aviso in cartao.avisos)
    # 4. Próxima ação
    if cartao.proxima_acao:
        corpo.append(_texto(f"Próxima ação: {cartao.proxima_acao}", spacing="Medium"))

    # 5. Botões
    acoes: List[Dict[str, Any]] = [
        {"type": "Action.OpenUrl", "title": "Abrir no painel", "url": link_pergunta(painel_url, pergunta)},
    ]
    for b in cartao.botoes:
        acoes.append({
            "type": "Action.Submit",
            "title": b.rotulo,
            "data": {"acao": "avaliar", "resposta_id": b.resposta_id, "util": b.util, "perfil": perfil},
        })
    return _card(corpo, acoes)


def cartao_resposta(resposta: Dict[str, Any], pergunta: str, painel_url: str, perfil: Optional[str] = None) -> Dict[str, Any]:
    """Resposta de ``/api/perguntar`` → cartão neutro → Adaptive Card."""
    return adaptive_card(montar_cartao(resposta, painel_url), pergunta, painel_url, perfil)


def normalizar(texto: str) -> str:
    """Minúsculas sem diacríticos (NFKD): ``Férias`` → ``ferias``."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in decomposto if not unicodedata.combining(ch)).casefold().strip()


def _tema_do_item(item: Dict[str, Any]) -> str:
    tema = item.get("tema")
    if isinstance(tema, dict):
        return " ".join(str(v) for v in (tema.get("assunto"), tema.get("serie_nome")) if v)
    return str(tema or "")


def filtrar_radar(itens: List[Dict[str, Any]], tema: str) -> List[Dict[str, Any]]:
    """O filtro de tema é do canal (RF37). Acentos e caixa são ignorados nos dois lados."""
    alvo = normalizar(tema)
    if not alvo:
        return list(itens)
    return [i for i in itens if alvo in normalizar(_tema_do_item(i))]


def _mais_severos(itens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mesma seleção de ``montar_cartoes_radar`` (ordenação estável), para casar cada cartão com o id do item."""
    ordenados = sorted(itens, key=lambda i: ORDEM_SEVERIDADE.get(i.get("severidade", "media"), 1))
    return ordenados[:MAX_ITENS_RADAR]


def cartao_radar(itens: List[Dict[str, Any]], tema: str, painel_url: str) -> Dict[str, Any]:
    """Itens do radar → cartões neutros → um bloco por item, com explicação, fontes e link para o T5."""
    selecionados = _mais_severos(itens)
    cartoes = montar_cartoes_radar({"itens": selecionados}, painel_url)
    corpo: List[Dict[str, Any]] = []
    for item, cartao in zip(selecionados, cartoes):
        blocos = [_texto(cartao.titulo or str(item.get("id", "")), weight="Bolder")]
        if cartao.conclusao:
            blocos.append(_texto(cartao.conclusao, size="Small", spacing="None"))
        for c in cartao.citacoes:
            linha = rotulo_citacao(c)
            blocos.append(_texto(f"{linha} ({c.selo})" if c.selo else linha, isSubtle=True, size="Small", spacing="None"))
        if item.get("id"):
            blocos.append(_texto(f"[Ver lado a lado]({link_radar(painel_url, item_id=str(item['id']))})", size="Small"))
        corpo.append({"type": "Container", "style": "emphasis", "spacing": "Medium", "items": blocos})
    if not corpo:
        vazio = TEXTO_RADAR_VAZIO.format(tema=tema) if tema else TEXTO_RADAR_VAZIO_GERAL
        corpo.append(_texto(vazio))
    acoes = [{"type": "Action.OpenUrl", "title": "Abrir no painel", "url": link_radar(painel_url, tema)}]
    return _card(corpo, acoes)


def anexo(card: Dict[str, Any]) -> Dict[str, Any]:
    return {"contentType": ADAPTIVE_CARD_CONTENT_TYPE, "content": card}


# --------------------------------------------------------------------------- #
# Lógica do turno (independe do SDK, para testar sem rede)
# --------------------------------------------------------------------------- #


Saida = Tuple[str, Any]  # ("texto", str) | ("cartao", dict)


class AgenteAcervo:
    def __init__(self, cliente: ClienteAcervo, config: Config):
        self.cliente = cliente
        self.config = config

    def _api_fora(self) -> Saida:
        return ("texto", TEXTO_API_FORA.format(painel_url=self.config.painel_url))

    def _erro(self, erro: ErroAPI, texto_recusado: str) -> Saida:
        if api_fora(erro):
            logger.error("API do acervo fora: %s", erro)
            return self._api_fora()
        logger.warning("API do acervo recusou o pedido: %s", erro)
        return ("texto", texto_recusado)

    async def avaliar(self, valor: Dict[str, Any]) -> List[Saida]:
        try:
            await self.cliente.avaliar(
                resposta_id=str(valor["resposta_id"]),
                util=bool(valor.get("util")),
                perfil=valor.get("perfil") or self.config.perfil,
            )
        except ErroAPI as erro:
            return [self._erro(erro, TEXTO_AVALIACAO_RECUSADA)]
        return [("texto", TEXTO_AVALIACAO_REGISTRADA)]

    async def responder(self, comando: Comando) -> List[Saida]:
        if comando.tipo == "ajuda":
            return [("texto", TEXTO_AJUDA)]
        try:
            if comando.tipo == "radar":
                itens = await self.cliente.radar()
                return [("cartao", cartao_radar(filtrar_radar(itens, comando.argumento),
                                                 comando.argumento, self.config.painel_url))]
            resposta = await self.cliente.perguntar(comando.argumento, self.config.perfil)
        except ErroAPI as erro:
            return [self._erro(erro, TEXTO_PERGUNTA_RECUSADA)]
        return [("cartao", cartao_resposta(resposta, comando.argumento, self.config.painel_url, self.config.perfil))]


# --------------------------------------------------------------------------- #
# Integração com o Microsoft 365 Agents SDK
# --------------------------------------------------------------------------- #


def _para_atividade(saida: Saida):
    from microsoft_agents.activity import Activity, ActivityTypes, Attachment

    tipo, conteudo = saida
    if tipo == "cartao":
        return Activity(
            type=ActivityTypes.message,
            attachments=[Attachment(content_type=ADAPTIVE_CARD_CONTENT_TYPE, content=conteudo)],
        )
    return Activity(type=ActivityTypes.message, text=conteudo)


async def tratar_turno(context, agente: AgenteAcervo) -> None:
    """Trata uma atividade ``message``: clique de botão (``value``) ou texto."""
    atividade = context.activity
    valor = atividade.value if isinstance(getattr(atividade, "value", None), dict) else None

    if valor and valor.get("acao") == "avaliar" and valor.get("resposta_id"):
        saidas = await agente.avaliar(valor)
    else:
        comando = interpretar(atividade.text)
        if comando.tipo != "ajuda":
            # Confirmação imediata (< 3 s); a resposta segue em outra mensagem.
            await context.send_activity(TEXTO_RESPONDENDO)
        saidas = await agente.responder(comando)

    for saida in saidas:
        await context.send_activity(_para_atividade(saida))


def criar_conexoes(config: Config):
    from microsoft_agents.authentication.msal import MsalConnectionManager
    from microsoft_agents.hosting.core import AgentAuthConfiguration

    auth = AgentAuthConfiguration(
        client_id=config.client_id or None,
        client_secret=config.client_secret or None,
        tenant_id=config.tenant_id or None,
        anonymous_allowed=config.anonimo,
    )
    return MsalConnectionManager(connections_configurations={"SERVICE_CONNECTION": auth}), auth


def criar_agent_app(agente: AgenteAcervo, conexoes):
    from microsoft_agents.hosting.aiohttp import CloudAdapter
    from microsoft_agents.hosting.core import AgentApplication, MemoryStorage, TurnContext, TurnState

    adapter = CloudAdapter(connection_manager=conexoes)
    agent_app = AgentApplication[TurnState](
        storage=MemoryStorage(), adapter=adapter, connection_manager=conexoes
    )

    @agent_app.conversation_update("membersAdded")
    async def _boas_vindas(context: TurnContext, _state: TurnState):
        for membro in context.activity.members_added or []:
            if membro.id != context.activity.recipient.id:
                await context.send_activity(TEXTO_AJUDA)

    @agent_app.activity("message")
    async def _mensagem(context: TurnContext, _state: TurnState):
        await tratar_turno(context, agente)

    return agent_app, adapter


async def validar_corpo(request) -> Optional[str]:
    """Motivo do 400 se o corpo não for uma atividade válida; ``None`` se estiver ok."""
    from microsoft_agents.activity import Activity
    from pydantic import ValidationError

    try:
        corpo = await request.json()
    except (ValueError, UnicodeDecodeError):
        return "corpo não é JSON"
    if not isinstance(corpo, dict):
        return "corpo deve ser um objeto JSON"
    faltando = [c for c in ("type", "serviceUrl", "conversation") if not corpo.get(c)]
    if faltando:
        return "atividade sem " + ", ".join(faltando)
    if not isinstance(corpo["conversation"], dict) or not corpo["conversation"].get("id"):
        return "atividade sem conversation.id"
    try:
        Activity.model_validate(corpo)
    except ValidationError:
        return "atividade inválida"
    return None


def criar_app(config: Optional[Config] = None, cliente: Optional[ClienteAcervo] = None):
    """Aplicação aiohttp com ``POST /api/messages``."""
    from aiohttp import web
    from microsoft_agents.hosting.aiohttp import jwt_authorization_middleware, start_agent_process

    config = config or Config.do_ambiente()
    cliente = cliente or ClienteAcervo(config.api_url)
    conexoes, auth = criar_conexoes(config)
    agent_app, adapter = criar_agent_app(AgenteAcervo(cliente, config), conexoes)

    async def mensagens(request: web.Request) -> web.Response:
        erro = await validar_corpo(request)
        if erro:
            return web.json_response({"erro": erro}, status=400)
        resposta = await start_agent_process(request, agent_app, adapter)
        return resposta if resposta is not None else web.Response(status=202)

    app = web.Application(middlewares=[jwt_authorization_middleware])
    app.router.add_post("/api/messages", mensagens)
    app["agent_configuration"] = auth
    return app


def main() -> None:
    from aiohttp import web

    logging.basicConfig(level=logging.INFO)
    config = Config.do_ambiente()
    modo = "anônimo (Agents Playground)" if config.anonimo else "autenticado"
    logger.info("Agente Teams em http://localhost:%s/api/messages · modo %s · API %s",
                config.porta, modo, config.api_url)
    web.run_app(criar_app(config), host="localhost", port=config.porta)


if __name__ == "__main__":
    main()
