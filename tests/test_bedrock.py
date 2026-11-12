"""Testes unitários do módulo Amazon Bedrock e recuperação híbrida (Issue #6).

Atende às provas de aceite da Issue #6:
- Testes com boto3 simulado (sem rede no CI);
- Resposta com citação válida aprovada;
- Citação inventada pelo modelo descartada com fallback para resposta extrativa;
- Erro de credencial / exceção do Bedrock gera degradação graciosa (extrativa + aviso);
- Abstenção mantida em 100% dos temas ausentes;
- Fallback automático entre modelo primário (Nova Pro) e reserva rápida (Nova Lite);
- Recuperação híbrida (BM25 + embeddings) com cache em data/cache/ e fallback para BM25;
- /api/saude expõe status de IA sem vazar dados de conta ou credenciais;
- /api/relatorio com síntese executiva por perspectiva via Bedrock.
"""

import io
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.acervo import AcervoRepository
from app.models import PerguntaRequest
from app.perguntar import PerguntarService
from app.recuperacao import BuscadorLexico
from app.bedrock import (
    get_ia_status,
    gerar_resposta_converse,
    gerar_embeddings,
    get_llm_provider,
)

client = TestClient(app)


def test_saude_exibe_ia_sem_dados_de_conta():
    """GET /api/saude expõe o bloco 'ia' sem expor chaves, tokens ou IDs de conta."""
    resp = client.get("/api/saude")
    assert resp.status_code == 200
    data = resp.json()
    assert "ia" in data
    ia = data["ia"]
    assert "provedor" in ia
    assert "disponivel" in ia
    # Garante que nenhum campo de credencial existe
    for campo_proibido in ["aws_access_key_id", "secret", "token", "account", "account_id"]:
        assert campo_proibido not in ia
        assert campo_proibido not in data


def test_saude_provedor_bedrock_com_mock(monkeypatch):
    """GET /api/saude com LLM_PROVIDER=bedrock reflete modelo e disponibilidade."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

    mock_client = MagicMock()
    with patch("app.bedrock.get_bedrock_client", return_value=mock_client):
        resp = client.get("/api/saude")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ia"]["provedor"] == "bedrock"
        assert data["ia"]["modelo"] == "amazon.nova-pro-v1:0"
        assert data["ia"]["disponivel"] is True


def test_resposta_bedrock_com_citacao_valida(monkeypatch):
    """Resposta com citação válida do Bedrock é aceita e estruturada por perfil."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    # Simula resposta do Nova Pro com citação válida de documento recuperado (NG_111)
    mock_boto_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": "Regra vigente: A antecedência mínima para férias é 45 dias corridos. (Fonte: NG_111 v3.0.0, 4.3.1.)"
                    }
                ]
            }
        }
    }

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        acervo = AcervoRepository()
        svc = PerguntarService(acervo)
        resp = svc.responder(
            PerguntaRequest(
                pergunta="Qual a antecedência mínima para pedir férias?",
                perfil="rh",
            )
        )

        assert resp.consta is True
        assert "45 dias" in resp.resposta
        assert "Regra vigente:" in resp.resposta
        assert len(resp.citacoes) >= 1
        assert any(c.codigo == "NG_111" for c in resp.citacoes)
        # Mock converse foi chamado
        assert mock_boto_client.converse.called


def test_resposta_bedrock_citacao_inventada_cai_para_extrativa(monkeypatch):
    """Citação inventada (alucinação) pelo modelo é descartada e cai para extrativa."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    # Modelo inventa documento inexistente no contexto recuperado (ex: CTR_9999)
    mock_boto_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": "O prazo foi alterado conforme CTR_9999 para 15 dias."
                    }
                ]
            }
        }
    }

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        acervo = AcervoRepository()
        svc = PerguntarService(acervo)
        resp = svc.responder(
            PerguntaRequest(
                pergunta="Qual a antecedência mínima para pedir férias?",
                perfil="rh",
            )
        )

        assert resp.consta is True
        # Resposta deve ter caído para a extrativa original (que fala de 45 dias da NG_111)
        assert "CTR_9999" not in resp.resposta
        assert "45" in resp.resposta
        assert any("não validada" in av or "extração direta" in av for av in resp.avisos)


def test_resposta_bedrock_erro_credencial_ou_rede_cai_para_extrativa(monkeypatch):
    """Erro de credencial expirada ou rede no Bedrock não quebra a API e cai para extrativa."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    # Simula erro de credencial expirada no Bedrock
    mock_boto_client.converse.side_effect = Exception("ExpiredTokenException: The security token included in the request is expired")

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        acervo = AcervoRepository()
        svc = PerguntarService(acervo)
        resp = svc.responder(
            PerguntaRequest(
                pergunta="Qual a antecedência mínima para pedir férias?",
                perfil="rh",
            )
        )

        # Não lança exceção; resposta extrativa devolvida com aviso
        assert resp.consta is True
        assert "45" in resp.resposta
        assert any("IA indisponível" in av for av in resp.avisos)


