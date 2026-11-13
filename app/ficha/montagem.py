"""Montagem determinística da Ficha do Documento por Regra (RF72 a RF76, Contrato C22).

Implementa a orquestração da ficha de forma totalmente genérica:
- Identidade e Governança (F-01)
- Candidatos e Verificador de Fontes (F-03, F-05)
- Derivação de Família e Blocos da Mesa de Decisão (F-17)
- Preenchimento por Regra a partir de itens verificados
- Relevância determinística com fatos comprovados nos motivos (F-17, F-18)
- Ações 'Precisa de você' e BLUF extrativo (RF72, C22)
- Mapa de calor determinístico e semáforo
"""

import re
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Tuple, Union, Any, Set

from app.models import DocumentoDetalhe, Fonte, Camada, Tema
from app.acervo import AcervoRepository
from app.inteligencia import trecho_consta_na_secao
from app.radar import RadarService
from app.ficha.modelos import (
    FichaDocumento,
    Identidade,
    Governanca,
    Semaforo,
    ItemFicha,
    Acao,
    PrazoAcao,
    Bloco,
    RelevanciaBloco,
    CelulaMapa,
    SinaisCelula,
    Alerta,
    Cobertura,
    PontosFicha,
    ModoFicha,
    FamiliaDocumento,
)
from app.ficha.metadados import (
    extrair_metadados_documento,
    obter_data_referencia,
)
from app.ficha.verificador import extrair_e_verificar
from app.ficha.familias import (
    FAMILIA_BLOCOS,
    BlocoTemplate,
    derivar_familia,
)
from app.ficha.relevancia import (
    PesosRelevancia,
    parse_valor_moeda,
    parse_data,
    calcular_relevancia_bloco,
)

ACTORS_RE = re.compile(
    r"\b(GOC|GFI|GCO|GGC|GJU|DIRAF|Empregado|Gestor|Diretor|LOCADORA|LOCAT[ÁA]RIA|fiscal técnico)\b",
    re.IGNORECASE,
)


def _calcular_mapa_calor_deterministico(doc: DocumentoDetalhe) -> List[CelulaMapa]:
    """Gera o mapa de calor determinístico por seção a partir de sinais léxicos."""
    total_palavras = sum(len(s.texto.split()) for s in doc.secoes)
    if total_palavras == 0:
        total_palavras = 1

    celulas = []
    max_sinais = 1

    contagens = []
    for idx, secao in enumerate(doc.secoes, start=1):
        txt_l = secao.texto.lower()
        palavras_sec = len(secao.texto.split())
        s_prazo = len([1 for w in ("dias", "prazo", "data", "vigora", "até o") if w in txt_l])
        s_valor = len([1 for w in ("r$", "%", "valor", "reais", "aluguel", "pagamento") if w in txt_l])
        s_obrig = len([1 for w in ("deve", "obriga", "compete", "cabe ao") if w in txt_l])
        s_risco = len([1 for w in ("multa", "rescis", "vedado", "penalidade", "inexecu") if w in txt_l])
        soma = s_prazo * 2 + s_valor * 2 + s_obrig + s_risco * 2
        if soma > max_sinais:
            max_sinais = soma
        contagens.append((secao, palavras_sec, s_prazo, s_valor, s_obrig, s_risco, soma))

    for idx, (secao, palavras_sec, s_prazo, s_valor, s_obrig, s_risco, soma) in enumerate(contagens, start=1):
        peso = round(palavras_sec / total_palavras, 2)
        intensidade = round(min(1.0, max(0.1, soma / max_sinais)), 2)
        celulas.append(
            CelulaMapa(
                secao_id=secao.id,
                titulo=secao.titulo or secao.id,
                ordem=idx,
                peso=peso,
                sinais=SinaisCelula(
                    prazo=s_prazo,
                    valor=s_valor,
                    obrigacao=s_obrig,
                    risco=s_risco,
                ),
                intensidade=intensidade,
            )
        )
    return celulas


