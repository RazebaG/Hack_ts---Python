"""Cliente de IA generativa (Amazon Bedrock, API Converse) — Issue #6.

Configuração só por variáveis de ambiente (carregadas de `.env` quando houver):
    LLM_PROVIDER=bedrock|nenhum      (padrão: nenhum)
    AWS_PROFILE                      (perfil local; nunca lido/copiado pelo código)
    AWS_REGION=us-east-1
    BEDROCK_MODEL_ID                 (padrão: amazon.nova-pro-v1:0)
    BEDROCK_FALLBACK_MODEL_ID        (padrão: amazon.nova-lite-v1:0)

Qualquer falha (sem boto3, credencial vencida, timeout, throttling) vira
`ErroIA`; quem chama degrada para a resposta extrativa. A demo nunca quebra
por causa da IA.
"""

import hashlib
import logging
import os
import threading
from typing import Any, Dict, List, Optional

try:  # python-dotenv é opcional em tempo de execução
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

MODELO_PADRAO = "amazon.nova-pro-v1:0"
MODELO_RESERVA_PADRAO = "amazon.nova-lite-v1:0"

# Códigos de erro em que trocar de modelo não resolve (problema de credencial/acesso)
_ERROS_CREDENCIAL = {
    "ExpiredTokenException",
    "ExpiredToken",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "AccessDeniedException",
    "InvalidClientTokenId",
    "ProfileNotFound",
    "NoCredentialsError",
    "PartialCredentialsError",
}


class ErroIA(Exception):
    """Falha ao obter texto do modelo. A mensagem é segura para exibir (sem dados da conta)."""


class ClienteIA:
    def __init__(
        self,
        provedor: Optional[str] = None,
        modelo: Optional[str] = None,
        modelo_reserva: Optional[str] = None,
        regiao: Optional[str] = None,
        cliente: Any = None,
    ):
        self.provedor = (provedor or os.getenv("LLM_PROVIDER") or "nenhum").strip().lower()
        self.modelo = modelo or os.getenv("BEDROCK_MODEL_ID") or MODELO_PADRAO
        self.modelo_reserva = modelo_reserva or os.getenv("BEDROCK_FALLBACK_MODEL_ID") or MODELO_RESERVA_PADRAO
        self.regiao = regiao or os.getenv("AWS_REGION") or "us-east-1"
        self._cliente = cliente
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()
        self.ultimo_erro: Optional[str] = None
        self.ultimo_modelo: Optional[str] = None

    @property
    def ativo(self) -> bool:
        return self.provedor == "bedrock"

    def status(self) -> Dict[str, Any]:
        """Estado para /api/saude, sem nenhum dado da conta."""
        if not self.ativo:
            return {"provedor": "nenhum", "modelo": None, "disponivel": False}
        return {
            "provedor": "bedrock",
            "modelo": self.ultimo_modelo or self.modelo,
            "disponivel": self.ultimo_erro is None,
        }

    def _bedrock(self):
        if self._cliente is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as e:
                raise ErroIA("biblioteca boto3 não instalada") from e
            # O perfil (AWS_PROFILE) é resolvido pelo próprio boto3; o código não lê ~/.aws.
            sessao = boto3.Session(region_name=self.regiao)
            self._cliente = sessao.client(
                "bedrock-runtime",
                config=Config(connect_timeout=3, read_timeout=25, retries={"max_attempts": 2, "mode": "standard"}),
            )
        return self._cliente

    @staticmethod
    def _codigo_erro(e: Exception) -> str:
        resp = getattr(e, "response", None)
        if isinstance(resp, dict):
            return str(resp.get("Error", {}).get("Code", ""))
        return type(e).__name__

    def _converse(self, modelo: str, sistema: str, mensagem: str, max_tokens: int) -> str:
        resp = self._bedrock().converse(
            modelId=modelo,
            system=[{"text": sistema}],
            messages=[{"role": "user", "content": [{"text": mensagem}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1, "topP": 0.9},
        )
        partes: List[str] = [
            c.get("text", "") for c in resp.get("output", {}).get("message", {}).get("content", []) if "text" in c
        ]
        texto = "".join(partes).strip()
        if not texto:
            raise ErroIA("o modelo não devolveu texto")
        return texto

    def gerar(self, sistema: str, mensagem: str, max_tokens: int = 900) -> str:
        """Gera texto com o modelo padrão; em erro não-credencial, tenta o reserva."""
        if not self.ativo:
            raise ErroIA("IA desativada (LLM_PROVIDER=nenhum)")

        chave = hashlib.sha256(f"{sistema}\x00{mensagem}\x00{max_tokens}".encode("utf-8")).hexdigest()
        with self._lock:
            if chave in self._cache:
                return self._cache[chave]

        modelos = [self.modelo] + ([self.modelo_reserva] if self.modelo_reserva != self.modelo else [])
        ultimo: Optional[str] = None
        for modelo in modelos:
            try:
                texto = self._converse(modelo, sistema, mensagem, max_tokens)
            except ErroIA as e:
                ultimo = str(e)
                if "boto3" in ultimo:
                    break
                continue
            except Exception as e:  # botocore: ClientError, NoCredentialsError, timeouts...
                codigo = self._codigo_erro(e)
                ultimo = f"falha no Bedrock ({codigo})"
                logger.warning("Bedrock %s falhou: %s", modelo, codigo)
                if codigo in _ERROS_CREDENCIAL or "Credential" in codigo or "Token" in codigo:
                    ultimo = "credencial da AWS ausente ou vencida"
                    break
                continue
            self.ultimo_erro = None
            self.ultimo_modelo = modelo
            with self._lock:
                self._cache[chave] = texto
            return texto

        self.ultimo_erro = ultimo or "falha no Bedrock"
        raise ErroIA(self.ultimo_erro)


_cliente_global: Optional[ClienteIA] = None


def get_cliente_ia() -> ClienteIA:
    global _cliente_global
    if _cliente_global is None:
        _cliente_global = ClienteIA()
    return _cliente_global
