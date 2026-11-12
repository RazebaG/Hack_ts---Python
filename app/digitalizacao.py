"""Digitalização de fotos e scans (RF24, RF25 · issue #10).

Motor principal: Amazon Bedrock Nova Pro com imagem (API Converse). Reserva:
Tesseract (pytesseract), se o binário estiver instalado. As credenciais vêm sempre
do ambiente (AWS_PROFILE / AWS_REGION / variáveis padrão do boto3), nunca do código.

Uma foto é lida por vez (RNF18: RAM limitada), garantido por um lock global.
Linhas que o motor marca como incertas voltam com `incerta=True` para a revisão
humana (T13): nada é publicado sem essa revisão.
"""

import io
import os
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

MARCA_INCERTA = "[?]"
LIMIAR_CONFIANCA_TESSERACT = 60.0

PROMPT_TRANSCRICAO = (
    "Transcreva fielmente o texto desta página de documento normativo, em português, "
    "linha por linha, mantendo a ordem, os números de seção e o cabeçalho "
    "(Documento:, Título:, Sigla e Número:, Versão:, Fase:, Vigência:, Vinculado a:, Referência:). "
    f"Comece com '{MARCA_INCERTA} ' cada linha que você não conseguiu ler com segurança. "
    "Não resuma, não traduza, não acrescente comentários. Responda só com o texto transcrito."
)

_lock_leitura = threading.Lock()


class LeituraFalhou(Exception):
    """Nenhum motor conseguiu ler a imagem."""


@dataclass
class LinhaLida:
    texto: str
    incerta: bool = False


@dataclass
class ResultadoLeitura:
    texto: str
    linhas: List[LinhaLida] = field(default_factory=list)
    motor: str = ""


def _linhas_de_texto_marcado(texto: str) -> List[LinhaLida]:
    linhas = []
    for bruta in texto.splitlines():
        s = bruta.rstrip()
        if s.lstrip().startswith(MARCA_INCERTA):
            linhas.append(LinhaLida(texto=s.lstrip()[len(MARCA_INCERTA):].strip(), incerta=True))
        else:
            linhas.append(LinhaLida(texto=s, incerta=False))
    return linhas


def _formato_bedrock(formato: str) -> str:
    formato = formato.lower().lstrip(".")
    return "jpeg" if formato in ("jpg", "jpeg") else formato


def bedrock_configurado() -> bool:
    if os.getenv("DIGITALIZACAO_BEDROCK", "1") == "0":
        return False
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("AWS_PROFILE") or os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_REGION"))


def ler_com_bedrock(conteudo: bytes, formato: str, cliente=None) -> ResultadoLeitura:
    """Lê a imagem com o Nova Pro via Converse. `cliente` permite injetar um stub nos testes."""
    if cliente is None:
        import boto3

        sessao = boto3.Session(
            profile_name=os.getenv("AWS_PROFILE") or None,
            region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1",
        )
        cliente = sessao.client("bedrock-runtime")
    modelo = os.getenv("BEDROCK_MODEL_OCR", "amazon.nova-pro-v1:0")
    resposta = cliente.converse(
        modelId=modelo,
        messages=[
            {
                "role": "user",
                "content": [
                    {"image": {"format": _formato_bedrock(formato), "source": {"bytes": conteudo}}},
                    {"text": PROMPT_TRANSCRICAO},
                ],
            }
        ],
        inferenceConfig={"maxTokens": 4096, "temperature": 0},
    )
    partes = resposta.get("output", {}).get("message", {}).get("content", [])
    texto_marcado = "\n".join(p.get("text", "") for p in partes if "text" in p).strip()
    if not texto_marcado:
        raise LeituraFalhou("Bedrock não devolveu texto.")
    linhas = _linhas_de_texto_marcado(texto_marcado)
    return ResultadoLeitura(texto="\n".join(l.texto for l in linhas), linhas=linhas, motor=f"bedrock:{modelo}")


def tesseract_disponivel() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def ler_com_tesseract(conteudo: bytes, formato: str) -> ResultadoLeitura:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(conteudo)) as img:
        dados = pytesseract.image_to_data(
            img, lang=os.getenv("TESSERACT_LANG", "por"), output_type=pytesseract.Output.DICT
        )
    # Agrupa palavras por linha; linha incerta se alguma palavra ficou abaixo do limiar.
    agrupado = {}
    for i, palavra in enumerate(dados["text"]):
        if not palavra.strip():
            continue
        chave = (dados["block_num"][i], dados["par_num"][i], dados["line_num"][i])
        conf = float(dados["conf"][i])
        item = agrupado.setdefault(chave, {"palavras": [], "min_conf": 100.0})
        item["palavras"].append(palavra)
        item["min_conf"] = min(item["min_conf"], conf)
    linhas = [
        LinhaLida(texto=" ".join(v["palavras"]), incerta=v["min_conf"] < LIMIAR_CONFIANCA_TESSERACT)
        for _, v in sorted(agrupado.items())
    ]
    if not linhas:
        raise LeituraFalhou("Tesseract não encontrou texto.")
    return ResultadoLeitura(texto="\n".join(l.texto for l in linhas), linhas=linhas, motor="tesseract")


# Pode ser substituído nos testes (Bedrock simulado), sem rede.
LeitorImagem = Callable[[bytes, str], ResultadoLeitura]
leitor_customizado: Optional[LeitorImagem] = None


def ler_imagem(conteudo: bytes, formato: str) -> ResultadoLeitura:
    """Lê uma foto/scan (uma por vez). Tenta Bedrock e depois Tesseract."""
    with _lock_leitura:
        if leitor_customizado is not None:
            return leitor_customizado(conteudo, formato)

        falhas = []
        if bedrock_configurado():
            try:
                return ler_com_bedrock(conteudo, formato)
            except Exception as exc:  # rede, credencial, modelo indisponível
                falhas.append(f"bedrock: {exc.__class__.__name__}")
        if tesseract_disponivel():
            try:
                return ler_com_tesseract(conteudo, formato)
            except Exception as exc:
                falhas.append(f"tesseract: {exc.__class__.__name__}")
        if not falhas:
            falhas.append("nenhum motor de leitura configurado (Bedrock ou Tesseract)")
        raise LeituraFalhou("; ".join(falhas))
