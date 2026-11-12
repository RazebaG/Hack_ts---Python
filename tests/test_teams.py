"""Testes do agente Teams (S2, RF33): SDK simulado e API em processo, sem rede."""

import asyncio
import html
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.canais import ClienteAPI, ServicoCanais, slack, teams
from app.canais.cartao import MAX_CITACOES
from app.canais.teams import (
    ADAPTIVE_CARD_CONTENT_TYPE,
    AgenteAcervo,
    ClienteAcervo,
    Comando,
    Config,
    MAX_TRECHO,
    TEXTO_API_FORA,
    TEXTO_AVALIACAO_RECUSADA,
    TEXTO_AVALIACAO_REGISTRADA,
    TEXTO_PERGUNTA_RECUSADA,
    TEXTO_RADAR_VAZIO,
    TEXTO_RESPONDENDO,
    cartao_radar,
    cartao_resposta,
    filtrar_radar,
    interpretar,
    normalizar,
    tratar_turno,
)
from app.main import app as api

PAINEL = "http://painel.teste"
CONFIG = Config(api_url="http://api.teste", painel_url=PAINEL)
PERGUNTAS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "eval" / "perguntas.yaml").read_text(encoding="utf-8")
)["perguntas"]

web = TestClient(api)


def cliente_api() -> ClienteAcervo:
    """Cliente apontado para a API FastAPI em processo (ASGI), sem rede."""
    return ClienteAcervo(CONFIG.api_url, transport=httpx.ASGITransport(app=api))


def cliente_mock(handler) -> ClienteAcervo:
    return ClienteAcervo(CONFIG.api_url, transport=httpx.MockTransport(handler))


def contexto(texto=None, valor=None):
    """TurnContext simulado do SDK: guarda o que o agente envia."""
    ctx = SimpleNamespace(activity=SimpleNamespace(text=texto, value=valor), enviadas=[])

    async def send_activity(atividade):
        ctx.enviadas.append(atividade)

    ctx.send_activity = AsyncMock(side_effect=send_activity)
    return ctx


def cartoes(ctx):
    return [
        a.attachments[0].content
        for a in ctx.enviadas
        if not isinstance(a, str) and a.attachments and a.attachments[0].content_type == ADAPTIVE_CARD_CONTENT_TYPE
    ]


def textos(ctx):
    return [a if isinstance(a, str) else a.text for a in ctx.enviadas if isinstance(a, str) or a.text]


def blocos_de_texto(card):
    """Todos os TextBlock do cartão, em ordem."""
    saida = []
    for el in card["body"]:
        if el["type"] == "TextBlock":
            saida.append(el["text"])
        for sub in el.get("items", []):
            saida.append(sub["text"])
    return saida


# --------------------------------------------------------------------------- #
# Interpretação
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("acervo Até quando peço férias?", Comando("perguntar", "Até quando peço férias?")),
        ("Até quando peço férias?", Comando("perguntar", "Até quando peço férias?")),
        ("/acervo radar férias", Comando("radar", "férias")),
        ("acervo radar", Comando("radar", "")),
        ("<at>Acervo</at> acervo radar locação", Comando("radar", "locação")),
        ("acervo ajuda", Comando("ajuda")),
        ("acervo", Comando("ajuda")),
        ("", Comando("ajuda")),
        ("acervos de férias", Comando("perguntar", "acervos de férias")),
    ],
)
def test_interpretar(texto, esperado):
    assert interpretar(texto) == esperado


# --------------------------------------------------------------------------- #
# Adaptive Card
# --------------------------------------------------------------------------- #

