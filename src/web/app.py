from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.collectors.prograd import sincronizar_documentos_publicos
from src.engine.cruzamento import MotorMatricula, turmas_conflitam
from src.models import HistoricoSanitizado
from src.parsers.catalogo import parse_pdf_catalogo
from src.parsers.historico import (
    carregar_historico_sanitizado,
    sanitizar_pdf_historico_bytes,
    sanitizar_texto_historico,
)
from src.parsers.oferta import parse_pdf_oferta
from src.parsers.ppc import parse_grade_bcc

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_PUBLICO = BASE_DIR / "data" / "publico"
DATA_PRIVADO = BASE_DIR / "data" / "privado"
HISTORICO_JSON = DATA_PRIVADO / "materias_cursadas.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Assistente de Matrícula UFABC — BCC")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class EstadoAplicacao:
    def __init__(self) -> None:
        self.motor: Optional[MotorMatricula] = None
        self.historico: Optional[HistoricoSanitizado] = None
        self.oferta_arquivo: str = ""

    def carregar(self, forcar_reparse: bool = False) -> None:
        DATA_PUBLICO.mkdir(parents=True, exist_ok=True)
        DATA_PRIVADO.mkdir(parents=True, exist_ok=True)

        ofertas = sorted(DATA_PUBLICO.glob("*turmas_ofertadas*.pdf"), reverse=True)
        if not ofertas:
            raise RuntimeError(
                "Nenhum PDF de turmas ofertadas encontrado em data/publico/. "
                "Clique em 'Atualizar PDFs da PROGRAD' ou coloque o PDF lá."
            )

        oferta_pdf = ofertas[0]
        self.oferta_arquivo = oferta_pdf.name

        oferta_cache = DATA_PUBLICO / f"{oferta_pdf.stem}_cache.json"
        if not forcar_reparse and oferta_cache.exists() and oferta_cache.stat().st_mtime >= oferta_pdf.stat().st_mtime:
            from src.models import Turma

            turmas = [Turma(**t) for t in json.loads(oferta_cache.read_text(encoding="utf-8"))]
        else:
            turmas = parse_pdf_oferta(oferta_pdf)
            oferta_cache.write_text(
                json.dumps([t.model_dump() for t in turmas], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        catalogo_pdf = DATA_PUBLICO / "catalogo_disciplinas.pdf"
        catalogo = (
            parse_pdf_catalogo(
                catalogo_pdf,
                cache_path=DATA_PUBLICO / "catalogo_cache.json",
                usar_cache=not forcar_reparse,
            )
            if catalogo_pdf.exists()
            else []
        )

        ppc_pdf = DATA_PUBLICO / "ppc_bcc.pdf"
        ol_pdf = DATA_PUBLICO / "opcoes_limitadas_bcc.pdf"
        grade = (
            parse_grade_bcc(
                ppc_pdf,
                opcoes_limitadas_pdf_path=ol_pdf if ol_pdf.exists() else None,
                cache_path=DATA_PUBLICO / "grade_bcc_cache.json",
                usar_cache=not forcar_reparse,
            )
            if ppc_pdf.exists()
            else []
        )

        self.motor = MotorMatricula(turmas=turmas, catalogo=catalogo, grade=grade)
        self.historico = carregar_historico_sanitizado(HISTORICO_JSON)

    def catalogo_nomes(self) -> dict[str, str]:
        if not self.motor:
            return {}
        return {d.codigo: d.nome for d in self.motor.catalogo if d.codigo}


estado = EstadoAplicacao()


@app.on_event("startup")
def startup_event() -> None:
    try:
        estado.carregar()
    except Exception as exc:
        print(f"[AVISO] Falha ao carregar dados iniciais: {exc}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/meta")
def get_meta() -> dict:
    if not estado.motor:
        return {"pronto": False, "erro": "Dados públicos ainda não carregados."}
    campi = sorted({t.campus for t in estado.motor.turmas})
    turnos = sorted({t.turno for t in estado.motor.turmas})
    return {
        "pronto": True,
        "oferta_arquivo": estado.oferta_arquivo,
        "total_turmas": len(estado.motor.turmas),
        "total_catalogo": len(estado.motor.catalogo),
        "total_grade": len(estado.motor.grade),
        "campi": campi,
        "turnos": turnos,
        "tem_historico": estado.historico is not None and len(estado.historico.disciplinas) > 0,
        "total_historico": len(estado.historico.disciplinas) if estado.historico else 0,
    }


@app.get("/api/turmas")
def listar_turmas(
    campus: str = "Santo André",
    turno: str = "Matutino",
    categoria: str = "Todas",
    ocultar_cursadas: bool = True,
    apenas_recomendacoes_ok: bool = False,
    contar_em_curso: bool = True,
    busca: str = "",
) -> dict:
    if not estado.motor:
        raise HTTPException(status_code=503, detail="Base ainda não carregada.")
    turmas = estado.motor.analisar_oferta(
        historico=estado.historico,
        contar_em_curso=contar_em_curso,
        campus=campus,
        turno=turno,
        categoria=categoria,
        ocultar_cursadas=ocultar_cursadas,
        apenas_recomendacoes_ok=apenas_recomendacoes_ok,
        busca=busca,
    )
    progresso = estado.motor.resumo_progresso(
        historico=estado.historico,
        contar_em_curso=contar_em_curso,
    )
    return {"turmas": turmas, "progresso": progresso}


class ConflitoRequest(BaseModel):
    ids_selecionados: list[str]
    candidata_id: str


@app.post("/api/conflito")
def verificar_conflito(req: ConflitoRequest) -> dict:
    if not estado.motor:
        raise HTTPException(status_code=503, detail="Base ainda não carregada.")
    por_id = {t.id: t for t in estado.motor.turmas}
    cand = por_id.get(req.candidata_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")
    conflitos = []
    for sid in req.ids_selecionados:
        outra = por_id.get(sid)
        if outra and outra.id != cand.id and turmas_conflitam(cand, outra):
            conflitos.append({"id": outra.id, "disciplina": outra.disciplina})
    return {"conflita": len(conflitos) > 0, "conflitos": conflitos}


@app.post("/api/historico/upload")
async def upload_historico_pdf(arquivo: UploadFile = File(...)) -> dict:
    """Processa o PDF do histórico 100% em memória, descarta PII e salva só o JSON anônimo."""
    if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF válido.")
    conteudo = await arquivo.read()
    sanitizado = sanitizar_pdf_historico_bytes(conteudo, estado.catalogo_nomes())
    # Descarta imediatamente o conteúdo bruto do PDF da memória
    del conteudo

    DATA_PRIVADO.mkdir(parents=True, exist_ok=True)
    HISTORICO_JSON.write_text(
        json.dumps(sanitizado.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    estado.historico = sanitizado
    return {
        "ok": True,
        "total_disciplinas": sanitizado.total_disciplinas,
        "aprovadas": sum(1 for d in sanitizado.disciplinas if d.status in ("aprovado", "equivalencia")),
        "em_curso": sum(1 for d in sanitizado.disciplinas if d.status == "em_curso"),
        "disciplinas": [d.model_dump() for d in sanitizado.disciplinas],
    }


@app.post("/api/historico/texto")
def upload_historico_texto(texto: str = Form(...)) -> dict:
    """Alternativa sem PDF: cola o texto das disciplinas do SIGAA/Portal do Aluno."""
    sanitizado = sanitizar_texto_historico(texto, estado.catalogo_nomes())
    DATA_PRIVADO.mkdir(parents=True, exist_ok=True)
    HISTORICO_JSON.write_text(
        json.dumps(sanitizado.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    estado.historico = sanitizado
    return {
        "ok": True,
        "total_disciplinas": sanitizado.total_disciplinas,
        "aprovadas": sum(1 for d in sanitizado.disciplinas if d.status in ("aprovado", "equivalencia")),
        "em_curso": sum(1 for d in sanitizado.disciplinas if d.status == "em_curso"),
        "disciplinas": [d.model_dump() for d in sanitizado.disciplinas],
    }


@app.get("/api/historico")
def obter_historico() -> dict:
    if not estado.historico:
        return {"tem_historico": False, "disciplinas": []}
    return {
        "tem_historico": True,
        "total_disciplinas": estado.historico.total_disciplinas,
        "disciplinas": [d.model_dump() for d in estado.historico.disciplinas],
    }


@app.delete("/api/historico")
def limpar_historico() -> dict:
    if HISTORICO_JSON.exists():
        HISTORICO_JSON.unlink()
    estado.historico = None
    return {"ok": True}


@app.post("/api/sincronizar")
def sincronizar_prograd(forcar: bool = False) -> dict:
    """Baixa os PDFs mais recentes da PROGRAD e recarrega a base."""
    try:
        arquivos = sincronizar_documentos_publicos(DATA_PUBLICO, forcar_download=forcar)
        estado.carregar(forcar_reparse=True)
        return {"ok": True, "arquivos": arquivos}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
