from __future__ import annotations

import json
from contextlib import asynccontextmanager
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


class EstadoAplicacao:
    def __init__(self) -> None:
        self.motor: Optional[MotorMatricula] = None
        self.historico: Optional[HistoricoSanitizado] = None
        self.oferta_arquivo: str = ""

    def carregar(self, forcar_reparse: bool = False) -> None:
        DATA_PUBLICO.mkdir(parents=True, exist_ok=True)
        DATA_PRIVADO.mkdir(parents=True, exist_ok=True)

        ofertas = sorted(DATA_PUBLICO.glob("*turmas_ofertadas*.pdf"), reverse=True)
        caches_oferta = sorted(DATA_PUBLICO.glob("*turmas_ofertadas*_cache.json"), reverse=True)
        if not ofertas and not caches_oferta:
            raise RuntimeError(
                "Nenhum PDF de turmas ofertadas encontrado em data/publico/. "
                "Clique em 'Atualizar PDFs da PROGRAD' ou coloque o PDF lá."
            )

        from src.models import DisciplinaCatalogo, DisciplinaGrade, Turma

        if ofertas:
            oferta_pdf = ofertas[0]
            self.oferta_arquivo = oferta_pdf.name
            oferta_cache = DATA_PUBLICO / f"{oferta_pdf.stem}_cache.json"
            if not forcar_reparse and oferta_cache.exists() and oferta_cache.stat().st_mtime >= oferta_pdf.stat().st_mtime:
                turmas = [Turma(**t) for t in json.loads(oferta_cache.read_text(encoding="utf-8"))]
            else:
                turmas = parse_pdf_oferta(oferta_pdf)
                oferta_cache.write_text(
                    json.dumps([t.model_dump() for t in turmas], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        else:
            oferta_cache = caches_oferta[0]
            self.oferta_arquivo = oferta_cache.name.replace("_cache.json", ".pdf")
            turmas = [Turma(**t) for t in json.loads(oferta_cache.read_text(encoding="utf-8"))]

        catalogo_pdf = DATA_PUBLICO / "catalogo_disciplinas.pdf"
        catalogo_cache = DATA_PUBLICO / "catalogo_cache.json"
        if catalogo_pdf.exists():
            catalogo = parse_pdf_catalogo(
                catalogo_pdf,
                cache_path=catalogo_cache,
                usar_cache=not forcar_reparse,
            )
        elif catalogo_cache.exists():
            catalogo = [DisciplinaCatalogo(**c) for c in json.loads(catalogo_cache.read_text(encoding="utf-8"))]
        else:
            catalogo = []

        ppc_pdf = DATA_PUBLICO / "ppc_bcc.pdf"
        ol_pdf = DATA_PUBLICO / "opcoes_limitadas_bcc.pdf"
        grade_cache = DATA_PUBLICO / "grade_bcc_cache.json"
        if ppc_pdf.exists():
            grade = parse_grade_bcc(
                ppc_pdf,
                opcoes_limitadas_pdf_path=ol_pdf if ol_pdf.exists() else None,
                cache_path=grade_cache,
                usar_cache=not forcar_reparse,
            )
        elif grade_cache.exists():
            grade = [DisciplinaGrade(**g) for g in json.loads(grade_cache.read_text(encoding="utf-8"))]
        else:
            grade = []

        self.motor = MotorMatricula(turmas=turmas, catalogo=catalogo, grade=grade)
        self.historico = carregar_historico_sanitizado(HISTORICO_JSON)

    def catalogo_nomes(self) -> dict[str, str]:
        if not self.motor:
            return {}
        return {d.codigo: d.nome for d in self.motor.catalogo if d.codigo}


estado = EstadoAplicacao()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        estado.carregar()
    except Exception as exc:
        print(f"[AVISO] Falha ao carregar dados iniciais: {exc}")
    yield


app = FastAPI(title="Assistente de Matrícula UFABC — BCC", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    dias: str = "",
    busca: str = "",
) -> dict:
    if not estado.motor:
        raise HTTPException(status_code=503, detail="Base ainda não carregada.")
    dias_list = [d.strip() for d in dias.split(",") if d.strip()] if dias.strip() else None
    turmas = estado.motor.analisar_oferta(
        historico=estado.historico,
        contar_em_curso=contar_em_curso,
        campus=campus,
        turno=turno,
        categoria=categoria,
        ocultar_cursadas=ocultar_cursadas,
        apenas_recomendacoes_ok=apenas_recomendacoes_ok,
        dias_permitidos=dias_list,
        busca=busca,
    )
    progresso = estado.motor.resumo_progresso(
        historico=estado.historico,
        contar_em_curso=contar_em_curso,
    )
    return {"turmas": turmas, "progresso": progresso}


class SugerirGradeRequest(BaseModel):
    campus: str = "Santo André"
    turno: str = "Matutino"
    dias_permitidos: Optional[list[str]] = None
    contar_em_curso: bool = True
    apenas_recomendacoes_ok: bool = True
    min_creditos: int = 12
    max_creditos: int = 20
    max_disciplinas: int = 5
    completar_com_leves: bool = False


@app.post("/api/sugerir-grade")
def sugerir_grade(req: SugerirGradeRequest) -> dict:
    if not estado.motor:
        raise HTTPException(status_code=503, detail="Base ainda não carregada.")
    sugestoes = estado.motor.sugerir_grades(
        historico=estado.historico,
        contar_em_curso=req.contar_em_curso,
        campus=req.campus,
        turno=req.turno,
        dias_permitidos=req.dias_permitidos,
        apenas_recomendacoes_ok=req.apenas_recomendacoes_ok,
        min_creditos=req.min_creditos,
        max_creditos=req.max_creditos,
        max_disciplinas=req.max_disciplinas,
        completar_com_leves=req.completar_com_leves,
    )
    return {"sugestoes": sugestoes}


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
