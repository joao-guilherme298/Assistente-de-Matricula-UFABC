from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.collectors.prograd import DEFAULT_HEADERS, _extract_links, _score_year
from src.parsers.ppc import parse_grade_bcc

DATA_PUBLICO = BASE_DIR / "data" / "publico"
CURSOS_PDF_DIR = DATA_PUBLICO / "cursos_pdfs"
DOCS_DATA = BASE_DIR / "docs" / "data"

CODIGO_RE = re.compile(r"\b([A-Z]{2,5}\d{3,4}-\d{2})\b")

# Mapa oficial: nome exato (igual oferta.json) -> (slug/url prograd, tipo_base, sigla_curta)
CURSOS_OFICIAIS: list[tuple[str, str, str, str]] = [
    # Cursos de Ingresso (Interdisciplinares)
    ("BACHARELADO EM CIÊNCIA E TECNOLOGIA", "https://prograd.ufabc.edu.br/bct", "nenhum", "BC&T"),
    ("BACHARELADO EM CIÊNCIAS E HUMANIDADES", "https://prograd.ufabc.edu.br/bch/projeto-pedagogico", "nenhum", "BC&H"),
    ("LICENCIATURA EM CIÊNCIAS NATURAIS E EXATAS", "https://prograd.ufabc.edu.br/lcne/projeto-pedagogico", "nenhum", "LCNE"),
    ("LICENCIATURA EM CIÊNCIAS HUMANAS", "https://prograd.ufabc.edu.br/lch/projeto-pedagogico", "nenhum", "LCH"),
    # Específicos pós-BC&T (Ciências & Computação)
    ("BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO", "https://prograd.ufabc.edu.br/cursos/bcc", "bct", "BCC"),
    ("BACHARELADO EM CIÊNCIA DE DADOS", "https://prograd.ufabc.edu.br/cursos/bcd", "bct", "BCD"),
    ("BACHARELADO EM BIOTECNOLOGIA", "https://prograd.ufabc.edu.br/cursos/bb", "bct", "Biotec"),
    ("BACHARELADO EM CIÊNCIAS BIOLÓGICAS", "https://prograd.ufabc.edu.br/cursos/bcb", "bct", "C. Biológicas"),
    ("BACHARELADO EM FÍSICA", "https://prograd.ufabc.edu.br/cursos/bfis", "bct", "Física"),
    ("BACHARELADO EM MATEMÁTICA", "https://prograd.ufabc.edu.br/cursos/bm", "bct", "Matemática"),
    ("BACHARELADO EM QUÍMICA", "https://prograd.ufabc.edu.br/cursos/bq", "bct", "Química"),
    ("BACHARELADO EM NEUROCIÊNCIA", "https://prograd.ufabc.edu.br/cursos/bn", "bct", "Neurociência"),
    # Engenharias (pós-BC&T)
    ("BACHARELADO EM ENGENHARIA AEROESPACIAL", "https://prograd.ufabc.edu.br/cursos/ea", "bct", "Eng. Aeroespacial"),
    ("BACHARELADO EM ENGENHARIA AMBIENTAL E URBANA", "https://prograd.ufabc.edu.br/cursos/eau", "bct", "Eng. Ambiental"),
    ("BACHARELADO EM ENGENHARIA BIOMÉDICA", "https://prograd.ufabc.edu.br/cursos/eb", "bct", "Eng. Biomédica"),
    ("BACHARELADO EM ENGENHARIA DE ENERGIA", "https://prograd.ufabc.edu.br/cursos/ee", "bct", "Eng. de Energia"),
    ("BACHARELADO EM ENGENHARIA DE GESTÃO", "https://prograd.ufabc.edu.br/cursos/eg", "bct", "Eng. de Gestão"),
    ("BACHARELADO EM ENGENHARIA DE INFORMAÇÃO", "https://prograd.ufabc.edu.br/cursos/ei", "bct", "Eng. de Informação"),
    ("BACHARELADO EM ENGENHARIA DE INSTRUMENTAÇÃO, AUTOMAÇÃO E ROBÓTICA", "https://prograd.ufabc.edu.br/cursos/eiar", "bct", "Eng. IAR"),
    ("BACHARELADO EM ENGENHARIA DE MATERIAIS", "https://prograd.ufabc.edu.br/cursos/em", "bct", "Eng. de Materiais"),
    # Específicos pós-BC&H
    ("BACHARELADO EM CIÊNCIAS ECONÔMICAS", "https://prograd.ufabc.edu.br/cursos/bce", "bch", "Economia"),
    ("BACHARELADO EM FILOSOFIA", "https://prograd.ufabc.edu.br/cursos/bfil", "bch", "Filosofia"),
    ("BACHARELADO EM PLANEJAMENTO TERRITORIAL", "https://prograd.ufabc.edu.br/cursos/bpt", "bch", "Planej. Territorial"),
    ("BACHARELADO EM POLÍTICAS PÚBLICAS", "https://prograd.ufabc.edu.br/cursos/bpp", "bch", "Políticas Públicas"),
    ("BACHARELADO EM RELAÇÕES INTERNACIONAIS", "https://prograd.ufabc.edu.br/cursos/bri", "bch", "Relações Internacionais"),
    # Licenciaturas pós-LCNE
    ("LICENCIATURA EM CIÊNCIAS BIOLÓGICAS", "https://prograd.ufabc.edu.br/cursos/lcb", "lcne", "Lic. Biologia"),
    ("LICENCIATURA EM FÍSICA", "https://prograd.ufabc.edu.br/cursos/lfis", "lcne", "Lic. Física"),
    ("LICENCIATURA EM MATEMÁTICA", "https://prograd.ufabc.edu.br/cursos/lm", "lcne", "Lic. Matemática"),
    ("LICENCIATURA EM QUÍMICA", "https://prograd.ufabc.edu.br/cursos/lq", "lcne", "Lic. Química"),
    # Licenciaturas pós-LCH
    ("LICENCIATURA EM FILOSOFIA", "https://prograd.ufabc.edu.br/cursos/lfil", "lch", "Lic. Filosofia"),
    ("LICENCIATURA EM GEOGRAFIA", "https://prograd.ufabc.edu.br/cursos/lg", "lch", "Lic. Geografia"),
    ("LICENCIATURA EM HISTÓRIA", "https://prograd.ufabc.edu.br/cursos/lh", "lch", "Lic. História"),
]


