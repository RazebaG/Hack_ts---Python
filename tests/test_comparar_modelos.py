"""Testes para o script de benchmark comparativo de modelos (HACKA/TS 2026)."""

import os
from pathlib import Path
from scripts.comparar_modelos import rodar_benchmark, calcular_p95


def test_calcular_p95():
    """Valida o cálculo do percentil 95."""
    assert calcular_p95([]) == 0.0
    assert calcular_p95([1.0]) == 1.0
    valores = [float(i) for i in range(1, 101)]
    # p95 de 1 a 100 deve ser >= 95.0
    p95 = calcular_p95(valores)
    assert p95 >= 95.0


def test_rodar_benchmark_simulado(tmp_path):
    """Executa o benchmark em modo simulado sem chamadas de rede."""
    json_saida = tmp_path / "resultado.json"
    relatorio = rodar_benchmark(
        modelos=["amazon.nova-pro-v1:0", "qwen.qwen3-32b-v1:0"],
        arquivo_yaml=Path("eval/perguntas.yaml"),
        simulado=True,
        salvar_json=json_saida,
    )

    assert "amazon.nova-pro-v1:0" in relatorio
    assert "qwen.qwen3-32b-v1:0" in relatorio

    for m in ["amazon.nova-pro-v1:0", "qwen.qwen3-32b-v1:0"]:
        dados = relatorio[m]
        assert dados["modo"] == "simulado"
        assert dados["citacoes_validas_acervo_pct"] == 100.0
        assert dados["abstencao_correta_pct"] == 100.0
        assert dados["quedas_fallback"] == 0
        assert len(dados["perguntas"]) == 23

    assert json_saida.exists()
