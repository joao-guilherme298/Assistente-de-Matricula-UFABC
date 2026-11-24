from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from src.models import DisciplinaGrade, normalizar_texto

CODIGO_RE = re.compile(r"^([A-Z]{2,5}\d{3,4}-\d{2})\s+(.*)$")
CREDITO_PPC_RE = re.compile(r"\s+(\d+)\s+\(\d+-\d+-\d+-\d+\)\s+\d+h\s*$")
CREDITO_OL_RE = re.compile(r"\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)\s+\d+h\s*$")


def _limpar_hifenizacao(nome: str) -> str:
    # Junta quebras de linha com hífen como "Mo- derna" -> "Moderna", mantendo hífens legítimos como "Humano-Computador"
    nome = re.sub(r"([a-záéíóúâêôãõç])-\s+([a-záéíóúâêôãõç])", r"\1\2", nome)
    return " ".join(nome.split()).strip()


def _parse_tabela_ppc(texto: str, categoria: str) -> list[DisciplinaGrade]:
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    itens: list[DisciplinaGrade] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        m = CODIGO_RE.match(linha)
        if not m:
            i += 1
            continue

        codigo = m.group(1)
        resto = m.group(2)

        # Pode haver quebra de linha no nome da disciplina antes dos créditos "(T-P-E-I) XXh"
        bloco = resto
        while not CREDITO_PPC_RE.search(bloco) and i + 1 < len(linhas):
            prox = linhas[i + 1]
            if CODIGO_RE.match(prox) or prox.startswith("As ementas") or prox.isdigit():
                break
            i += 1
            bloco = f"{bloco} {prox}"

        creditos: Optional[int] = None
        m_cred = CREDITO_PPC_RE.search(bloco)
        if m_cred:
            creditos = int(m_cred.group(1))
            nome = bloco[: m_cred.start()]
        else:
            nome = bloco

        nome = _limpar_hifenizacao(nome)
        if nome:
            itens.append(
                DisciplinaGrade(
                    codigo=codigo,
                    nome=nome,
                    nome_norm=normalizar_texto(nome),
                    categoria=categoria,
                    creditos=creditos,
                )
            )
        i += 1
    return itens


def _parse_opcoes_limitadas(pdf_path: Path) -> list[DisciplinaGrade]:
    reader = PdfReader(str(pdf_path))
    itens: list[DisciplinaGrade] = []
    vistos: set[str] = set()

    for page in reader.pages:
        texto = page.extract_text() or ""
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        i = 0
        while i < len(linhas):
            linha = linhas[i]
            m = CODIGO_RE.match(linha)
            if not m:
                i += 1
                continue
            codigo = m.group(1)
            bloco = m.group(2)
            while not CREDITO_OL_RE.search(bloco) and i + 1 < len(linhas):
                prox = linhas[i + 1]
                if CODIGO_RE.match(prox) or prox.startswith("ANEXO") or prox.startswith("Boletim"):
                    break
                i += 1
                bloco = f"{bloco} {prox}"

            creditos: Optional[int] = None
            m_cred = CREDITO_OL_RE.search(bloco)
            if m_cred:
                creditos = int(m_cred.group(1))
                nome = bloco[: m_cred.start()]
            else:
                nome = bloco

            nome = _limpar_hifenizacao(nome)
            chave = codigo or normalizar_texto(nome)
            if nome and chave not in vistos:
                vistos.add(chave)
                itens.append(
                    DisciplinaGrade(
                        codigo=codigo,
                        nome=nome,
                        nome_norm=normalizar_texto(nome),
                        categoria="opcao_limitada",
                        creditos=creditos,
                    )
                )
            i += 1
    return itens


def parse_grade_bcc(
    ppc_pdf_path: Path,
    opcoes_limitadas_pdf_path: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    usar_cache: bool = True,
) -> list[DisciplinaGrade]:
    """Extrai a grade curricular do BCC 2023 (Obrigatórias BC&T, Obrigatórias BCC e Opções Limitadas)."""
    if usar_cache and cache_path and cache_path.exists():
        mtime_ref = ppc_pdf_path.stat().st_mtime
        if opcoes_limitadas_pdf_path and opcoes_limitadas_pdf_path.exists():
            mtime_ref = max(mtime_ref, opcoes_limitadas_pdf_path.stat().st_mtime)
        if cache_path.stat().st_mtime >= mtime_ref:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return [DisciplinaGrade(**item) for item in data]

    reader = PdfReader(str(ppc_pdf_path))
    itens: list[DisciplinaGrade] = []
    vistos: set[str] = set()

    for page in reader.pages:
        texto = page.extract_text() or ""
        upper = texto.upper()
        if "DISCIPLINAS OBRIGATÓRIAS DO BC&T" in upper or "OBRIGATÓRIAS DO BC&T" in upper:
            for d in _parse_tabela_ppc(texto, "obrigatoria_bct"):
                if d.codigo not in vistos:
                    vistos.add(d.codigo)
                    itens.append(d)
        if "DISCIPLINAS OBRIGATÓRIAS DO BCC" in upper or "OBRIGATÓRIAS DO BCC" in upper:
            for d in _parse_tabela_ppc(texto, "obrigatoria_bcc"):
                if d.codigo not in vistos:
                    vistos.add(d.codigo)
                    itens.append(d)

    if opcoes_limitadas_pdf_path and opcoes_limitadas_pdf_path.exists():
        for d in _parse_opcoes_limitadas(opcoes_limitadas_pdf_path):
            if d.codigo not in vistos:
                vistos.add(d.codigo)
                itens.append(d)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps([d.model_dump() for d in itens], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return itens