def _slug(url: str) -> str:
    partes = [p for p in url.rstrip("/").split("/") if p]
    if partes[-1] == "projeto-pedagogico" and len(partes) >= 2:
        return partes[-2]
    return partes[-1]


ENGENHARIA_NOMES = {
    "BACHARELADO EM ENGENHARIA AEROESPACIAL": ("ENGENHARIA AEROESPACIAL", "EAERO"),
    "BACHARELADO EM ENGENHARIA AMBIENTAL E URBANA": ("ENGENHARIA AMBIENTAL", "EAU"),
    "BACHARELADO EM ENGENHARIA BIOMÉDICA": ("ENGENHARIA BIOMÉDICA", "EBM"),
    "BACHARELADO EM ENGENHARIA DE ENERGIA": ("ENGENHARIA DE ENERGIA", "EENE"),
    "BACHARELADO EM ENGENHARIA DE GESTÃO": ("ENGENHARIA DE GESTÃO", "EGES"),
    "BACHARELADO EM ENGENHARIA DE INFORMAÇÃO": ("ENGENHARIA DE INFORMAÇÃO", "EINFO"),
    "BACHARELADO EM ENGENHARIA DE INSTRUMENTAÇÃO, AUTOMAÇÃO E ROBÓTICA": ("AUTOMAÇÃO E", "EIAR"),
    "BACHARELADO EM ENGENHARIA DE MATERIAIS": ("ENGENHARIA DE MATERIAIS", "EMAT"),
}