RESPOSTA = {
    "resposta_id": "resp_abc",
    "resposta": "Peça até 21/03/2027.",
    "consta": True,
    "citacoes": [
        {"codigo": "NG_111", "versao": "3.0.0", "secao": "Anexo C", "trecho": "x" * 500,
         "camada": {"sigla": "NG", "tipo_nome": "Norma Geral", "grupo": "Normativo", "subordinado_a": None}},
        {"codigo": "PX_1111-001", "versao": "1.0.0", "secao": "2.1", "trecho": "b", "camada": None},
        {"codigo": "C", "versao": "1", "secao": "1", "trecho": "c"},
        {"codigo": "D", "versao": "1", "secao": "1", "trecho": "d"},
    ],
    "avisos": ["NG_111 v2.0.0 foi substituída pela v3.0.0"],
    "proxima_acao": "Peça no Portal.",
}


def test_cartao_resposta_tem_as_cinco_partes():
    card = cartao_resposta(RESPOSTA, "Até quando?", PAINEL, perfil="empregado")
    assert card["type"] == "AdaptiveCard" and card["version"]
    corpo = card["body"]

    # 1. Conclusão = texto da API, sem alteração
    assert corpo[0]["text"] == RESPOSTA["resposta"]
    # 2. Até 3 citações, camada curta, trecho ≤ 200
    citacoes = [b for b in corpo if b["type"] == "Container"]
    assert len(citacoes) == MAX_CITACOES
    primeira = [i["text"] for i in citacoes[0]["items"]]
    assert primeira[0].startswith("[NG_111 · v3.0.0 · Anexo C](")
    assert f"{PAINEL}/documento/NG_111?versao=3.0.0#secao-Anexo%20C" in primeira[0]
    assert primeira[1] == "NG · Normativo"
    assert len(primeira[2]) <= MAX_TRECHO
    # 3. Avisos e 4. Próxima ação
    textos_corpo = blocos_de_texto(card)
    assert any(RESPOSTA["avisos"][0] in t for t in textos_corpo)
    assert any(t.endswith(RESPOSTA["proxima_acao"]) for t in textos_corpo)
    # 5. Botões
    acoes = card["actions"]
    assert acoes[0] == {"type": "Action.OpenUrl", "title": "Abrir no painel",
                        "url": f"{PAINEL}/perguntar?q=At%C3%A9+quando%3F"}
    submits = [a for a in acoes if a["type"] == "Action.Submit"]
    assert [a["title"] for a in submits] == ["Útil", "Não útil"]
    assert [a["data"]["util"] for a in submits] == [True, False]
    assert all(a["data"]["resposta_id"] == "resp_abc" and a["data"]["acao"] == "avaliar" for a in submits)


def test_cartao_nao_consta_segue_o_cartao_neutro():
    resposta = {"resposta_id": "r", "resposta": "O acervo não trata disso.", "consta": False,
                "citacoes": [{"codigo": "X", "versao": "1", "secao": "1", "trecho": "t"}],
                "avisos": [], "proxima_acao": "Reformule."}
    card = cartao_resposta(resposta, "pergunta", PAINEL)
    assert card["body"][0]["text"] == resposta["resposta"]
    assert not [b for b in card["body"] if b["type"] == "Container"]  # sem citações quando não consta
    neutro = teams.montar_cartao(resposta, PAINEL)
    assert [a["title"] for a in card["actions"][1:]] == [b.rotulo for b in neutro.botoes]


def test_adaptive_card_vem_do_cartao_neutro():
    """O adaptador só traduz `montar_cartao` (o mesmo cartão do Slack)."""
    neutro = teams.montar_cartao(RESPOSTA, PAINEL)
    card = teams.adaptive_card(neutro, "Até quando?", PAINEL, perfil="empregado")
    assert card == cartao_resposta(RESPOSTA, "Até quando?", PAINEL, perfil="empregado")
    assert card["body"][0]["text"] == neutro.conclusao
    rotulos = [c["items"][0]["text"].split("](")[0].lstrip("[") for c in card["body"] if c["type"] == "Container"]
    assert rotulos == [c.referencia for c in neutro.citacoes]


# --------------------------------------------------------------------------- #
# Turno com SDK simulado + API em processo
# --------------------------------------------------------------------------- #


