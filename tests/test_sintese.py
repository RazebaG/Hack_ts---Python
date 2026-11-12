"""Síntese via Bedrock ancorada nas citações (Issue #6), com boto3 simulado (sem rede)."""

import json

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app.acervo import AcervoRepository
from app.ia import ClienteIA
from app.inteligencia import InteligenciaService
from app.models import PerguntaRequest
from app.perguntar import PerguntarService
from app.sintese import carregar_guia

PERGUNTA = "Com quantos dias de antecedência devo pedir férias?"


class FakeBedrock:
    """Imita bedrock-runtime.converse. `saida` pode ser texto, callable(kwargs) ou exceção."""

    def __init__(self, saida):
        self.saida = saida
        self.chamadas = []

    def converse(self, **kwargs):
        self.chamadas.append(kwargs)
        saida = self.saida(kwargs) if callable(self.saida) else self.saida
        if isinstance(saida, Exception):
            raise saida
        return {"output": {"message": {"role": "assistant", "content": [{"text": saida}]}}}


def _ia(saida):
    fake = FakeBedrock(saida)
    return ClienteIA(provedor="bedrock", cliente=fake), fake


@pytest.fixture(scope="module")
def acervo():
    return AcervoRepository()


def _extrativa(acervo):
    servico = PerguntarService(acervo, ia=ClienteIA(provedor="nenhum"))
    return servico.responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))


def _etiqueta(c):
    return f"[{c.codigo}·{c.versao}·{c.secao}]"


def test_resposta_com_citacao_valida_usa_sintese(acervo):
    base = _extrativa(acervo)
    c = base.citacoes[1]  # NG_111 v3.0.0, item 2 (45 dias, Portal Raiz)
    saida = json.dumps(
        {
            "resposta": f"Peça as férias no Portal Raiz com 45 dias corridos de antecedência {_etiqueta(c)}. "
            "A versão 2.0.0 da NG_111 foi substituída.",
            "proxima_acao": f"Preencha o FM_1111-001 no Portal Raiz {_etiqueta(c)}.",
        },
        ensure_ascii=False,
    )
    ia, fake = _ia(saida)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))

    assert resp.consta is True
    assert resp.resposta.startswith("Peça as férias no Portal Raiz com 45 dias")
    assert f"(Fonte: {c.codigo} v{c.versao}, item {c.secao}.)" in resp.resposta
    assert "[" not in resp.resposta
    assert resp.proxima_acao.startswith("Preencha o FM_1111-001")
    # citações e avisos de versão inalterados; nenhum aviso de falha da IA
    assert [x.model_dump() for x in resp.citacoes] == [x.model_dump() for x in base.citacoes]
    assert resp.avisos == base.avisos

    # o prompt leva só os trechos citados e a ordem do perfil lida do guia
    pedido = fake.chamadas[0]
    mensagem = pedido["messages"][0]["content"][0]["text"]
    for x in base.citacoes:
        assert _etiqueta(x) in mensagem and x.trecho.rstrip(".;") in mensagem
    from app.sintese import ETIQUETA_RE

    assert len(ETIQUETA_RE.findall(mensagem)) == len(base.citacoes)  # só as seções citadas
    assert carregar_guia().ordem_por_perfil["empregado"] in mensagem
    assert "SOMENTE" in pedido["system"][0]["text"]
    assert pedido["modelId"] == "amazon.nova-pro-v1:0"


def test_citacao_inventada_cai_para_extrativa(acervo):
    base = _extrativa(acervo)
    saida = json.dumps({"resposta": "Peça com 45 dias de antecedência [NG_111·9.9.9·2].", "proxima_acao": ""})
    ia, _ = _ia(saida)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == base.resposta
    assert resp.proxima_acao == base.proxima_acao
    assert any("Síntese por IA indisponível" in a for a in resp.avisos)


def test_numero_sem_sustentacao_cai_para_extrativa(acervo):
    base = _extrativa(acervo)
    c = base.citacoes[1]
    saida = json.dumps({"resposta": f"Peça com 60 dias de antecedência {_etiqueta(c)}."})
    ia, _ = _ia(saida)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == base.resposta


def test_afirmacao_sem_citacao_cai_para_extrativa(acervo):
    base = _extrativa(acervo)
    c = base.citacoes[1]
    saida = json.dumps(
        {"resposta": f"Peça no Portal Raiz {_etiqueta(c)}.\nO gestor sempre aprova os pedidos feitos com antecedência adequada."}
    )
    ia, _ = _ia(saida)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == base.resposta


def test_modelo_sem_sustentacao_cai_para_extrativa(acervo):
    base = _extrativa(acervo)
    ia, _ = _ia("Não consta nas fontes.")
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == base.resposta
    assert resp.consta is True


