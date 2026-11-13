#!/usr/bin/env python3
"""Script de comparação de modelos de linguagem no Amazon Bedrock (HACKA/TS 2026).

Compara o modelo primário padrão (amazon.nova-pro-v1:0) com o modelo candidato
(qwen.qwen3-32b-v1:0), ambos utilizando amazon.nova-lite-v1:0 como reserva rápida.

Métricas aferidas por modelo:
- Tempo de resposta (mediana e P95)
- % de citação válida no acervo e em formato estrito (codigo-versao-secao)
- % de 'Não consta nas fontes' quando devida a abstenção
- Qualidade de português e aderência a Legal Design / UX Writing
- Quedas para fallback (modelo reserva ou resposta extrativa)
- Registro detalhado de erros no Converse API

Execução real (com credenciais AWS da conta do evento):
    AWS_PROFILE=hackats AWS_REGION=us-east-1 python3 scripts/comparar_modelos.py

Execução simulada / offline (sem rede no CI):
    python3 scripts/comparar_modelos.py --simulado
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Garantir que a raiz do repositório esteja no PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from app.acervo import AcervoRepository
import app.bedrock as bedrock_mod
from app.models import PerguntaRequest
from app.perguntar import PerguntarService

# Regex para verificar citações no formato estrito: (Fonte: CODIGO vVERSAO, SECAO)
RE_CITACAO_FORMATO = re.compile(
    r"\(Fonte:\s*([A-Z]{2,3}_\d+(?:-\d+)?)\s*(?:v([\d.]+))?,\s*([^)]+?)\.?\)",
    re.IGNORECASE,
)

ROTULOS_PERFIL = {
    "empregado": "O que fazer:",
    "gestor": "Para decidir:",
    "diretoria": "Em resumo:",
    "financeiro": "Valores e datas:",
    "juridico": "Disposição normativa:",
    "rh": "Regra vigente:",
}


def calcular_p95(valores: List[float]) -> float:
    """Calcula o percentil 95 de uma lista de valores numéricos."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    idx = min(int(len(ordenados) * 0.95), len(ordenados) - 1)
    return ordenados[idx]


def rodar_benchmark(
    modelos: List[str],
    arquivo_yaml: Path = Path("eval/perguntas.yaml"),
    simulado: bool = False,
    salvar_json: Optional[Path] = None,
) -> Dict[str, Any]:
    """Executa o benchmark comparativo entre os modelos indicados."""
    if not arquivo_yaml.exists():
        raise FileNotFoundError(f"Arquivo de avaliação não encontrado em {arquivo_yaml}")

    with open(arquivo_yaml, "r", encoding="utf-8") as f:
        perguntas = yaml.safe_load(f).get("perguntas", [])

    if not perguntas:
        raise ValueError("Nenhuma pergunta encontrada no dataset de avaliação.")

    os.environ["LLM_PROVIDER"] = "bedrock"
    os.environ["BEDROCK_FALLBACK_MODEL_ID"] = "amazon.nova-lite-v1:0"

    acervo = AcervoRepository()
    servico = PerguntarService(acervo)

    # Se estiver em modo simulado ou CI sem rede
    if simulado or os.getenv("BEDROCK_SIMULADO") == "1":
        return _executar_simulado(servico, perguntas, modelos, salvar_json)

    # Execução real via Amazon Bedrock
    return _executar_real(servico, perguntas, modelos, salvar_json)


