"""Testes do agente Teams (S2, RF33): SDK simulado e API em processo, sem rede."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.canais import teams
from app.canais.teams import (
    ADAPTIVE_CARD_CONTENT_TYPE,
    AgenteAcervo,
    ClienteAcervo,
    Comando,
    Config,
    MAX_CITACOES,
    MAX_TRECHO,
    TEXTO_API_FORA,
    TEXTO_AVALIACAO_REGISTRADA,
    TEXTO_RESPONDENDO,
    cartao_radar,
    cartao_resposta,
    filtrar_radar,
    interpretar,
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


def test_cartao_nao_consta_sem_botoes_de_avaliacao():
    resposta = {"resposta_id": "r", "resposta": "O acervo não trata disso.", "consta": False,
                "citacoes": [], "avisos": [], "proxima_acao": "Reformule."}
    card = cartao_resposta(resposta, "pergunta", PAINEL)
    assert card["body"][0]["text"] == resposta["resposta"]
    assert [a["title"] for a in card["actions"]] == ["Abrir no painel"]


# --------------------------------------------------------------------------- #
# Turno com SDK simulado + API em processo
# --------------------------------------------------------------------------- #


def test_turno_confirma_antes_e_envia_cartao():
    ctx = contexto("acervo Até quando peço férias que começam em 05/05/2027?")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))
    assert ctx.enviadas[0] == TEXTO_RESPONDENDO
    [card] = cartoes(ctx)
    assert any("21/03/2027" in t for t in blocos_de_texto(card))


@pytest.mark.parametrize("caso", PERGUNTAS, ids=[p["id"] for p in PERGUNTAS])
def test_paridade_web_teams(caso):
    """RNF17: mesmo texto, mesmas citações e mesmo link que a web (/api/perguntar)."""
    pergunta, perfil = caso["pergunta"], caso.get("perfil")
    web_resp = web.post("/api/perguntar", json={"pergunta": pergunta, "perfil": perfil}).json()

    ctx = contexto(f"acervo {pergunta}")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), Config(api_url=CONFIG.api_url,
                                                                      painel_url=PAINEL, perfil=perfil))))
    [card] = cartoes(ctx)

    assert card["body"][0]["text"] == web_resp["resposta"]
    rotulos = [c["items"][0]["text"].split("](")[0].lstrip("[") for c in card["body"] if c["type"] == "Container"]
    assert rotulos == [f"{c['codigo']} · v{c['versao']} · {c['secao']}" for c in web_resp["citacoes"][:MAX_CITACOES]]
    assert card["actions"][0]["url"] == teams.link_pergunta(PAINEL, pergunta)
    tem_botoes = any(a["type"] == "Action.Submit" for a in card["actions"])
    assert tem_botoes == web_resp["consta"]


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


def test_ajuda_nao_chama_a_api():
    def handler(request):
        raise AssertionError("não deveria chamar a API")

    ctx = contexto("acervo ajuda")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_mock(handler), CONFIG)))
    assert textos(ctx) == [teams.TEXTO_AJUDA]


# --------------------------------------------------------------------------- #
# Radar
# --------------------------------------------------------------------------- #

ITENS_RADAR = [
    {"id": "r1", "titulo": "Antecedência mudou", "tema": {"assunto": "ferias", "serie_nome": "Gente e Cultura"},
     "fontes": [{"codigo": "NG_111", "versao": "3.0.0", "secao": "Anexo F",
                 "camada": {"sigla": "NG", "grupo": "Normativo"}}]},
    {"id": "r2", "titulo": "Norma ausente", "tema": {"assunto": "locacao"},
     "fonte": {"codigo": "CTR_2026-012", "versao": "1.0.0", "secao": "Cláusula Sétima"}},
]


def test_filtrar_radar_por_tema():
    assert [i["id"] for i in filtrar_radar(ITENS_RADAR, "ferias")] == ["r1"]
    assert [i["id"] for i in filtrar_radar(ITENS_RADAR, "")] == ["r1", "r2"]


def test_cartao_radar_um_bloco_por_item():
    card = cartao_radar(ITENS_RADAR, "", PAINEL)
    blocos = [b for b in card["body"] if b["type"] == "Container"]
    assert len(blocos) == 2
    textos_r1 = [i["text"] for i in blocos[0]["items"]]
    assert "NG_111 · v3.0.0 · Anexo F (NG · Normativo)" in textos_r1
    assert any(f"{PAINEL}/radar?item=r1" in t for t in textos_r1)


def test_radar_pela_api_simulada():
    ctx = contexto("acervo radar locacao")
    agente = AgenteAcervo(cliente_mock(lambda r: httpx.Response(200, json=ITENS_RADAR)), CONFIG)
    asyncio.run(tratar_turno(ctx, agente))
    [card] = cartoes(ctx)
    assert [b["items"][0]["text"] for b in card["body"] if b["type"] == "Container"] == ["Norma ausente"]
    assert card["actions"][0]["url"] == f"{PAINEL}/radar?tema=locacao"


def test_radar_sem_endpoint_aponta_para_o_painel():
    ctx = contexto("acervo radar ferias")
    asyncio.run(tratar_turno(ctx, AgenteAcervo(cliente_api(), CONFIG)))  # /api/radar ainda não existe
    assert not cartoes(ctx)
    assert f"{PAINEL}/radar?tema=ferias" in textos(ctx)[-1]


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
