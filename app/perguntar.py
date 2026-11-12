import re
import uuid
from typing import Dict, List, Tuple

from app.acervo import AcervoRepository
from app.models import Citacao, PerguntaRequest, PerguntaResponse
from app.recuperacao import BuscadorLexico, ResultadoBusca

PERFIL_MAP = {
    "empregado": "empregado",
    "p-emp": "empregado",
    "gestor": "gestor",
    "p-ges": "gestor",
    "diretoria": "diretoria",
    "p-dir": "diretoria",
    "financeiro": "financeiro",
    "p-fin": "financeiro",
    "gfi": "financeiro",
    "juridico": "juridico",
    "p-jur": "juridico",
    "gco": "juridico",
    "rh": "rh",
    "p-rh": "rh",
    "ggc": "rh",
}

# Modelos por perfil (docs/requisitos/PESQUISA-LEGAL-DESIGN-UX-WRITING.md):
# o perfil muda a ORDEM e a FORMA da resposta, nunca o conteúdo nem as fontes.
# Cada perfil define (rótulo de abertura, padrão que puxa um trecho para a frente,
# próxima ação). Os trechos são sempre os mesmos, extraídos das citações.
MODELOS_PERFIL: Dict[str, Tuple[str, str, str]] = {
    "empregado": (
        "O que fazer",
        r"solicit|pe[çc]a|pedi|registr|portal|preench|envi|assin",
        "Siga o passo indicado no documento citado e guarde o comprovante.",
    ),
    "gestor": (
        "Para decidir",
        r"decid|decis|aprov|autoriz|gestor|prazo",
        "Registre a decisão dentro do prazo indicado no documento citado.",
    ),
    "diretoria": (
        "Em resumo",
        r"R\$|valor|risco|aprova|diretor",
        "Confira na fonte citada quem aprova e quais riscos se aplicam.",
    ),
    "financeiro": (
        "Valores e datas",
        r"R\$|\d{1,2}/\d{1,2}/\d{4}|pag|multa|valor|\d+%",
        "Confira valores e datas de pagamento na fonte citada.",
    ),
    "juridico": (
        "Disposição normativa",
        r"cl[áa]usula|vig[êe]n|rescis|vedad|multa|obriga",
        "Leia o texto original da seção citada para avaliar a conformidade.",
    ),
    "rh": (
        "Regra vigente",
        r"anteced|regra|aviso|ggc|empregad",
        "Oriente a equipe com base na regra vigente e nos documentos vinculados.",
    ),
    "geral": (
        "",
        r"(?!)",
        "Consulte a norma completa para orientações complementares.",
    ),
}

# Quantos trechos citados entram no texto da resposta (os mesmos para todo perfil)
TRECHOS_NA_RESPOSTA = 2

RESPOSTA_ABSTENCAO = (
    "O acervo não trata disso. Não foram encontradas informações sobre este tema nas normas vigentes."
)


def _rotulo_secao(secao_id: str) -> str:
    return f"item {secao_id}" if re.match(r"^\d+(?:\.\d+)*$", secao_id) else secao_id


def _frase_citada(r: ResultadoBusca) -> str:
    trecho = r.trecho.rstrip(" ;,")
    if not trecho.endswith((".", "!", "?", "...")):
        trecho += "."
    return f"{trecho} (Fonte: {r.codigo} v{r.versao}, {_rotulo_secao(r.secao_id)}.)"


def montar_resposta(resultados: List[ResultadoBusca], avisos: List[str], perfil_key: str) -> Tuple[str, str]:
    """Resposta extrativa: os trechos citados, reordenados e rotulados conforme o perfil."""
    rotulo, padrao, proxima_acao = MODELOS_PERFIL.get(perfil_key, MODELOS_PERFIL["geral"])
    base: List[ResultadoBusca] = []
    for r in resultados:
        if len(base) >= TRECHOS_NA_RESPOSTA:
            break
        if all(r.trecho != b.trecho for b in base):
            base.append(r)
    prioridade = re.compile(padrao, re.IGNORECASE)
    # sort estável: trechos que casam com o foco do perfil vêm primeiro
    ordenados = sorted(base, key=lambda r: 0 if prioridade.search(r.trecho) else 1)

    partes = [_frase_citada(r) for r in ordenados]
    texto = " ".join(partes)
    if rotulo:
        texto = f"{rotulo}: {texto}"
    if avisos:
        texto += " Atenção: " + "; ".join(avisos) + "."
    return texto, proxima_acao


class PerguntarService:
    """Serviço de respostas a perguntas sobre o acervo normativo (C13, C15, RF02, RF03, RF05, RF32)."""

    def __init__(self, acervo: AcervoRepository):
        self.acervo = acervo
        self.buscador = BuscadorLexico(acervo)

    def responder(self, req: PerguntaRequest) -> PerguntaResponse:
        pergunta = req.pergunta.strip()
        perfil_key = PERFIL_MAP.get(req.perfil.lower().strip(), "geral") if req.perfil else "geral"

        consta, resultados, avisos = self.buscador.buscar(pergunta)
        resposta_id = f"resp_{uuid.uuid4().hex[:12]}"

        # Abstenção (consta = false, citacoes = [])
        if not consta or not resultados:
            return PerguntaResponse(
                resposta_id=resposta_id,
                resposta=RESPOSTA_ABSTENCAO,
                consta=False,
                citacoes=[],
                avisos=[],
                proxima_acao="Reformule sua pergunta ou consulte as perguntas sugeridas no painel.",
            )

        # C15: toda citação carrega camada; Adendo v0.1 A: secao = secoes[].id.
        # O conjunto de citações é idêntico para todos os perfis.
        citacoes = [
            Citacao(codigo=r.codigo, versao=r.versao, secao=r.secao_id, trecho=r.trecho, camada=r.camada)
            for r in resultados
        ]
        resposta_texto, proxima_acao = montar_resposta(resultados, avisos, perfil_key)

        return PerguntaResponse(
            resposta_id=resposta_id,
            resposta=resposta_texto,
            consta=True,
            citacoes=citacoes,
            avisos=avisos,
            proxima_acao=proxima_acao,
        )