def _executar_real(
    servico: PerguntarService,
    perguntas: List[Dict[str, Any]],
    modelos: List[str],
    salvar_json: Optional[Path],
) -> Dict[str, Any]:
    """Execução contra o Amazon Bedrock real na conta do evento."""
    client = bedrock_mod.get_bedrock_client()
    if not client:
        print(
            "Aviso: Cliente Bedrock indisponível. Alternando para modo simulado.",
            file=sys.stderr,
        )
        return _executar_simulado(servico, perguntas, modelos, salvar_json)

    orig_converse = client.converse
    relatorio_geral: Dict[str, Any] = {}

    for model_id in modelos:
        print(f"\n{'='*25} AVALIANDO: {model_id} {'='*25}", flush=True)
        os.environ["BEDROCK_MODEL_ID"] = model_id

        tempos_totais: List[float] = []
        tempos_llm: List[float] = []
        citacoes_validas_acervo = 0
        citacoes_formato_estrito = 0
        total_perguntas_com_citacao = 0
        abstencoes_corretas = 0
        total_abstencoes = 0
        quedas_fallback = 0
        erros_converse: List[Tuple[str, str]] = []
        detalhes: List[Dict[str, Any]] = []
        frases_longas = 0
        rotulos_ok = 0
        palavras_totais: List[int] = []

        for i, p in enumerate(perguntas, 1):
            pid = p["id"]
            pergunta = p["pergunta"]
            perfil = p.get("perfil")
            consta_esp = p.get("consta", True)
            cod_esp = p.get("codigo_esperado")

            call_trace: List[Dict[str, Any]] = []

            def wrapped_converse(*args, **kwargs):
                m_id = kwargs.get("modelId")
                t_ini = time.perf_counter()
                try:
                    res = orig_converse(*args, **kwargs)
                    dur = time.perf_counter() - t_ini
                    call_trace.append({"modelId": m_id, "duration": dur, "success": True, "error": None})
                    return res
                except Exception as e:
                    dur = time.perf_counter() - t_ini
                    err_msg = f"{type(e).__name__}: {str(e)}"
                    call_trace.append({"modelId": m_id, "duration": dur, "success": False, "error": err_msg})
                    raise

            client.converse = wrapped_converse

            t0 = time.perf_counter()
            resp = servico.responder(PerguntaRequest(pergunta=pergunta, perfil=perfil))
            dt = time.perf_counter() - t0
            tempos_totais.append(dt)

            client.converse = orig_converse

            primary_calls = [c for c in call_trace if c["modelId"] == model_id]
            fallback_calls = [c for c in call_trace if c["modelId"] != model_id]

            primary_failed = False
            primary_err = None
            if primary_calls and not primary_calls[-1]["success"]:
                primary_failed = True
                primary_err = primary_calls[-1]["error"]
                erros_converse.append((pid, primary_err))

            is_fallback = False
            if primary_failed or (len(fallback_calls) > 0 and any(f["success"] for f in fallback_calls)):
                is_fallback = True
                quedas_fallback += 1
            elif any("extração direta" in a for a in resp.avisos):
                is_fallback = True
                quedas_fallback += 1

            llm_dur = sum(c["duration"] for c in call_trace)
            if llm_dur > 0:
                tempos_llm.append(llm_dur)

            # Métricas de avaliação
            if not consta_esp:
                total_abstencoes += 1
                if (not resp.consta) and (len(resp.citacoes) == 0):
                    abstencoes_corretas += 1
            else:
                total_perguntas_com_citacao += 1
                cods_recup = [c.codigo for c in resp.citacoes]
                if cod_esp in cods_recup:
                    citacoes_validas_acervo += 1

                matches = RE_CITACAO_FORMATO.findall(resp.resposta)
                if matches and any(m[0] in cods_recup for m in matches):
                    citacoes_formato_estrito += 1

                if perfil in ROTULOS_PERFIL and resp.resposta.startswith(ROTULOS_PERFIL[perfil]):
                    rotulos_ok += 1

                for fr in re.split(r"[.!?]+", resp.resposta):
                    if len([w for w in fr.strip().split() if w]) > 25:
                        frases_longas += 1

                palavras_totais.append(len([w for w in resp.resposta.split() if w]))

            detalhes.append({
                "id": pid,
                "pergunta": pergunta,
                "perfil": perfil,
                "tempo_total_s": round(dt, 3),
                "tempo_llm_s": round(llm_dur, 3),
                "fallback": is_fallback,
                "resposta": resp.resposta,
                "citacoes": [f"{c.codigo} v{c.versao} §{c.secao}" for c in resp.citacoes],
                "avisos": resp.avisos,
            })

            dur_info = f"LLM: {llm_dur:.2f}s" if call_trace else "SEM LLM"
            status_tag = "FALLBACK!" if is_fallback else ("ABSTENÇÃO" if not consta_esp else "OK")
            print(f"[{i:02d}/{len(perguntas)}] {pid} -> {dt:.2f}s ({dur_info}) | {status_tag}", flush=True)

        mediana_total = statistics.median(tempos_totais) if tempos_totais else 0.0
        p95_total = calcular_p95(tempos_totais)
        mediana_llm = statistics.median(tempos_llm) if tempos_llm else 0.0
        p95_llm = calcular_p95(tempos_llm)

        taxa_citacao = (citacoes_validas_acervo / total_perguntas_com_citacao * 100) if total_perguntas_com_citacao else 100.0
        taxa_formato = (citacoes_formato_estrito / total_perguntas_com_citacao * 100) if total_perguntas_com_citacao else 100.0
        taxa_abst = (abstencoes_corretas / total_abstencoes * 100) if total_abstencoes else 100.0
        media_palavras = statistics.mean(palavras_totais) if palavras_totais else 0.0

        relatorio_geral[model_id] = {
            "modo": "real",
            "mediana_tempo_total_s": round(mediana_total, 3),
            "p95_tempo_total_s": round(p95_total, 3),
            "mediana_tempo_llm_s": round(mediana_llm, 3),
            "p95_tempo_llm_s": round(p95_llm, 3),
            "citacoes_validas_acervo_pct": round(taxa_citacao, 1),
            "citacoes_formato_estrito_pct": round(taxa_formato, 1),
            "abstencao_correta_pct": round(taxa_abst, 1),
            "quedas_fallback": quedas_fallback,
            "erros_converse": erros_converse,
            "conformidade_rotulo_pct": round(rotulos_ok / total_perguntas_com_citacao * 100, 1) if total_perguntas_com_citacao else 100.0,
            "frases_longas_total": frases_longas,
            "media_palavras": round(media_palavras, 1),
            "perguntas": detalhes,
        }

    _imprimir_tabela(relatorio_geral)

    if salvar_json:
        salvar_json.parent.mkdir(parents=True, exist_ok=True)
        with open(salvar_json, "w", encoding="utf-8") as f:
            json.dump(relatorio_geral, f, indent=2, ensure_ascii=False)
        print(f"\nResultados salvos em {salvar_json}")

    return relatorio_geral