def test_turno_confirma_antes_e_envia_cartao():
    ctx = contexto("acervo Até quando peço férias que começam em 05/05/2027?")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))
    assert ctx.enviadas[0] == TEXTO_RESPONDENDO
    [card] = cartoes(ctx)
    assert any("21/03/2027" in t for t in blocos_de_texto(card))


def _resumo_web(resp):
    return {
        "conclusao": resp["resposta"],
        "citacoes": [f"{c['codigo']} · v{c['versao']} · {c['secao']}" for c in resp["citacoes"][:MAX_CITACOES]]
        if resp["consta"] else [],
        "avisos": resp["avisos"],
        "proxima_acao": resp.get("proxima_acao"),
        "botoes": [("Útil", True), ("Não útil", False)] if resp.get("resposta_id") else [],
    }


def _resumo_teams(card):
    corpo = card["body"]
    textos_soltos = [b["text"] for b in corpo[1:] if b["type"] == "TextBlock"]
    proxima = [t.removeprefix("Próxima ação: ") for t in textos_soltos if t.startswith("Próxima ação: ")]
    return {
        "conclusao": corpo[0]["text"],
        "citacoes": [c["items"][0]["text"].split("](")[0].lstrip("[") for c in corpo if c["type"] == "Container"],
        "avisos": [t.removeprefix("⚠️ ") for t in textos_soltos if t.startswith("⚠️ ")],
        "proxima_acao": proxima[0] if proxima else None,
        "botoes": [(a["title"], a["data"]["util"]) for a in card["actions"] if a["type"] == "Action.Submit"],
    }


def _resumo_slack(payload):
    blocos = payload["blocks"]
    secoes = [html.unescape(b["text"]["text"]) for b in blocos if b["type"] == "section"]
    contextos = [html.unescape(b["elements"][0]["text"]) for b in blocos if b["type"] == "context"]
    proxima = [t.removeprefix(":arrow_right: ") for t in contextos if t.startswith(":arrow_right: ")]
    rotulos = {"avaliacao_util": True, "avaliacao_nao_util": False}
    botoes = [e for b in blocos if b["type"] == "actions" for e in b["elements"] if e["action_id"] in rotulos]
    return {
        "conclusao": secoes[0],
        "citacoes": [s.split("*")[1] for s in secoes[1:]],
        "avisos": [t.removeprefix(":warning: ") for t in contextos if t.startswith(":warning: ")],
        "proxima_acao": proxima[0] if proxima else None,
        "botoes": [(e["text"]["text"], rotulos[e["action_id"]]) for e in botoes],
    }


@pytest.mark.parametrize("caso", PERGUNTAS, ids=[p["id"] for p in PERGUNTAS])
def test_paridade_web_slack_teams(caso):
    """RNF17: web, Slack e Teams mostram o mesmo texto, citações, avisos, próxima ação e botões."""
    pergunta, perfil = caso["pergunta"], caso.get("perfil")
    web_resp = web.post("/api/perguntar", json={"pergunta": pergunta, "perfil": perfil}).json()

    servico = ServicoCanais(ClienteAPI(base_url="http://teste", http=TestClient(api)), PAINEL)
    slack_payload = slack.renderizar([servico.perguntar(pergunta, perfil)])

    ctx = contexto(f"acervo {pergunta}")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), Config(api_url=CONFIG.api_url,
                                                                      painel_url=PAINEL, perfil=perfil))))
    [card] = cartoes(ctx)

    esperado = _resumo_web(web_resp)
    assert _resumo_slack(slack_payload) == esperado
    assert _resumo_teams(card) == esperado
    assert card["actions"][0]["url"] == teams.link_pergunta(PAINEL, pergunta)


def test_botao_util_grava_avaliacao_canal_teams():
    antes = web.get("/api/avaliacoes/resumo").json()["por_canal"]["teams"]
    ctx = contexto(valor={"acao": "avaliar", "resposta_id": "resp_teste", "util": False, "perfil": "gestor"})
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))
    assert textos(ctx) == [TEXTO_AVALIACAO_REGISTRADA]
    assert web.get("/api/avaliacoes/resumo").json()["por_canal"]["teams"] == antes + 1


