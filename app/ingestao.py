"""Envio em lote com classificação por tema e digitalização (issue #10).

RF23–RF26, RF35, RF36 (regras 1–2), RNF18; contrato C18.

- Arquivos digitais (.md, .pdf com texto) passam pelo parser do acervo
  (`app.parser.parse_document_text`) e recebem um tema sugerido.
- Fotos e scans (.jpg/.png, 1 página) são lidos por `app.digitalizacao` e ficam em
  "revisar": nada é publicado sem revisão humana do texto lido.
- O erro de um arquivo não para os demais.
- Publicar inclui o documento no acervo em memória (catálogo, busca, painéis, radar).
"""

import io
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from app.acervo import AcervoRepository
from app.digitalizacao import LeituraFalhou, ler_imagem
from app.models import DocumentoDetalhe, Tema
from app.parser import parse_document_text
from app.taxonomia import SERIES_CATALOGO, derivar_tema, inferir_norma_raiz

# ---------------------------------------------------------------------------
# Limites e tipos (RF35, REQUISITOS-v2 §4)
# ---------------------------------------------------------------------------
MAX_ARQUIVOS = 20
MAX_BYTES_ARQUIVO = 10 * 1024 * 1024
MAX_BYTES_LOTE = 50 * 1024 * 1024

TIPOS_DIGITAIS = {".md": "markdown", ".pdf": "pdf"}
TIPOS_FOTO = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png"}
ASSINATURAS = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}

MSG_TIPO = "tipo não aceito. Envie PDF, Markdown, JPG ou PNG."
MSG_CONTEUDO_INVALIDO = "Envie PDF, Markdown, JPG ou PNG válido."
MSG_SEM_TEMA = "Sem tema: escolha um."
MSG_FOTO_ILEGIVEL = "não deu para ler esta foto. Tente com mais luz e a página inteira no quadro."

ROTULOS_ASSUNTO = {"ferias": "Férias", "inovacao": "Inovação", "locacao": "Locação", "geral": "Geral"}

# Regra "assunto por palavras do conteúdo" (usada quando o código não leva a um
# documento do acervo). Palavras normalizadas sem acento.
PALAVRAS_ASSUNTO = {
    "ferias": ("ferias", "periodo aquisitivo", "abono pecuniario"),
    "inovacao": ("inovacao", "ideia", "ideias", "premiacao"),
    "locacao": ("locacao", "coworking", "locatario", "locador", "aluguel"),
}

CODIGO_RE = re.compile(r"\b(?:NG|PX|PP|GU|FM|TB|FL|RG|CT|DV|CTR|NT)_[0-9]+(?:-[0-9]+)?\b")


class LoteInvalido(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )


# ---------------------------------------------------------------------------
# Classificação por tema (RF36, regras 1–2)
# ---------------------------------------------------------------------------
def assunto_por_palavras(texto: str) -> Optional[str]:
    norm = _sem_acento(texto)
    contagem = {a: sum(norm.count(p) for p in palavras) for a, palavras in PALAVRAS_ASSUNTO.items()}
    melhor = max(contagem, key=contagem.get)
    return melhor if contagem[melhor] > 0 else None


def _texto_documento(doc: DocumentoDetalhe) -> str:
    return " ".join([doc.titulo or ""] + [f"{s.titulo} {s.texto}" for s in doc.secoes])


def rotulo_tema(assunto: str, serie: Optional[int], serie_nome: Optional[str]) -> str:
    rotulo = ROTULOS_ASSUNTO.get(assunto, assunto.capitalize() if assunto else "")
    if serie is not None:
        return f"{rotulo} (Série {serie} · {serie_nome})"
    return rotulo


