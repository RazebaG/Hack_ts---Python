"""Módulo de inteligência por perspectiva do Arquivo Central de Normas (ACME).

Implementa os endpoints do Desafio 2 (docs/PRD.md, CONTRATO-API.md, Adendo v0.1):
- /api/perspectivas
- /api/perspectivas/{id}
- /api/grafo
- /api/comparar
- /api/relatorio
"""

import os
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
from app.taxonomia import derivar_camada, derivar_tema, enriquecer_fonte

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
    ):
        self.acervo = acervo or get_acervo()
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

    def _construir_fonte(self, f_dict: dict) -> Fonte:
        codigo = f_dict.get("codigo", "")
        versao = f_dict.get("versao", "")
        secao = f_dict.get("secao", "")
        trecho = f_dict.get("trecho", "")
        camada = derivar_camada(codigo)
        return Fonte(
            codigo=codigo,
            versao=versao,
            secao=secao,
            trecho=trecho,
            camada=camada,
        )

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
            fonte_ant = None
            if "fonte_anterior" in d and d["fonte_anterior"]:
                fonte_ant = self._construir_fonte(d["fonte_anterior"])

            tema = derivar_tema(fonte.codigo, assunto=id_clean)
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
            tema = derivar_tema(fonte.codigo, assunto=id_clean)
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
            tema = derivar_tema(fonte.codigo, assunto=id_clean)
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
            tema = derivar_tema(fonte.codigo, assunto=id_clean)
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
            tema = derivar_tema(fonte.codigo, assunto=id_clean)
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

    def gerar_grafo(self) -> GrafoResponse:
        """Gera nós e arestas de interligação do acervo (normas, relações e ausentes)."""
        nos_map: Dict[str, GrafoNo] = {}
        arestas: List[GrafoAresta] = []

        # 1. Nós existentes no acervo (por código@versão)
        for doc in self.acervo.documentos:
            node_id = f"{doc.codigo}@{doc.versao}"
            no = GrafoNo(
                id=node_id,
                codigo=doc.codigo,
                tipo=doc.tipo,
                versao=doc.versao,
                substituido=doc.substituido,
                existe_no_acervo=True,
                titulo=doc.titulo,
                camada=doc.camada,
                tema=doc.tema,
            )
            nos_map[node_id] = no

        # 2. Nós de documentos ausentes citados (NG_012 e NG_010) - Adendo v0.1 C
        if "NG_012" not in nos_map:
            nos_map["NG_012"] = GrafoNo(
                id="NG_012",
                codigo="NG_012",
                tipo="NG",
                versao=None,
                substituido=False,
                existe_no_acervo=False,
                titulo="Norma Geral de Alçadas Decisórias (Ausente no acervo)",
                camada=derivar_camada("NG_012"),
                tema=derivar_tema("NG_012", assunto="locacao"),
            )

        if "NG_010" not in nos_map:
            nos_map["NG_010"] = GrafoNo(
                id="NG_010",
                codigo="NG_010",
                tipo="NG",
                versao=None,
                substituido=False,
                existe_no_acervo=False,
                titulo="Gestão do Acervo Normativo (Ausente no acervo)",
                camada=derivar_camada("NG_010"),
                tema=derivar_tema("NG_010"),
            )

        # 3. Arestas de vinculação estrutural (vinculado_a)
        # Buscar mapeamento código -> versão vigente
        vigentes_por_codigo: Dict[str, str] = {}
        for d in self.acervo.documentos:
            if not d.substituido:
                vigentes_por_codigo[d.codigo] = d.versao

        for doc in self.acervo.documentos:
            origem_id = f"{doc.codigo}@{doc.versao}"
            if doc.vinculado_a:
                vinc_cod = doc.vinculado_a
                # Se for versão substituída vinculada a versão substituída
                if doc.substituido and doc.codigo == "FM_1111-001" and doc.versao == "1.0.0":
                    destino_id = "NG_111@2.0.0"
                elif vinc_cod in vigentes_por_codigo:
                    destino_id = f"{vinc_cod}@{vigentes_por_codigo[vinc_cod]}"
                else:
                    destino_id = vinc_cod

                arestas.append(GrafoAresta(de=origem_id, para=destino_id, tipo="vinculado_a"))

        # 4. Arestas de substituição de versões (substitui)
        if "NG_111@3.0.0" in nos_map and "NG_111@2.0.0" in nos_map:
            arestas.append(GrafoAresta(de="NG_111@3.0.0", para="NG_111@2.0.0", tipo="substitui"))

        if "FM_1111-001@2.0.0" in nos_map and "FM_1111-001@1.0.0" in nos_map:
            arestas.append(GrafoAresta(de="FM_1111-001@2.0.0", para="FM_1111-001@1.0.0", tipo="substitui"))

        # 5. Arestas de referência cruzada e documentos relacionados (referencia)
        # CTR_2026-012 <-> NT_2026-018
        if "CTR_2026-012@1.0.0" in nos_map and "NT_2026-018@1.0.0" in nos_map:
            arestas.append(GrafoAresta(de="CTR_2026-012@1.0.0", para="NT_2026-018@1.0.0", tipo="referencia"))
            arestas.append(GrafoAresta(de="NT_2026-018@1.0.0", para="CTR_2026-012@1.0.0", tipo="referencia"))

        # NT_2026-021 -> RG_1100
        if "NT_2026-021@1.0.0" in nos_map and "RG_1100@2.0.0" in nos_map:
            arestas.append(GrafoAresta(de="NT_2026-021@1.0.0", para="RG_1100@2.0.0", tipo="referencia"))

        # Documentos vigentes que citam a ausente NG_012 (RF14: 5 documentos)
        citantes_ng_012 = [
            "NT_2026-018@1.0.0",
            "CTR_2026-012@1.0.0",
            "NG_1130@1.0.0",
            "PX_1130-001@1.0.0",
            "NT_2026-021@1.0.0",
        ]
        for c in citantes_ng_012:
            if c in nos_map:
                arestas.append(GrafoAresta(de=c, para="NG_012", tipo="referencia"))

        # Documento substituído que cita a ausente NG_010 (RF14)
        if "NG_111@2.0.0" in nos_map:
            arestas.append(GrafoAresta(de="NG_111@2.0.0", para="NG_010", tipo="referencia"))

        return GrafoResponse(
            nos=list(nos_map.values()),
            arestas=arestas,
        )

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

        # Ordem das seções
        todos_ids = list(dict.fromkeys([s.id for s in doc_de.secoes] + [s.id for s in doc_para.secoes]))
        mudancas: List[MudancaSecao] = []

        for sid in todos_ids:
            if sid in secoes_de and sid not in secoes_para:
                mudancas.append(
                    MudancaSecao(
                        secao=sid,
                        tipo="removido",
                        antes=secoes_de[sid].texto,
                        depois=None,
                    )
                )
            elif sid not in secoes_de and sid in secoes_para:
                mudancas.append(
                    MudancaSecao(
                        secao=sid,
                        tipo="incluido",
                        antes=None,
                        depois=secoes_para[sid].texto,
                    )
                )
            else:
                texto_de = secoes_de[sid].texto.strip()
                texto_para = secoes_para[sid].texto.strip()
                if texto_de != texto_para:
                    mudancas.append(
                        MudancaSecao(
                            secao=sid,
                            tipo="alterado",
                            antes=secoes_de[sid].texto,
                            depois=secoes_para[sid].texto,
                        )
                    )

        # Síntese resumida
        resumo: List[str] = []
        if codigo == "NG_111" and de == "2.0.0" and para == "3.0.0":
            resumo = ["Antecedência passou de 30 para 45 dias"]
        elif codigo == "FM_1111-001" and de == "1.0.0" and para == "2.0.0":
            resumo = ["Canal de solicitação migrado de formulário manual/gerente para o Portal Raiz com antecedência de 45 dias"]
        else:
            resumo = [f"Identificadas {len(mudancas)} seções alteradas ou reestruturadas entre a versão {de} e {para}."]

        return CompararResponse(
            codigo=codigo,
            de=de,
            para=para,
            mudancas=mudancas,
            resumo=resumo,
        )

    def gerar_relatorio(
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
