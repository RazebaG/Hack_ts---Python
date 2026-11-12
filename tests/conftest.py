import os
import tempfile
from pathlib import Path

# Os testes nunca escrevem (nem apagam) o data/avaliacoes.jsonl real:
# o repositório de avaliações é criado na importação de app.main e lê esta variável.
os.environ.setdefault(
    "AVALIACOES_FILE",
    str(Path(tempfile.mkdtemp(prefix="avaliacoes-teste-")) / "avaliacoes.jsonl"),
)

# Os testes nunca chamam o Bedrock de verdade, mesmo com um .env local de bedrock.
os.environ["LLM_PROVIDER"] = "nenhum"