def sugerir_tema(doc: DocumentoDetalhe, acervo: AcervoRepository) -> Optional[dict]:
    """Tema sugerido {assunto, serie, serie_nome, confianca, motivo} ou None (sem código)."""
    codigo = (doc.codigo or "").strip()
    if not codigo:
        return None

    sigla = codigo.split("_")[0].upper() if "_" in codigo else ""
    assunto: Optional[str] = None
    motivo = ""
    confianca = 0.0

    if sigla in ("CTR", "NT", "CT"):
        # Regra 2: número próprio → assunto do documento citado em Referência
        alvo = None
        for campo in (doc.referencia, doc.vinculado_a):
            m = CODIGO_RE.search(campo or "")
            if m:
                alvo = m.group(0)
                break
        ref_doc = acervo.buscar(alvo) if alvo else None
        if ref_doc:
            assunto = ref_doc.assunto
            motivo = f"o {codigo} tem número próprio e a Referência {alvo} é de {ROTULOS_ASSUNTO.get(assunto, assunto)}"
            confianca = 0.9
    else:
        # Regra 1: código → série pela faixa do catálogo e documento pai
        raiz = inferir_norma_raiz(codigo, doc.vinculado_a)
        pai = doc.vinculado_a.strip() if doc.vinculado_a and doc.vinculado_a.strip() else raiz
        pai_doc = acervo.buscar(pai) if pai else None
        raiz_doc = acervo.buscar(raiz) if raiz else None
        ref_doc = pai_doc or raiz_doc
        if ref_doc and ref_doc.codigo != codigo:
            assunto = ref_doc.assunto
            motivo = f"o código {codigo} se liga à {raiz or ref_doc.codigo}"
            confianca = 0.95

    if not assunto:
        assunto = assunto_por_palavras(_texto_documento(doc))
        if assunto:
            motivo = (motivo + "; " if motivo else "") + "assunto pelas palavras do conteúdo"
            confianca = 0.6
        else:
            assunto = "geral"
            motivo = (motivo + "; " if motivo else "") + "código sem documento pai no acervo e sem palavras do assunto"
            confianca = 0.3

    tema = derivar_tema(codigo=codigo, assunto=assunto, vinculado_a=doc.vinculado_a, referencia=doc.referencia)
    if tema.serie is not None and "série" not in motivo:
        motivo += f"; série {tema.serie} pela faixa de numeração do catálogo §5"
    return {
        "assunto": tema.assunto,
        "serie": tema.serie,
        "serie_nome": tema.serie_nome,
        "confianca": confianca,
        "motivo": motivo,
        "rotulo": rotulo_tema(tema.assunto, tema.serie, tema.serie_nome),
        "observacao": tema.observacao,
    }


# ---------------------------------------------------------------------------
# Extração de texto
# ---------------------------------------------------------------------------
def extrair_texto_pdf(conteudo: bytes) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(conteudo))
    return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages).strip()


def validar_tipo(nome: str, conteudo: bytes) -> Tuple[Optional[str], Optional[Tuple[int, str]]]:
    """Devolve (extensão, erro). erro = (status_http, mensagem)."""
    ext = Path(nome or "").suffix.lower()
    if ext not in TIPOS_DIGITAIS and ext not in TIPOS_FOTO:
        return None, (415, MSG_TIPO)
    if len(conteudo) == 0:
        return ext, (422, "arquivo vazio.")
    if len(conteudo) > MAX_BYTES_ARQUIVO:
        return ext, (413, "arquivo maior que 10 MB. Divida o documento ou reduza a imagem.")
    assinaturas = ASSINATURAS.get(ext)
    if assinaturas and not any(conteudo.startswith(a) for a in assinaturas):
        return ext, (415, f"o conteúdo não corresponde a um arquivo {ext}. {MSG_CONTEUDO_INVALIDO}")
    if ext == ".md":
        if b"\x00" in conteudo:
            return ext, (415, f"o conteúdo não é texto Markdown. {MSG_CONTEUDO_INVALIDO}")
        try:
            conteudo.decode("utf-8")
        except UnicodeDecodeError:
            return ext, (415, "o Markdown precisa estar em UTF-8.")
    return ext, None


# ---------------------------------------------------------------------------
# Estado do lote
# ---------------------------------------------------------------------------
@dataclass
class ArquivoLote:
    id: str
    nome: str
    tamanho: int
    tipo: Optional[str] = None  # digital | foto
    formato: Optional[str] = None
    estado: str = "enviando"  # enviando, lendo, classificado, sem_tema, revisar, publicado, erro
    erro: Optional[dict] = None
    tema_sugerido: Optional[dict] = None
    tema_escolhido: Optional[dict] = None
    texto: Optional[str] = None
    linhas: List[dict] = field(default_factory=list)
    motor: Optional[str] = None
    revisado: bool = False
    avisos: List[str] = field(default_factory=list)
    documento: Optional[DocumentoDetalhe] = None
    caminho: Optional[str] = None
    tempo_ms: Optional[int] = None

    def para_dict(self) -> dict:
        doc = self.documento
        return {
            "id": self.id,
            "nome": self.nome,
            "tamanho": self.tamanho,
            "tipo": self.tipo,
            "formato": self.formato,
            "estado": self.estado,
            "erro": self.erro,
            "tema_sugerido": self.tema_sugerido,
            "tema_escolhido": self.tema_escolhido,
            "mensagem_tema": MSG_SEM_TEMA if self.estado == "sem_tema" else None,
            "documento": (
                {"codigo": doc.codigo, "versao": doc.versao, "titulo": doc.titulo, "origem": doc.origem}
                if doc
                else None
            ),
            "texto_lido": self.texto if self.tipo == "foto" else None,
            "linhas": self.linhas,
            "linhas_incertas": sum(1 for l in self.linhas if l.get("incerta")),
            "motor": self.motor,
            "revisado": self.revisado,
            "avisos": self.avisos,
            "tempo_classificacao_ms": self.tempo_ms,
        }