def _obter_alertas_documento(
    doc: DocumentoDetalhe,
    governanca: Governanca,
    acervo: Optional[AcervoRepository],
) -> List[Alerta]:
    """Obtém os alertas determinísticos para o documento (Radar, referências ausentes, substituição)."""
    alertas: List[Alerta] = []

    # 1. Alertas da curadoria via RadarService declarado
    if acervo is not None:
        try:
            radar_service = RadarService(acervo)
            radar_resp = radar_service.obter_radar()
            for r_item in radar_resp.itens:
                fontes_do_doc = [
                    f for f in r_item.fontes
                    if (f.codigo, f.versao) == (doc.codigo, doc.versao)
                ]
                if fontes_do_doc:
                    alertas.append(
                        Alerta(
                            tipo=r_item.tipo,
                            titulo=r_item.titulo,
                            explicacao=r_item.explicacao,
                            radar_id=r_item.id,
                            fontes=fontes_do_doc,
                        )
                    )
                elif r_item.codigo_ausente and r_item.codigo_ausente in governanca.referencias:
                    secao_cita = next(
                        (s for s in doc.secoes if r_item.codigo_ausente in s.texto),
                        None,
                    )
                    if secao_cita:
                        trecho_cita = r_item.codigo_ausente
                        for linha in secao_cita.texto.splitlines():
                            if r_item.codigo_ausente in linha:
                                trecho_cita = linha.strip()
                                break
                        alertas.append(
                            Alerta(
                                tipo=r_item.tipo,
                                titulo=f"{r_item.codigo_ausente} é citada e não está no acervo",
                                explicacao=f"A norma {r_item.codigo_ausente} é citada, mas não consta no acervo central; não pode ser conferida na fonte.",
                                radar_id=r_item.id,
                                fontes=[
                                    Fonte(
                                        codigo=doc.codigo,
                                        versao=doc.versao,
                                        secao=secao_cita.id,
                                        trecho=trecho_cita,
                                        camada=doc.camada,
                                    )
                                ],
                            )
                        )
        except Exception:
            pass

    # 2. Alertas de referências ausentes da governança não cobertas acima
    if acervo is not None:
        codigos_alertados = {a.titulo.split()[0] for a in alertas if a.tipo == "referencia_ausente"}
        for ref_cod in governanca.referencias:
            if ref_cod not in codigos_alertados and acervo.buscar(ref_cod) is None:
                secao_cita = next(
                    (s for s in doc.secoes if ref_cod in s.texto),
                    doc.secoes[-1] if doc.secoes else None,
                )
                trecho = ref_cod
                if secao_cita:
                    for linha in secao_cita.texto.splitlines():
                        if ref_cod in linha:
                            trecho = linha.strip()
                            break

                fonte_alerta = Fonte(
                    codigo=doc.codigo,
                    versao=doc.versao,
                    secao=secao_cita.id if secao_cita else "1",
                    trecho=trecho,
                    camada=doc.camada,
                )
                alertas.append(
                    Alerta(
                        tipo="referencia_ausente",
                        titulo=f"{ref_cod} é citada e não está no acervo",
                        explicacao=f"A norma {ref_cod} é citada, mas não consta no acervo central; não pode ser conferida na fonte.",
                        radar_id=None,
                        fontes=[fonte_alerta],
                    )
                )

    # 3. Alerta se o próprio documento for versão substituída
    if doc.substituido and not any(a.tipo == "versao_substituida" for a in alertas):
        fonte_subst = None
        if doc.secoes:
            s_vig = next(
                (
                    s
                    for s in doc.secoes
                    if any(
                        k in (s.titulo or "").lower()
                        for k in ("vigência", "vigencia", "histórico", "historico", "disposições transitórias")
                    )
                ),
                doc.secoes[0],
            )
            trecho = (s_vig.texto or "").splitlines()[0] if s_vig.texto else doc.titulo
            fonte_subst = Fonte(
                codigo=doc.codigo,
                versao=doc.versao,
                secao=s_vig.id,
                trecho=trecho,
                camada=doc.camada,
            )
        alertas.append(
            Alerta(
                tipo="versao_substituida",
                titulo=f"Documento em versão anterior substituída ({doc.versao})",
                explicacao="Este documento foi revogado/substituído por versão mais recente em vigor.",
                radar_id=None,
                fontes=[fonte_subst] if fonte_subst else [],
            )
        )

    return alertas


