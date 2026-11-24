from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.engine.cruzamento import MotorMatricula, horarios_conflitam, turmas_conflitam
from src.models import DisciplinaCatalogo, DisciplinaGrade, Horario, Turma
from src.parsers.historico import sanitizar_texto_historico
from src.web.app import app


def test_sanitizador_descarta_pii_e_classifica_em_curso():
    texto_fake = """
    UNIVERSIDADE FEDERAL DO ABC - HISTÓRICO ESCOLAR
    Nome: JOÃO DA SILVA
    CPF: 123.456.789-00   RG: 12.345.678-9   RA: 11202312345
    2023.3 OBR BCJ0204
    -15 FENÔMENOS MECÂNICOS 5 60 0 -- - DISP
    2024.1 OBR BCL030
    6-15 BIODIVERSIDADE: INTERAÇÕES ENTRE ORGANISMOS E AMBIENTE 3 36 0 DA3BCL0306-15SA B APR
    2025.1 BCN040
    7-15 FUNÇÕES DE VÁRIAS VARIÁVEIS 4 48 0 DA1BCN0407-15SA F REP
    2026.1 OBR BCN040
    7-15 FUNÇÕES DE VÁRIAS VARIÁVEIS 4 48 0 DA3BCN0407-15SA A APR
    2024.3 MCCC00
    7-23 COMPUTAÇÃO GRÁFICA 4 48 0 DA2MCCC007-23SA O REPF
    2026.3 OBR MCCC001-23 ALGORITMOS E ESTRUTURAS DE DADOS I 4 48 0 DA1MCCC001-23SA -- MATR
    """
    sanitizado = sanitizar_texto_historico(texto_fake)
    dump = json.dumps(sanitizado.model_dump(), ensure_ascii=False)

    # Garantia absoluta de privacidade
    assert "123.456.789-00" not in dump
    assert "12.345.678-9" not in dump
    assert "11202312345" not in dump
    assert "JOÃO DA SILVA" not in dump

    por_cod = {d.codigo: d for d in sanitizado.disciplinas}
    assert por_cod["BCJ0204-15"].status == "equivalencia"
    assert por_cod["BCL0306-15"].status == "aprovado"
    assert por_cod["BCN0407-15"].status == "aprovado"  # APR em 2026.1 vence REP de 2025.1
    assert por_cod["MCCC007-23"].status == "reprovado"
    assert por_cod["MCCC001-23"].status == "em_curso"


def test_parse_tabelas_sigaa_codigos_quebrados():
    from src.parsers.historico import _parse_tabelas_sigaa

    class FakePage:
        def extract_tables(self):
            return [
                [
                    ["Ano/Período Letivo", "", "Componente Curricular", "", "Cred.", "CH", "CH EXT", "Turma", "Conceito", "Situação", "Docente(s)"],
                    ["--", "", "ENADE", "DISPENSADO EM RAZÃO DA NATUREZA DO CURSO", "0", "0", "0", "--", "---", "--", ""],
                    ["2023.3", "OBR", "BCJ0204\n-15", "FENÔMENOS MECÂNICOS", "5", "60", "0", "--", "-", "DISP", ""],
                    ["2023.3", "OBR", "BCL030\n6-15", "BIODIVERSIDADE: INTERAÇÕES ENTRE ORGANISMOS E AMBIENTE", "3", "36", "0", "DA3BCL0306-15SA", "B", "APR", "PROF."],
                    ["2024.1", "LIV", "IFSP-\nELES3", "ELETRICIDADE E MAGNETISMO", "2", "24", "0", "--", "-", "TRANS", ""],
                    ["2024.3", "", "MCCC00\n7-23", "COMPUTAÇÃO GRÁFICA", "4", "48", "0", "DA2MCCC007-23SA", "O", "REPF", "PROF."],
                    ["2025.1", "", "BCN040\n7-15", "FUNÇÕES DE VÁRIAS VARIÁVEIS", "4", "48", "0", "DA1BCN0407-15SA", "F", "REP", "PROF."],
                    ["2026.1", "OBR", "BCN040\n7-15", "FUNÇÕES DE VÁRIAS VARIÁVEIS", "4", "48", "0", "DA3BCN0407-15SA", "A", "APR", "PROF."],
                    ["2026.3", "OBR", "MCTA02\n6-13", "SISTEMAS OPERACIONAIS", "4", "48", "0", "DA1MCTA026-13SA", "-", "MATR", "PROF."],
                ]
            ]

    class FakePDF:
        pages = [FakePage()]

    itens = _parse_tabelas_sigaa(FakePDF())
    assert "ENADE" not in itens
    assert itens["BCJ0204-15"].status == "equivalencia"
    assert itens["BCL0306-15"].status == "aprovado"
    assert itens["IFSP-ELES3"].status == "equivalencia"
    assert itens["MCCC007-23"].status == "reprovado"
    assert itens["BCN0407-15"].status == "aprovado"
    assert itens["MCTA026-13"].status == "em_curso"


