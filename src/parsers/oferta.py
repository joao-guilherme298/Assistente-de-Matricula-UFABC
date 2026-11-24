from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from src.models import Horario, Turma, normalizar_texto

DIA_MAP = {
    "segunda": "segunda",
    "terca": "terca",
    "terça": "terca",
    "quarta": "quarta",
    "quinta": "quinta",
    "sexta": "sexta",
    "sabado": "sabado",
    "sábado": "sabado",
}

HORARIO_RE = re.compile(
    r"(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado)"
    r"(?:-feira)?\s+das\s+(\d{1,2}:\d{2})\s+[aà]s\s+(\d{1,2}:\d{2})"
    r"(?:,\s*(semanal|quinzenal\s*(?:I{1,2}|1|2)))?",
    re.IGNORECASE,
)

# Ex: DA1ESTB019-17SA -> codigo disciplina ESTB019-17
CODIGO_DISC_RE = re.compile(r"([A-Z]{2,5}\d{3,4}-\d{2})")


def _normalizar_hora(h: str) -> str:
    partes = h.strip().split(":")
    return f"{int(partes[0]):02d}:{int(partes[1]):02d}"


def parse_horarios(texto: str, tipo: str) -> list[Horario]:
    if not texto:
        return []
    limpo = " ".join(texto.split())
    horarios: list[Horario] = []
    for m in HORARIO_RE.finditer(limpo):
        dia_raw = m.group(1).lower()
        dia = DIA_MAP.get(dia_raw)
        if not dia:
            continue
        inicio = _normalizar_hora(m.group(2))
        fim = _normalizar_hora(m.group(3))
        sem_raw = (m.group(4) or "semanal").lower().strip()
        if "quinzenal" in sem_raw:
            if sem_raw.endswith("ii") or sem_raw.endswith("2"):
                semanalidade = "quinzenal_2"
            else:
                semanalidade = "quinzenal_1"
        else:
            semanalidade = "semanal"
        horarios.append(
            Horario(
                dia=dia,
                inicio=inicio,
                fim=fim,
                tipo=tipo,
                semanalidade=semanalidade,
                raw=m.group(0),
            )
        )
    return horarios


def _extrair_nome_e_turma(turma_col: str) -> tuple[str, str]:
    """De 'BIOESTATÍSTICA A1-Matutino (SA)' extrai ('BIOESTATÍSTICA', 'A1')."""
    limpo = " ".join((turma_col or "").split())
    m = re.match(
        r"^(.*?)\s+([A-Z]\d+|[A-Z]{1,2}\d*)\s*-\s*(?:Matutino|Noturno|Diurno|Vespertino|Integral).*$",
        limpo,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Fallback: remover sufixo '(SA)' / '(SBC)'
    sem_campus = re.sub(r"\s*\((?:SA|SBC|SB)\)\s*$", "", limpo, flags=re.IGNORECASE)
    return sem_campus.strip(), ""


def _extrair_codigo_disciplina(codigo_turma: str) -> str:
    m = CODIGO_DISC_RE.search(codigo_turma or "")
    return m.group(1) if m else ""


def _normalizar_campus(campus: str) -> str:
    c = (campus or "").strip().upper()
    if c in ("SA", "SANTO ANDRE", "SANTO ANDRÉ"):
        return "Santo André"
    if c in ("SBC", "SB", "SAO BERNARDO", "SÃO BERNARDO", "SÃO BERNARDO DO CAMPO"):
        return "São Bernardo do Campo"
    return campus.strip() or "Outro"


def _normalizar_turno(turno: str) -> str:
    t = (turno or "").strip().lower()
    if "matutino" in t or "diurno" in t:
        return "Matutino"
    if "noturno" in t:
        return "Noturno"
    return turno.strip().title() or "Outro"


def _creditos_de_tpi(tpi: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", tpi or "")]
    if len(nums) >= 2:
        # Na UFABC, créditos = T + P (ou T + P + E se houver 4 dígitos T-P-E-I)
        if len(nums) == 4:
            return nums[0] + nums[1] + nums[2]
        return nums[0] + nums[1]
    return 0


def _juntar_docentes(*valores: Optional[str]) -> str:
    nomes = []
    for v in valores:
        if v:
            limpo = " ".join(v.split())
            if limpo and limpo not in nomes:
                nomes.append(limpo)
    return " / ".join(nomes)


def parse_pdf_oferta(pdf_path: Path) -> list[Turma]:
    """Lê o PDF de turmas ofertadas da PROGRAD UFABC e retorna lista de Turma."""
    turmas: list[Turma] = []
    por_id: dict[str, Turma] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 9:
                        continue
                    header_check = (row[0] or "").strip().upper()
                    if header_check == "CURSO" or (row[1] or "").strip().upper() == "CÓDIGO DE TURMA":
                        continue

                    curso = " ".join((row[0] or "").split())
                    codigo_turma = " ".join((row[1] or "").split())
                    turma_col = " ".join((row[2] or "").split())
                    teoria_raw = " ".join((row[3] or "").split())
                    pratica_raw = " ".join((row[4] or "").split())
                    campus_raw = " ".join((row[5] or "").split())
                    turno_raw = " ".join((row[6] or "").split())
                    tpi = " ".join((row[7] or "").split())
                    vagas_raw = " ".join((row[8] or "").split())

                    if not codigo_turma and not turma_col:
                        continue

                    disciplina, turma_nome = _extrair_nome_e_turma(turma_col)
                    if not disciplina:
                        continue

                    docente_teoria = _juntar_docentes(
                        row[9] if len(row) > 9 else "",
                        row[10] if len(row) > 10 else "",
                        row[11] if len(row) > 11 else "",
                    )
                    docente_pratica = _juntar_docentes(
                        row[12] if len(row) > 12 else "",
                        row[13] if len(row) > 13 else "",
                        row[14] if len(row) > 14 else "",
                    )

                    horarios = parse_horarios(teoria_raw, "teoria") + parse_horarios(
                        pratica_raw, "pratica"
                    )
                    horarios_raw = " | ".join(
                        p for p in [f"T: {teoria_raw}" if teoria_raw else "", f"P: {pratica_raw}" if pratica_raw else ""] if p
                    )

                    try:
                        vagas = int(re.sub(r"\D", "", vagas_raw)) if vagas_raw else None
                    except ValueError:
                        vagas = None

                    turma_id = codigo_turma or f"{normalizar_texto(disciplina)}_{turma_nome}_{campus_raw}_{turno_raw}"
                    # Mesma turma pode aparecer listada sob mais de um curso no PDF; acumulamos os cursos
                    if turma_id in por_id:
                        if curso and curso not in por_id[turma_id].cursos_oferta:
                            por_id[turma_id].cursos_oferta.append(curso)
                        continue

                    nova = Turma(
                        id=turma_id,
                        codigo=_extrair_codigo_disciplina(codigo_turma),
                        disciplina=disciplina,
                        disciplina_norm=normalizar_texto(disciplina),
                        turma=turma_nome,
                        campus=_normalizar_campus(campus_raw),
                        turno=_normalizar_turno(turno_raw),
                        tpi=tpi,
                        creditos=_creditos_de_tpi(tpi),
                        vagas=vagas,
                        docente_teoria=docente_teoria,
                        docente_pratica=docente_pratica,
                        horarios=horarios,
                        horarios_raw=horarios_raw,
                        cursos_oferta=[curso] if curso else [],
                    )
                    por_id[turma_id] = nova
                    turmas.append(nova)

    return turmas