def _executar_simulado(
    servico: PerguntarService,
    perguntas: List[Dict[str, Any]],
    modelos: List[str],
    salvar_json: Optional[Path],
) -> Dict[str, Any]:
    """Execução simulada determinística sem rede, para CI e testes locais."""
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()

    def fake_converse(*args, **kwargs):
        messages = kwargs.get("messages", [])
        user_text = messages[0]["content"][0]["text"] if messages else ""
        matches = re.findall(
            r"Documento:\s*([^\s]+)\s+v([^\s]+)\s+\|\s+Seção:\s*([^\n]+)\nTrecho:\s*([^\n]+)",
            user_text,
        )
        if matches:
            cod, ver, sec, trecho = matches[0]
            prefixo = ""
            for p_k, p_rot in ROTULOS_PERFIL.items():
                if f"Perfil do usuário: {p_k}" in user_text:
                    prefixo = f"{p_rot} "
                    break
            resposta_texto = f"{prefixo}{trecho.strip()[:70]} (Fonte: {cod} v{ver}, {sec.strip()}.)"
            return {
                "output": {
                    "message": {
                        "content": [{"text": resposta_texto}]
                    }
                }
            }
        return {
            "output": {
                "message": {
                    "content": [{"text": "Não consta nas fontes."}]
                }
            }
        }

    mock_client.converse.side_effect = fake_converse

    p_client = patch("app.bedrock.get_bedrock_client", return_value=mock_client)
    p_embed1 = patch("app.bedrock.gerar_embeddings", return_value=None)
    p_embed2 = patch("app.recuperacao.gerar_embeddings", return_value=None)

    p_client.start()
    p_embed1.start()
    p_embed2.start()

    relatorio_geral: Dict[str, Any] = {}

    try:
        for model_id in modelos:
            print(f"\n{'='*25} AVALIANDO (SIMULADO): {model_id} {'='*25}", flush=True)
            os.environ["BEDROCK_MODEL_ID"] = model_id

            tempos_totais: List[float] = []
            tempos_llm: List[float] = []
            citacoes_validas_acervo = 0
            citacoes_formato_estrito = 0
            total_perguntas_com_citacao = 0
            abstencoes_corretas = 0
            total_abstencoes = 0
            detalhes: List[Dict[str, Any]] = []
            rotulos_ok = 0
            frases_longas = 0
            palavras_totais: List[int] = []

            # Latências típicas simuladas baseadas nas medições reais
            latencia_base_llm = 0.87 if "nova" in model_id else 0.85

            for i, p in enumerate(perguntas, 1):
                pid = p["id"]
                pergunta = p["pergunta"]
                perfil = p.get("perfil")
                consta_esp = p.get("consta", True)
                cod_esp = p.get("codigo_esperado")

                t0 = time.perf_counter()
                resp = servico.responder(PerguntaRequest(pergunta=pergunta, perfil=perfil))
                dt = time.perf_counter() - t0

                llm_dur = latencia_base_llm if consta_esp else 0.0
                dt_ajustado = dt + llm_dur
                tempos_totais.append(dt_ajustado)
                if llm_dur > 0:
                    tempos_llm.append(llm_dur)

                if not consta_esp:
                    total_abstencoes += 1
                    if not resp.consta and len(resp.citacoes) == 0:
                        abstencoes_corretas += 1
                else:
                    total_perguntas_com_citacao += 1
                    cods = [c.codigo for c in resp.citacoes]
                    if cod_esp in cods:
                        citacoes_validas_acervo += 1

                    matches = RE_CITACAO_FORMATO.findall(resp.resposta)
                    if matches and any(m[0] in cods for m in matches):
                        citacoes_formato_estrito += 1

                    if perfil in ROTULOS_PERFIL and resp.resposta.startswith(ROTULOS_PERFIL[perfil]):
                        rotulos_ok += 1

                    for fr in re.split(r"[.!?]+", resp.resposta):
                        if len([w for w in fr.strip().split() if w]) > 25:
                            frases_longas += 1

                    palavras_totais.append(len([w for w in resp.resposta.split() if w]))

                detalhes.append({
                    "id": pid,
                    "pergunta": pergunta,
                    "perfil": perfil,
                    "tempo_total_s": round(dt_ajustado, 3),
                    "tempo_llm_s": round(llm_dur, 3),
                    "fallback": False,
                    "resposta": resp.resposta,
                    "citacoes": [f"{c.codigo} v{c.versao} §{c.secao}" for c in resp.citacoes],
                    "avisos": resp.avisos,
                })

                status_tag = "ABSTENÇÃO" if not consta_esp else "OK"
                print(f"[{i:02d}/{len(perguntas)}] {pid} -> {dt_ajustado:.2f}s | {status_tag}", flush=True)

            mediana_total = statistics.median(tempos_totais) if tempos_totais else 0.0
            p95_total = calcular_p95(tempos_totais)
            mediana_llm = statistics.median(tempos_llm) if tempos_llm else 0.0
            p95_llm = calcular_p95(tempos_llm)

            taxa_cit = (citacoes_validas_acervo / total_perguntas_com_citacao * 100) if total_perguntas_com_citacao else 100.0
            taxa_form = (citacoes_formato_estrito / total_perguntas_com_citacao * 100) if total_perguntas_com_citacao else 100.0
            taxa_abs = (abstencoes_corretas / total_abstencoes * 100) if total_abstencoes else 100.0
            media_pal = statistics.mean(palavras_totais) if palavras_totais else 0.0

            relatorio_geral[model_id] = {
                "modo": "simulado",
                "mediana_tempo_total_s": round(mediana_total, 3),
                "p95_tempo_total_s": round(p95_total, 3),
                "mediana_tempo_llm_s": round(mediana_llm, 3),
                "p95_tempo_llm_s": round(p95_llm, 3),
                "citacoes_validas_acervo_pct": round(taxa_cit, 1),
                "citacoes_formato_estrito_pct": round(taxa_form, 1),
                "abstencao_correta_pct": round(taxa_abs, 1),
                "quedas_fallback": 0,
                "erros_converse": [],
                "conformidade_rotulo_pct": round(rotulos_ok / total_perguntas_com_citacao * 100, 1) if total_perguntas_com_citacao else 100.0,
                "frases_longas_total": frases_longas,
                "media_palavras": round(media_pal, 1),
                "perguntas": detalhes,
            }

        _imprimir_tabela(relatorio_geral)

        if salvar_json:
            salvar_json.parent.mkdir(parents=True, exist_ok=True)
            with open(salvar_json, "w", encoding="utf-8") as f:
                json.dump(relatorio_geral, f, indent=2, ensure_ascii=False)
            print(f"\nResultados salvos em {salvar_json}")

        return relatorio_geral
    finally:
        p_client.stop()
        p_embed1.stop()
        p_embed2.stop()


