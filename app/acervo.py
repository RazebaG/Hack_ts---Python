import os
from pathlib import Path
from typing import List, Optional, Dict
from app.models import DocumentoResumo, DocumentoDetalhe
from app.parser import parse_document_file


class AcervoRepository:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or self._discover_data_dir()
        self.documentos: List[DocumentoDetalhe] = []
        self._por_codigo_versao: Dict[tuple[str, str], DocumentoDetalhe] = {}
        self._por_codigo: Dict[str, List[DocumentoDetalhe]] = {}
        self.carregar()

    @staticmethod
    def _discover_data_dir() -> Path:
        env_dir = os.getenv("ACERVO_DIR")
        if env_dir:
            return Path(env_dir)

        # Buscar relativo ao arquivo atual
        candidato = Path(__file__).resolve().parent.parent / "data" / "acervo"
        if candidato.exists():
            return candidato

        # Buscar relativo ao cwd
        cwd_candidato = Path.cwd() / "data" / "acervo"
        if cwd_candidato.exists():
            return cwd_candidato

        return candidato

    def carregar(self) -> None:
        self.documentos.clear()
        self._por_codigo_versao.clear()
        self._por_codigo.clear()

        if not self.data_dir.exists():
            return

        md_files = sorted(self.data_dir.rglob("*.md"))
        for file_path in md_files:
            # Ignorar o catálogo de instruções e referências
            if "CATALOGO" in file_path.name.upper():
                continue

            doc = parse_document_file(file_path)
            self.documentos.append(doc)

            key = (doc.codigo, doc.versao)
            self._por_codigo_versao[key] = doc

            if doc.codigo not in self._por_codigo:
                self._por_codigo[doc.codigo] = []
            self._por_codigo[doc.codigo].append(doc)

    def total(self) -> int:
        return len(self.documentos)

    def listar(
        self,
        assunto: Optional[str] = None,
        substituido: Optional[bool] = None,
        serie: Optional[int] = None,
    ) -> List[DocumentoResumo]:
        resultado = []
        for d in self.documentos:
            if assunto and d.assunto.lower() != assunto.lower():
                continue
            if substituido is not None and d.substituido != substituido:
                continue
            if serie is not None and d.tema.serie != serie:
                continue
            resumo = DocumentoResumo(
                codigo=d.codigo,
                titulo=d.titulo,
                tipo=d.tipo,
                tipo_nome=d.tipo_nome,
                versao=d.versao,
                fase=d.fase,
                vigencia=d.vigencia,
                vinculado_a=d.vinculado_a,
                referencia=d.referencia,
                assunto=d.assunto,
                substituido=d.substituido,
                elaborado_por=d.elaborado_por,
                aprovado_por=d.aprovado_por,
                camada=d.camada,
                tema=d.tema,
            )
            resultado.append(resumo)
        return resultado

    def buscar(self, codigo: str, versao: Optional[str] = None) -> Optional[DocumentoDetalhe]:
        docs = self._por_codigo.get(codigo, [])
        if not docs:
            return None

        if versao:
            return self._por_codigo_versao.get((codigo, versao))

        # Sem versão -> buscar a versão vigente (substituido == False)
        for d in docs:
            if not d.substituido:
                return d

        # Caso não haja vigente, retorna a última da lista
        return docs[-1]

    def estatisticas(self) -> dict:
        total = len(self.documentos)
        vigentes = sum(1 for d in self.documentos if not d.substituido)
        substituidos = sum(1 for d in self.documentos if d.substituido)

        por_assunto: Dict[str, int] = {}
        por_tipo: Dict[str, int] = {}
        por_grupo: Dict[str, int] = {}
        por_serie: Dict[str, int] = {}

        for d in self.documentos:
            por_assunto[d.assunto] = por_assunto.get(d.assunto, 0) + 1
            por_tipo[d.tipo] = por_tipo.get(d.tipo, 0) + 1
            por_grupo[d.camada.grupo] = por_grupo.get(d.camada.grupo, 0) + 1
            serie_rotulo = f"Série {d.tema.serie}" if d.tema.serie is not None else "Sem série"
            por_serie[serie_rotulo] = por_serie.get(serie_rotulo, 0) + 1

        return {
            "total": total,
            "vigentes": vigentes,
            "substituidos": substituidos,
            "por_assunto": por_assunto,
            "por_tipo": por_tipo,
            "por_grupo": por_grupo,
            "por_serie": por_serie,
        }
