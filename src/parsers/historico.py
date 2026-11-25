from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pdfplumber

from src.models import HistoricoItem, HistoricoSanitizado, normalizar_texto

# Código padrão UFABC (ex: MCCC001-23, BIS0003-15, MCTA028-15, BCN0402-15)
CODIGO_UFABC_RE = re.compile(r"\b([A-Z]{2,5}\d{3,4}-\d{2})\b")

# Verificação defensiva para garantir que nenhum CPF/RG escape na saída sanitizada
CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")

# Siglas oficiais de situação do histórico SIGAA / UFABC
SITUACAO_APROVADO = {"APR", "APRN", "CUMP", "APROVADO", "APROVADA", "CUMPRIU"}
SITUACAO_EQUIVALENCIA = {"DISP", "TRANS", "INCORP", "DISPENSADO", "TRANSFERIDO", "INCORPORADO"}
SITUACAO_EM_CURSO = {"MATR", "REC", "MATRICULADO", "EM CURSO", "CURSANDO"}
SITUACAO_REPROVADO = {
    "REP",
    "REPF",
    "REPMF",
    "REPN",
    "REPNF",
    "TRANC",
    "CANC",
    "REPROVADO",
    "TRANCADO",
    "CANCELADO",
}

CONCEITOS_APROVADO = {"A", "B", "C", "D", "E"}
PRIORIDADE_STATUS = {"aprovado": 4, "equivalencia": 3, "em_curso": 2, "reprovado": 1}


def _classificar_situacao_sigla(situacao_raw: str, conceito: str = "") -> Optional[str]:
    """Mapeia a sigla oficial da coluna Situação do SIGAA UFABC para o status interno."""
    sigla = re.sub(r"[^A-Z]", "", (situacao_raw or "").upper())
    if sigla in SITUACAO_APROVADO:
        return "aprovado"
    if sigla in SITUACAO_EQUIVALENCIA:
        return "equivalencia"
    if sigla in SITUACAO_EM_CURSO:
        return "em_curso"
    if sigla in SITUACAO_REPROVADO:
        return "reprovado"

    # Fallback pelo conceito se a situação estiver vazia ou não reconhecida
    c = (conceito or "").strip().upper()
    if c in CONCEITOS_APROVADO:
        return "aprovado"
    if c in ("F", "O"):
        return "reprovado"
    return None


def _classificar_status_texto(linha_upper: str, conceito: str) -> str:
    tokens = set(re.findall(r"\b[A-Z]+\b", linha_upper))
    if tokens & SITUACAO_EM_CURSO or "EM CURSO" in linha_upper or "CURSANDO" in linha_upper:
        return "em_curso"
    if tokens & SITUACAO_EQUIVALENCIA or "EQUIVAL" in linha_upper:
        return "equivalencia"
    if tokens & SITUACAO_REPROVADO or conceito in ("F", "O"):
        return "reprovado"
    if tokens & SITUACAO_APROVADO or conceito in CONCEITOS_APROVADO:
        return "aprovado"
    if "--" in linha_upper:
        return "em_curso"
    return "aprovado"


def _extrair_conceito(texto: str) -> str:
    tokens = re.findall(r"\b([A-FO])\b", (texto or "").upper())
    for tok in reversed(tokens):
        if tok in {"A", "B", "C", "D", "E", "F", "O"}:
            return tok
    return ""


def _limpar_codigo_celula(celula: Optional[str]) -> str:
    """Remove quebras de linha/espaços dentro do código (ex: 'BCL030\\n6-15' -> 'BCL0306-15')."""
    if not celula:
        return ""
    return re.sub(r"\s+", "", celula).strip().upper()


def _limpar_nome_celula(celula: Optional[str]) -> str:
    if not celula:
        return ""
    nome = " ".join(celula.split()).strip()
    if CPF_RE.search(nome):
        return ""
    return nome


def _adicionar_item(
    itens_por_chave: dict[str, HistoricoItem],
    item: HistoricoItem,
) -> None:
    chave = item.codigo or item.nome_norm
    if not chave:
        return
    anterior = itens_por_chave.get(chave)
    if not anterior or PRIORIDADE_STATUS[item.status] >= PRIORIDADE_STATUS[anterior.status]:
        itens_por_chave[chave] = item


