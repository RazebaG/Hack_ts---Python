import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional
from app.models import AvaliacaoRequest, AvaliacaoResponse, AvaliacaoResumoResponse


class AvaliacoesRepository:
    """Repositório de avaliações de respostas (C14, RF39, RNF16).

    Persistência em memória e em arquivo data/avaliacoes.jsonl.
    Garante privacidade: nada de nome, e-mail ou ID de usuário.
    """

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or self._discover_file_path()
        self._lock = Lock()
        self._registros: List[dict] = []
        self._carregar()

    @staticmethod
    def _discover_file_path() -> Path:
        env_path = os.getenv("AVALIACOES_FILE")
        if env_path:
            return Path(env_path)
        base = Path(__file__).resolve().parent.parent / "data" / "avaliacoes.jsonl"
        return base

    def _carregar(self) -> None:
        if not self.file_path.exists():
            return
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        self._registros.append(json.loads(line))
                    except Exception:
                        pass

    def registrar(self, req: AvaliacaoRequest) -> AvaliacaoResponse:
        registro_id = f"aval_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # RNF16: Privacidade estrita - apenas resposta_id, util, motivo, comentario, canal, perfil, registrado_em
        dado = {
            "id": registro_id,
            "resposta_id": req.resposta_id,
            "util": req.util,
            "motivo": req.motivo,
            "comentario": req.comentario,
            "canal": req.canal,
            "perfil": req.perfil,
            "registrado_em": timestamp,
        }

        with self._lock:
            self._registros.append(dado)
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(dado, ensure_ascii=False) + "\n")

        return AvaliacaoResponse(id=registro_id, registrado_em=timestamp)

    def resumo(self) -> AvaliacaoResumoResponse:
        with self._lock:
            total = len(self._registros)
            uteis = sum(1 for r in self._registros if r.get("util") is True)
            por_canal: Dict[str, int] = {"web": 0, "slack": 0, "teams": 0}
            for r in self._registros:
                c = r.get("canal", "web")
                por_canal[c] = por_canal.get(c, 0) + 1
            return AvaliacaoResumoResponse(
                total=total,
                uteis=uteis,
                por_canal=por_canal,
            )

    def limpar(self) -> None:
        """Limpa registros em memória e no arquivo (útil para testes isolados)."""
        with self._lock:
            self._registros.clear()
            if self.file_path.exists():
                try:
                    self.file_path.unlink()
                except Exception:
                    pass
