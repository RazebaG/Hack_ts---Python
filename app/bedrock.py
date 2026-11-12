"""Módulo de integração com Amazon Bedrock (HACKA/TS 2026 - Issue #6).

Atende:
- API Converse (bedrock-runtime) para respostas redigidas e sínteses executivas;
- Modelo primário: amazon.nova-pro-v1:0; reserva rápida: amazon.nova-lite-v1:0;
- Embeddings: us.cohere.embed-v4:0 (1536 dimensões, input_type search_document/search_query);
- Configuração apenas por variáveis de ambiente (.env via python-dotenv);
- Degradação graciosa para extrativo em caso de indisponibilidade, credencial expirada ou LLM_PROVIDER=nenhum;
- NUNCA expõe chaves, tokens ou IDs de conta em logs ou retornos.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Configurações padrão conforme Issue #6
DEFAULT_PROVIDER = "nenhum"
DEFAULT_PROFILE = "hackats"
DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "amazon.nova-pro-v1:0"
DEFAULT_FALLBACK_MODEL_ID = "amazon.nova-lite-v1:0"
DEFAULT_EMBED_MODEL_ID = "us.cohere.embed-v4:0"

_bedrock_client = None


def get_llm_provider() -> str:
    """Retorna o provedor de LLM configurado (bedrock ou nenhum)."""
    return os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower().strip()


def get_aws_profile() -> str:
    """Retorna o perfil AWS local (padrão hackats)."""
    return os.getenv("AWS_PROFILE", DEFAULT_PROFILE).strip()


def get_aws_region() -> str:
    """Retorna a região AWS (padrão us-east-1)."""
    return os.getenv("AWS_REGION", DEFAULT_REGION).strip()


def get_bedrock_model_id() -> str:
    """Retorna o modelo de texto principal do Bedrock."""
    return os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID).strip()


def get_bedrock_fallback_model_id() -> str:
    """Retorna o modelo de texto de fallback rápido."""
    return os.getenv("BEDROCK_FALLBACK_MODEL_ID", DEFAULT_FALLBACK_MODEL_ID).strip()


def get_bedrock_embed_model_id() -> str:
    """Retorna o modelo de embeddings do Bedrock."""
    return os.getenv("BEDROCK_EMBED_MODEL_ID", DEFAULT_EMBED_MODEL_ID).strip()


def get_bedrock_client(force_new: bool = False):
    """Obtém cliente boto3 para bedrock-runtime de forma segura."""
    global _bedrock_client
    if _bedrock_client is not None and not force_new:
        return _bedrock_client

    try:
        import boto3
    except ImportError:
        logger.warning("boto3 não instalado; Bedrock indisponível.")
        return None

    profile = get_aws_profile()
    region = get_aws_region()

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        _bedrock_client = session.client("bedrock-runtime", region_name=region)
        return _bedrock_client
    except Exception as e_prof:
        logger.debug(f"Tentativa com profile {profile} falhou ({type(e_prof).__name__}), tentando sessão padrão...")
        try:
            session = boto3.Session(region_name=region)
            _bedrock_client = session.client("bedrock-runtime", region_name=region)
            return _bedrock_client
        except Exception as e_def:
            logger.warning(f"Não foi possível conectar ao Amazon Bedrock ({type(e_def).__name__}).")
            return None


def get_ia_status() -> Dict[str, Any]:
    """Retorna o status da IA para /api/saude sem dados de conta ou credenciais."""
    provider = get_llm_provider()
    if provider != "bedrock":
        return {
            "provedor": provider,
            "modelo": None,
            "disponivel": False,
        }

    client = get_bedrock_client()
    disponivel = client is not None
    return {
        "provedor": "bedrock",
        "modelo": get_bedrock_model_id(),
        "disponivel": disponivel,
    }


def gerar_resposta_converse(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 400,
    temperature: float = 0.0,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Gera texto usando a API Converse do Bedrock com fallback para o modelo reserva.

    Retorna:
        (texto_resposta, modelo_utilizado, mensagem_erro_se_houver)
    """
    if get_llm_provider() != "bedrock":
        return None, None, "LLM_PROVIDER não é bedrock"

    client = get_bedrock_client()
    if not client:
        return None, None, "Cliente Bedrock não inicializado"

    models_to_try = [
        get_bedrock_model_id(),
        get_bedrock_fallback_model_id(),
    ]

    last_error = None
    for model_id in models_to_try:
        try:
            response = client.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_message}]}],
                inferenceConfig={
                    "maxTokens": max_tokens,
                    "temperature": temperature,
                },
            )
            output = response.get("output", {})
            msg = output.get("message", {})
            content = msg.get("content", [])
            if content and "text" in content[0]:
                return content[0]["text"].strip(), model_id, None
        except Exception as e:
            err_name = type(e).__name__
            logger.warning(f"Erro ao chamar modelo Bedrock {model_id}: {err_name}")
            last_error = f"{err_name} no modelo {model_id}"

    return None, None, last_error


def gerar_embeddings(
    texts: List[str],
    input_type: str = "search_document",
    batch_size: int = 50,
) -> Optional[List[List[float]]]:
    """Gera embeddings vetoriais com us.cohere.embed-v4:0 no Bedrock.

    Retorna lista de vetores de 1536 dimensões ou None se falhar.
    """
    if get_llm_provider() != "bedrock":
        return None

    client = get_bedrock_client()
    if not client or not texts:
        return None

    model_id = get_bedrock_embed_model_id()
    todos_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        body = json.dumps(
            {
                "texts": batch,
                "input_type": input_type,
                "truncate": "END",
            }
        )
        try:
            res = client.invoke_model(modelId=model_id, body=body)
            data = json.loads(res["body"].read())
            embs = data.get("embeddings", {})
            if isinstance(embs, dict):
                embs = embs.get("float", [])
            if not embs or len(embs) != len(batch):
                logger.warning(f"Formato inesperado de embeddings retornado por {model_id}")
                return None
            todos_embeddings.extend(embs)
        except Exception as e:
            logger.warning(f"Falha ao gerar embeddings no Bedrock ({type(e).__name__})")
            return None

    return todos_embeddings