@dataclass
class Lote:
    id: str
    criado_em: float
    arquivos: List[ArquivoLote] = field(default_factory=list)

    def arquivo(self, arq_id: str) -> Optional[ArquivoLote]:
        return next((a for a in self.arquivos if a.id == arq_id), None)

    def para_dict(self) -> dict:
        total = len(self.arquivos)
        prontos = sum(1 for a in self.arquivos if a.estado in ("classificado", "publicado"))
        revisar = sum(1 for a in self.arquivos if a.estado == "revisar")
        sem_tema = sum(1 for a in self.arquivos if a.estado == "sem_tema")
        erros = sum(1 for a in self.arquivos if a.estado == "erro")
        publicados = sum(1 for a in self.arquivos if a.estado == "publicado")
        mensagem = f"{prontos} de {total} arquivos prontos."
        if revisar:
            mensagem += f" {revisar} precisa{'m' if revisar > 1 else ''} da sua revisão."
        if sem_tema:
            mensagem += f" {sem_tema} sem tema: escolha um."
        if erros:
            mensagem += f" {erros} com erro."
        return {
            "id": self.id,
            "criado_em": self.criado_em,
            "arquivos": [a.para_dict() for a in self.arquivos],
            "resumo": {
                "total": total,
                "prontos": prontos,
                "revisar": revisar,
                "sem_tema": sem_tema,
                "erros": erros,
                "publicados": publicados,
                "concluido": all(a.estado in ("publicado", "erro") for a in self.arquivos),
                "mensagem": mensagem,
            },
        }


