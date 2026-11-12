"""Script de avaliação do motor de perguntas e respostas (/api/perguntar).

Execução:
    python -m eval.rodar

Critérios de aceite da Issue #2:
    - Avaliação >= 80% com citação correta
    - 100% de abstenção correta
    - Testes das cenas 1-3 do PRD
"""

import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml

from app.acervo import AcervoRepository
from app.models import PerguntaRequest
from app.perguntar import PerguntarService


def rodar_avaliacao(
    arquivo_yaml: Path = Path("eval/perguntas.yaml"),
    simulado: bool = False,
) -> bool:
    if not arquivo_yaml.exists():
        print(f"Erro: arquivo de avaliação não encontrado em {arquivo_yaml}", file=sys.stderr)
        return False

    with open(arquivo_yaml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    perguntas = data.get("perguntas", [])
    if not perguntas:
        print("Erro: nenhuma pergunta encontrada no dataset de avaliação.", file=sys.stderr)
        return False

    if simulado or os.getenv("BEDROCK_SIMULADO") == "1":
        os.environ["LLM_PROVIDER"] = "bedrock"
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
                return {
                    "output": {
                        "message": {
                            "content": [
                                {"text": f"{trecho.strip()} (Fonte: {cod} v{ver}, {sec.strip()}.)"}
                            ]
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
        patcher = patch("app.bedrock.get_bedrock_client", return_value=mock_client)
        patcher.start()
        patcher_embed = patch("app.bedrock.gerar_embeddings", return_value=None)
        patcher_embed.start()
        patcher_embed_recup = patch("app.recuperacao.gerar_embeddings", return_value=None)
        patcher_embed_recup.start()

    # Inicializar repositório e serviço
    acervo = AcervoRepository()
    servico = PerguntarService(acervo)

    total = len(perguntas)
    total_abstencoes_esperadas = sum(1 for p in perguntas if not p.get("consta", True))
    total_citacoes_esperadas = total - total_abstencoes_esperadas

    acertos_abstencao = 0
    acertos_citacao = 0
    acertos_resposta = 0
    acertos_aviso = 0
    total_avisos_esperados = sum(1 for p in perguntas if p.get("aviso_esperado"))

    print("=" * 80)
    print(f"EXECUÇÃO DO EVAL: {total} PERGUNTAS (HACKA/TS 2026 - ISSUE #2)")
    print("=" * 80)

    for i, item in enumerate(perguntas, 1):
        pid = item["id"]
        pergunta = item["pergunta"]
        perfil = item.get("perfil")
        consta_esperado = item.get("consta", True)
        codigo_esperado = item.get("codigo_esperado")
        resposta_curta = item.get("resposta_curta_esperada", "")
        aviso_esperado = item.get("aviso_esperado")

        req = PerguntaRequest(pergunta=pergunta, perfil=perfil)
        resp = servico.responder(req)

        status_ok = True
        detalhes = []

        if not consta_esperado:
            # Caso de abstenção
            if not resp.consta and len(resp.citacoes) == 0:
                acertos_abstencao += 1
                detalhes.append("Abstenção correta (consta=false, citacoes=[])")
            else:
                status_ok = False
                detalhes.append(f"FALHA: esperava abstenção, obteve consta={resp.consta}, citacoes={len(resp.citacoes)}")
        else:
            # Caso de pergunta que consta nas fontes
            if resp.consta:
                # Verificar citação
                codigos_obtidos = [c.codigo for c in resp.citacoes]
                if codigo_esperado in codigos_obtidos:
                    acertos_citacao += 1
                    detalhes.append(f"Citação correta: {codigo_esperado}")
                else:
                    status_ok = False
                    detalhes.append(f"FALHA CITAÇÃO: esperava {codigo_esperado}, obteve {codigos_obtidos}")

                # Verificar resposta curta
                if resposta_curta.lower() in resp.resposta.lower():
                    acertos_resposta += 1
                    detalhes.append(f"Conteúdo confirmado ('{resposta_curta}')")
                else:
                    detalhes.append(f"Aviso conteúdo: '{resposta_curta}' não destacada na resposta")

                # Verificar aviso quando esperado
                if aviso_esperado:
                    if any(aviso_esperado in av for av in resp.avisos):
                        acertos_aviso += 1
                        detalhes.append(f"Aviso confirmado ('{aviso_esperado}')")
                    else:
                        status_ok = False
                        detalhes.append(f"FALHA AVISO: esperava '{aviso_esperado}', obteve {resp.avisos}")
            else:
                status_ok = False
                detalhes.append("FALHA: absteve indevidamente (esperava resposta)")

        simbolo = "✓ PASS" if status_ok else "✗ FAIL"
        print(f"[{i:02d}/{total}] {simbolo} {pid}")
        print(f"     P: {pergunta}")
        print(f"     R: {resp.resposta[:90]}...")
        if resp.citacoes:
            cits_str = ", ".join(f"{c.codigo} v{c.versao} §{c.secao}" for c in resp.citacoes)
            print(f"     Fontes: {cits_str}")
        print(f"     Status: {'; '.join(detalhes)}")
        print("-" * 80)

    # Consolidação dos resultados
    taxa_abstencao = (acertos_abstencao / total_abstencoes_esperadas * 100) if total_abstencoes_esperadas > 0 else 100.0
    taxa_citacao = (acertos_citacao / total_citacoes_esperadas * 100) if total_citacoes_esperadas > 0 else 100.0

    print("\n" + "=" * 80)
    print("RESUMO CONSOLIDADO DO EVAL")
    print("=" * 80)
    print(f"Total de perguntas avaliadas: {total}")
    print(f"Acurácia de Abstenção:        {acertos_abstencao}/{total_abstencoes_esperadas} ({taxa_abstencao:.1f}%) [Meta: 100.0%]")
    print(f"Acurácia de Citação Correta:  {acertos_citacao}/{total_citacoes_esperadas} ({taxa_citacao:.1f}%) [Meta: >= 80.0%]")
    print(f"Acurácia de Conteúdo:         {acertos_resposta}/{total_citacoes_esperadas} ({acertos_resposta/total_citacoes_esperadas*100:.1f}%)")
    if total_avisos_esperados > 0:
        print(f"Avisos de Substituição:       {acertos_aviso}/{total_avisos_esperados} ({acertos_aviso/total_avisos_esperados*100:.1f}%)")
    print("-" * 80)

    aprovado = (taxa_abstencao == 100.0) and (taxa_citacao >= 80.0)
    if aprovado:
        print("VEREDITO: APROVADO NOS CRITÉRIOS DE ACEITE DA ISSUE #2")
        print("=" * 80)
        return True
    else:
        print("VEREDITO: REPROVADO NOS CRITÉRIOS DE ACEITE DA ISSUE #2", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Script de avaliação do motor /api/perguntar")
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Executa avaliação com Bedrock simulado (sem rede/CI)",
    )
    parser.add_argument(
        "--arquivo",
        type=Path,
        default=Path("eval/perguntas.yaml"),
        help="Caminho do arquivo YAML com dataset de perguntas",
    )
    args = parser.parse_args()

    sucesso = rodar_avaliacao(arquivo_yaml=args.arquivo, simulado=args.simulado)
    sys.exit(0 if sucesso else 1)