def test_fallback_modelo_primario_para_reserva_rapida(monkeypatch):
    """Quando o modelo principal falha, a API tenta o modelo reserva rápida (Nova Lite)."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "amazon.nova-lite-v1:0")

    mock_boto_client = MagicMock()

    # Primeira chamada (nova-pro) falha; segunda chamada (nova-lite) sucede
    def converse_side_effect(modelId, **kwargs):
        if modelId == "amazon.nova-pro-v1:0":
            raise Exception("ThrottlingException: Rate exceeded")
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": "O que fazer: Peça com antecedência de 45 dias. (Fonte: NG_111 v3.0.0, 4.3.1.)"
                        }
                    ]
                }
            }
        }

    mock_boto_client.converse.side_effect = converse_side_effect

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        texto, modelo_usado, erro = gerar_resposta_converse("prompt", "mensagem")
        assert erro is None
        assert modelo_usado == "amazon.nova-lite-v1:0"
        assert "45 dias" in texto


def test_abstencao_mantida_com_bedrock_ativo(monkeypatch):
    """Abstenção é mantida (consta=False, citacoes=[]) mesmo com LLM_PROVIDER=bedrock."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        acervo = AcervoRepository()
        svc = PerguntarService(acervo)
        resp = svc.responder(
            PerguntaRequest(
                pergunta="Uma mesma pessoa pode elaborar, revisar e aprovar?",
                perfil="gestor",
            )
        )

        # Deve abster imediatamente sem chamar o gerador de texto
        assert resp.consta is False
        assert resp.citacoes == []
        assert "não trata disso" in resp.resposta.lower()
        assert not mock_boto_client.converse.called


def test_gerar_embeddings_e_cache(monkeypatch, tmp_path):
    """Testa geração de embeddings com us.cohere.embed-v4:0 e gravação em cache."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    cache_file = tmp_path / "embeddings.json"
    monkeypatch.setattr("app.recuperacao.EMBEDDINGS_CACHE_FILE", cache_file)
    monkeypatch.setattr("app.recuperacao.CACHE_DIR", tmp_path)

    # 1536 dimensões simuladas
    vetor_fake = [0.1] * 1536
    mock_boto_client = MagicMock()
    corpo_resposta = io.BytesIO(
        json.dumps({"embeddings": {"float": [vetor_fake, vetor_fake]}}).encode("utf-8")
    )
    mock_boto_client.invoke_model.return_value = {"body": corpo_resposta}

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        embs = gerar_embeddings(["texto 1", "texto 2"])
        assert embs is not None
        assert len(embs) == 2
        assert len(embs[0]) == 1536


def test_embeddings_falha_degrada_para_bm25_puro(monkeypatch):
    """Quando o modelo de embeddings falha, o buscador executa normalmente com BM25."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    mock_boto_client.invoke_model.side_effect = Exception("ServiceUnavailableException")

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        acervo = AcervoRepository()
        buscador = BuscadorLexico(acervo)
        consta, resultados, avisos = buscador.buscar("Qual a antecedência mínima para pedir férias?")

        assert consta is True
        assert len(resultados) >= 1
        assert any(r.codigo == "NG_111" for r in resultados)


def test_relatorio_com_sintese_ia(monkeypatch):
    """GET /api/relatorio?perspectiva=financeiro inclui síntese executiva gerada por IA."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    mock_boto_client = MagicMock()
    mock_boto_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": "• [FATO-1]: Contrato de coworking possui valor de R$ 18.250,00."
                    }
                ]
            }
        }
    }

    with patch("app.bedrock.get_bedrock_client", return_value=mock_boto_client):
        resp = client.get("/api/relatorio?perspectiva=financeiro")
        assert resp.status_code == 200
        data = resp.json()
        titulos_secoes = [s["titulo"] for s in data["secoes"]]
        assert any("Síntese Executiva" in t for t in titulos_secoes)
        secao_ia = next(s for s in data["secoes"] if "Síntese Executiva" in s["titulo"])
        assert len(secao_ia["itens"]) >= 1
        assert secao_ia["itens"][0]["fonte"]["codigo"] == "CTR_2026-012"
