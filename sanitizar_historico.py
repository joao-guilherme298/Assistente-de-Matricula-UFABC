from __future__ import annotations

import argparse
from pathlib import Path

from src.parsers.historico import sanitizar_pdf_historico_arquivo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sanitiza o PDF do histórico escolar da UFABC localmente, descartando CPF/RG/RA/Nome."
    )
    parser.add_argument("pdf", type=Path, help="Caminho para o PDF do seu histórico escolar")
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("data/privado/materias_cursadas.json"),
        help="Caminho de saída do JSON anônimo (padrão: data/privado/materias_cursadas.json)",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"Arquivo não encontrado: {args.pdf}")

    resultado = sanitizar_pdf_historico_arquivo(args.pdf, destino_json=args.saida)
    aprov = sum(1 for d in resultado.disciplinas if d.status in ("aprovado", "equivalencia"))
    curso = sum(1 for d in resultado.disciplinas if d.status == "em_curso")

    print(f"✅ Histórico sanitizado com sucesso em: {args.saida}")
    print(f"   Total extraído: {resultado.total_disciplinas} disciplinas ({aprov} aprovadas/equiv., {curso} em curso)")
    print("🔒 Nenhum dado pessoal (CPF, RG, RA, nome) foi salvo. Você já pode apagar/mover o PDF original.")


if __name__ == "__main__":
    main()
