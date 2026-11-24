from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

from src.models import DisciplinaCatalogo, normalizar_texto

# Padrão de cabeçalho de disciplina no catálogo oficial da UFABC:
# Ex: MCBM013-23 ÁLGEBRA COMUTATIVA \n TPEI 4-0-0-4 \n RECOMENDAÇÃO: Teoria de Anéis; Teoria de Grupos
HEADER_RE = re.compile(
    r"(?P<codigo>[A-Z]{2,5}\d{3,4}-\d{2})\s+(?P<nome>.+?)\s+(?:TPEI|TPI)\s+(?P<tpi>\d+-\d+-\d+(?:-\d+)?)",
    re.DOTALL,
)
RECOM_RE = re.compile(
    r"RECOMENDA[CÇ][AÃ]O\s*:\s*(?P<rec>.+?)(?=\n\s*(?:OBJETIVOS|EMENTA|METODOLOGIA|BIBLIOGRAFIA|PR[ÉE]-REQUISITO)\b|$)",
    re.DOTALL | re.IGNORECASE,
)
OBJ_RE = re.compile(
    r"OBJETIVOS\s*:\s*(?P<obj>.+?)(?=\n\s*(?:METODOLOGIA|EMENTA|BIBLIOGRAFIA)\b|$)",
    re.DOTALL | re.IGNORECASE,
)
EMENTA_RE = re.compile(
    r"\bEMENTA\b\s*:?\s*(?P<ementa>.+?)(?=\n\s*(?:BIBLIOGRAFIA|REFER[EÊ]NCIAS)\b|$)",
    re.DOTALL | re.IGNORECASE,
)


def _creditos_de_tpi(tpi: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", tpi or "")]
    if len(nums) == 4:
        return nums[0] + nums[1] + nums[2]
    if len(nums) >= 2:
        return nums[0] + nums[1]
    return 0


def _split_recomendacoes(rec_raw: str) -> list[str]:
    limpo = " ".join((rec_raw or "").split()).strip(" .;")
    if not limpo:
        return []
    low = normalizar_texto(limpo)
    if low in ("nao ha", "nenhuma", "nenhum", "nao se aplica", "nao possui", ""):
        return []
    # Na UFABC, recomendações vêm separadas por ';'
    partes = [p.strip(" .") for p in re.split(r"[;|\n]+", limpo)]
    return [p for p in partes if p and normalizar_texto(p) not in ("nao ha", "nenhuma")]


def parse_pdf_catalogo(
    pdf_path: Path,
    cache_path: Path | None = None,
    usar_cache: bool = True,
) -> list[DisciplinaCatalogo]:
    """Extrai todas as disciplinas e recomendações do Catálogo PDF da UFABC.

    Como o catálogo tem ~2.400 páginas, salva e reutiliza cache JSON local.
    """
    if usar_cache and cache_path and cache_path.exists():
        if cache_path.stat().st_mtime >= pdf_path.stat().st_mtime:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return [DisciplinaCatalogo(**item) for item in data]

    reader = PdfReader(str(pdf_path))
    disciplinas: dict[str, DisciplinaCatalogo] = {}

    for page in reader.pages:
        texto = page.extract_text() or ""
        if "TPEI" not in texto and "TPI" not in texto:
            continue
        # Ignorar páginas do sumário (contêm muitos pontos sequenciais '.....')
        if "SUMÁRIO" in texto.upper() or ".........." in texto:
            continue

        m_head = HEADER_RE.search(texto)
        if not m_head:
            continue

        codigo = m_head.group("codigo").strip()
        nome = " ".join(m_head.group("nome").split())
        tpi = m_head.group("tpi").strip()

        resto = texto[m_head.end() :]
        rec_raw = ""
        m_rec = RECOM_RE.search(resto)
        if m_rec:
            rec_raw = " ".join(m_rec.group("rec").split())

        objetivos = ""
        m_obj = OBJ_RE.search(resto)
        if m_obj:
            objetivos = " ".join(m_obj.group("obj").split())

        ementa = ""
        m_em = EMENTA_RE.search(resto)
        if m_em:
            ementa = " ".join(m_em.group("ementa").split())

        disc = DisciplinaCatalogo(
            codigo=codigo,
            nome=nome,
            nome_norm=normalizar_texto(nome),
            tpi=tpi,
            creditos=_creditos_de_tpi(tpi),
            recomendacoes=_split_recomendacoes(rec_raw),
            recomendacoes_raw=rec_raw,
            objetivos=objetivos,
            ementa=ementa,
        )
        disciplinas[codigo] = disc

    lista = sorted(disciplinas.values(), key=lambda d: d.nome_norm)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps([d.model_dump() for d in lista], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return lista