def test_conflito_horarios_semanal_e_quinzenal():
    h_seg_sem = Horario(dia="segunda", inicio="08:00", fim="10:00", semanalidade="semanal")
    h_seg_q1 = Horario(dia="segunda", inicio="08:00", fim="10:00", semanalidade="quinzenal_1")
    h_seg_q2 = Horario(dia="segunda", inicio="08:00", fim="10:00", semanalidade="quinzenal_2")
    h_seg_depois = Horario(dia="segunda", inicio="10:00", fim="12:00", semanalidade="semanal")

    assert horarios_conflitam(h_seg_sem, h_seg_q1) is True
    assert horarios_conflitam(h_seg_q1, h_seg_q2) is False
    assert horarios_conflitam(h_seg_sem, h_seg_depois) is False

    t1 = Turma(id="T1", disciplina="A", horarios=[h_seg_q1])
    t2 = Turma(id="T2", disciplina="B", horarios=[h_seg_q2])
    t3 = Turma(id="T3", disciplina="C", horarios=[h_seg_sem])
    assert turmas_conflitam(t1, t2) is False
    assert turmas_conflitam(t1, t3) is True


def test_motor_cruzamento_recomendacoes_e_em_curso():
    turmas = [
        Turma(
            id="DA1MCCC001-23SA",
            codigo="MCCC001-23",
            disciplina="ALGORITMOS E ESTRUTURAS DE DADOS I",
            campus="Santo André",
            turno="Matutino",
        ),
        Turma(
            id="DA1MCCC002-23SA",
            codigo="MCCC002-23",
            disciplina="ALGORITMOS E ESTRUTURAS DE DADOS II",
            campus="Santo André",
            turno="Matutino",
        ),
    ]
    catalogo = [
        DisciplinaCatalogo(
            codigo="MCCC001-23",
            nome="Algoritmos e Estruturas de Dados I",
            recomendacoes=["Programação Estruturada"],
        ),
        DisciplinaCatalogo(
            codigo="MCCC002-23",
            nome="Algoritmos e Estruturas de Dados II",
            recomendacoes=["Algoritmos e Estruturas de Dados I"],
        ),
    ]
    grade = [
        DisciplinaGrade(codigo="MCCC001-23", nome="Algoritmos e Estruturas de Dados I", categoria="obrigatoria_bcc"),
        DisciplinaGrade(codigo="MCCC002-23", nome="Algoritmos e Estruturas de Dados II", categoria="obrigatoria_bcc"),
    ]
    hist = sanitizar_texto_historico(
        "MCTA028-15 Programação Estruturada APROVADO\nMCCC001-23 Algoritmos e Estruturas de Dados I MATRICULADO"
    )

    motor = MotorMatricula(turmas, catalogo, grade)
    # Contando em_curso como concluída: AED I some (já cursada) e AED II fica com recomendação OK!
    res = motor.analisar_oferta(historico=hist, contar_em_curso=True, campus="Santo André", turno="Matutino")
    assert len(res) == 1
    assert res[0]["codigo"] == "MCCC002-23"
    assert res[0]["status_recomendacao"] == "ok"


def test_api_endpoints_basicos():
    with TestClient(app) as client:
        r_meta = client.get("/api/meta")
        assert r_meta.status_code == 200
        meta = r_meta.json()
        assert meta["pronto"] is True
        assert meta["total_turmas"] > 500
        assert meta["total_catalogo"] > 1000
        assert meta["total_grade"] > 100

        r_turmas = client.get("/api/turmas?campus=Santo+Andr%C3%A9&turno=Matutino&categoria=obrigatoria_bcc")
        assert r_turmas.status_code == 200
        payload = r_turmas.json()
        assert len(payload["turmas"]) > 0
        # Verificar campo de destravamento calculado pelo grafo
        assert "destrava_count" in payload["turmas"][0]

        # Testar filtro de dias (excluindo sexta)
        r_sem_sexta = client.get(
            "/api/turmas?campus=Santo+Andr%C3%A9&turno=Matutino&dias=segunda,terca,quarta,quinta"
        )
        assert r_sem_sexta.status_code == 200
        for t in r_sem_sexta.json()["turmas"]:
            for h in t["horarios"]:
                assert h["dia"] != "sexta"

        # Testar gerador automático de sugestões de grade sem conflitos
        r_sug = client.post(
            "/api/sugerir-grade",
            json={
                "campus": "Santo André",
                "turno": "Matutino",
                "dias_permitidos": ["segunda", "terca", "quarta", "quinta"],
                "apenas_recomendacoes_ok": False,
                "min_creditos": 8,
                "max_creditos": 16,
                "max_disciplinas": 4,
            },
        )
        assert r_sug.status_code == 200
        sugestoes = r_sug.json()["sugestoes"]
        assert len(sugestoes) >= 1
        assert sugestoes[0]["total_creditos"] <= 16
        assert sugestoes[0]["total_disciplinas"] <= 4

        # Testar preenchimento de créditos restantes com livres/limitadas leves
        r_sug_full = client.post(
            "/api/sugerir-grade",
            json={
                "campus": "Santo André",
                "turno": "Matutino",
                "apenas_recomendacoes_ok": False,
                "min_creditos": 12,
                "max_creditos": 24,
                "max_disciplinas": 6,
                "completar_com_leves": True,
            },
        )
        assert r_sug_full.status_code == 200
        sugs_full = r_sug_full.json()["sugestoes"]
        assert len(sugs_full) >= 1
        assert sugs_full[0]["total_creditos"] <= 24
        assert sugs_full[0]["total_disciplinas"] <= 6

        # Testar suporte a outros cursos (ex: Engenharia de Informação e BC&T)
        assert len(meta["cursos"]) >= 20
        r_eng = client.get(
            "/api/turmas?curso=BACHARELADO+EM+ENGENHARIA+DE+INFORMA%C3%87%C3%83O&campus=Todos&turno=Todos&categoria=obrigatoria_bcc"
        )
        assert r_eng.status_code == 200
        assert len(r_eng.json()["turmas"]) > 0
