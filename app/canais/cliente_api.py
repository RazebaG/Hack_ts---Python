"""Cliente HTTP da API do acervo usado pelos canais.

O bot não acessa os dados por conta própria: toda resposta vem da API.
"""

import os
from typing import Any, Dict, Optional

import httpx

API_URL_PADRAO = "http://localhost:8000"


class ErroAPI(Exception):
    """A API não respondeu ou respondeu com erro."""

    def __init__(self, mensagem: str, status: Optional[int] = None, detalhe: Optional[str] = None):
        super().__init__(mensagem)
        self.status = status
        self.detalhe = detalhe

    @property
    def recusado(self) -> bool:
        """4xx: a API está no ar, mas recusou o pedido (ex.: perspectiva inválida)."""
        return self.status is not None and 400 <= self.status < 500


class ClienteAPI:
    def __init__(self, base_url: Optional[str] = None, http: Optional[httpx.Client] = None, timeout: float = 20.0):
        self.base_url = (base_url or os.getenv("API_URL") or API_URL_PADRAO).rstrip("/")
        # `http` permite injetar um cliente (ex.: TestClient do FastAPI) nos testes, sem rede.
        self._http = http or httpx.Client(base_url=self.base_url, timeout=timeout)

    def _requisitar(self, metodo: str, caminho: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            r = self._http.request(metodo, caminho, **kwargs)
        except httpx.HTTPError as e:
            raise ErroAPI(f"API indisponível em {self.base_url}: {e.__class__.__name__}") from e
        if r.status_code >= 400:
            try:
                detalhe = r.json().get("detail", r.text)
            except ValueError:
                detalhe = r.text
            if not isinstance(detalhe, str):
                detalhe = str(detalhe)
            raise ErroAPI(f"{metodo} {caminho} → {r.status_code}: {detalhe}", status=r.status_code, detalhe=detalhe)
        return r.json()

    def perguntar(self, pergunta: str, perfil: Optional[str] = None) -> Dict[str, Any]:
        return self._requisitar("POST", "/api/perguntar", json={"pergunta": pergunta, "perfil": perfil})

    def radar(self, perspectiva: Optional[str] = None) -> Dict[str, Any]:
        params = {"perspectiva": perspectiva} if perspectiva else None
        return self._requisitar("GET", "/api/radar", params=params)

    def avaliar(self, resposta_id: str, util: bool, canal: str, perfil: Optional[str] = None) -> Dict[str, Any]:
        corpo = {"resposta_id": resposta_id, "util": util, "canal": canal, "perfil": perfil}
        return self._requisitar("POST", "/api/avaliacoes", json=corpo)