def _parse_tabelas_sigaa(
    pdf: pdfplumber.PDF,
    catalogo_nomes_por_codigo: Optional[dict[str, str]] = None,
) -> dict[str, HistoricoItem]:
    """Lê diretamente as tabelas do histórico oficial do SIGAA UFABC.

    Estrutura típica da tabela 'Componentes Curriculares Cursados/Cursando':
    [Ano/Período, Categoria(OBR/OL/LIV/ATC), Código, Nome, Cred, CH, CH EXT, Turma, Conceito, Situação, Docente(s)]
    """
    itens_por_chave: dict[str, HistoricoItem] = {}

    for page in pdf.pages:
        tables = page.extract_tables() or []
        for table in tables:
            for row in table:
                if not row or len(row) < 6:
                    continue

                cells = [c if c is not None else "" for c in row]
                row_joined_upper = " ".join(" ".join(c.split()) for c in cells).upper()

                # Pular cabeçalhos de tabela
                if "COMPONENTE CURRICULAR" in row_joined_upper or "ANO/PERÍODO" in row_joined_upper:
                    continue

                # Detectar colunas dinamicamente para suportar pequenas variações entre 9 e 11 colunas
                # Na tabela SIGAA UFABC (11 colunas):
                # 0: Ano/Período | 1: Cat | 2: Código | 3: Nome | 4: Cred | 5: CH | 6: CH EXT | 7: Turma | 8: Conceito | 9: Situação | 10: Docente
                codigo = ""
                nome = ""
                conceito = ""
                situacao_raw = ""

                # Localizar a célula de Situação pela sigla oficial (geralmente penúltima coluna, índice -2)
                idx_sit = -1
                for i in range(len(cells) - 1, -1, -1):
                    cand_sigla = re.sub(r"[^A-Z]", "", cells[i].upper())
                    if cand_sigla in (
                        SITUACAO_APROVADO | SITUACAO_EQUIVALENCIA | SITUACAO_EM_CURSO | SITUACAO_REPROVADO
                    ):
                        idx_sit = i
                        situacao_raw = cells[i]
                        break

                if idx_sit == -1:
                    # Linha não representa uma disciplina com situação válida (ex: ENADE com '--')
                    continue

                # Conceito fica logo à esquerda de Situação
                if idx_sit - 1 >= 0:
                    c_cand = " ".join(cells[idx_sit - 1].split()).upper()
                    if c_cand in {"A", "B", "C", "D", "E", "F", "O"}:
                        conceito = c_cand

                # Encontrar código (geralmente col 2, ou primeira célula entre 0..3 que bate padrão UFABC ou alfanumérico curto)
                idx_cod = -1
                for i in range(min(4, len(cells))):
                    c_limpo = _limpar_codigo_celula(cells[i])
                    if not c_limpo or c_limpo in ("OBR", "OL", "LIV", "ATC", "ENADE", "--"):
                        continue
                    if re.match(r"^20\d{2}\.[123]$", c_limpo):
                        continue
                    if CODIGO_UFABC_RE.fullmatch(c_limpo):
                        idx_cod = i
                        codigo = c_limpo
                        break

                # Fallback para códigos de transferência (ex: IFSP-ELES3, IFSPOMETS1) na coluna 2
                if idx_cod == -1 and len(cells) >= 4:
                    c2 = _limpar_codigo_celula(cells[2])
                    if c2 and c2 != "ENADE" and not re.match(r"^20\d{2}\.[123]$", c2):
                        idx_cod = 2
                        codigo = c2

                # Nome da disciplina fica logo após o código (geralmente col 3)
                if idx_cod != -1 and idx_cod + 1 < len(cells):
                    nome = _limpar_nome_celula(cells[idx_cod + 1])
                elif len(cells) >= 4:
                    nome = _limpar_nome_celula(cells[3])

                if codigo == "ENADE" or "ENADE" in nome.upper():
                    continue

                if (not nome or len(nome) < 3) and catalogo_nomes_por_codigo and codigo in catalogo_nomes_por_codigo:
                    nome = catalogo_nomes_por_codigo[codigo]

                status = _classificar_situacao_sigla(situacao_raw, conceito)
                if not status or (not codigo and not nome):
                    continue

                # Categoria (col 1: OBR, OL, LIV, ATC)
                categoria_hist = ""
                if len(cells) > 1:
                    cat_cand = re.sub(r"[^A-Z]", "", cells[1].upper())
                    if cat_cand in ("OBR", "OL", "LIV", "ATC"):
                        categoria_hist = cat_cand

                # Créditos (col 4) e CH EXT (col 6)
                creditos = 0
                ch_ext = 0
                if idx_cod != -1 and idx_cod + 2 < len(cells):
                    c_str = re.sub(r"\D", "", cells[idx_cod + 2])
                    if c_str:
                        creditos = int(c_str)
                if idx_cod != -1 and idx_cod + 4 < len(cells):
                    ext_str = re.sub(r"\D", "", cells[idx_cod + 4])
                    if ext_str:
                        ch_ext = int(ext_str)

                item = HistoricoItem(
                    codigo=codigo,
                    nome=nome or codigo,
                    nome_norm=normalizar_texto(nome or codigo),
                    status=status,
                    conceito=conceito,
                    categoria_hist=categoria_hist,
                    creditos=creditos,
                    ch_ext=ch_ext,
                )
                _adicionar_item(itens_por_chave, item)

    return itens_por_chave


