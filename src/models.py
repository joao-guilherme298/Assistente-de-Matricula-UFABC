from __future__ import annotations

import re
import unicodedata
from typing import Literal, Optional

from pydantic import BaseModel, Field


def normalizar_texto(texto: str) -> str:
    """Remove acentos, pontuação redundante e normaliza espaços para matching."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


class Horario(BaseModel):
    dia: Literal["segunda", "terca", "quarta", "quinta", "sexta", "sabado"]
    inicio: str  # HH:MM
    fim: str     # HH:MM
    tipo: Literal["teoria", "pratica", "geral"] = "geral"
    semanalidade: Literal["semanal", "quinzenal_1", "quinzenal_2"] = "semanal"
    raw: str = ""


class Turma(BaseModel):
    id: str
    codigo: str = ""
    disciplina: str
    disciplina_norm: str = ""
    turma: str = ""
    campus: str = "Outro"
    turno: str = "Outro"
    tpi: str = ""
    creditos: int = 0
    vagas: Optional[int] = None
    docente_teoria: str = ""
    docente_pratica: str = ""
    horarios: list[Horario] = Field(default_factory=list)
    horarios_raw: str = ""
    cursos_oferta: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if not self.disciplina_norm:
            self.disciplina_norm = normalizar_texto(self.disciplina)


class DisciplinaCatalogo(BaseModel):
    codigo: str = ""
    nome: str
    nome_norm: str = ""
    tpi: str = ""
    creditos: int = 0
    recomendacoes: list[str] = Field(default_factory=list)
    recomendacoes_raw: str = ""

    def model_post_init(self, __context) -> None:
        if not self.nome_norm:
            self.nome_norm = normalizar_texto(self.nome)


class DisciplinaGrade(BaseModel):
    codigo: str = ""
    nome: str
    nome_norm: str = ""
    categoria: Literal["obrigatoria_bcc", "obrigatoria_bct", "opcao_limitada", "livre"]
    quadrimestre_ideal: Optional[int] = None
    creditos: Optional[int] = None

    def model_post_init(self, __context) -> None:
        if not self.nome_norm:
            self.nome_norm = normalizar_texto(self.nome)


class HistoricoItem(BaseModel):
    """Representa apenas uma disciplina do histórico — sem dados pessoais (PII)."""

    codigo: str = ""
    nome: str
    nome_norm: str = ""
    status: Literal["aprovado", "em_curso", "equivalencia", "reprovado"] = "aprovado"
    conceito: str = ""

    def model_post_init(self, __context) -> None:
        if not self.nome_norm:
            self.nome_norm = normalizar_texto(self.nome)


class HistoricoSanitizado(BaseModel):
    gerado_em: str = ""
    total_disciplinas: int = 0
    disciplinas: list[HistoricoItem] = Field(default_factory=list)