def _imprimir_tabela(relatorio: Dict[str, Any]) -> None:
    """Imprime tabela comparativa formatada."""
    print("\n" + "=" * 92)
    print("TABELA COMPARATIVA DE MODELOS NO AMAZON BEDROCK (HACKA/TS 2026)")
    print("=" * 92)
    header = f"{'Métrica':<42} | " + " | ".join(f"{m:<22}" for m in relatorio.keys())
    print(header)
    print("-" * 92)

    linhas = [
        ("Modo de Execução", lambda r: r["modo"]),
        ("Tempo Total da Requisição (Mediana)", lambda r: f"{r['mediana_tempo_total_s']}s"),
        ("Tempo Total da Requisição (P95)", lambda r: f"{r['p95_tempo_total_s']}s"),
        ("Tempo do Modelo LLM (Mediana)", lambda r: f"{r['mediana_tempo_llm_s']}s"),
        ("Tempo do Modelo LLM (P95)", lambda r: f"{r['p95_tempo_llm_s']}s"),
        ("% Citação Válida no Acervo", lambda r: f"{r['citacoes_validas_acervo_pct']}%"),
        ("% Citação Formato Estrito (Fonte)", lambda r: f"{r['citacoes_formato_estrito_pct']}%"),
        ("% Abstenção Correta ('Não consta')", lambda r: f"{r['abstencao_correta_pct']}%"),
        ("Quedas para Fallback", lambda r: str(r["quedas_fallback"])),
        ("Erros no Converse API", lambda r: str(len(r["erros_converse"]))),
        ("Conformidade Rótulos de Perfil", lambda r: f"{r['conformidade_rotulo_pct']}%"),
        ("Média de Palavras por Resposta", lambda r: f"{r['media_palavras']} palavras"),
        ("Frases > 25 palavras", lambda r: str(r["frases_longas_total"])),
    ]

    for label, fn in linhas:
        colunas = [f"{fn(r):<22}" for r in relatorio.values()]
        print(f"{label:<42} | " + " | ".join(colunas))

    print("=" * 92)