def test_corpo_da_avaliacao_enviado_a_api():
    recebido = {}

    def handler(request: httpx.Request):
        recebido["url"] = str(request.url)
        recebido["json"] = __import__("json").loads(request.content)
        return httpx.Response(201, json={"id": "aval_1", "registrado_em": "2026-11-12T00:00:00Z"})

    ctx = contexto(valor={"acao": "avaliar", "resposta_id": "resp_1", "util": True, "perfil": "rh"})
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(handler), CONFIG)))
    assert recebido["url"] == "http://api.teste/api/avaliacoes"
    assert recebido["json"] == {"resposta_id": "resp_1", "util": True, "canal": "teams", "perfil": "rh"}


def test_api_fora_mantem_o_agente_vivo():
    def handler(request):
        raise httpx.ConnectError("recusada", request=request)

    ctx = contexto("acervo prazo de férias")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(handler), CONFIG)))
    assert textos(ctx) == [TEXTO_RESPONDENDO, TEXTO_API_FORA.format(painel_url=PAINEL)]


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_e_api_fora(status):
    ctx = contexto("acervo prazo de férias")
    agente = AgenteAcervo(cliente_mock(lambda r: httpx.Response(status, text="erro")), CONFIG)
    asyncio.run(tratar_turno(ctx, agente))
    assert textos(ctx) == [TEXTO_RESPONDENDO, TEXTO_API_FORA.format(painel_url=PAINEL)]


@pytest.mark.parametrize("status", [400, 413, 422])
def test_4xx_fala_da_pergunta_e_nao_de_api_fora(status):
    ctx = contexto("acervo prazo de férias")
    agente = AgenteAcervo(cliente_mock(lambda r: httpx.Response(status, json={"detail": "inválida"})), CONFIG)
    asyncio.run(tratar_turno(ctx, agente))
    assert textos(ctx) == [TEXTO_RESPONDENDO, TEXTO_PERGUNTA_RECUSADA]


def test_avaliacao_4xx_e_5xx():
    valor = {"acao": "avaliar", "resposta_id": "r", "util": True}
    ctx = contexto(valor=valor)
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(lambda r: httpx.Response(422, json={})), CONFIG)))
    assert textos(ctx) == [TEXTO_AVALIACAO_RECUSADA]
    ctx = contexto(valor=valor)
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(lambda r: httpx.Response(503)), CONFIG)))
    assert textos(ctx) == [TEXTO_API_FORA.format(painel_url=PAINEL)]


def test_ajuda_nao_chama_a_api():
    def handler(request):
        raise AssertionError("não deveria chamar a API")

    ctx = contexto("acervo ajuda")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(handler), CONFIG)))
    assert textos(ctx) == [teams.TEXTO_AJUDA]


# --------------------------------------------------------------------------- #
# Radar
# --------------------------------------------------------------------------- #

def _fonte(codigo, secao):
    return {"codigo": codigo, "versao": "3.0.0", "secao": secao, "trecho": "t",
            "camada": {"sigla": "NG", "grupo": "Normativo"}}


ITENS_RADAR = [
    {"id": "r1", "tipo": "versao_substituida", "status": "divergente", "severidade": "alta",
     "titulo": "Antecedência mudou", "explicacao": "A v3.0.0 passou de 30 para 45 dias.",
     "tema": {"assunto": "ferias", "serie_nome": "Gente e Cultura"}, "fontes": [_fonte("NG_111", "Anexo F")]},
    {"id": "r2", "tipo": "referencia_ausente", "status": "atencao", "severidade": "media",
     "titulo": "Norma ausente", "explicacao": "O contrato cita um documento fora do acervo.",
     "tema": {"assunto": "locacao"}, "fontes": [{"codigo": "CTR_2026-012", "versao": "1.0.0",
                                                 "secao": "Cláusula Sétima", "trecho": "t"}]},
]