def _extrair_obrigatorias_engenharias_consolidado(
    eng_pdf_path: Path,
    bct_codigos: set[str],
) -> dict[str, list[str]]:
    """Extrai o Rol de Disciplinas Obrigatórias de cada uma das 8 Engenharias do PPC consolidado."""
    if not eng_pdf_path.exists():
        return {}
    reader = PdfReader(str(eng_pdf_path))
    resultado: dict[str, list[str]] = {k: [] for k in ENGENHARIA_NOMES}
    eng_ativa: Optional[str] = None

    for page in reader.pages:
        txt = page.extract_text() or ""
        txt_junto = re.sub(r"([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})", r"\1\2", txt)
        upper = " ".join(txt_junto.upper().split())

        iniciou = False
        if "OBRIGATÓRI" in upper and ("ROL DE DISCIPLINAS" in upper or "QUADRO E" in upper or "LISTA DE DISCIPLINAS" in upper):
            for nome_oficial, (chave_nome, sigla_q) in ENGENHARIA_NOMES.items():
                if chave_nome in upper or f"QUADRO {sigla_q}" in upper:
                    eng_ativa = nome_oficial
                    iniciou = True
                    break

        if not iniciou and eng_ativa:
            if "PROJETO PEDAGÓGICO DO CURSO" in upper or "1. DADOS DO CURSO" in upper:
                eng_ativa = None
                continue

        if eng_ativa:
            cods = CODIGO_RE.findall(txt_junto)
            if not cods and not iniciou:
                eng_ativa = None
                continue
            for c in cods:
                if c not in bct_codigos and c not in resultado[eng_ativa]:
                    resultado[eng_ativa].append(c)

    return resultado


def _descobrir_pdfs_curso(client: httpx.Client, url: str) -> tuple[Optional[str], Optional[str]]:
    """Retorna (url_ppc_mais_recente, url_opcoes_limitadas) de uma página de curso da PROGRAD."""
    resp = client.get(url, follow_redirects=True)
    resp.raise_for_status()
    links = _extract_links(resp.text, str(resp.url))

    candidatos_ppc = []
    candidatos_ol = []

    for text, link in links:
        low_t = text.lower()
        low_u = link.lower()
        if ".pdf" not in low_u:
            continue
        # Ignorar portarias, atas, retificações, transição e boletins de nomeação
        if any(k in low_t for k in ("portaria", "retifica", "transi", "ato decis", "resolu")):
            # Exceto se o próprio texto disser "Projeto Pedagógico"
            if "projeto pedag" not in low_t and "ppc" not in low_t:
                continue

        if "limitada" in low_t or "rol de disciplinas" in low_t:
            candidatos_ol.append((_score_year(text, link), text, link))
        elif "projeto pedag" in low_t or "ppc" in low_t:
            bonus = 2 if "anexo" in low_u else 0
            candidatos_ppc.append(((*_score_year(text, link), bonus), text, link))

    candidatos_ppc.sort(key=lambda x: x[0], reverse=True)
    candidatos_ol.sort(key=lambda x: x[0], reverse=True)

    url_ppc = candidatos_ppc[0][2] if candidatos_ppc else None
    url_ol = candidatos_ol[0][2] if candidatos_ol else None
    return url_ppc, url_ol


def _baixar(client: httpx.Client, url: str, destino: Path) -> Path:
    if destino.exists() and destino.stat().st_size > 1000:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        with destino.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return destino


def _extrair_codigos_pdf_simples(pdf_path: Path, codigos_validos: set[str]) -> list[str]:
    reader = PdfReader(str(pdf_path))
    encontrados: list[str] = []
    vistos: set[str] = set()
    for page in reader.pages:
        txt = page.extract_text() or ""
        # Rejuntar códigos quebrados por quebra de linha
        txt = re.sub(r"([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})", r"\1\2", txt)
        for m in CODIGO_RE.finditer(txt):
            cod = m.group(1)
            if cod not in vistos:
                vistos.add(cod)
                encontrados.append(cod)
    return encontrados


