import json
import logging
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    from nltk.stem.snowball import PortugueseStemmer
    stemmer = PortugueseStemmer()
except ImportError:
    class SimplePortugueseStemmer:
        def stem(self, word: str) -> str:
            w = word.lower()
            for suf in (
                "amentos", "imentos", "amento", "imento", "idades", "mente",
                "acoes", "acao", "aram", "avam", "emos", "ando", "endo", "indo",
                "adas", "ados", "ada", "ado", "idos", "ida", "ido", "iram",
                "eza", "oso", "osa", "ar", "er", "ir", "as", "es", "os"
            ):
                if len(w) > len(suf) + 3 and w.endswith(suf):
                    return w[:-len(suf)]
            if w.endswith("s") and len(w) > 3:
                return w[:-1]
            return w

    stemmer = SimplePortugueseStemmer()

from app.acervo import AcervoRepository
from app.models import Camada, Citacao, Secao
from app.taxonomia import derivar_camada
from app.bedrock import gerar_embeddings, get_llm_provider
from app.rbac import get_rbac

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
EMBEDDINGS_CACHE_FILE = CACHE_DIR / "embeddings.json"

STOPWORDS = {
    "a", "ao", "aos", "as", "ate", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "era", "eram", "essa", "essas", "esse", "esses", "esta",
    "estas", "este", "estes", "eu", "foi", "foram", "ha", "isso", "isto", "ja",
    "lhe", "lhes", "mais", "mas", "me", "mesmo", "mesma", "meu", "meus", "minha",
    "minhas", "muito", "na", "nao", "nas", "no", "nos", "nossa", "nossas", "nosso",
    "nossos", "num", "numa", "o", "os", "ou", "para", "pela", "pelas", "pelo",
    "pelos", "por", "qual", "quais", "quando", "quanto", "quantos", "quantas",
    "que", "quem", "se", "sem", "seu", "seus", "so", "sua", "suas", "tambem",
    "te", "tem", "temos", "tenho", "um", "uma", "umas", "uns", "voce", "voces",
    "pode", "podem", "ser", "posso", "devo", "preciso", "gostaria", "saber",
    "hoje", "amanha", "ontem", "agora",
}

# Limiares de evidência para abstenção (consta=false)
LIMIAR_SCORE = 6.0
LIMIAR_COBERTURA = 0.6
# Seções abaixo desta fração da melhor pontuação não entram como citação
FRACAO_RELEVANCIA = 0.4
MAX_POR_DOCUMENTO = 2
LIMITE_TRECHO = 220
# Penalidade de versões substituídas e limiar (sem penalidade) para emitir aviso
FATOR_SUBSTITUIDO = 0.5
FRACAO_AVISO = 0.75

VERB_LEMMAS = {
    "peco": ["pedir", "pedido", "solicitar", "solicitacao"],
    "pedir": ["pedido", "solicitar", "solicitacao"],
    "decido": ["decidir", "decisao", "decide", "gestor"],
    "decide": ["decidir", "decisao", "gestor"],
    "tirar": ["gozo", "gozar", "ferias"],
    "vender": ["abono", "converter", "conversao"],
    # sinônimos usuais para o vocabulário do acervo
    "colaborador": ["empregado"],
    "colaboradores": ["empregados"],
    "funcionario": ["empregado"],
    "funcionarios": ["empregados"],
    "chefe": ["gestor"],
}


def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8").lower()


DATA_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")


def tokenizar(text_norm: str) -> List[str]:
    """Tokens de texto já normalizado; datas (05/05/2027) viram um token próprio."""
    datas = DATA_RE.findall(text_norm)
    resto = DATA_RE.sub(" ", text_norm)
    return datas + re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", resto)


def extract_content_words(text: str) -> List[str]:
    """Extrai palavras de conteúdo (removendo stopwords) com expansão de lemas."""
    text_norm = normalize_text(text)
    words = tokenizar(text_norm)
    res = []
    for w in words:
        if w not in STOPWORDS and len(w) > 1:
            res.append(w)
            if w in VERB_LEMMAS:
                res.extend(VERB_LEMMAS[w])
    return res


@dataclass
class SectionItem:
    codigo: str
    versao: str
    substituido: bool
    secao_id: str
    titulo: str
    texto: str
    tipo_nome: str
    vinculado_a: Optional[str]
    camada: Camada
    tokens: List[str]
    len: int
    tf: Counter
    words_set: Set[str]
    stems_set: Set[str]
    raw_text: str
    assunto: str = ""