def _blocos(card):
    return [b for b in card["body"] if b["type"] == "Container"]


def test_normalizar_remove_acentos_e_caixa():
    assert normalizar("  Férias ") == "ferias"
    assert normalizar("LOCAÇÃO") == "locacao"


@pytest.mark.parametrize("tema, esperado", [
    ("ferias", ["r1"]), ("férias", ["r1"]), ("FÉRIAS", ["r1"]), ("locação", ["r2"]),
    ("gente e cultura", ["r1"]), ("", ["r1", "r2"]), ("drones", []),
])
def test_filtrar_radar_por_tema_ignora_acentos(tema, esperado):
    assert [i["id"] for i in filtrar_radar(ITENS_RADAR, tema)] == esperado


def test_filtrar_radar_normaliza_o_lado_do_item():
    item = {"id": "x", "tema": {"assunto": "Locação"}}
    assert filtrar_radar([item], "locacao") == [item]


def test_cartao_radar_um_bloco_por_item_com_explicacao():
    card = cartao_radar(ITENS_RADAR, "", PAINEL)
    blocos = _blocos(card)
    assert len(blocos) == 2
    textos_r1 = [i["text"] for i in blocos[0]["items"]]
    assert textos_r1[0] == "Antecedência mudou"
    assert ITENS_RADAR[0]["explicacao"] in textos_r1
    assert "NG_111 · v3.0.0 · Anexo F (NG · Normativo)" in textos_r1
    assert any(f"{PAINEL}/radar?item=r1" in t for t in textos_r1)
    assert any(f"{PAINEL}/radar?item=r2" in t for t in [i["text"] for i in blocos[1]["items"]])


def test_cartao_radar_vazio_mostra_texto_de_estado():
    card = cartao_radar([], "drones", PAINEL)
    assert not _blocos(card)
    assert card["body"] == [{"type": "TextBlock", "text": TEXTO_RADAR_VAZIO.format(tema="drones"), "wrap": True}]
    assert card["actions"][0]["url"] == f"{PAINEL}/radar?tema=drones"


def test_radar_pela_api_simulada():
    ctx = contexto("acervo radar locação")
    resposta = {"gerado_em": "2026-11-12T00:00:00Z", "resumo": {}, "itens": ITENS_RADAR}
    agente = AgenteAcervo(cliente_mock(lambda r: httpx.Response(200, json=resposta)), CONFIG)
    asyncio.run(tratar_turno(ctx, agente))
    [card] = cartoes(ctx)
    assert [b["items"][0]["text"] for b in _blocos(card)] == ["Norma ausente"]
    assert card["actions"][0]["url"] == f"{PAINEL}/radar?tema=loca%C3%A7%C3%A3o"


def test_radar_contra_o_api_radar_real():
    """`acervo radar férias` (com acento) contra o GET /api/radar da main, em processo."""
    itens_api = web.get("/api/radar").json()["itens"]
    esperados = [i for i in itens_api if "ferias" in normalizar(i["tema"]["assunto"] if i.get("tema") else "")]
    assert esperados, "o radar real deveria ter itens de férias"

    ctx = contexto("acervo radar férias")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))
    assert ctx.enviadas[0] == TEXTO_RESPONDENDO
    [card] = cartoes(ctx)
    blocos = _blocos(card)
    assert len(blocos) == min(len(esperados), teams.MAX_ITENS_RADAR)
    titulos = {i["titulo"]: i for i in esperados}
    for bloco in blocos:
        textos_bloco = [t["text"] for t in bloco["items"]]
        item = titulos[textos_bloco[0]]
        assert item["explicacao"] in textos_bloco
        assert any(f"{PAINEL}/radar?item=" in t for t in textos_bloco)


def test_radar_real_sem_itens_para_o_tema():
    ctx = contexto("acervo radar tema-que-nao-existe")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))
    [card] = cartoes(ctx)
    assert card["body"][0]["text"] == TEXTO_RADAR_VAZIO.format(tema="tema-que-nao-existe")