def _extrair_obrigatorias_ppc(
    pdf_path: Path,
    codigos_base: set[str],
    codigos_ol: set[str],
    eh_curso_ingresso: bool,
) -> list[str]:
    """Extrai códigos de disciplinas obrigatórias de um PDF de PPC da UFABC."""
    reader = PdfReader(str(pdf_path))
    codigos_secao_obrig: list[str] = []
    codigos_matriz: list[str] = []
    vistos_obrig: set[str] = set()
    vistos_matriz: set[str] = set()

    for page in reader.pages:
        txt = page.extract_text() or ""
        txt_junto = re.sub(r"([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})", r"\1\2", txt)
        upper = txt_junto.upper()

        # Ignorar páginas de sumário, opções limitadas, transição/equivalência ou ementário
        if ".........." in txt_junto or "SUMÁRIO" in upper[:200]:
            continue
        if any(
            k in upper
            for k in (
                "TABELA DE TRANSIÇÃO",
                "REGRAS DE TRANSIÇÃO",
                "CONVALIDAÇÃO",
                "EQUIVALÊNCIA ENTRE",
                "ROL DE DISCIPLINAS DE OPÇÃO LIMITADA",
                "DISCIPLINAS DE OPÇÃO LIMITADA",
            )
        ):
            # Se a página só fala de opções limitadas/transição e não de obrigatórias, pular
            if "OBRIGATÓRIA" not in upper:
                continue

        cods_pagina = CODIGO_RE.findall(txt_junto)
        if not cods_pagina:
            continue

        # Critério 1 (mais preciso): páginas com título/tabela de Disciplinas Obrigatórias
        if any(
            k in upper
            for k in (
                "DISCIPLINAS OBRIGATÓRIAS",
                "COMPONENTES OBRIGATÓRIOS",
                "COMPONENTES CURRICULARES OBRIGATÓRIOS",
                "OBRIGATÓRIAS DO CURSO",
                "OBRIGATÓRIAS ESPECÍFICAS",
                "OBRIGATÓRIAS DO BC",
                "OBRIGATÓRIAS DA LICENCIATURA",
            )
        ):
            for c in cods_pagina:
                if c not in vistos_obrig:
                    vistos_obrig.add(c)
                    codigos_secao_obrig.append(c)

        # Critério 2 (fallback): páginas de Matriz Curricular Recomendada / Estrutura Curricular
        if any(
            k in upper
            for k in (
                "MATRIZ CURRICULAR",
                "GRADE CURRICULAR",
                "ESTRUTURA CURRICULAR",
                "QUADRIMESTRE",
            )
        ) and "OPÇÃO LIMITADA" not in upper[:400]:
            for c in cods_pagina:
                if c not in vistos_matriz:
                    vistos_matriz.add(c)
                    codigos_matriz.append(c)

    brutos = codigos_secao_obrig if len(codigos_secao_obrig) >= 5 else codigos_matriz

    # Se ainda ficou vazio, último fallback: coletar códigos que aparecem em tabelas (páginas com >= 4 códigos e sem "EMENTA")
    if len(brutos) < 5:
        for page in reader.pages:
            txt = page.extract_text() or ""
            txt_junto = re.sub(r"([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})", r"\1\2", txt)
            upper = txt_junto.upper()
            if "EMENTA" in upper or "BIBLIOGRAFIA" in upper or "OPÇÃO LIMITADA" in upper:
                continue
            cods = CODIGO_RE.findall(txt_junto)
            if len(cods) >= 4:
                for c in cods:
                    if c not in brutos:
                        brutos.append(c)

    # Filtrar: remover códigos que pertencem às opções limitadas ou à base (quando curso específico)
    filtrados = []
    vistos = set()
    for c in brutos:
        if c in vistos:
            continue
        if c in codigos_ol:
            continue
        if not eh_curso_ingresso and c in codigos_base:
            continue
        vistos.add(c)
        filtrados.append(c)
    return filtrados


