from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.collectors.prograd import sincronizar_documentos_publicos
from src.parsers.catalogo import parse_pdf_catalogo
from src.parsers.oferta import parse_pdf_oferta
from src.parsers.ppc import parse_grade_bcc

DATA_PUBLICO = BASE_DIR / "data" / "publico"
DOCS_DATA = BASE_DIR / "docs" / "data"


def exportar(atualizar_prograd: bool = False) -> None:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    if atualizar_prograd:
        print("🔄 Baixando PDFs mais recentes da PROGRAD...")
        sincronizar_documentos_publicos(DATA_PUBLICO, forcar_download=True)

    # 1. Oferta
    ofertas_pdf = sorted(DATA_PUBLICO.glob("*turmas_ofertadas*.pdf"), reverse=True)
    ofertas_cache = sorted(DATA_PUBLICO.glob("*turmas_ofertadas*_cache.json"), reverse=True)
    if ofertas_pdf and (atualizar_prograd or not ofertas_cache):
        turmas_raw = [t.model_dump() for t in parse_pdf_oferta(ofertas_pdf[0])]
        oferta_nome = ofertas_pdf[0].name
    elif ofertas_cache:
        turmas_raw = json.loads(ofertas_cache[0].read_text(encoding="utf-8"))
        oferta_nome = ofertas_cache[0].name.replace("_cache.json", ".pdf")
    else:
        raise RuntimeError("Nenhuma oferta encontrada em data/publico/.")

    # 2. Catálogo (somente campos necessários para manter o JSON leve na web)
    cat_pdf = DATA_PUBLICO / "catalogo_disciplinas.pdf"
    cat_cache = DATA_PUBLICO / "catalogo_cache.json"
    if cat_pdf.exists() and (atualizar_prograd or not cat_cache.exists()):
        cat_raw = [c.model_dump() for c in parse_pdf_catalogo(cat_pdf, cache_path=cat_cache, usar_cache=not atualizar_prograd)]
    elif cat_cache.exists():
        cat_raw = json.loads(cat_cache.read_text(encoding="utf-8"))
    else:
        cat_raw = []

    # Compactar catálogo para a web (remover campos redundantes)
    cat_web = [
        {
            "codigo": c["codigo"],
            "nome": c["nome"],
            "creditos": c["creditos"],
            "recomendacoes": c["recomendacoes"],
        }
        for c in cat_raw
    ]

    # 3. Grade BCC 2023
    ppc_pdf = DATA_PUBLICO / "ppc_bcc.pdf"
    ol_pdf = DATA_PUBLICO / "opcoes_limitadas_bcc.pdf"
    grade_cache = DATA_PUBLICO / "grade_bcc_cache.json"
    if ppc_pdf.exists() and (atualizar_prograd or not grade_cache.exists()):
        grade_raw = [
            g.model_dump()
            for g in parse_grade_bcc(
                ppc_pdf,
                opcoes_limitadas_pdf_path=ol_pdf if ol_pdf.exists() else None,
                cache_path=grade_cache,
                usar_cache=not atualizar_prograd,
            )
        ]
    elif grade_cache.exists():
        grade_raw = json.loads(grade_cache.read_text(encoding="utf-8"))
    else:
        grade_raw = []

    grade_web = [
        {
            "codigo": g["codigo"],
            "nome": g["nome"],
            "categoria": g["categoria"],
            "creditos": g.get("creditos"),
        }
        for g in grade_raw
    ]

    (DOCS_DATA / "oferta.json").write_text(
        json.dumps(turmas_raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (DOCS_DATA / "catalogo.json").write_text(
        json.dumps(cat_web, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (DOCS_DATA / "grade_bcc.json").write_text(
        json.dumps(grade_web, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (DOCS_DATA / "meta.json").write_text(
        json.dumps(
            {
                "oferta_arquivo": oferta_nome,
                "atualizado_em": datetime.now(timezone.utc).isoformat(),
                "total_turmas": len(turmas_raw),
                "total_catalogo": len(cat_web),
                "total_grade": len(grade_web),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"✅ Dados públicos exportados para {DOCS_DATA}:")
    print(f"   {len(turmas_raw)} turmas | {len(cat_web)} catálogo | {len(grade_web)} grade BCC")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exporta os dados públicos da UFABC para a versão web (docs/data/).")
    parser.add_argument("--atualizar", action="store_true", help="Baixar novamente os PDFs mais recentes da PROGRAD.")
    args = parser.parse_args()
    exportar(atualizar_prograd=args.atualizar)
