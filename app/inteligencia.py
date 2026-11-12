"""Módulo de inteligência por perspectiva do Arquivo Central de Normas (ACME).

Implementa os endpoints do Desafio 2 (docs/PRD.md, CONTRATO-API.md, Adendo v0.1):
- /api/perspectivas
- /api/perspectivas/{id}
- /api/grafo
- /api/comparar
- /api/relatorio
"""

import logging
import os
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml
from fastapi import HTTPException

from app.models import (
    PerspectivaResumo,
    PerspectivaDetalhe,
    DestaqueItem,
    ValorItem,
    PrazoItem,
    ResponsavelItem,
    RiscoItem,
    Fonte,
    GrafoNo,
    GrafoAresta,
    GrafoResponse,
    MudancaSecao,
    CompararResponse,
    RelatorioItem,
    RelatorioSecao,
    RelatorioResponse,
)
from app.acervo import AcervoRepository, get_acervo
from app.ia import ClienteIA, ErroIA, get_cliente_ia
from app.sintese import SinteseInvalida, TrechoFonte, sintetizar_itens
from app.taxonomia import derivar_camada, derivar_tema

logger = logging.getLogger(__name__)

# Códigos de documento citados no texto (catálogo §2). "CT_" não casa dentro de "CTR_".
CODIGO_RE = re.compile(r"\b(?:NG|PX|PP|GU|FM|TB|FL|RG|CT|DV|CTR|NT)_\d+(?:-\d+)*\b")
# Quantidade com unidade, para o resumo do /api/comparar
QUANTIDADE_RE = re.compile(r"((?:[\wÀ-ÿ]+\s+){0,3})(\d+(?:[.,]\d+)?)\s*(dias|meses|anos|horas|%)")


def _tokens(texto: str) -> List[str]:
    """Tokens normalizados (minúsculas, sem acento, sem pipes/markup) para conferir trechos."""
    t = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+(?:[.,/][a-z0-9]+)*", t)


def trecho_consta_na_secao(trecho: str, texto_secao: str) -> bool:
    """O trecho precisa estar no texto da seção.

    Prosa: sequência contígua de tokens. Linha de tabela (com "|", pois o PDF
    quebra as células em colunas): todos os tokens precisam constar na seção.
    """
    t_trecho = _tokens(trecho.replace("...", " ").replace("…", " "))
    t_secao = _tokens(texto_secao)
    if not t_trecho:
        return False
    if "|" in trecho:
        return set(t_trecho) <= set(t_secao)
    n = len(t_trecho)
    return any(t_secao[i : i + n] == t_trecho for i in range(len(t_secao) - n + 1))

PERSPECTIVAS_LISTA = [
    {"id": "juridico", "nome": "Jurídico e Contratos"},
    {"id": "financeiro", "nome": "Financeiro"},
    {"id": "pessoas", "nome": "Pessoas (RH)"},
    {"id": "gestao", "nome": "Gestão e Inovação"},
]

PERSPECTIVAS_NOMES = {p["id"]: p["nome"] for p in PERSPECTIVAS_LISTA}