def main(offline: bool = False) -> None:
    CURSOS_PDF_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    cat_cache = DATA_PUBLICO / "catalogo_cache.json"
    catalogo = json.loads(cat_cache.read_text(encoding="utf-8")) if cat_cache.exists() else []
    codigos_validos = {c["codigo"] for c in catalogo if c.get("codigo")}

    # Base BC&T exata do PPC BCC 2023 já validado
    grade_bcc_list = parse_grade_bcc(
        DATA_PUBLICO / "ppc_bcc.pdf",
        DATA_PUBLICO / "opcoes_limitadas_bcc.pdf",
        DATA_PUBLICO / "grade_bcc_cache.json",
    )
    bct_exatas = [g.codigo for g in grade_bcc_list if g.categoria == "obrigatoria_bct" and g.codigo]
    bcc_obrig = [g.codigo for g in grade_bcc_list if g.categoria == "obrigatoria_bcc" and g.codigo]
    bcc_ol = [g.codigo for g in grade_bcc_list if g.categoria == "opcao_limitada" and g.codigo]

    bases: dict[str, list[str]] = {"bct": bct_exatas, "bch": [], "lcne": [], "lch": []}
    resultado: dict[str, dict] = {}

    # Extrair obrigatórias das 8 Engenharias do PPC consolidado 2023
    eng_pdf_path = CURSOS_PDF_DIR / "engenharias_ppc.pdf"
    eng_obrig_map = _extrair_obrigatorias_engenharias_consolidado(eng_pdf_path, set(bct_exatas))

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=60.0, verify=True) as client:
        if not offline and not eng_pdf_path.exists():
            _baixar(
                client,
                "https://www.ufabc.edu.br/images/consepe/atos_decisorios/ato_decisrio_270_-_ppc_consolidado_-_4_dez_2025_-_retificao_240.pdf",
                eng_pdf_path,
            )
            eng_obrig_map = _extrair_obrigatorias_engenharias_consolidado(eng_pdf_path, set(bct_exatas))

        for nome_curso, url, tipo_base, sigla in CURSOS_OFICIAIS:
            slug = _slug(url)
            if nome_curso == "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO":
                resultado[nome_curso] = {
                    "sigla": sigla,
                    "tipo_base": "bct",
                    "tem_ppc": True,
                    "obrigatorias": bcc_obrig,
                    "opcoes_limitadas": bcc_ol,
                }
                print(f"[OK-EXATO] {sigla:22s} | obrig: {len(bcc_obrig):2d} | ol: {len(bcc_ol):3d}")
                continue

            if nome_curso == "BACHARELADO EM CIÊNCIA E TECNOLOGIA":
                resultado[nome_curso] = {
                    "sigla": sigla,
                    "tipo_base": "nenhum",
                    "tem_ppc": True,
                    "obrigatorias": bct_exatas,
                    "opcoes_limitadas": [],
                }
                print(f"[OK-EXATO] {sigla:22s} | obrig: {len(bct_exatas):2d} | ol:   0")
                continue

            try:
                ol_pdf = CURSOS_PDF_DIR / f"{slug}_ol.pdf"
                ppc_pdf = CURSOS_PDF_DIR / f"{slug}_ppc.pdf"

                if not offline:
                    url_ppc, url_ol = _descobrir_pdfs_curso(client, url)
                    if url_ol:
                        _baixar(client, url_ol, ol_pdf)
                    if url_ppc:
                        _baixar(client, url_ppc, ppc_pdf)

                ol_cods = _extrair_codigos_pdf_simples(ol_pdf, codigos_validos) if ol_pdf.exists() else []

                obrig_cods: list[str] = []
                if nome_curso in eng_obrig_map and eng_obrig_map[nome_curso]:
                    obrig_cods = [c for c in eng_obrig_map[nome_curso] if c not in set(ol_cods)]
                elif ppc_pdf.exists():
                    codigos_base_set = set(bases.get(tipo_base, []))
                    obrig_cods = _extrair_obrigatorias_ppc(
                        ppc_pdf,
                        codigos_base=codigos_base_set,
                        codigos_ol=set(ol_cods),
                        eh_curso_ingresso=(tipo_base == "nenhum"),
                    )

                if slug in bases and obrig_cods:
                    bases[slug] = obrig_cods

                resultado[nome_curso] = {
                    "sigla": sigla,
                    "tipo_base": tipo_base,
                    "tem_ppc": len(obrig_cods) > 0,
                    "obrigatorias": obrig_cods,
                    "opcoes_limitadas": ol_cods,
                }
                status = "OK" if obrig_cods else "SEM_OBRIG"
                print(f"[{status:9s}] {sigla:22s} | obrig: {len(obrig_cods):2d} | ol: {len(ol_cods):3d}")
            except Exception as exc:
                print(f"[ERRO     ] {sigla:22s} | {exc}")
                resultado[nome_curso] = {
                    "sigla": sigla,
                    "tipo_base": tipo_base,
                    "tem_ppc": False,
                    "obrigatorias": [],
                    "opcoes_limitadas": [],
                }

    saida_payload = {"bases": bases, "cursos": resultado}
    out_docs = DOCS_DATA / "grades_cursos.json"
    out_pub = DATA_PUBLICO / "grades_cursos.json"
    texto_json = json.dumps(saida_payload, ensure_ascii=False, separators=(",", ":"))
    out_docs.write_text(texto_json, encoding="utf-8")
    out_pub.write_text(json.dumps(saida_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Salvo em {out_docs} ({len(texto_json) / 1024:.1f} KB)")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="Usa apenas PDFs já baixados em data/publico/cursos_pdfs/")
    args = ap.parse_args()
    main(offline=args.offline)