def _extrair_bluf_extrativo(
    doc: DocumentoDetalhe,
    identidade: Identidade,
    pontos: PontosFicha,
) -> Optional[ItemFicha]:
    """Monta o resumo extrativo BLUF em uma frase a partir de objeto, vigência e valor global (sem IA)."""
    fontes_bluf: List[Fonte] = []
    partes: List[str] = []

    # 1. Objeto / Descrição
    s_obj = next((s for s in doc.secoes if "objet" in (s.titulo or "").lower() or "objet" in s.id.lower()), None)
    if not s_obj and doc.secoes:
        s_obj = doc.secoes[0]

    if s_obj:
        linhas = [ln.strip() for ln in s_obj.texto.splitlines() if ln.strip()]
        trecho_obj = None
        for ln in linhas:
            if ln.lower() in ("objeto", "objetivo", "1. objetivo", "1 objetivo", "cláusula primeira", "cláusula 1"):
                continue
            trecho_obj = ln
            break
        if not trecho_obj and linhas:
            trecho_obj = linhas[0]

        if trecho_obj:
            partes.append(trecho_obj.rstrip("."))
            fontes_bluf.append(
                Fonte(
                    codigo=doc.codigo,
                    versao=doc.versao,
                    secao=s_obj.id,
                    trecho=trecho_obj,
                    camada=doc.camada,
                )
            )

    # 2. Vigência
    if identidade.vigencia.texto and "sem vigência" not in identidade.vigencia.texto.lower():
        partes.append(f"vigência de {identidade.vigencia.texto}")
        p_vig = next((p for p in pontos.prazos if "vigência" in p.titulo.lower() or "vigora" in (p.texto or "").lower()), None)
        if p_vig and p_vig.fontes:
            fontes_bluf.extend(p_vig.fontes)

    # 3. Valor global
    if pontos.valores:
        maior_val = max(pontos.valores, key=lambda v: parse_valor_moeda(v.valor))
        if parse_valor_moeda(maior_val.valor) > 0 and maior_val.valor:
            partes.append(f"valor de {maior_val.valor}")
            if maior_val.fontes:
                fontes_bluf.extend(maior_val.fontes)

    texto_bluf = "; ".join(partes) + "." if partes else f"{doc.titulo}."

    if not fontes_bluf and doc.secoes:
        sec0 = doc.secoes[0]
        trecho0 = sec0.texto.splitlines()[0].strip() if sec0.texto else sec0.id
        fontes_bluf.append(
            Fonte(codigo=doc.codigo, versao=doc.versao, secao=sec0.id, trecho=trecho0, camada=doc.camada)
        )

    return ItemFicha(
        id="bluf-1",
        titulo="Em uma frase",
        valor=None,
        texto=texto_bluf,
        origem="resumo",
        fontes=fontes_bluf,
    )


def _extrair_acoes_precisa_de_voce(
    doc: DocumentoDetalhe,
    pontos: PontosFicha,
    data_referencia: date,
) -> List[Acao]:
    """Extrai ações determinísticas 'Precisa de você' ordenadas por urgência (RF72, C22)."""
    acoes: List[Acao] = []

    # Ranqueia prazos por proximidade da data de referência
    prazos_com_dt: List[Tuple[int, date, ItemFicha]] = []
    prazos_rel: List[ItemFicha] = []

    for p in pontos.prazos:
        dt = parse_data(p.valor)
        if dt:
            dias = (dt - data_referencia).days
            if dias >= 0:
                prazos_com_dt.append((dias, dt, p))
        elif p.valor and "dias" in p.valor.lower():
            prazos_rel.append(p)

    prazos_com_dt.sort(key=lambda x: x[0])
    selecionados: List[ItemFicha] = [p for _, _, p in prazos_com_dt[:3]]
    if len(selecionados) < 3:
        for p in prazos_rel:
            if p not in selecionados:
                selecionados.append(p)
            if len(selecionados) >= 3:
                break

    if not selecionados and pontos.prazos:
        selecionados = pontos.prazos[:3]

    for idx, p in enumerate(selecionados, start=1):
        sec = next((s for s in doc.secoes if s.id == p.fontes[0].secao), None) if p.fontes else None
        sec_txt = sec.texto if sec else ""

        # Identificação do responsável (quem)
        encontrados = [m.group(0).upper() for m in ACTORS_RE.finditer(sec_txt)]
        if not encontrados:
            # Busca nos responsáveis já verificados
            encontrados = [r.valor for r in pontos.responsaveis if r.valor]
        quem = " · ".join(dict.fromkeys(encontrados[:3])) if encontrados else "Unidade responsável"

        # Consequência extraída de sentenças com termos condicionais/penalidades
        consequencia = None
        for linha in sec_txt.splitlines():
            l_low = linha.lower()
            if any(k in l_low for k in ("sem ", "sob pena", "não há", "só é aceit", "multa", "termina", "rescis")):
                consequencia = linha.strip()
                break

        dt = parse_data(p.valor)
        dias = (dt - data_referencia).days if dt else 999
        urgencia = "alta" if dias <= 30 else "media"

        acoes.append(
            Acao(
                id=f"a-{idx}",
                acao=p.titulo,
                quem=quem,
                prazo=PrazoAcao(data=dt.isoformat() if dt else None, regra=p.valor or p.titulo),
                consequencia=consequencia,
                urgencia=urgencia,
                origem="resumo",
                fontes=p.fontes,
            )
        )

    return acoes