def _diretorio_uploads() -> Path:
    env = os.getenv("UPLOADS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "uploads"


def _enviar_s3(caminho: Path, chave: str) -> Optional[str]:
    """Cópia opcional no S3, só se S3_BUCKET existir (credenciais do ambiente)."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return None
    try:
        import boto3

        sessao = boto3.Session(
            profile_name=os.getenv("AWS_PROFILE") or None,
            region_name=os.getenv("AWS_REGION") or None,
        )
        sessao.client("s3").upload_file(str(caminho), bucket, chave)
        return f"s3://{bucket}/{chave}"
    except Exception:
        return None


class LotesService:
    def __init__(self, acervo: AcervoRepository):
        self.acervo = acervo
        self.lotes: Dict[str, Lote] = {}
        self._lock = threading.Lock()
        self._ao_publicar: List[Callable[[], None]] = []

    def registrar_ao_publicar(self, callback: Callable[[], None]) -> None:
        """Ex.: reconstruir o índice de /api/perguntar depois de publicar."""
        self._ao_publicar.append(callback)

    # -- criação ---------------------------------------------------------
    def criar_lote(self, arquivos: List[Tuple[str, bytes]]) -> Lote:
        if not arquivos:
            raise LoteInvalido(422, "Envie ao menos um arquivo.")
        if len(arquivos) > MAX_ARQUIVOS:
            raise LoteInvalido(413, f"Lote com {len(arquivos)} arquivos. Envie até {MAX_ARQUIVOS} por vez.")
        total = sum(len(c) for _, c in arquivos)
        if total > MAX_BYTES_LOTE:
            raise LoteInvalido(413, "Lote maior que 50 MB. Envie em partes.")

        lote = Lote(id=f"lote-{uuid.uuid4().hex[:10]}", criado_em=time.time())
        with self._lock:
            self.lotes[lote.id] = lote
        for indice, (nome, conteudo) in enumerate(arquivos, start=1):
            arq = ArquivoLote(id=f"arq-{indice}", nome=nome or f"arquivo-{indice}", tamanho=len(conteudo))
            lote.arquivos.append(arq)
            try:
                self._processar(lote, arq, conteudo)
            except Exception as exc:  # o erro de um arquivo não para os demais
                arq.estado = "erro"
                arq.erro = {"status": 500, "mensagem": f"{arq.nome}: falha inesperada ({exc.__class__.__name__})."}
        return lote

    def _salvar(self, lote: Lote, arq: ArquivoLote, conteudo: bytes) -> None:
        destino = _diretorio_uploads() / lote.id
        destino.mkdir(parents=True, exist_ok=True)
        nome_seguro = re.sub(r"[^A-Za-z0-9._-]", "_", Path(arq.nome).name)
        caminho = destino / f"{arq.id}__{nome_seguro}"
        caminho.write_bytes(conteudo)
        arq.caminho = str(caminho)
        _enviar_s3(caminho, f"uploads/{lote.id}/{caminho.name}")

    def _erro(self, arq: ArquivoLote, status: int, mensagem: str) -> None:
        arq.estado = "erro"
        arq.erro = {"status": status, "mensagem": f"{arq.nome}: {mensagem}"}

    def _processar(self, lote: Lote, arq: ArquivoLote, conteudo: bytes) -> None:
        ext, erro = validar_tipo(arq.nome, conteudo)
        if erro:
            self._erro(arq, *erro)
            return
        arq.tipo = "foto" if ext in TIPOS_FOTO else "digital"
        arq.formato = TIPOS_FOTO.get(ext) or TIPOS_DIGITAIS.get(ext)
        self._salvar(lote, arq, conteudo)

        inicio = time.perf_counter()
        if arq.tipo == "foto":
            arq.estado = "lendo"
            try:
                leitura = ler_imagem(conteudo, arq.formato)
            except LeituraFalhou:
                self._erro(arq, 422, MSG_FOTO_ILEGIVEL)
                return
            arq.texto = leitura.texto
            arq.linhas = [{"numero": i, "texto": l.texto, "incerta": l.incerta} for i, l in enumerate(leitura.linhas, 1)]
            arq.motor = leitura.motor
            self._classificar(arq, leitura.texto, origem="digitalizado")
            if arq.estado != "erro":
                arq.estado = "revisar"  # nada é publicado sem revisão humana
        else:
            if ext == ".pdf":
                try:
                    texto = extrair_texto_pdf(conteudo)
                except Exception:
                    self._erro(arq, 422, "não deu para ler este PDF.")
                    return
                if not texto:
                    self._erro(arq, 422, "PDF sem texto (escaneado). Envie a página como foto JPG ou PNG.")
                    return
            else:
                texto = conteudo.decode("utf-8")
            arq.texto = texto
            self._classificar(arq, texto, origem="upload")
        arq.tempo_ms = int((time.perf_counter() - inicio) * 1000)

    def _classificar(self, arq: ArquivoLote, texto: str, origem: str) -> None:
        doc = parse_document_text(texto, origem=origem)
        arq.documento = doc
        arq.avisos = []
        faltando = [n for n, v in (("título", doc.titulo), ("versão", doc.versao)) if not v]
        if faltando:
            arq.avisos.append(f"cabeçalho incompleto: falta {', '.join(faltando)}.")
        if doc.codigo and self.acervo.existe(doc.codigo, doc.versao):
            self._erro(
                arq, 409, f"{doc.codigo} v{doc.versao} já existe no acervo. Altere a versão ou retire este arquivo."
            )
            arq.tema_sugerido = None
            return
        arq.tema_sugerido = sugerir_tema(doc, self.acervo)
        if arq.tema_sugerido is None:
            arq.avisos.append("cabeçalho sem código (Sigla e Número).")
        arq.erro = None
        arq.estado = self._estado_apos_tema(arq)

    @staticmethod
    def _estado_apos_tema(arq: ArquivoLote) -> str:
        """sem_tema → falta tema; revisar → tem tema, mas o texto ainda não tem código
        (a publicação seria recusada); classificado → pronto para publicar."""
        if not (arq.tema_sugerido or arq.tema_escolhido):
            return "sem_tema"
        if not (arq.documento and arq.documento.codigo):
            return "revisar"
        return "classificado"

    # -- consulta e edição ----------------------------------------------
    def obter(self, lote_id: str) -> Optional[Lote]:
        return self.lotes.get(lote_id)

    def atualizar_arquivo(
        self,
        lote: Lote,
        arq: ArquivoLote,
        assunto: Optional[str] = None,
        serie: Optional[int] = None,
        texto: Optional[str] = None,
        revisado: Optional[bool] = None,
    ) -> ArquivoLote:
        if arq.estado == "publicado":
            raise LoteInvalido(409, f"{arq.nome}: já publicado.")
        if arq.tipo is None:
            raise LoteInvalido(409, f"{arq.nome}: arquivo com erro de tipo ou tamanho. Retire e envie de novo.")

        if assunto is not None:
            assunto_norm = _sem_acento(assunto).strip()
            if not assunto_norm:
                raise LoteInvalido(422, "Informe o assunto do tema.")
            if serie is not None and serie not in SERIES_CATALOGO:
                raise LoteInvalido(422, f"Série {serie} não existe no catálogo §5.")
            arq.tema_escolhido = {
                "assunto": assunto_norm,
                "serie": serie,
                "serie_nome": SERIES_CATALOGO.get(serie) if serie is not None else None,
                "confirmado_por": "pessoa",
                "rotulo": rotulo_tema(assunto_norm, serie, SERIES_CATALOGO.get(serie) if serie is not None else None),
            }

        if texto is not None:
            arq.texto = texto
            if arq.tipo == "foto":
                arq.linhas = [{"numero": i, "texto": l, "incerta": False} for i, l in enumerate(texto.splitlines(), 1)]
            self._classificar(arq, texto, origem="digitalizado" if arq.tipo == "foto" else "upload")
        elif arq.estado in ("sem_tema", "revisar") and arq.tema_escolhido and arq.tipo != "foto":
            arq.estado = self._estado_apos_tema(arq)

        if revisado is not None and arq.tipo == "foto":
            arq.revisado = bool(revisado)
            if arq.revisado:
                for linha in arq.linhas:
                    linha["incerta"] = False

        if arq.tipo == "foto" and arq.estado in ("classificado", "sem_tema") and not arq.revisado:
            arq.estado = "revisar"
        elif arq.tipo == "foto" and arq.estado == "revisar" and arq.revisado:
            arq.estado = self._estado_apos_tema(arq)
        return arq

    # -- publicação -----------------------------------------------------
    def _bloqueio_publicacao(self, arq: ArquivoLote) -> Optional[str]:
        if arq.estado == "publicado":
            return "já publicado."
        if arq.estado == "erro":
            return (arq.erro or {}).get("mensagem", "arquivo com erro.")
        if arq.tipo == "foto" and not arq.revisado:
            return "revise o texto lido antes de publicar."
        if not (arq.tema_escolhido or arq.tema_sugerido):
            return MSG_SEM_TEMA
        doc = arq.documento
        if not doc or not doc.codigo:
            return "cabeçalho sem código (Sigla e Número). Corrija o texto antes de publicar."
        if arq.tipo == "foto" and not (doc.titulo and doc.versao):
            return "preencha código, versão e título antes de publicar."
        if self.acervo.existe(doc.codigo, doc.versao):
            return f"{doc.codigo} v{doc.versao} já existe no acervo. Altere a versão ou retire este arquivo."
        return None

    def publicar(self, lote: Lote, arquivos: Optional[List[str]] = None) -> dict:
        resultados = []
        publicou = False
        for arq in lote.arquivos:
            if arquivos and arq.id not in arquivos:
                continue
            motivo = self._bloqueio_publicacao(arq)
            if motivo:
                if arq.estado != "publicado":
                    resultados.append({"arquivo": arq.id, "nome": arq.nome, "publicado": False, "motivo": motivo})
                continue
            doc = arq.documento
            escolhido = arq.tema_escolhido
            if escolhido:
                tema = Tema(
                    assunto=escolhido["assunto"],
                    serie=escolhido["serie"],
                    serie_nome=escolhido["serie_nome"],
                    confirmado_por="pessoa",
                )
            else:
                sug = arq.tema_sugerido
                tema = Tema(
                    assunto=sug["assunto"],
                    serie=sug["serie"],
                    serie_nome=sug["serie_nome"],
                    confirmado_por="regra",
                    observacao=sug.get("observacao"),
                )
            doc = doc.model_copy(update={"tema": tema, "assunto": tema.assunto})
            try:
                self.acervo.adicionar(doc)
            except ValueError as exc:
                resultados.append({"arquivo": arq.id, "nome": arq.nome, "publicado": False, "motivo": str(exc)})
                continue
            arq.documento = doc
            arq.estado = "publicado"
            publicou = True
            resultados.append(
                {"arquivo": arq.id, "nome": arq.nome, "publicado": True, "codigo": doc.codigo, "versao": doc.versao}
            )
        if publicou:
            for cb in self._ao_publicar:
                cb()
        return {"lote": lote.para_dict(), "resultados": resultados}