def test_erro_de_credencial_extrativa_com_aviso_sem_tentar_reserva(acervo):
    base = _extrativa(acervo)
    erro = ClientError({"Error": {"Code": "ExpiredTokenException", "Message": "x"}}, "Converse")
    ia, fake = _ia(erro)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == base.resposta
    assert any("credencial" in a for a in resp.avisos)
    assert len(fake.chamadas) == 1
    assert ia.status() == {"provedor": "bedrock", "modelo": "amazon.nova-pro-v1:0", "disponivel": False}


def test_sem_credencial_extrativa_com_aviso(acervo):
    ia, _ = _ia(NoCredentialsError())
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta == _extrativa(acervo).resposta
    assert any("credencial" in a for a in resp.avisos)


def test_erro_no_modelo_padrao_usa_reserva(acervo):
    base = _extrativa(acervo)
    c = base.citacoes[1]
    ok = json.dumps({"resposta": f"Peça com 45 dias corridos de antecedência {_etiqueta(c)}."})

    def saida(kwargs):
        if kwargs["modelId"] == "amazon.nova-pro-v1:0":
            return ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")
        return ok

    ia, fake = _ia(saida)
    resp = PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert resp.resposta.startswith("Peça com 45 dias corridos")
    assert [c["modelId"] for c in fake.chamadas] == ["amazon.nova-pro-v1:0", "amazon.nova-lite-v1:0"]
    assert ia.status()["modelo"] == "amazon.nova-lite-v1:0"


def test_abstencao_mantida_sem_chamar_modelo(acervo):
    ia, fake = _ia("qualquer coisa [NG_111·3.0.0·2]")
    resp = PerguntarService(acervo, ia=ia).responder(
        PerguntaRequest(pergunta="Qual o valor do benefício alimentação?", perfil="empregado")
    )
    assert resp.consta is False and resp.citacoes == []
    assert fake.chamadas == []


def test_provedor_nenhum_nao_chama_modelo(acervo):
    fake = FakeBedrock("nunca")
    ia = ClienteIA(provedor="nenhum", cliente=fake)
    PerguntarService(acervo, ia=ia).responder(PerguntaRequest(pergunta=PERGUNTA, perfil="gestor"))
    assert fake.chamadas == []
    assert ia.status() == {"provedor": "nenhum", "modelo": None, "disponivel": False}


def test_mesma_resposta_cacheada(acervo):
    c = _extrativa(acervo).citacoes[1]
    ia, fake = _ia(json.dumps({"resposta": f"Peça com 45 dias {_etiqueta(c)}."}))
    servico = PerguntarService(acervo, ia=ia)
    a = servico.responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    b = servico.responder(PerguntaRequest(pergunta=PERGUNTA, perfil="empregado"))
    assert a.resposta == b.resposta and len(fake.chamadas) == 1


# ------------------------------------------------------------------ /api/relatorio


def _relatorio_base(acervo):
    return InteligenciaService(acervo=acervo, ia=ClienteIA(provedor="nenhum")).gerar_relatorio(perspectiva="juridico")


def test_relatorio_sintese_valida_entra_primeiro_com_fonte(acervo):
    base = _relatorio_base(acervo)
    fonte = base.secoes[0].itens[0].fonte
    tag = f"[{fonte.codigo}·{fonte.versao}·{fonte.secao}]"
    palavras = " ".join(base.secoes[0].itens[0].texto.split()[:8])
    saida = json.dumps({"itens": [f"{palavras} {tag}.", "Item inventado [XX_1·1.0.0·1].", "Sem fonte nenhuma aqui para validar o texto."]})
    ia, _ = _ia(saida)
    rel = InteligenciaService(acervo=acervo, ia=ia).gerar_relatorio(perspectiva="juridico")

    assert rel.secoes[0].titulo == "Síntese executiva"
    assert len(rel.secoes[0].itens) == 1  # só o item ancorado sobrevive
    item = rel.secoes[0].itens[0]
    assert item.fonte == fonte and item.fonte.camada is not None
    assert "[" not in item.texto and "(Fonte:" in item.texto
    assert [s.model_dump() for s in rel.secoes[1:]] == [s.model_dump() for s in base.secoes]
    assert rel.avisos == []


def test_relatorio_falha_da_ia_mantem_itens_com_aviso(acervo):
    base = _relatorio_base(acervo)
    ia, _ = _ia(ClientError({"Error": {"Code": "ExpiredTokenException", "Message": "x"}}, "Converse"))
    rel = InteligenciaService(acervo=acervo, ia=ia).gerar_relatorio(perspectiva="juridico")
    assert [s.model_dump() for s in rel.secoes] == [s.model_dump() for s in base.secoes]
    assert any("credencial" in a for a in rel.avisos)


def test_guia_lido_do_documento():
    guia = carregar_guia()
    assert set(guia.ordem_por_perfil) >= {"empregado", "gestor", "diretoria", "financeiro", "juridico", "rh"}
    assert guia.voz and guia.checklist


def test_saude_expoe_ia_sem_dados_da_conta():
    from fastapi.testclient import TestClient

    from app.main import app

    dados = TestClient(app).get("/api/saude").json()
    assert dados["ia"] == {"provedor": "nenhum", "modelo": None, "disponivel": False}