# --------------------------------------------------------------------------- #
# Configuração e SDK real (em processo, sem sockets)
# --------------------------------------------------------------------------- #


def test_config_somente_do_ambiente():
    cfg = Config.do_ambiente({"API_URL": "http://x/", "PAINEL_URL": "http://p/", "TEAMS_PORTA": "4000"})
    assert (cfg.api_url, cfg.painel_url, cfg.porta) == ("http://x", "http://p", 4000)
    assert cfg.anonimo
    assert not Config.do_ambiente({"CLIENT_ID": "id", "CLIENT_SECRET": "s", "TENANT_ID": "t"}).anonimo


def test_env_example_so_com_nomes_das_credenciais():
    exemplo = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    for nome in ("CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"):
        assert f"{nome}=\n" in exemplo


def test_sdk_processa_atividade_expect_replies():
    """Atividade passa pelo CloudAdapter/AgentApplication do SDK em modo anônimo."""
    pytest.importorskip("microsoft_agents.hosting.aiohttp")
    from microsoft_agents.hosting.core import ClaimsIdentity

    conexoes, _ = teams.criar_conexoes(CONFIG)
    agent_app, adapter = teams.criar_agent_app(AgenteAcervo(cliente_api(), CONFIG), conexoes)

    atividade = {
        "type": "message", "id": "1", "channelId": "msteams", "serviceUrl": "http://localhost:56150",
        "deliveryMode": "expectReplies", "text": "acervo Qual a antecedência mínima para pedir férias?",
        "from": {"id": "usuario"}, "recipient": {"id": "agente"}, "conversation": {"id": "conversa"},
    }

    class Requisicao:
        method = "POST"
        headers = {"Content-Type": "application/json"}

        async def json(self):
            return atividade

        def get_claims_identity(self):
            return ClaimsIdentity({}, False)

        def get_path_param(self, nome):
            return ""

    resposta = asyncio.run(adapter.process_request(Requisicao(), agent_app))
    assert resposta.status_code == 200
    enviadas = resposta.body["activities"]
    assert enviadas[0]["text"] == TEXTO_RESPONDENDO
    card = enviadas[1]["attachments"][0]
    assert card["contentType"] == ADAPTIVE_CARD_CONTENT_TYPE
    assert card["content"]["type"] == "AdaptiveCard"


@pytest.mark.parametrize("corpo", [
    b'{"foo": 1}',
    b"nao e json",
    b"[1, 2]",
    b'{"type": "message", "serviceUrl": "http://x", "conversation": {}}',
])
def test_corpo_invalido_em_api_messages_responde_400(corpo):
    pytest.importorskip("microsoft_agents.hosting.aiohttp")
    from aiohttp.test_utils import TestClient as AioCliente, TestServer

    async def rodar():
        async with AioCliente(TestServer(teams.criar_app(CONFIG, cliente_api()))) as cliente:
            r = await cliente.post("/api/messages", data=corpo, headers={"Content-Type": "application/json"})
            return r.status, await r.json()

    status, json_resp = asyncio.run(rodar())
    assert status == 400 and json_resp["erro"]


def test_corpo_valido_em_api_messages_passa_pelo_sdk():
    pytest.importorskip("microsoft_agents.hosting.aiohttp")
    from aiohttp.test_utils import TestClient as AioCliente, TestServer

    atividade = {
        "type": "message", "id": "1", "channelId": "msteams", "serviceUrl": "http://localhost",
        "deliveryMode": "expectReplies", "text": "acervo ajuda",
        "from": {"id": "u"}, "recipient": {"id": "agente"}, "conversation": {"id": "c"},
    }

    async def rodar():
        async with AioCliente(TestServer(teams.criar_app(CONFIG, cliente_api()))) as cliente:
            r = await cliente.post("/api/messages", json=atividade)
            return r.status, await r.json()

    status, corpo = asyncio.run(rodar())
    assert status == 200
    assert corpo["activities"][0]["text"] == teams.TEXTO_AJUDA
