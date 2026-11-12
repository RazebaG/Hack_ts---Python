"""Camada comum de canais + adaptador Slack (Issue #9).

Sem rede: a API é o próprio app FastAPI via TestClient (ou um transporte
simulado), e o Slack é simulado (ack/respond falsos e um App falso).
"""

import json
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient

from app.canais import ClienteAPI, ErroAPI, ServicoCanais, montar_cartao, montar_cartoes_radar
from app.canais.base import interpretar
from app.canais import slack
from app.main import app, avaliacoes_repo

PAINEL = "http://painel.teste"
PERGUNTA_CONSTA = "Qual a antecedência para solicitar férias?"
PERGUNTA_NAO_CONSTA = "Qual é a política de uso de drones no estacionamento?"


@pytest.fixture
def servico() -> ServicoCanais:
    api = ClienteAPI(base_url="http://teste", http=TestClient(app))
    return ServicoCanais(api=api, painel_url=PAINEL)


class SlackFalso:
    """Registra o que o handler mandou ao Slack."""

    def __init__(self) -> None:
        self.acks: List[Any] = []
        self.respostas: List[Dict[str, Any]] = []

    def ack(self, *args: Any, **kwargs: Any) -> None:
        self.acks.append(args[0] if args else kwargs or None)

    def respond(self, **kwargs: Any) -> None:
        self.respostas.append(kwargs)


class AppFalso:
    def __init__(self) -> None:
        self.comandos: Dict[str, Any] = {}
        self.acoes: Dict[str, Any] = {}

    def command(self, nome):
        def deco(fn):
            self.comandos[nome] = fn
            return fn
        return deco

    def action(self, nome):
        def deco(fn):
            self.acoes[nome] = fn
            return fn
        return deco


def _textos(blocos: List[Dict[str, Any]]) -> str:
    return json.dumps(blocos, ensure_ascii=False)


# --- interface comum ---------------------------------------------------------

def test_interpretar_comandos():
    assert interpretar("radar pessoas").tipo == "radar"
    assert interpretar("radar pessoas").texto == "pessoas"
    assert interpretar("Radar").texto == ""
    assert interpretar("radares de velocidade?").tipo == "perguntar"
    assert interpretar("  ").tipo == "vazio"


def test_cartao_com_citacao_vem_da_api(servico):
    resposta = TestClient(app).post("/api/perguntar", json={"pergunta": PERGUNTA_CONSTA}).json()
    cartao = montar_cartao(resposta, PAINEL)

    assert cartao.consta is True
    assert cartao.conclusao == resposta["resposta"]  # nenhum texto inventado pelo canal
    assert 1 <= len(cartao.citacoes) <= 3
    for c, original in zip(cartao.citacoes, resposta["citacoes"]):
        assert (c.codigo, c.versao, c.secao, c.trecho) == (
            original["codigo"], original["versao"], original["secao"], original["trecho"]
        )
        assert c.selo == f"{original['camada']['sigla']} · {original['camada']['grupo']}"
    assert cartao.avisos == resposta["avisos"]
    assert cartao.proxima_acao == resposta["proxima_acao"]
    assert cartao.link_painel == PAINEL
    assert [(b.rotulo, b.util, b.resposta_id) for b in cartao.botoes] == [
        ("Útil", True, resposta["resposta_id"]),
        ("Não útil", False, resposta["resposta_id"]),
    ]


def test_cartao_abstencao(servico):
    resposta = TestClient(app).post("/api/perguntar", json={"pergunta": PERGUNTA_NAO_CONSTA}).json()
    assert resposta["consta"] is False
    cartao = montar_cartao(resposta, PAINEL)
    assert cartao.consta is False
    assert cartao.citacoes == []
    assert cartao.conclusao == resposta["resposta"]


def test_cartao_limita_tres_citacoes_e_aceita_camada_ausente():
    citacoes = [{"codigo": f"NG_{i}", "versao": "1.0.0", "secao": "1", "trecho": "t"} for i in range(5)]
    cartao = montar_cartao({"resposta_id": "r1", "resposta": "x", "consta": True, "citacoes": citacoes}, "")
    assert len(cartao.citacoes) == 3
    assert cartao.citacoes[0].selo is None
    assert cartao.link_painel is None


