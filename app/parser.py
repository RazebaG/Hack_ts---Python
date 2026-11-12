import re
from pathlib import Path
from typing import List, Tuple, Optional
from app.models import Secao, DocumentoDetalhe
from app.taxonomia import derivar_camada, derivar_tema

KNOWN_HEADER_KEYS = (
    "Documento:",
    "Título:",
    "Sigla e Número:",
    "Versão:",
    "Elaborado por:",
    "Aprovado por:",
    "Referência:",
    "Fase:",
    "Vigência:",
    "Aprovado em:",
    "Assinada em:",
    "Vinculado a:",
)

SECTION_HEADING_RE = re.compile(
    r"^(?:"
    r"(CLÁUSULA\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+)*)\s*—\s*(.*)|"
    r"(Anexo\s+[A-Z0-9]+|Apêndice\s+[A-Z0-9]+)\s*—\s*(.*)|"
    r"(Bloco\s+[A-Z0-9]+)\s*—\s*(.*)|"
    r"(Tabela\s+[0-9]+)\s*—\s*(.*)|"
    r"(\d+(?:\.\d+)*\.)\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇa-z0-9].*)"
    r")$"
)


def is_key_line(line: str) -> bool:
    return any(line.startswith(k) for k in KNOWN_HEADER_KEYS)


def parse_header(header_text: str, file_path: Path) -> dict:
    raw_lines = [line.strip() for line in header_text.splitlines() if line.strip()]

    # Derivar assunto a partir da estrutura de diretórios
    # Ex: .../data/acervo/ferias/NG_... -> ferias
    # Ex: .../data/acervo/ferias/substituidos/NG_... -> ferias
    parts = file_path.resolve().parts
    assunto = "geral"
    if "acervo" in parts:
        acervo_idx = parts.index("acervo")
        if acervo_idx + 1 < len(parts):
            assunto = parts[acervo_idx + 1]

    doc_data = {
        "tipo_nome": "Norma Geral",
        "titulo": "",
        "codigo": "",
        "versao": "1.0.0",
        "fase": "Vigente",
        "vigencia": None,
        "aprovado_em": None,
        "assinada_em": None,
        "vinculado_a": None,
        "referencia": None,
        "elaborado_por": None,
        "aprovado_por": None,
        "assunto": assunto,
        "substituido": False,
    }

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        if line.startswith("Documento:"):
            doc_data["tipo_nome"] = line.split("Documento:", 1)[1].strip()
        elif line.startswith("Título:"):
            doc_data["titulo"] = line.split("Título:", 1)[1].strip()
        elif line.startswith("Sigla e Número:"):
            doc_data["codigo"] = line.split("Sigla e Número:", 1)[1].strip()
        elif line.startswith("Versão:"):
            doc_data["versao"] = line.split("Versão:", 1)[1].strip()
        elif line.startswith("Fase:"):
            doc_data["fase"] = line.split("Fase:", 1)[1].strip()
            if doc_data["fase"].lower() in ("versão anterior", "substituído", "substituido"):
                doc_data["substituido"] = True
        elif line.startswith("Vigência:"):
            doc_data["vigencia"] = line.split("Vigência:", 1)[1].strip()
        elif line.startswith("Aprovado em:"):
            doc_data["aprovado_em"] = line.split("Aprovado em:", 1)[1].strip()
        elif line.startswith("Assinada em:"):
            doc_data["assinada_em"] = line.split("Assinada em:", 1)[1].strip()
        elif line.startswith("Vinculado a:"):
            doc_data["vinculado_a"] = line.split("Vinculado a:", 1)[1].strip()
        elif line.startswith("Referência:"):
            doc_data["referencia"] = line.split("Referência:", 1)[1].strip()
        elif line.startswith("Elaborado por:"):
            el_val = line.split("Elaborado por:", 1)[1].strip()
            # Detectar colunas alternadas da extração de PDF
            if i + 1 < len(raw_lines) and raw_lines[i + 1].startswith("Aprovado por:"):
                ap_val = raw_lines[i + 1].split("Aprovado por:", 1)[1].strip()
                if (
                    i + 3 < len(raw_lines)
                    and not is_key_line(raw_lines[i + 2])
                    and not is_key_line(raw_lines[i + 3])
                ):
                    el_cont = raw_lines[i + 2]
                    ap_cont = raw_lines[i + 3]
                    doc_data["elaborado_por"] = f"{el_val} {el_cont}".strip()
                    doc_data["aprovado_por"] = f"{ap_val} {ap_cont}".strip()
                    i += 3
                else:
                    doc_data["elaborado_por"] = el_val
                    doc_data["aprovado_por"] = ap_val
                    i += 1
            elif i + 1 < len(raw_lines) and raw_lines[i + 1].startswith("Referência:"):
                doc_data["referencia"] = raw_lines[i + 1].split("Referência:", 1)[1].strip()
                if i + 2 < len(raw_lines) and not is_key_line(raw_lines[i + 2]):
                    el_cont = raw_lines[i + 2]
                    doc_data["elaborado_por"] = f"{el_val} {el_cont}".strip()
                    i += 2
                else:
                    doc_data["elaborado_por"] = el_val
                    i += 1
            else:
                doc_data["elaborado_por"] = el_val
        elif line.startswith("Aprovado por:"):
            doc_data["aprovado_por"] = line.split("Aprovado por:", 1)[1].strip()
        i += 1

    # Derivar tipo a partir da sigla no código
    codigo = doc_data["codigo"]
    doc_data["tipo"] = codigo.split("_")[0] if "_" in codigo else doc_data["tipo_nome"][:2].upper()

    # Vigência unificada caso vigência explícita não conste
    if not doc_data["vigencia"]:
        doc_data["vigencia"] = doc_data["aprovado_em"] or doc_data["assinada_em"] or ""

    return doc_data