def _montar_blocos_por_familia(
    doc: DocumentoDetalhe,
    familia: FamiliaDocumento,
    pontos: PontosFicha,
    acoes: List[Acao],
    alertas: List[Alerta],
    data_referencia: date,
    governanca: Governanca,
    pesos: Optional[PesosRelevancia] = None,
) -> List[Bloco]:
    """Monta determinística os blocos por família de documento (RF73, RF74, C22).

    Garante:
    - Omissão de bloco vazio (sem item verificado e sem alerta comprovado).
    - Destaque é o item de maior peso do sinal.
    - Apoio até 2 linhas montado dos itens.
    - Relevância calculada determinística com o motivo citando fatos.
    - Desempate estável pela ordem do template.
    - Fallback para lista simples se menos de 3 blocos forem preenchidos.
    """
    templates = FAMILIA_BLOCOS.get(familia, FAMILIA_BLOCOS["contrato"])

    # Encontra maior valor numérico no documento para cálculo de peso_valor
    maior_valor_doc = 0.0
    for v in pontos.valores:
        num = parse_valor_moeda(v.valor)
        if num > maior_valor_doc:
            maior_valor_doc = num

    candidatos_blocos: List[Tuple[Bloco, int]] = []

    for tmpl in templates:
        b_destaque = ""
        b_apoio = ""
        b_secoes: List[str] = []
        b_itens: List[str] = []
        b_alerta_idx: Optional[int] = None

        if tmpl.sinal == "valor":
            if pontos.valores:
                maior_val = max(pontos.valores, key=lambda v: parse_valor_moeda(v.valor))
                b_destaque = maior_val.valor or maior_val.titulo
                outros = [v.valor for v in pontos.valores if v.valor and v.valor != b_destaque]
                b_apoio = f"{maior_val.titulo}." + (f" Demais valores: {', '.join(dict.fromkeys(outros[:2]))}." if outros else "")
                b_secoes = list(dict.fromkeys(f.secao for f in maior_val.fontes))
                b_itens = [maior_val.id] + [v.id for v in pontos.valores if v.id != maior_val.id][:2]

        elif tmpl.sinal == "prazo":
            if pontos.prazos:
                com_data = [p for p in pontos.prazos if parse_data(p.valor)]
                if com_data:
                    top_prz = min(
                        com_data,
                        key=lambda p: (
                            0 if (parse_data(p.valor) - data_referencia).days >= 0 else 1,
                            abs((parse_data(p.valor) - data_referencia).days),
                        ),
                    )
                else:
                    top_prz = pontos.prazos[0]

                b_destaque = top_prz.valor or top_prz.titulo
                outros = [p.valor for p in pontos.prazos if p.valor and p.valor != b_destaque]
                b_apoio = f"{top_prz.titulo}." + (f" Prazos adicionais: {', '.join(dict.fromkeys(outros[:2]))}." if outros else "")
                b_secoes = list(dict.fromkeys(f.secao for f in top_prz.fontes))
                b_itens = [top_prz.id] + [p.id for p in pontos.prazos if p.id != top_prz.id][:2]

        elif tmpl.sinal == "responsavel":
            if pontos.responsaveis:
                resp_nomes = list(dict.fromkeys(r.valor for r in pontos.responsaveis if r.valor))
                b_destaque = " · ".join(resp_nomes[:3]) if resp_nomes else pontos.responsaveis[0].titulo
                b_apoio = f"Atribuições e competências de {b_destaque}."
                b_secoes = list(dict.fromkeys(f.secao for r in pontos.responsaveis[:3] for f in r.fontes))
                b_itens = [r.id for r in pontos.responsaveis[:3]]

        elif tmpl.sinal == "risco":
            itens_risco = pontos.riscos or pontos.condicoes
            multas = [v for v in pontos.valores if "multa" in v.titulo.lower() or "multa" in (v.texto or "").lower()]

            if tmpl.id == "b-risco" and multas:
                multas_num = [m for m in multas if 0 < parse_valor_moeda(m.valor) < (maior_valor_doc or 1e9)]
                top_r = multas_num[0] if multas_num else multas[0]
                b_destaque = top_r.valor or top_r.titulo
                b_apoio = top_r.texto or f"Penalidade: {top_r.titulo}."
                b_secoes = list(dict.fromkeys(f.secao for f in top_r.fontes))
                b_itens = [top_r.id]
            elif tmpl.id == "b-penalidades":
                cands_penal = [
                    p for p in pontos.riscos + pontos.condicoes + pontos.prazos
                    if any(w in (p.texto or "").lower() or w in p.titulo.lower() for w in ("penalid", "exce", "ressalv", "só é aceit", "so e aceit", "vedado", "proibido", "multa"))
                ]
                if cands_penal:
                    top_r = cands_penal[0]
                    b_destaque = top_r.valor or top_r.titulo
                    b_apoio = top_r.texto or f"Condições e penalidades: {top_r.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in top_r.fontes))
                    b_itens = [top_r.id]
                elif itens_risco:
                    top_r = itens_risco[0]
                    b_destaque = top_r.valor or top_r.titulo
                    b_apoio = top_r.texto or f"Condições e penalidades aplicáveis: {top_r.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in top_r.fontes))
                    b_itens = [top_r.id]
            elif itens_risco:
                top_r = itens_risco[0]
                b_destaque = top_r.valor or top_r.titulo
                b_apoio = top_r.texto or f"Condições e penalidades aplicáveis: {top_r.titulo}."
                b_secoes = list(dict.fromkeys(f.secao for f in top_r.fontes))
                b_itens = [top_r.id]

        elif tmpl.sinal == "regra":
            if tmpl.id == "b-muda":
                alerta_v2 = next((a for a in alertas if a.tipo == "versao_substituida"), None)
                item_mudanca = None
                if alerta_v2 and alerta_v2.fontes:
                    secoes_alerta = {f.secao for f in alerta_v2.fontes}
                    cands = [p for p in pontos.prazos + pontos.obrigacoes + pontos.condicoes if any(f.secao in secoes_alerta for f in p.fontes)]
                    if cands:
                        item_mudanca = cands[0]
                if not item_mudanca and pontos.obrigacoes:
                    item_mudanca = pontos.obrigacoes[0]
                elif not item_mudanca and pontos.prazos:
                    item_mudanca = pontos.prazos[0]

                if item_mudanca:
                    b_destaque = item_mudanca.valor or item_mudanca.titulo
                    if alerta_v2:
                        b_apoio = f"{item_mudanca.texto or item_mudanca.titulo} ({alerta_v2.explicacao})"
                        b_alerta_idx = alertas.index(alerta_v2)
                    else:
                        b_apoio = item_mudanca.texto or f"Regra e diretriz aplicável: {item_mudanca.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in item_mudanca.fontes))
                    b_itens = [item_mudanca.id]
                elif alerta_v2:
                    b_destaque = alerta_v2.titulo.split(":")[0]
                    b_apoio = alerta_v2.explicacao
                    b_secoes = list(dict.fromkeys(f.secao for f in alerta_v2.fontes))
                    b_itens = []
                    b_alerta_idx = alertas.index(alerta_v2)

            elif tmpl.id == "b-ligados":
                # Bloco sem item verificado na seção é omitido conforme regra geral (PRD 3.5)
                continue

            elif tmpl.id == "b-regras":
                vedacao = next(
                    (c for c in pontos.condicoes + pontos.riscos if "vedado" in (c.titulo or "").lower() or "vedado" in (c.texto or "").lower()),
                    None,
                )
                if vedacao:
                    b_destaque = vedacao.valor or vedacao.titulo
                    b_apoio = vedacao.texto or f"Regra e vedação expressa: {vedacao.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in vedacao.fontes))
                    b_itens = [vedacao.id]
                elif pontos.obrigacoes:
                    reg_top = pontos.obrigacoes[0]
                    b_destaque = reg_top.titulo
                    b_apoio = reg_top.texto or f"Regra e diretriz aplicável: {reg_top.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in reg_top.fontes))
                    b_itens = [reg_top.id]

            else:
                itens_regra = pontos.obrigacoes or pontos.condicoes
                if itens_regra:
                    reg_top = itens_regra[0]
                    b_destaque = reg_top.titulo
                    b_apoio = reg_top.texto or f"Regra e diretriz aplicável: {reg_top.titulo}."
                    b_secoes = list(dict.fromkeys(f.secao for f in reg_top.fontes))
                    b_itens = [reg_top.id]

        elif tmpl.sinal == "alerta":
            if tmpl.id == "b-falta":
                alerta_falta = next((a for a in alertas if a.tipo == "referencia_ausente"), None)
                if alerta_falta:
                    b_destaque = alerta_falta.titulo.split()[0]
                    b_apoio = alerta_falta.explicacao
                    b_secoes = list(dict.fromkeys(f.secao for f in alerta_falta.fontes))
                    b_itens = []
                    b_alerta_idx = alertas.index(alerta_falta)

            elif tmpl.id == "b-versao":
                alerta_versao = next((a for a in alertas if a.tipo == "versao_substituida"), None)
                if alerta_versao or doc.substituido:
                    b_destaque = f"v{doc.versao} em vigor" if not doc.substituido else f"v{doc.versao} substituída"
                    b_apoio = alerta_versao.explicacao if alerta_versao else "Documento substituído por versão mais recente."
                    b_secoes = list(dict.fromkeys(f.secao for f in alerta_versao.fontes)) if alerta_versao else ([doc.secoes[0].id] if doc.secoes else [])
                    b_itens = []
                    b_alerta_idx = alertas.index(alerta_versao) if alerta_versao else None

            elif alertas:
                alerta_cand = alertas[0]
                b_destaque = alerta_cand.titulo.split(":")[0] if ":" in alerta_cand.titulo else alerta_cand.titulo
                b_apoio = alerta_cand.explicacao
                b_secoes = list(dict.fromkeys(f.secao for f in alerta_cand.fontes))
                b_itens = []
                b_alerta_idx = 0

        # Omissão de bloco sem fonte (sem item verificado e sem alerta comprovado, PRD 3.5)
        if not b_destaque or (not b_itens and b_alerta_idx is None):
            continue

        pontuacao, motivo = calcular_relevancia_bloco(
            id_bloco=tmpl.id,
            titulo=tmpl.titulo,
            sinal=tmpl.sinal,
            destaque=b_destaque,
            apoio=b_apoio,
            maior_valor_doc=maior_valor_doc,
            data_referencia=data_referencia,
            pesos=pesos,
            familia=familia,
        )

        bloco_pronto = Bloco(
            id=tmpl.id,
            titulo=tmpl.titulo,
            destaque=b_destaque,
            apoio=b_apoio,
            relevancia=RelevanciaBloco(posicao=tmpl.ordem_padrao, motivo=motivo, pontuacao=pontuacao),
            sinal=tmpl.sinal,
            secoes_mapa=b_secoes,
            itens=b_itens,
            alerta=b_alerta_idx,
        )
        candidatos_blocos.append((bloco_pronto, tmpl.ordem_padrao))

    # Regra: Família com menos de 3 blocos preenchidos cai para uma lista simples (sem erro)
    if len(candidatos_blocos) < 3:
        blocos_simples: List[Tuple[Bloco, int]] = []
        ordem = 1
        for cat_nome, itens_cat, sinal_cat in [
            ("Prazos", pontos.prazos, "prazo"),
            ("Valores", pontos.valores, "valor"),
            ("Quem faz o quê", pontos.responsaveis, "responsavel"),
            ("Riscos", pontos.riscos, "risco"),
            ("Obrigações", pontos.obrigacoes, "regra"),
        ]:
            if itens_cat:
                item0 = itens_cat[0]
                destaque = item0.valor or item0.titulo
                apoio = item0.texto or item0.titulo
                secoes = list(dict.fromkeys(f.secao for f in item0.fontes))
                pontuacao, motivo = calcular_relevancia_bloco(
                    id_bloco=f"b-simples-{cat_nome.lower()}",
                    titulo=cat_nome,
                    sinal=sinal_cat,  # type: ignore[arg-type]
                    destaque=destaque,
                    apoio=apoio,
                    maior_valor_doc=maior_valor_doc,
                    data_referencia=data_referencia,
                    pesos=pesos,
                    familia=familia,
                )
                b = Bloco(
                    id=f"b-simples-{ordem}",
                    titulo=cat_nome,
                    destaque=destaque,
                    apoio=apoio,
                    relevancia=RelevanciaBloco(posicao=ordem, motivo=motivo, pontuacao=pontuacao),
                    sinal=sinal_cat,  # type: ignore[arg-type]
                    secoes_mapa=secoes,
                    itens=[item0.id],
                    alerta=None,
                )
                blocos_simples.append((b, ordem))
                ordem += 1

        candidatos_blocos = blocos_simples

    # Ordenação estável por relevância:
    # 1º maior pontuação decrescente
    # 2º ordem padrão crescente (desempate determinístico)
    candidatos_blocos.sort(key=lambda x: (-x[0].relevancia.pontuacao, x[1]))

    # Atribuição da posição ordinal de 1 a N
    blocos_ordenados: List[Bloco] = []
    for pos, (b, _) in enumerate(candidatos_blocos, start=1):
        b.relevancia.posicao = pos
        blocos_ordenados.append(b)

    return blocos_ordenados