class InteligenciaService:
    def __init__(
        self,
        acervo: Optional[AcervoRepository] = None,
        curadoria_dir: Optional[Path] = None,
        ia: Optional[ClienteIA] = None,
    ):
        self.acervo = acervo or get_acervo()
        self.ia = ia or get_cliente_ia()
        self.curadoria_dir = curadoria_dir or self._discover_curadoria_dir()
        self._curadoria_cache: Dict[str, dict] = {}
        self.carregar_curadoria()

    @staticmethod
    def _discover_curadoria_dir() -> Path:
        env_dir = os.getenv("CURADORIA_DIR")
        if env_dir:
            return Path(env_dir)

        candidato = Path(__file__).resolve().parent.parent / "data" / "curadoria"
        if candidato.exists():
            return candidato

        cwd_candidato = Path.cwd() / "data" / "curadoria"
        if cwd_candidato.exists():
            return cwd_candidato

        return candidato

    def carregar_curadoria(self) -> None:
        self._curadoria_cache.clear()
        if not self.curadoria_dir.exists():
            return

        for arquivo in self.curadoria_dir.glob("*.yaml"):
            try:
                with open(arquivo, "r", encoding="utf-8") as f:
                    dados = yaml.safe_load(f)
                    if isinstance(dados, dict) and "id" in dados:
                        self._curadoria_cache[dados["id"]] = dados
            except Exception as e:
                print(f"Erro ao carregar curadoria {arquivo}: {e}")

    def listar_perspectivas(self) -> List[PerspectivaResumo]:
        """Retorna a lista das 4 perspectivas normativas."""
        return [
            PerspectivaResumo(id=p["id"], nome=p["nome"])
            for p in PERSPECTIVAS_LISTA
        ]

    def validar_fonte(self, f_dict: dict) -> Optional[str]:
        """Devolve o motivo de erro se a fonte da curadoria não confere com o acervo."""
        codigo, versao, secao = f_dict.get("codigo", ""), f_dict.get("versao", ""), f_dict.get("secao", "")
        doc = self.acervo.buscar(codigo=codigo, versao=versao)
        if not doc:
            return f"{codigo} v{versao} não existe no acervo"
        sec = next((x for x in doc.secoes if x.id == secao), None)
        if not sec:
            return f"{codigo} v{versao}: seção '{secao}' não existe"
        if not trecho_consta_na_secao(f_dict.get("trecho", ""), f"{sec.titulo}\n{sec.texto}"):
            return f"{codigo} v{versao} §{secao}: trecho não consta no texto da seção"
        return None

    def erros_curadoria(self) -> List[str]:
        """Lista todas as fontes da curadoria que não conferem com o acervo."""
        erros: List[str] = []
        for pid, dados in self._curadoria_cache.items():
            for chave, itens in dados.items():
                if not isinstance(itens, list):
                    continue
                for item in itens:
                    for campo in ("fonte", "fonte_anterior"):
                        f = item.get(campo) if isinstance(item, dict) else None
                        if f:
                            erro = self.validar_fonte(f)
                            if erro:
                                erros.append(f"{pid}.{chave}.{campo}: {erro}")
        return erros

    def _construir_fonte(self, f_dict: dict) -> Optional[Fonte]:
        """Fonte com camada do acervo; None (item descartado) se não confere com o acervo."""
        erro = self.validar_fonte(f_dict)
        if erro:
            logger.warning("Curadoria descartada: %s", erro)
            return None
        doc = self.acervo.buscar(codigo=f_dict["codigo"], versao=f_dict["versao"])
        return Fonte(
            codigo=doc.codigo,
            versao=doc.versao,
            secao=f_dict["secao"],
            trecho=f_dict["trecho"],
            camada=doc.camada,
        )

    def _tema_da_fonte(self, fonte: Fonte):
        """Tema do documento citado (assunto = pasta do acervo, série do catálogo)."""
        doc = self.acervo.buscar(codigo=fonte.codigo, versao=fonte.versao)
        return doc.tema

    def obter_perspectiva(self, id: str) -> PerspectivaDetalhe:
        """Retorna dados de uma perspectiva com validação de fontes, tema e camada."""
        id_clean = id.strip().lower()
        if id_clean not in PERSPECTIVAS_NOMES:
            raise HTTPException(
                status_code=404,
                detail=f"Perspectiva '{id}' não encontrada.",
            )

        nome = PERSPECTIVAS_NOMES[id_clean]
        dados = self._curadoria_cache.get(id_clean, {})

        destaques: List[DestaqueItem] = []
        for d in dados.get("destaques", []):
            fonte = self._construir_fonte(d["fonte"])
            if fonte is None:
                continue
            fonte_ant = None
            if "fonte_anterior" in d and d["fonte_anterior"]:
                fonte_ant = self._construir_fonte(d["fonte_anterior"])

            tema = self._tema_da_fonte(fonte)
            destaques.append(
                DestaqueItem(
                    titulo=d.get("titulo", ""),
                    valor=d.get("valor"),
                    fonte=fonte,
                    fonte_anterior=fonte_ant,
                    aviso=d.get("aviso"),
                    tema=tema,
                )
            )

        valores: List[ValorItem] = []
        for v in dados.get("valores", []):
            fonte = self._construir_fonte(v["fonte"])
            if fonte is None:
                continue
            tema = self._tema_da_fonte(fonte)
            valores.append(
                ValorItem(
                    rotulo=v.get("rotulo", ""),
                    numero=float(v.get("numero", 0.0)),
                    unidade=v.get("unidade", "BRL"),
                    fonte=fonte,
                    tema=tema,
                )
            )

        prazos: List[PrazoItem] = []
        for p in dados.get("prazos", []):
            fonte = self._construir_fonte(p["fonte"])
            if fonte is None:
                continue
            tema = self._tema_da_fonte(fonte)
            prazos.append(
                PrazoItem(
                    data=p.get("data"),
                    evento=p.get("evento", ""),
                    marco=p.get("marco"),
                    cenario=p.get("cenario"),
                    fonte=fonte,
                    tema=tema,
                )
            )

        responsaveis: List[ResponsavelItem] = []
        for r in dados.get("responsaveis", []):
            fonte = self._construir_fonte(r["fonte"])
            if fonte is None:
                continue
            tema = self._tema_da_fonte(fonte)
            resp_desc = r.get("responsabilidade", "")
            responsaveis.append(
                ResponsavelItem(
                    papel=r.get("papel", ""),
                    responsabilidade=resp_desc,
                    obrigacao=resp_desc,
                    fonte=fonte,
                    tema=tema,
                )
            )

        riscos: List[RiscoItem] = []
        for rk in dados.get("riscos", []):
            fonte = self._construir_fonte(rk["fonte"])
            if fonte is None:
                continue
            tema = self._tema_da_fonte(fonte)
            riscos.append(
                RiscoItem(
                    descricao=rk.get("descricao", ""),
                    fonte=fonte,
                    tema=tema,
                )
            )

        return PerspectivaDetalhe(
            id=id_clean,
            nome=nome,
            destaques=destaques,
            valores=valores,
            prazos=prazos,
            responsaveis=responsaveis,
            riscos=riscos,
        )

    @staticmethod
    def _chave_versao(versao: str):
        return tuple(int(x) if x.isdigit() else 0 for x in versao.split("."))

    def _destino(self, codigo: str, origem_substituida: bool, versoes: Dict[str, list]) -> str:
        """Id do nó de destino de uma relação para `codigo`.

        Documento vigente aponta para a versão vigente; documento substituído aponta
        para a versão substituída mais recente do destino, se houver (era a que
        vigorava junto com ele). Código fora do acervo → nó ausente (id = código).
        """
        docs = versoes.get(codigo)
        if not docs:
            return codigo
        if origem_substituida:
            antigas = [d for d in docs if d.substituido]
            if antigas:
                d = max(antigas, key=lambda x: self._chave_versao(x.versao))
                return f"{d.codigo}@{d.versao}"
        vigente = next((d for d in docs if not d.substituido), docs[-1])
        return f"{vigente.codigo}@{vigente.versao}"

    def gerar_grafo(self) -> GrafoResponse:
        """Grafo derivado do acervo: cabeçalhos (Vinculado a, Referência), versões e
        códigos citados no texto. Códigos citados que não existem no acervo viram nós
        com existe_no_acervo=false (Adendo v0.1 C); o filtro de exibição (ex.: NG_010,
        citada só por versão substituída, RF14) fica com o frontend.
        """
        nos_map: Dict[str, GrafoNo] = {}
        arestas: List[GrafoAresta] = []
        vistas = set()

        def add_aresta(de: str, para: str, tipo: str) -> None:
            if de != para and (de, para, tipo) not in vistas:
                vistas.add((de, para, tipo))
                arestas.append(GrafoAresta(de=de, para=para, tipo=tipo))

        versoes: Dict[str, list] = {}
        for doc in self.acervo.documentos:
            versoes.setdefault(doc.codigo, []).append(doc)
            nos_map[f"{doc.codigo}@{doc.versao}"] = GrafoNo(
                id=f"{doc.codigo}@{doc.versao}",
                codigo=doc.codigo,
                tipo=doc.tipo,
                versao=doc.versao,
                substituido=doc.substituido,
                existe_no_acervo=True,
                titulo=doc.titulo,
                camada=doc.camada,
                tema=doc.tema,
            )

        # Substituição: cada versão aponta para a imediatamente anterior
        for codigo, docs in versoes.items():
            ordenadas = sorted(docs, key=lambda d: self._chave_versao(d.versao))
            for antiga, nova in zip(ordenadas, ordenadas[1:]):
                add_aresta(f"{nova.codigo}@{nova.versao}", f"{antiga.codigo}@{antiga.versao}", "substitui")

        for doc in self.acervo.documentos:
            origem = f"{doc.codigo}@{doc.versao}"
            vinculo = (doc.vinculado_a or "").strip() or None
            if vinculo:
                add_aresta(origem, self._destino(vinculo, doc.substituido, versoes), "vinculado_a")

            texto = " ".join(f"{s.titulo} {s.texto}" for s in doc.secoes)
            citados = set(CODIGO_RE.findall(texto))
            if doc.referencia:
                citados |= set(CODIGO_RE.findall(doc.referencia))
            citados -= {doc.codigo, vinculo}

            for codigo in sorted(citados):
                destino = self._destino(codigo, doc.substituido, versoes)
                if destino not in nos_map:
                    nos_map[destino] = GrafoNo(
                        id=destino,
                        codigo=codigo,
                        tipo=codigo.split("_")[0],
                        versao=None,
                        substituido=False,
                        existe_no_acervo=False,
                        titulo=None,
                        camada=derivar_camada(codigo),
                        tema=derivar_tema(codigo, assunto=doc.assunto),
                    )
                add_aresta(origem, destino, "referencia")

        return GrafoResponse(nos=list(nos_map.values()), arestas=arestas)

    @staticmethod
    def _frases_com_quantidade(doc) -> List[tuple]:
        frases = []
        for s in doc.secoes:
            texto = re.sub(r"\s+", " ", f"{s.texto}")
            for f in re.split(r"(?<=[.;])\s+", texto):
                if QUANTIDADE_RE.search(f):
                    frases.append((s.id, f))
        return frases

    def _resumo_comparacao(self, doc_de, doc_para) -> List[str]:
        """Resumo derivado do texto: regras cuja quantidade mudou entre as versões.

        Para cada frase da versão antiga com quantidade (dias, meses, %), procura a
        frase mais parecida da versão nova (Jaccard de palavras); se a quantidade
        mudou, registra os dois trechos literais com as seções.
        """
        def palavras(f: str) -> set:
            return set(_tokens(f)) - {"dias", "meses", "anos", "horas", "de", "a", "o", "e", "do", "da"}

        novas = [(sid, f, palavras(f)) for sid, f in self._frases_com_quantidade(doc_para)]
        resumo: List[str] = []
        for sid, f in self._frases_com_quantidade(doc_de):
            wf = palavras(f)
            melhor, melhor_j = None, 0.0
            for sid2, g, wg in novas:
                j = len(wf & wg) / max(1, len(wf | wg))
                if j > melhor_j:
                    melhor, melhor_j = (sid2, g), j
            if not melhor or melhor_j < 0.25:
                continue
            q_de, q_para = QUANTIDADE_RE.search(f), QUANTIDADE_RE.search(melhor[1])
            if q_de.group(3) == q_para.group(3) and q_de.group(2) != q_para.group(2):
                antes = f"{q_de.group(1)}{q_de.group(2)} {q_de.group(3)}".strip()
                depois = f"{q_para.group(1)}{q_para.group(2)} {q_para.group(3)}".strip()
                resumo.append(
                    f"{antes[0].upper()}{antes[1:]} (v{doc_de.versao}, seção {sid}) passou para "
                    f"{depois} (v{doc_para.versao}, seção {melhor[0]})"
                )
        return resumo

    def comparar_versoes(self, codigo: str, de: str, para: str) -> CompararResponse:
        """Compara duas versões do mesmo documento seção a seção com resumo."""
        doc_de = self.acervo.buscar(codigo=codigo, versao=de)
        doc_para = self.acervo.buscar(codigo=codigo, versao=para)

        if not doc_de or not doc_para:
            raise HTTPException(
                status_code=404,
                detail=f"Versão '{de}' ou '{para}' do documento '{codigo}' não encontrada no acervo.",
            )

        secoes_de = {s.id: s for s in doc_de.secoes}
        secoes_para = {s.id: s for s in doc_para.secoes}
        todos_ids = list(dict.fromkeys([s.id for s in doc_de.secoes] + [s.id for s in doc_para.secoes]))
        mudancas: List[MudancaSecao] = []

        for sid in todos_ids:
            if sid in secoes_de and sid not in secoes_para:
                mudancas.append(MudancaSecao(secao=sid, tipo="removido", antes=secoes_de[sid].texto, depois=None))
            elif sid not in secoes_de and sid in secoes_para:
                mudancas.append(MudancaSecao(secao=sid, tipo="incluido", antes=None, depois=secoes_para[sid].texto))
            elif secoes_de[sid].texto.strip() != secoes_para[sid].texto.strip():
                mudancas.append(
                    MudancaSecao(secao=sid, tipo="alterado", antes=secoes_de[sid].texto, depois=secoes_para[sid].texto)
                )

        resumo = self._resumo_comparacao(doc_de, doc_para)
        if not resumo:
            resumo = [f"{len(mudancas)} seções alteradas, incluídas ou removidas entre a versão {de} e a {para}."]

        return CompararResponse(codigo=codigo, de=de, para=para, mudancas=mudancas, resumo=resumo)

    def gerar_relatorio(
        self,
        perspectiva: Optional[str] = None,
        codigo: Optional[str] = None,
    ) -> RelatorioResponse:
        """Relatório executivo; com IA ativa, abre com uma síntese ancorada nos itens (Issue #6)."""
        rel = self._gerar_relatorio_base(perspectiva=perspectiva, codigo=codigo)
        if not self.ia.ativo or not rel.secoes:
            return rel

        trechos: List[TrechoFonte] = []
        for sec in rel.secoes:
            for item in sec.itens:
                f = item.fonte
                texto = item.texto if f.trecho in item.texto else f"{item.texto} {f.trecho}"
                trechos.append(TrechoFonte(f.codigo, f.versao, f.secao, texto))
        fontes: Dict[tuple, Fonte] = {}
        for sec in rel.secoes:
            for item in sec.itens:
                fontes.setdefault((item.fonte.codigo, item.fonte.versao, item.fonte.secao), item.fonte)

        try:
            itens = sintetizar_itens(self.ia, rel.titulo, trechos)
        except (ErroIA, SinteseInvalida) as e:
            logger.info("Síntese do relatório descartada: %s", e)
            rel.avisos.append(f"Síntese por IA indisponível ({e}); o relatório traz os itens extraídos das fontes")
            return rel

        sintese = RelatorioSecao(
            titulo="Síntese executiva",
            itens=[RelatorioItem(texto=texto, fonte=fontes[(t.codigo, t.versao, t.secao)]) for texto, t in itens],
        )
        rel.secoes.insert(0, sintese)
        return rel

    def _gerar_relatorio_base(
        self,
        perspectiva: Optional[str] = None,
        codigo: Optional[str] = None,
    ) -> RelatorioResponse:
        """Gera relatório executivo estruturado por perspectiva ou documento."""
        if not perspectiva and not codigo:
            raise HTTPException(
                status_code=422,
                detail="Parâmetro 'perspectiva' ou 'codigo' é obrigatório.",
            )

        tz_br = timezone(timedelta(hours=-3))
        timestamp = datetime.now(tz_br).isoformat()

        if perspectiva:
            p_clean = perspectiva.strip().lower()
            if p_clean not in PERSPECTIVAS_NOMES:
                raise HTTPException(
                    status_code=404,
                    detail=f"Perspectiva '{perspectiva}' não encontrada.",
                )

            p_detalhe = self.obter_perspectiva(p_clean)
            secoes_rel: List[RelatorioSecao] = []

            # Seção Destaques
            if p_detalhe.destaques:
                itens_dest = [
                    RelatorioItem(
                        texto=f"{d.titulo}: {d.valor}" if d.valor else d.titulo,
                        fonte=d.fonte,
                    )
                    for d in p_detalhe.destaques
                ]
                secoes_rel.append(RelatorioSecao(titulo="Destaques Principais", itens=itens_dest))

            # Seção Valores
            if p_detalhe.valores:
                itens_val = [
                    RelatorioItem(
                        texto=f"{v.rotulo}: {v.unidade} {v.numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                        fonte=v.fonte,
                    )
                    for v in p_detalhe.valores
                ]
                secoes_rel.append(RelatorioSecao(titulo="Valores e Limites Financeiros", itens=itens_val))

            # Seção Prazos
            if p_detalhe.prazos:
                itens_prz = [
                    RelatorioItem(
                        texto=f"[{p.data or p.marco}] {p.evento}" if (p.data or p.marco) else p.evento,
                        fonte=p.fonte,
                    )
                    for p in p_detalhe.prazos
                ]
                secoes_rel.append(RelatorioSecao(titulo="Prazos e Linha do Tempo", itens=itens_prz))

            # Seção Responsáveis
            if p_detalhe.responsaveis:
                itens_resp = [
                    RelatorioItem(
                        texto=f"{r.papel}: {r.responsabilidade}",
                        fonte=r.fonte,
                    )
                    for r in p_detalhe.responsaveis
                ]
                secoes_rel.append(RelatorioSecao(titulo="Responsáveis e Obrigações", itens=itens_resp))

            # Seção Riscos
            if p_detalhe.riscos:
                itens_rsk = [
                    RelatorioItem(
                        texto=r.descricao,
                        fonte=r.fonte,
                    )
                    for r in p_detalhe.riscos
                ]
                secoes_rel.append(RelatorioSecao(titulo="Riscos e Conformidade", itens=itens_rsk))

            return RelatorioResponse(
                titulo=f"Relatório Executivo — Perspectiva {p_detalhe.nome}",
                gerado_em=timestamp,
                perspectiva=p_clean,
                codigo=None,
                secoes=secoes_rel,
            )

        # Relatório por código de documento
        doc = self.acervo.buscar(codigo=codigo)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"Documento '{codigo}' não encontrado no acervo.",
            )

        secoes_doc: List[RelatorioSecao] = []
        for s in doc.secoes:
            fonte = Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao=s.id,
                trecho=s.texto[:200] + ("..." if len(s.texto) > 200 else ""),
                camada=doc.camada,
            )
            secoes_doc.append(
                RelatorioSecao(
                    titulo=f"Seção {s.id} — {s.titulo}",
                    itens=[
                        RelatorioItem(
                            texto=s.texto,
                            fonte=fonte,
                        )
                    ],
                )
            )

        return RelatorioResponse(
            titulo=f"Relatório do Documento {doc.codigo} — {doc.titulo} (v{doc.versao})",
            gerado_em=timestamp,
            perspectiva=None,
            codigo=doc.codigo,
            secoes=secoes_doc,
        )