@dataclass
class ResultadoBusca:
    codigo: str
    versao: str
    secao_id: str
    titulo: str
    texto: str
    trecho: str
    camada: Camada
    score: float
    avisos: List[str]


class BuscadorLexico:
    """Motor de recuperação lexical BM25 com normalização de acentos, códigos e abstenção."""

    def __init__(self, acervo: AcervoRepository):
        self.acervo = acervo
        self.sections: List[SectionItem] = []
        self.corpus_tokens: Set[str] = set()
        self.df: Counter = Counter()
        self.N: int = 0
        self.avgdl: float = 0.0
        self.dense_embeddings: Dict[str, List[float]] = {}
        self._construir_indice()
        self._carregar_ou_gerar_embeddings()

    def _carregar_ou_gerar_embeddings(self) -> None:
        """Carrega embeddings em cache (data/cache/) ou gera via Bedrock Cohere Embed v4."""
        if get_llm_provider() != "bedrock":
            return

        if EMBEDDINGS_CACHE_FILE.exists():
            try:
                with open(EMBEDDINGS_CACHE_FILE, "r", encoding="utf-8") as f:
                    self.dense_embeddings = json.load(f)
                logger.info(f"Carregados {len(self.dense_embeddings)} embeddings do cache.")
                return
            except Exception as e:
                logger.warning(f"Erro ao ler cache de embeddings ({type(e).__name__}); gerando novo...")

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            texts = [
                f"{s.codigo} {s.titulo} {s.secao_id}: {s.texto[:300]}"
                for s in self.sections
            ]
            embs = gerar_embeddings(texts, input_type="search_document")
            if embs and len(embs) == len(self.sections):
                self.dense_embeddings = {
                    f"{s.codigo}@{s.versao}#{s.secao_id}": vec
                    for s, vec in zip(self.sections, embs)
                }
                with open(EMBEDDINGS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.dense_embeddings, f)
                logger.info(f"Cache de embeddings salvo com sucesso ({len(self.dense_embeddings)} vetores).")
        except Exception as e:
            logger.warning(f"Falha ao gerar índice denso ({type(e).__name__}); operando em BM25 puro.")

    @staticmethod
    def _chave_densa(s: "SectionItem") -> str:
        return f"{s.codigo}@{s.versao}#{s.secao_id}"

    def reindexar(self) -> None:
        """Reconstrói o índice após mudança no acervo (ex.: publicação de lote, issue #10).

        Refaz o BM25 e, com o provedor Bedrock ativo, gera embeddings só das seções
        que ainda não têm vetor. Vetores de seções que saíram do acervo são
        descartados. Os vetores novos ficam em memória (o cache em disco guarda só
        o acervo base). Se a geração falhar, as seções novas seguem só no BM25.
        """
        self._construir_indice()
        if not self.dense_embeddings:
            return
        chaves = {self._chave_densa(s) for s in self.sections}
        for chave in [k for k in self.dense_embeddings if k not in chaves]:
            del self.dense_embeddings[chave]
        faltando = [s for s in self.sections if self._chave_densa(s) not in self.dense_embeddings]
        if not faltando or get_llm_provider() != "bedrock":
            return
        try:
            embs = gerar_embeddings(
                [f"{s.codigo} {s.titulo} {s.secao_id}: {s.texto[:300]}" for s in faltando],
                input_type="search_document",
            )
            if embs and len(embs) == len(faltando):
                for s, vec in zip(faltando, embs):
                    self.dense_embeddings[self._chave_densa(s)] = vec
        except Exception as e:
            logger.warning(f"Falha ao gerar embeddings das seções novas ({type(e).__name__}); seguem só no BM25.")

    def _construir_indice(self) -> None:
        self.sections.clear()
        self.corpus_tokens.clear()
        self.df.clear()

        for d in self.acervo.documentos:
            for s in d.secoes:
                doc_header = f"{d.codigo} {d.titulo}"
                sec_header = f"{s.id} {s.titulo}"
                body = s.texto

                header_words = extract_content_words(f"{doc_header} {sec_header}")
                body_words = extract_content_words(body)

                # Ponderação do cabeçalho / título (4x)
                all_words = header_words * 4 + body_words
                all_stems = [stemmer.stem(w) for w in all_words]

                tokens = all_words + all_stems
                self.corpus_tokens.update(all_words)
                self.corpus_tokens.update(all_stems)

                sec_item = SectionItem(
                    codigo=d.codigo,
                    versao=d.versao,
                    substituido=d.substituido,
                    secao_id=s.id,
                    titulo=s.titulo,
                    texto=s.texto,
                    tipo_nome=d.tipo_nome,
                    vinculado_a=d.vinculado_a,
                    camada=d.camada,
                    assunto=getattr(d, "assunto", ""),
                    tokens=tokens,
                    len=len(tokens),
                    tf=Counter(tokens),
                    words_set=set(all_words),
                    stems_set=set(all_stems),
                    raw_text=f"{doc_header} {sec_header} {body}".lower(),
                )
                self.sections.append(sec_item)

        self.N = len(self.sections)
        self.avgdl = sum(s.len for s in self.sections) / self.N if self.N > 0 else 1.0

        for s in self.sections:
            for t in set(s.tokens):
                self.df[t] += 1

    def _idf(self, word: str) -> float:
        n = self.df.get(word, 0)
        if n == 0:
            return 0.0
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)

    def _extrair_trecho_relevante(self, texto: str, titulo: str, query: str) -> str:
        """Extrai o trecho literal mais relevante para a citação (≤ ~220 caracteres).

        Escolhe a frase com maior sobreposição (palavras, radicais e lemas) com a
        pergunta e completa com as frases seguintes até o limite, para não cortar
        a resposta quando ela vem logo depois (ex.: tabelas de marcos e datas).
        """
        clean_text = re.sub(r"\s+", " ", texto).strip()
        if not clean_text:
            return titulo[:200]

        sentences = [x for x in re.split(r"(?<=[.!?;])\s+", clean_text) if x]
        q_words = set(extract_content_words(query))
        q_terms = q_words | {stemmer.stem(w) for w in q_words}

        best_idx, max_overlap = 0, -1
        for i, sent in enumerate(sentences):
            s_words = set(extract_content_words(sent))
            s_terms = s_words | {stemmer.stem(w) for w in s_words}
            overlap = sum(self._idf(t) or 1.0 for t in q_terms & s_terms)
            if overlap > max_overlap:
                max_overlap, best_idx = overlap, i

        trecho = sentences[best_idx]
        for nxt in sentences[best_idx + 1:]:
            if len(trecho) + 1 + len(nxt) > LIMITE_TRECHO:
                break
            trecho = f"{trecho} {nxt}"
        if len(trecho) > LIMITE_TRECHO:
            trecho = trecho[: LIMITE_TRECHO - 3].rstrip() + "..."
        return trecho

    def buscar(self, query: str, top_k: int = 3, cargo: Optional[str] = None) -> Tuple[bool, List[ResultadoBusca], List[str]]:
        """Realiza busca lexical sobre as seções com filtro por cargo (RBAC).

        Retorna:
            (consta: bool, resultados: List[ResultadoBusca], avisos: List[str])
        """
        q_norm = normalize_text(query)
        raw_words = list(
            dict.fromkeys(w for w in tokenizar(q_norm) if w not in STOPWORDS and len(w) > 1)
        )
        if not raw_words:
            return False, [], []

        # Cada termo da pergunta vira um grupo de equivalência (palavra, radical e
        # lemas/sinônimos). O grupo pontua uma vez só (melhor token), para que a
        # expansão de lemas não infle a pontuação. Termo ausente do acervo recebe o
        # IDF máximo: pesa contra a cobertura e leva à abstenção quando é o núcleo
        # da pergunta (ex.: "benefício alimentação").
        idf_max = math.log((self.N + 0.5) / 0.5 + 1.0)
        grupos: List[Tuple[Set[str], float]] = []
        for w in raw_words:
            equivs = {w} | set(VERB_LEMMAS.get(w, []))
            toks = equivs | {stemmer.stem(e) for e in equivs}
            presentes = [t for t in toks if t in self.df]
            peso = max((self._idf(t) for t in presentes), default=idf_max)
            grupos.append((toks, peso))
        peso_total = sum(p for _, p in grupos) or 1.0

        k1 = 1.5
        b = 0.75
        scored: List[Tuple[float, float, SectionItem]] = []
        avisos_detectados: List[str] = []
        rbac = get_rbac()

        for s in self.sections:
            if cargo and not rbac.documento_permitido(cargo, s):
                continue
            tf = s.tf
            norm_len = k1 * (1 - b + b * (s.len / self.avgdl))
            score = 0.0
            peso_coberto = 0.0
            for toks, peso in grupos:
                melhor = 0.0
                for t in toks:
                    term_tf = tf.get(t, 0)
                    if term_tf:
                        parcial = self._idf(t) * (term_tf * (k1 + 1)) / (term_tf + norm_len)
                        melhor = max(melhor, parcial)
                if melhor > 0:
                    score += melhor
                    peso_coberto += peso
            cobertura = peso_coberto / peso_total

            # Penalizar documentos substituídos na pontuação direta
            if s.substituido:
                score *= FATOR_SUBSTITUIDO

            scored.append((score, cobertura, s))

        # Ordena por BM25 ponderado pela cobertura (ponderada por IDF) dos termos
        scored.sort(key=lambda x: x[0] * (0.25 + x[1]), reverse=True)
        if not scored:
            return False, [], []

        top_score, top_cov, _ = scored[0]
        if os.getenv("BUSCA_DEBUG"):
            print("TOP", [(round(x[0], 1), round(x[1], 2), x[2].codigo, x[2].secao_id) for x in scored[:5]])


        # Limiar de abstenção: entre as primeiras colocadas, alguma seção precisa ter
        # pontuação e cobertura suficientes
        if not any(sc >= LIMIAR_SCORE and cov >= LIMIAR_COBERTURA for sc, cov, _ in scored[:5]):
            return False, [], []

        # Recuperação híbrida: se embeddings estiverem disponíveis, re-ranqueia os candidatos
        if self.dense_embeddings and np is not None:
            try:
                q_embs = gerar_embeddings([query], input_type="search_query")
                if q_embs and len(q_embs) > 0:
                    q_vec = np.array(q_embs[0], dtype=np.float32)
                    q_norm = np.linalg.norm(q_vec)
                    if q_norm > 0:
                        q_vec /= q_norm
                        rescored = []
                        for sc, cov, s in scored:
                            key = f"{s.codigo}@{s.versao}#{s.secao_id}"
                            vec = self.dense_embeddings.get(key)
                            sim = 0.0
                            if vec is not None:
                                d_arr = np.array(vec, dtype=np.float32)
                                d_norm = np.linalg.norm(d_arr)
                                if d_norm > 0:
                                    sim = float(np.dot(q_vec, d_arr / d_norm))
                            sim_bonus = max(0.0, sim)
                            h_score = sc * (0.25 + cov) * (1.0 + 0.25 * sim_bonus)
                            rescored.append((sc, cov, s, h_score))

                        rescored.sort(key=lambda x: x[3], reverse=True)
                        scored = [(x[0], x[1], x[2]) for x in rescored]
            except Exception as e:
                logger.warning(f"Embeddings falharam na consulta ({type(e).__name__}); segue só BM25.")

        top_score, top_cov, _ = scored[0]
        chave_top = top_score * (0.25 + top_cov)

        # Seleciona top_k seções vigentes (no máximo MAX_POR_DOCUMENTO por documento).
        # Seções de versões substituídas não são citadas: quando são relevantes
        # para a pergunta, viram aviso de que a regra mudou na versão vigente.
        resultados: List[ResultadoBusca] = []
        por_documento: Counter = Counter()
        substituidas_relevantes: List[SectionItem] = []

        for sc, cov, s in scored:
            chave = sc * (0.25 + cov)
            if s.substituido:
                # Sem a penalidade, o trecho antigo competiria com o melhor vigente:
                # a regra mudou (ou foi reescrita) e o usuário deve ser avisado.
                if chave / FATOR_SUBSTITUIDO >= chave_top * FRACAO_AVISO:
                    substituidas_relevantes.append(s)
                continue
            if chave < chave_top * FRACAO_RELEVANCIA:
                continue
            if len(resultados) >= top_k or por_documento[s.codigo] >= MAX_POR_DOCUMENTO:
                continue
            por_documento[s.codigo] += 1
            resultados.append(
                ResultadoBusca(
                    codigo=s.codigo,
                    versao=s.versao,
                    secao_id=s.secao_id,
                    titulo=s.titulo,
                    texto=s.texto,
                    trecho=self._extrair_trecho_relevante(s.texto, s.titulo, query),
                    camada=s.camada,
                    score=sc,
                    avisos=[],
                )
            )

        if not resultados:
            return False, [], []

        citados = {r.codigo: r.versao for r in resultados}
        for s in substituidas_relevantes:
            if s.codigo in citados:
                aviso = f"{s.codigo} v{s.versao} foi substituída pela v{citados[s.codigo]}"
                if aviso not in avisos_detectados:
                    avisos_detectados.append(aviso)
        for r in resultados:
            r.avisos = list(avisos_detectados)

        return True, resultados, avisos_detectados