def montar_ficha(
    doc: DocumentoDetalhe,
    acervo: Optional[AcervoRepository] = None,
    data_referencia: Optional[Union[date, str]] = None,
    perfil: Optional[str] = None,
    linguagem: str = "original",
) -> FichaDocumento:
    """Função principal que orquestra a montagem completa da Ficha do Documento por Regra (C22)."""
    if acervo is None:
        try:
            from app.acervo import get_acervo
            acervo = get_acervo()
        except Exception:
            pass

    data_ref = obter_data_referencia(data_referencia)

    # 1. Metadados determinísticos
    identidade, governanca, semaforo_base, _ = extrair_metadados_documento(
        doc,
        data_referencia=data_ref,
        acervo=acervo,
    )

    # 2. Candidatos e verificador de fontes
    pontos, cobertura = extrair_e_verificar(doc)

    # 3. Derivação da família
    familia = derivar_familia(doc, candidatos={"valores": pontos.valores, "prazos": pontos.prazos})

    # 4. Alertas do documento (Radar e referências ausentes declaradas)
    alertas = _obter_alertas_documento(doc, governanca=governanca, acervo=acervo)

    # 5. Ações 'Precisa de você'
    acoes = _extrair_acoes_precisa_de_voce(doc, pontos=pontos, data_referencia=data_ref)

    # 6. BLUF extrativo
    bluf = _extrair_bluf_extrativo(doc, identidade=identidade, pontos=pontos)

    # 7. Blocos da Mesa de Decisão ordenados por relevância
    blocos = _montar_blocos_por_familia(
        doc=doc,
        familia=familia,
        pontos=pontos,
        acoes=acoes,
        alertas=alertas,
        data_referencia=data_ref,
        governanca=governanca,
    )

    # 8. Números destacados com fontes verificadas (compatibilidade retroativa RF48)
    numeros: List[ItemFicha] = []
    if pontos.valores:
        maior_v = max(pontos.valores, key=lambda v: parse_valor_moeda(v.valor))
        numeros.append(maior_v)
    if pontos.prazos:
        com_dt = [p for p in pontos.prazos if parse_data(p.valor)]
        prox_p = min(com_dt, key=lambda p: abs((parse_data(p.valor) - data_ref).days)) if com_dt else pontos.prazos[0]
        if prox_p not in numeros:
            numeros.append(prox_p)
    multas = [v for v in pontos.valores if "multa" in v.titulo.lower() or "multa" in (v.texto or "").lower()]
    if multas and multas[0] not in numeros:
        numeros.append(multas[0])

    # 9. Mapa de calor determinístico
    mapa_calor = _calcular_mapa_calor_deterministico(doc)

    # 10. Atualização do Semáforo determinístico (RF46, C22, Issue #48)
    motivos_critico: List[str] = []
    motivos_atencao: List[str] = []

    # 1. Documento substituído -> crítico
    if doc.substituido:
        motivos_critico.append(f"Documento em versão anterior substituída ({doc.versao})")

    # 2. Vigência do documento
    if identidade.vigencia and identidade.vigencia.dias_restantes is not None:
        dias_vig = identidade.vigencia.dias_restantes
        if dias_vig < 0:
            motivos_critico.append(f"Vigência encerrada há {abs(dias_vig)} dias")
        elif 0 <= dias_vig <= 7:
            motivos_critico.append(f"Vigência encerra em {dias_vig} dias")
        elif 7 < dias_vig <= 60:
            motivos_atencao.append(f"Vigência encerra em {dias_vig} dias")

    # 3. Prazos extraídos (ignora histórico de versões e exemplos)
    prazos_urgentes: List[Tuple[int, str]] = []
    prazos_atencao: List[Tuple[int, str]] = []
    for p in pontos.prazos:
        sec = next((s for s in doc.secoes if p.fontes and s.id == p.fontes[0].secao), None)
        sec_tit = (sec.titulo or "").lower() if sec else ""
        if any(w in sec_tit for w in ("histórico", "historico", "versão", "versao", "exemplo")):
            continue
        dt = parse_data(p.valor)
        if dt:
            dias = (dt - data_ref).days
            if dias < 0:
                prazos_urgentes.append((dias, f"Prazo vencido: {p.titulo} há {abs(dias)} dias"))
            elif 0 <= dias <= 7:
                prazos_urgentes.append((dias, f"Prazo crítico: {p.titulo} em {dias} dias"))
            elif 7 < dias <= 30:
                m_prz = f"{p.titulo} até {dt.strftime('%d/%m/%Y')} ({dias} dias)"
                prazos_atencao.append((dias, m_prz))

    if prazos_urgentes:
        prazos_urgentes.sort(key=lambda x: x[0])
        for _, m_crit in prazos_urgentes[:2]:
            if m_crit not in motivos_critico:
                motivos_critico.append(m_crit)
    elif prazos_atencao:
        prazos_atencao.sort(key=lambda x: x[0])
        top_atencao = prazos_atencao[0][1]
        if top_atencao not in motivos_atencao:
            motivos_atencao.append(top_atencao)

    # 4. Referência ausente e alertas do Radar
    for a in alertas:
        if a.tipo == "referencia_ausente":
            cod_ausente = a.titulo.split()[0]
            motivo_ref = f"{cod_ausente} citada e ausente do acervo"
            if motivo_ref not in motivos_atencao:
                motivos_atencao.append(motivo_ref)
        elif a.tipo == "versao_substituida":
            if doc.substituido:
                if a.titulo not in motivos_critico:
                    motivos_critico.append(a.titulo)
        else:
            if a.titulo not in motivos_atencao:
                motivos_atencao.append(a.titulo)

    # 5. Item descartado > 0 -> atenção
    if cobertura.itens_descartados > 0:
        motivos_atencao.append(
            f"{cobertura.itens_descartados} itens descartados por inconsistência de fonte"
        )

    # Consolidação do Semáforo
    if motivos_critico:
        nivel_semaforo = "critico"
        motivos_semaforo = motivos_critico + motivos_atencao
    elif motivos_atencao:
        nivel_semaforo = "atencao"
        motivos_semaforo = motivos_atencao
    else:
        nivel_semaforo = "ok"
        motivos_semaforo = semaforo_base.motivos or ["Documento em conformidade e sem pendências críticas"]

    semaforo_final = Semaforo(
        nivel=nivel_semaforo,  # type: ignore[arg-type]
        motivos=motivos_semaforo,
    )

    # 11. Perguntas sugeridas conforme a família (RF72 a RF76)
    perguntas_por_familia = {
        "contrato": [
            "Posso rescindir o contrato sem incidência de multa?",
            "Quem é responsável pela fiscalização técnica e pelo atesto?",
            "Até quando é possível solicitar a prorrogação da vigência?",
            "Quais penalidades e multas se aplicam em caso de inadimplemento?",
        ],
        "norma": [
            f"Quais são os prazos e condições mínimas estabelecidos em {doc.codigo}?",
            "Quem são as áreas e gestores responsáveis pela aplicação desta norma?",
            "Quais penalidades e hipóteses de exceção estão previstas?",
            "Qual é a versão vigente e quais foram as principais alterações?",
        ],
        "procedimento": [
            f"Qual é o fluxo operacional passo a passo definido em {doc.codigo}?",
            "Quem são os responsáveis pela execução de cada etapa?",
            "Quais prazos regulamentares devem ser observados?",
            "Quais formulários e documentos correlatos devem ser preenchidos?",
        ],
        "nota_tecnica": [
            f"Qual é a justificativa técnica apresentada em {doc.codigo}?",
            "Quais alçadas e limites financeiros foram analisados?",
            "Quais riscos ou pontos de atenção foram sinalizados?",
            "Quais são os encaminhamentos e recomendações propostos?",
        ],
    }
    perguntas_sugeridas = perguntas_por_familia.get(familia, perguntas_por_familia["norma"])

    # Timestamp de geração
    tz_br = timezone(timedelta(hours=-3))
    gerada_em = datetime.now(tz_br).isoformat()

    return FichaDocumento(
        codigo=doc.codigo,
        versao=doc.versao,
        gerada_em=gerada_em,
        perfil=perfil,
        linguagem=linguagem,
        estado="pronta",
        progresso=None,
        modo=ModoFicha(ia="extrativo", modelo=None),
        identidade=identidade,
        semaforo=semaforo_final,
        governanca=governanca,
        familia=familia,
        blocos=blocos,
        bluf=bluf,
        numeros=numeros,
        acoes=acoes,
        pontos=pontos,
        mapa_calor=mapa_calor,
        alertas=alertas,
        perguntas_sugeridas=perguntas_sugeridas,
        cobertura=cobertura,
        delta=None,
    )