def test_paridade_mesma_pergunta_mesmo_cartao(servico):
    """Mesma pergunta → mesmo cartão neutro (só o resposta_id muda a cada chamada)."""
    a = servico.perguntar(PERGUNTA_CONSTA)
    b = servico.perguntar(PERGUNTA_CONSTA)
    sem_id = lambda c: (c.conclusao, c.consta, c.citacoes, c.avisos, c.proxima_acao, c.link_painel,
                        [(x.acao, x.rotulo, x.util) for x in c.botoes])
    assert sem_id(a) == sem_id(b)
    # resposta_id fixo → cartões idênticos, independente do canal que vai renderizar
    resposta = TestClient(app).post("/api/perguntar", json={"pergunta": PERGUNTA_CONSTA}).json()
    assert montar_cartao(resposta, PAINEL) == montar_cartao(dict(resposta), PAINEL)


def test_radar_tres_mais_severos():
    fonte = {"codigo": "NG_111", "versao": "3.0.0", "secao": "4.3.1", "trecho": "t",
             "camada": {"sigla": "NG", "grupo": "Normativo"}}
    radar = {"itens": [
        {"titulo": "baixa", "explicacao": "e1", "severidade": "baixa", "fontes": [fonte]},
        {"titulo": "alta", "explicacao": "e2", "severidade": "alta", "fontes": [fonte, fonte]},
        {"titulo": "media", "explicacao": "e3", "severidade": "media", "fontes": []},
        {"titulo": "alta2", "explicacao": "e4", "severidade": "alta", "fontes": []},
    ]}
    cartoes = montar_cartoes_radar(radar, PAINEL)
    assert [c.titulo for c in cartoes] == ["alta", "alta2", "media"]
    assert cartoes[0].conclusao == "e2"
    assert cartoes[0].citacoes[0].selo == "NG · Normativo"
    assert all(not c.botoes for c in cartoes)


def test_api_fora_vira_erro_api():
    def falha(request):
        raise httpx.ConnectError("sem rede", request=request)

    api = ClienteAPI(base_url="http://teste", http=httpx.Client(transport=httpx.MockTransport(falha), base_url="http://teste"))
    with pytest.raises(ErroAPI):
        api.perguntar("x")


def test_erro_http_vira_erro_api_com_status():
    api = ClienteAPI(http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, json={"detail": "Not Found"})),
        base_url="http://teste",
    ))
    with pytest.raises(ErroAPI) as e:
        api.radar("pessoas")
    assert e.value.status == 404


# --- adaptador Slack ------------------------------------------------------------

def test_slack_blocos_espelham_o_cartao(servico):
    cartao = servico.perguntar(PERGUNTA_CONSTA)
    payload = slack.renderizar([cartao])
    texto = _textos(payload["blocks"])

    assert payload["text"]
    for c in cartao.citacoes:
        assert c.codigo in texto and c.versao in texto and c.selo in texto
    acoes = [b for b in payload["blocks"] if b["type"] == "actions"][0]["elements"]
    assert [e["action_id"] for e in acoes] == ["avaliacao_util", "avaliacao_nao_util", "abrir_painel"]
    assert acoes[0]["value"] == cartao.resposta_id
    assert acoes[2]["url"] == PAINEL


def test_slack_escapa_mrkdwn():
    cartao = montar_cartao({"resposta_id": "r", "resposta": "a < b & c > d", "consta": True}, "")
    assert "a &lt; b &amp; c &gt; d" in _textos(slack.renderizar([cartao])["blocks"])


def test_slack_comando_pergunta_ack_e_resposta(servico):
    sf = SlackFalso()
    slack.tratar_comando(servico, sf.ack, sf.respond, {"text": PERGUNTA_CONSTA})
    assert sf.acks == [slack.MSG_CONSULTANDO]
    assert len(sf.respostas) == 1
    blocos = sf.respostas[0]["blocks"]
    assert any(b["type"] == "actions" for b in blocos)


def test_slack_comando_abstencao(servico):
    sf = SlackFalso()
    slack.tratar_comando(servico, sf.ack, sf.respond, {"text": PERGUNTA_NAO_CONSTA})
    resposta = TestClient(app).post("/api/perguntar", json={"pergunta": PERGUNTA_NAO_CONSTA}).json()
    texto = _textos(sf.respostas[0]["blocks"])
    assert resposta["resposta"] in texto
    assert "> " not in texto  # nenhuma citação


def test_slack_comando_vazio_mostra_uso(servico):
    sf = SlackFalso()
    slack.tratar_comando(servico, sf.ack, sf.respond, {"text": ""})
    assert sf.acks == [slack.MSG_USO]
    assert sf.respostas == []