def _limpar_nome_disciplina_texto(bruto: str) -> str:
    s = re.sub(r"\b20\d{2}\s*[./-]\s*[123]\b.*$", "", bruto)
    s = re.sub(
        r"\b(APROVAD[OA]?|REPROVAD[OA]?|MATRICULAD[OA]?|TRANCAD[OA]?|DISPENSAD[OA]?|EQUIVAL[EÊ]NCIA|EM CURSO|CURSANDO|APRN?|REPM?F?|REPNF?|MATR|DISP|TRANS|INCORP|CUMP|TRANC|CANC|REC|OBR|OL|LIV|ATC)\b.*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s+\d{1,3}h?\s*$", "", s)
    s = re.sub(r"\s+\d{1,2}\s+\d{1,3}\s*$", "", s)
    s = re.sub(r"\s+[A-FO]\s*$", "", s)
    s = re.sub(r"\s+--\s*$", "", s)
    return " ".join(s.split()).strip(" -–|:\t")


def sanitizar_texto_historico(
    texto: str,
    catalogo_nomes_por_codigo: Optional[dict[str, str]] = None,
) -> HistoricoSanitizado:
    """Extrai APENAS disciplinas e status de texto colado do histórico, descartando todo PII."""
    # Rejuntar códigos UFABC quebrados por quebra de linha (ex: "BCL030\n6-15" -> "BCL0306-15")
    texto_norm = re.sub(r"([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})", r"\1\2", texto)

    itens_por_chave: dict[str, HistoricoItem] = {}
    linhas = texto_norm.splitlines()

    for idx, linha in enumerate(linhas):
        linha_limpa = " ".join(linha.split())
        if not linha_limpa:
            continue

        m_cod = CODIGO_UFABC_RE.search(linha_limpa)
        if not m_cod:
            continue

        codigo = m_cod.group(1)
        pos_codigo = linha_limpa[m_cod.end() :].strip()

        contexto = pos_codigo
        if idx + 1 < len(linhas):
            prox = " ".join(linhas[idx + 1].split())
            if prox and not CODIGO_UFABC_RE.search(prox) and len(prox) < 120:
                tokens_cur = set(re.findall(r"\b[A-Z]+\b", contexto.upper()))
                if not (
                    tokens_cur
                    & (SITUACAO_APROVADO | SITUACAO_EQUIVALENCIA | SITUACAO_EM_CURSO | SITUACAO_REPROVADO)
                ):
                    contexto = f"{contexto} {prox}".strip()

        conceito = _extrair_conceito(contexto)
        status = _classificar_status_texto(contexto.upper(), conceito)
        nome = _limpar_nome_disciplina_texto(pos_codigo)

        if (not nome or len(nome) < 3) and catalogo_nomes_por_codigo and codigo in catalogo_nomes_por_codigo:
            nome = catalogo_nomes_por_codigo[codigo]
        if not nome or CPF_RE.search(nome):
            nome = codigo

        item = HistoricoItem(
            codigo=codigo,
            nome=nome,
            nome_norm=normalizar_texto(nome),
            status=status,
            conceito=conceito,
        )
        _adicionar_item(itens_por_chave, item)

    lista = sorted(itens_por_chave.values(), key=lambda x: x.nome_norm)
    return HistoricoSanitizado(
        gerado_em=datetime.now(timezone.utc).isoformat(),
        total_disciplinas=len(lista),
        disciplinas=lista,
    )


def sanitizar_pdf_historico_bytes(
    pdf_bytes: bytes,
    catalogo_nomes_por_codigo: Optional[dict[str, str]] = None,
) -> HistoricoSanitizado:
    """Processa o PDF do histórico 100% em memória via tabelas (pdfplumber) e descarta todo PII."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        itens_por_chave = _parse_tabelas_sigaa(pdf, catalogo_nomes_por_codigo)

        # Fallback para texto puro apenas se o PDF não tiver tabelas reconhecíveis
        if not itens_por_chave:
            texto_completo = "\n".join((p.extract_text() or "") for p in pdf.pages)
            return sanitizar_texto_historico(texto_completo, catalogo_nomes_por_codigo)

    lista = sorted(itens_por_chave.values(), key=lambda x: x.nome_norm)
    return HistoricoSanitizado(
        gerado_em=datetime.now(timezone.utc).isoformat(),
        total_disciplinas=len(lista),
        disciplinas=lista,
    )


def sanitizar_pdf_historico_arquivo(
    pdf_path: Path,
    destino_json: Optional[Path] = None,
    catalogo_nomes_por_codigo: Optional[dict[str, str]] = None,
) -> HistoricoSanitizado:
    """Lê um PDF local do histórico, extrai só as matérias e opcionalmente salva o JSON anônimo."""
    pdf_bytes = pdf_path.read_bytes()
    sanitizado = sanitizar_pdf_historico_bytes(pdf_bytes, catalogo_nomes_por_codigo)
    if destino_json:
        destino_json.parent.mkdir(parents=True, exist_ok=True)
        destino_json.write_text(
            json.dumps(sanitizado.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return sanitizado


def carregar_historico_sanitizado(json_path: Path) -> Optional[HistoricoSanitizado]:
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return HistoricoSanitizado(**data)