def parse_sections(body_text: str, default_title: str) -> List[Secao]:
    sections: List[Secao] = []
    curr_id: Optional[str] = None
    curr_title: Optional[str] = None
    curr_text_lines: List[str] = []

    for line in body_text.splitlines():
        line_s = line.strip()
        m = SECTION_HEADING_RE.match(line_s)
        if m:
            if curr_id is not None:
                sections.append(
                    Secao(
                        id=curr_id,
                        titulo=curr_title or "",
                        texto="\n".join(curr_text_lines).strip(),
                    )
                )
            curr_text_lines = []

            if m.group(1):  # CLÁUSULA ...
                curr_id = m.group(1).strip().title()
                after = m.group(2).strip()
                if ". " in after:
                    tit, rest = after.split(". ", 1)
                    curr_title = tit.strip()
                    curr_text_lines.append(rest.strip())
                else:
                    curr_title = after.rstrip(".")
            elif m.group(3):  # Anexo / Apêndice ...
                curr_id = m.group(3).strip()
                curr_title = m.group(4).strip()
            elif m.group(5):  # Bloco ...
                curr_id = m.group(5).strip()
                curr_title = m.group(6).strip()
            elif m.group(7):  # Tabela ...
                curr_id = m.group(7).strip()
                curr_title = m.group(8).strip()
            elif m.group(9):  # 1. / 2.1. / 8.3.2.
                # Remove o ponto final do ID para conformidade com o contrato (ex: "2.1")
                curr_id = m.group(9).strip().rstrip(".")
                after = m.group(10).strip()
                curr_title = after.rstrip(".")
                # Em itens numerados a primeira linha já é conteúdo normativo
                # (ex.: "4.3.1. A solicitação é formal ... com antecedência"); sem isto
                # o texto da seção perderia a primeira linha.
                curr_text_lines.append(after)
        else:
            if curr_id is not None:
                curr_text_lines.append(line)

    if curr_id is not None:
        sections.append(
            Secao(
                id=curr_id,
                titulo=curr_title or "",
                texto="\n".join(curr_text_lines).strip(),
            )
        )

    # Se nenhuma seção estruturada foi encontrada, cria uma seção com o corpo do documento
    if not sections:
        clean_body = body_text.strip()
        # Remove eventuais cabeçalhos sintéticos repetidos
        clean_body = re.sub(
            r"^\.?\s*A\s+ACME\s+Tecnologia.*?\n\n?", "", clean_body, flags=re.DOTALL
        ).strip()
        sections.append(
            Secao(
                id="1",
                titulo=default_title or "Conteúdo Geral",
                texto=clean_body,
            )
        )

    return sections


def parse_document_file(file_path: Path) -> DocumentoDetalhe:
    text = file_path.read_text(encoding="utf-8")
    parts = text.split("DOCUMENTO SINTÉTICO")
    header_part = parts[0]
    body_part = parts[1] if len(parts) > 1 else ""

    header_data = parse_header(header_part, file_path)
    secoes = parse_sections(body_part, header_data["titulo"])

    camada = derivar_camada(
        codigo=header_data["codigo"],
        tipo_nome=header_data["tipo_nome"],
        vinculado_a=header_data["vinculado_a"],
    )
    tema = derivar_tema(
        codigo=header_data["codigo"],
        assunto=header_data["assunto"],
        vinculado_a=header_data["vinculado_a"],
        referencia=header_data["referencia"],
    )

    return DocumentoDetalhe(
        codigo=header_data["codigo"],
        titulo=header_data["titulo"],
        tipo=header_data["tipo"],
        tipo_nome=header_data["tipo_nome"],
        versao=header_data["versao"],
        fase=header_data["fase"],
        vigencia=header_data["vigencia"],
        vinculado_a=header_data["vinculado_a"],
        referencia=header_data["referencia"],
        assunto=header_data["assunto"],
        substituido=header_data["substituido"],
        elaborado_por=header_data["elaborado_por"],
        aprovado_por=header_data["aprovado_por"],
        camada=camada,
        tema=tema,
        secoes=secoes,
    )