def test_slack_radar_chama_api_com_tema():
    chamadas = []

    def api(request: httpx.Request):
        chamadas.append(request)
        return httpx.Response(200, json={"itens": [
            {"titulo": "NG_111 mudou", "explicacao": "30 → 45 dias", "severidade": "alta",
             "fontes": [{"codigo": "NG_111", "versao": "3.0.0", "secao": "4.3.1", "trecho": "45 dias"}]},
        ]})

    servico = ServicoCanais(ClienteAPI(http=httpx.Client(transport=httpx.MockTransport(api), base_url="http://teste")), "")
    sf = SlackFalso()
    slack.tratar_comando(servico, sf.ack, sf.respond, {"text": "radar pessoas"})
    assert chamadas[0].url.path == "/api/radar"
    assert chamadas[0].url.params["perspectiva"] == "pessoas"
    texto = _textos(sf.respostas[0]["blocks"])
    assert "NG_111 mudou" in texto and "4.3.1" in texto


def test_slack_api_fora_responde_mensagem_clara():
    def falha(request):
        raise httpx.ConnectError("sem rede", request=request)

    servico = ServicoCanais(ClienteAPI(http=httpx.Client(transport=httpx.MockTransport(falha), base_url="http://teste")))
    sf = SlackFalso()
    slack.tratar_comando(servico, sf.ack, sf.respond, {"text": "qualquer"})
    assert sf.acks == [slack.MSG_CONSULTANDO]
    assert sf.respostas[0]["text"] == slack.MSG_API_FORA


@pytest.mark.parametrize("acao,util", [("avaliacao_util", True), ("avaliacao_nao_util", False)])
def test_slack_botao_grava_avaliacao_canal_slack(servico, acao, util):
    avaliacoes_repo.limpar()
    cartao = servico.perguntar(PERGUNTA_CONSTA)
    sf = SlackFalso()
    body = {"actions": [{"action_id": acao, "value": cartao.resposta_id}]}
    slack.tratar_avaliacao(servico, sf.ack, sf.respond, body)

    assert sf.acks == [None]
    resumo = TestClient(app).get("/api/avaliacoes/resumo").json()
    assert resumo["total"] == 1
    assert resumo["por_canal"]["slack"] == 1
    assert resumo["uteis"] == (1 if util else 0)
    assert sf.respostas[0]["text"] == slack.MSG_AVALIADO[util]


def test_slack_registra_handlers():
    falso = AppFalso()
    slack.registrar_handlers(falso, ServicoCanais(ClienteAPI(base_url="http://teste")))
    assert set(falso.comandos) == {"/acervo"}
    assert set(falso.acoes) == {"avaliacao_util", "avaliacao_nao_util", "abrir_painel"}


def test_slack_exige_token_por_ambiente(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        slack.criar_app(ServicoCanais(ClienteAPI(base_url="http://teste")))


def test_slack_bolt_real_despacha_comando_e_botao(servico):
    """App Bolt de verdade, sem token e sem rede: `respond` é interceptado."""
    from unittest.mock import patch
    from urllib.parse import urlencode
    from slack_bolt import App, BoltRequest
    from slack_bolt.authorization import AuthorizeResult

    bolt = App(
        signing_secret="",
        request_verification_enabled=False,
        ssl_check_enabled=False,
        url_verification_enabled=False,
        process_before_response=True,
        authorize=lambda **kw: AuthorizeResult(enterprise_id=None, team_id="T1", bot_user_id="U1", bot_id="B1"),
    )
    slack.registrar_handlers(bolt, servico)
    form = {"content-type": ["application/x-www-form-urlencoded"]}
    enviados: List[Dict[str, Any]] = []
    avaliacoes_repo.limpar()

    with patch("slack_bolt.context.respond.respond.Respond.__call__", lambda self, **kw: enviados.append(kw)):
        corpo = urlencode({"command": "/acervo", "text": PERGUNTA_CONSTA, "team_id": "T1", "user_id": "U2",
                           "channel_id": "C1", "response_url": "https://hooks.invalid/x", "trigger_id": "1"})
        r = bolt.dispatch(BoltRequest(body=corpo, headers=form))
        assert r.status == 200 and r.body == slack.MSG_CONSULTANDO
        botoes = [b for b in enviados[0]["blocks"] if b["type"] == "actions"][0]["elements"]

        acao = {"type": "block_actions", "team": {"id": "T1"}, "user": {"id": "U2"},
                "response_url": "https://hooks.invalid/x",
                "actions": [{"type": "button", "action_id": botoes[1]["action_id"], "value": botoes[1]["value"]}]}
        r = bolt.dispatch(BoltRequest(body=urlencode({"payload": json.dumps(acao)}), headers=form))
        assert r.status == 200

    resumo = TestClient(app).get("/api/avaliacoes/resumo").json()
    assert resumo["por_canal"]["slack"] == 1 and resumo["uteis"] == 0
