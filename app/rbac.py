"""Controle de Acesso Baseado em Cargo (RBAC) - HACKA/TS 2026 (Issue #22).

Implementa o controle de acesso conforme `docs/propostas/RBAC-MVP.md`:
- Matriz de cargos em `data/rbac/matriz.yaml`
- Fixture de usuários e e-mails em `data/rbac/usuarios.yaml`
- Resolução por header `X-Cargo`, `X-User-Email`, query params (`cargo`, `email`) ou payload
- Filtro no retrieval (busca lexical e híbrida) para impedir vazamento de trechos e citações
- Bloqueio HTTP 403 Forbidden para acesso direto a documentos, perspectivas e radar restritos
- Trilha de auditoria local em JSONL (`data/rbac/audit.jsonl`)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import yaml

logger = logging.getLogger(__name__)

RBAC_DIR = Path(__file__).resolve().parent.parent / "data" / "rbac"
MATRIZ_FILE = RBAC_DIR / "matriz.yaml"
USUARIOS_FILE = RBAC_DIR / "usuarios.yaml"
AUDIT_FILE = RBAC_DIR / "audit.jsonl"


@dataclass
class RegraCargo:
    cargo: str
    descricao: str = ""
    assuntos_permitidos: List[str] = field(default_factory=list)
    tipos_permitidos: List[str] = field(default_factory=list)
    documentos_proibidos: List[str] = field(default_factory=list)
    perspectivas_permitidas: List[str] = field(default_factory=list)
    ver_radar: bool = False
    ver_substituidos: bool = False
    ver_grafo: bool = True
    ver_relatorio: bool = False


@dataclass
class UsuarioFixture:
    email: str
    nome: str
    cargo: str
    descricao: str = ""


class RBACService:
    """Gerenciador centralizado de regras de acesso por cargo."""

    def __init__(self):
        self.cargos: Dict[str, RegraCargo] = {}
        self.usuarios_por_email: Dict[str, UsuarioFixture] = {}
        self.aliases: Dict[str, str] = {}
        self.carregar_configuracoes()

    def carregar_configuracoes(self):
        self.cargos.clear()
        self.usuarios_por_email.clear()
        self.aliases.clear()

        # Carregar matriz
        if MATRIZ_FILE.exists():
            try:
                with open(MATRIZ_FILE, "r", encoding="utf-8") as f:
                    dados = yaml.safe_load(f) or {}
                for cargo_id, c in dados.get("cargos", {}).items():
                    self.cargos[cargo_id.lower()] = RegraCargo(
                        cargo=cargo_id.lower(),
                        descricao=c.get("descricao", ""),
                        assuntos_permitidos=c.get("assuntos_permitidos", []),
                        tipos_permitidos=c.get("tipos_permitidos", []),
                        documentos_proibidos=c.get("documentos_proibidos", []),
                        perspectivas_permitidas=c.get("perspectivas_permitidas", []),
                        ver_radar=bool(c.get("ver_radar", False)),
                        ver_substituidos=bool(c.get("ver_substituidos", False)),
                        ver_grafo=bool(c.get("ver_grafo", True)),
                        ver_relatorio=bool(c.get("ver_relatorio", False)),
                    )
            except Exception as e:
                logger.error(f"Erro ao carregar {MATRIZ_FILE}: {e}")

        # Defaults se matriz vazia
        if not self.cargos:
            self._criar_defaults_matriz()

        # Carregar usuários
        if USUARIOS_FILE.exists():
            try:
                with open(USUARIOS_FILE, "r", encoding="utf-8") as f:
                    dados_u = yaml.safe_load(f) or {}
                for u in dados_u.get("usuarios", []):
                    usr = UsuarioFixture(
                        email=u.get("email", "").lower().strip(),
                        nome=u.get("nome", ""),
                        cargo=u.get("cargo", "").lower().strip(),
                        descricao=u.get("descricao", ""),
                    )
                    self.usuarios_por_email[usr.email] = usr

                for alias_email, cargo in dados_u.get("aliases", {}).items():
                    self.aliases[alias_email.lower().strip()] = cargo.lower().strip()
            except Exception as e:
                logger.error(f"Erro ao carregar {USUARIOS_FILE}: {e}")

    def _criar_defaults_matriz(self):
        self.cargos["empregado"] = RegraCargo(
            cargo="empregado",
            descricao="Colaborador",
            assuntos_permitidos=["ferias", "inovacao", "geral"],
            tipos_permitidos=["NG", "PX", "FM", "TB", "FL", "RG"],
            documentos_proibidos=["CTR_2026-012", "NT_2026-018", "NT_2026-021"],
            perspectivas_permitidas=["pessoas"],
            ver_radar=False,
            ver_substituidos=False,
        )
        self.cargos["financeiro"] = RegraCargo(
            cargo="financeiro",
            descricao="Financeiro",
            assuntos_permitidos=["locacao", "inovacao", "ferias", "geral"],
            tipos_permitidos=["CTR", "NT", "NG", "PX", "TB", "RG"],
            documentos_proibidos=[],
            perspectivas_permitidas=["financeiro", "gestao", "pessoas"],
            ver_radar=True,
            ver_substituidos=False,
            ver_relatorio=True,
        )
        self.cargos["diretoria"] = RegraCargo(
            cargo="diretoria",
            descricao="Diretoria",
            assuntos_permitidos=["*"],
            tipos_permitidos=["*"],
            documentos_proibidos=[],
            perspectivas_permitidas=["juridico", "financeiro", "pessoas", "gestao"],
            ver_radar=True,
            ver_substituidos=True,
            ver_relatorio=True,
        )

    def resolver_cargo(
        self,
        cargo: Optional[str] = None,
        x_cargo: Optional[str] = None,
        x_user_email: Optional[str] = None,
        email: Optional[str] = None,
        perfil: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve o cargo a partir de cabeçalhos, parâmetros, e-mails de fixture ou perfil."""
        # 1. Header X-Cargo direto
        if x_cargo and x_cargo.strip():
            c = x_cargo.strip().lower()
            return self._normalizar_cargo(c)

        # 2. Query param ou payload 'cargo'
        if cargo and cargo.strip():
            c = cargo.strip().lower()
            return self._normalizar_cargo(c)

        # 3. Header X-User-Email
        if x_user_email and x_user_email.strip():
            c = self._cargo_por_email(x_user_email.strip())
            if c:
                return c

        # 4. Query param ou payload 'email'
        if email and email.strip():
            c = self._cargo_por_email(email.strip())
            if c:
                return c

        # 5. Se perfil foi informado e corresponde a um cargo (ex: empregado, financeiro)
        if perfil and perfil.strip():
            p = perfil.strip().lower()
            # Mapeamento de perfis para cargos
            p_map = {
                "empregado": "empregado",
                "p-emp": "empregado",
                "gestor": "gestor",
                "p-ges": "gestor",
                "financeiro": "financeiro",
                "p-fin": "financeiro",
                "rh": "rh",
                "p-rh": "rh",
                "juridico": "juridico",
                "p-jur": "juridico",
                "diretoria": "diretoria",
                "p-dir": "diretoria",
            }
            if p in p_map:
                return p_map[p]

        # 6. Variável de ambiente default (ex.: RBAC_DEFAULT_CARGO=empregado)
        default_env = os.getenv("RBAC_DEFAULT_CARGO")
        if default_env and default_env.strip():
            return self._normalizar_cargo(default_env.strip().lower())

        return None

    def _normalizar_cargo(self, cargo: str) -> str:
        cargo = cargo.lower().strip()
        # Mapeamento amigável
        aliases_cargo = {
            "p-emp": "empregado",
            "p-fin": "financeiro",
            "gfi": "financeiro",
            "p-ges": "gestor",
            "p-rh": "rh",
            "ggc": "rh",
            "p-jur": "juridico",
            "gco": "juridico",
            "p-dir": "diretoria",
            "admin": "diretoria",
        }
        return aliases_cargo.get(cargo, cargo)

    def _cargo_por_email(self, email: str) -> Optional[str]:
        em = email.lower().strip()
        if em in self.usuarios_por_email:
            return self.usuarios_por_email[em].cargo
        if em in self.aliases:
            return self.aliases[em]
        # Se for nome.cargo@acme.test ou cargo@acme.test
        for c in self.cargos:
            if f".{c}@" in em or em.startswith(f"{c}@"):
                return c
        return None

    def documento_permitido(self, cargo: Optional[str], doc_ou_codigo: Any) -> bool:
        """Verifica se um documento é visível/recuperável pelo cargo."""
        if not cargo or cargo.lower() == "diretoria":
            return True

        c_norm = self._normalizar_cargo(cargo)
        regra = self.cargos.get(c_norm)
        if not regra:
            # Cargo desconhecido -> menor privilégio (empregado)
            regra = self.cargos.get("empregado")
            if not regra:
                return False

        # Extrair atributos do objeto
        codigo = ""
        assunto = ""
        substituido = False
        tipo = ""

        if isinstance(doc_ou_codigo, str):
            codigo = doc_ou_codigo
            tipo = codigo.split("_")[0] if "_" in codigo else ""
            # Buscar metadados do código se estiver em memória
        elif hasattr(doc_ou_codigo, "codigo"):
            codigo = doc_ou_codigo.codigo
            assunto = getattr(doc_ou_codigo, "assunto", "")
            substituido = getattr(doc_ou_codigo, "substituido", False)
            tipo = getattr(doc_ou_codigo, "tipo", "") or (codigo.split("_")[0] if "_" in codigo else "")

        # 1. Proibição explícita
        if codigo in regra.documentos_proibidos:
            return False

        # 2. Versões substituídas
        if substituido and not regra.ver_substituidos:
            return False

        # 3. Assunto permitido
        if regra.assuntos_permitidos and "*" not in regra.assuntos_permitidos:
            if assunto and assunto not in regra.assuntos_permitidos:
                return False

        # 4. Tipo permitido
        if regra.tipos_permitidos and "*" not in regra.tipos_permitidos:
            if tipo and tipo not in regra.tipos_permitidos:
                return False

        return True

    def perspectiva_permitida(self, cargo: Optional[str], perspectiva_id: str) -> bool:
        """Verifica se uma perspectiva analítica pode ser acessada pelo cargo."""
        if not cargo or cargo.lower() == "diretoria":
            return True

        c_norm = self._normalizar_cargo(cargo)
        regra = self.cargos.get(c_norm, self.cargos.get("empregado"))
        if not regra:
            return False

        pid = perspectiva_id.lower().strip()
        return pid in regra.perspectivas_permitidas

    def radar_permitido(self, cargo: Optional[str]) -> bool:
        """Verifica se o radar de contradições é acessível pelo cargo."""
        if not cargo or cargo.lower() == "diretoria":
            return True

        c_norm = self._normalizar_cargo(cargo)
        regra = self.cargos.get(c_norm, self.cargos.get("empregado"))
        return bool(regra and regra.ver_radar)

    def relatorio_permitido(
        self,
        cargo: Optional[str],
        perspectiva: Optional[str] = None,
        codigo: Optional[str] = None,
    ) -> bool:
        """Verifica se o relatório executivo é acessível pelo cargo."""
        if not cargo or cargo.lower() == "diretoria":
            return True

        c_norm = self._normalizar_cargo(cargo)
        regra = self.cargos.get(c_norm, self.cargos.get("empregado"))
        if not regra or not regra.ver_relatorio:
            return False

        if perspectiva and not self.perspectiva_permitida(cargo, perspectiva):
            return False
        if codigo and not self.documento_permitido(cargo, codigo):
            return False

        return True

    def registrar_auditoria(self, cargo: Optional[str], endpoint: str, recurso: str, permitido: bool):
        """Registra log local de auditoria de acesso em JSONL (RNF de segurança, sem PII)."""
        try:
            RBAC_DIR.mkdir(parents=True, exist_ok=True)
            registro = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cargo": cargo or "anonimo",
                "endpoint": endpoint,
                "recurso": recurso,
                "status": "permitido" if permitido else "negado",
            }
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Falha ao registrar auditoria RBAC: {e}")


# Instância global singleton
_rbac_service: Optional[RBACService] = None


def get_rbac() -> RBACService:
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService()
    return _rbac_service