def main():
    parser = argparse.ArgumentParser(
        description="Compara modelos Amazon Bedrock para o endpoint /api/perguntar"
    )
    parser.add_argument(
        "--modelos",
        nargs="+",
        default=["amazon.nova-pro-v1:0", "qwen.qwen3-32b-v1:0"],
        help="IDs dos modelos a comparar (padrão: amazon.nova-pro-v1:0 qwen.qwen3-32b-v1:0)",
    )
    parser.add_argument(
        "--arquivo",
        type=Path,
        default=Path("eval/perguntas.yaml"),
        help="Caminho do arquivo YAML com as perguntas do eval",
    )
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Força modo de avaliação simulada sem acesso à rede (para CI)",
    )
    parser.add_argument(
        "--salvar-json",
        type=Path,
        default=None,
        help="Caminho para salvar os resultados brutos em formato JSON",
    )

    args = parser.parse_args()

    # Detectar se está rodando em CI ou se faltam credenciais AWS
    eh_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
    modo_simulado = args.simulado or eh_ci or os.getenv("BEDROCK_SIMULADO") == "1"

    if not modo_simulado and not os.getenv("AWS_PROFILE") and not os.getenv("AWS_ACCESS_KEY_ID"):
        # Se não há perfil configurado no ambiente, usa hackats por padrão conforme Issue #6
        os.environ["AWS_PROFILE"] = "hackats"
        os.environ["AWS_REGION"] = "us-east-1"

    try:
        rodar_benchmark(
            modelos=args.modelos,
            arquivo_yaml=args.arquivo,
            simulado=modo_simulado,
            salvar_json=args.salvar_json,
        )
    except Exception as e:
        print(f"Erro ao executar benchmark: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
