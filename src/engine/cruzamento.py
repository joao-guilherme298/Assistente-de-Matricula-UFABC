from __future__ import annotations

from typing import Any, Optional

from src.models import (
    DisciplinaCatalogo,
    DisciplinaGrade,
    HistoricoSanitizado,
    Horario,
    Turma,
    normalizar_texto,
)


def _hora_para_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def horarios_conflitam(h1: Horario, h2: Horario) -> bool:
    if h1.dia != h2.dia:
        return False
    # Quinzenal I e Quinzenal II acontecem em semanas alternadas -> não conflitam
    if (h1.semanalidade == "quinzenal_1" and h2.semanalidade == "quinzenal_2") or (
        h1.semanalidade == "quinzenal_2" and h2.semanalidade == "quinzenal_1"
    ):
        return False
    ini1, fim1 = _hora_para_min(h1.inicio), _hora_para_min(h1.fim)
    ini2, fim2 = _hora_para_min(h2.inicio), _hora_para_min(h2.fim)
    return ini1 < fim2 and ini2 < fim1


def turmas_conflitam(t1: Turma, t2: Turma) -> bool:
    for h1 in t1.horarios:
        for h2 in t2.horarios:
            if horarios_conflitam(h1, h2):
                return True
    return False


def _base_codigo(codigo: str) -> str:
    """Remove o sufixo de ano do código (ex: MCCC001-23 -> MCCC001) para matching flexível."""
    return codigo.split("-")[0].strip().upper() if codigo else ""


class MotorMatricula:
    def __init__(
        self,
        turmas: list[Turma],
        catalogo: list[DisciplinaCatalogo],
        grade: list[DisciplinaGrade],
    ) -> None:
        self.turmas = turmas
        self.catalogo = catalogo
        self.grade = grade

        self.catalogo_por_codigo: dict[str, DisciplinaCatalogo] = {
            d.codigo: d for d in catalogo if d.codigo
        }
        self.catalogo_por_base: dict[str, DisciplinaCatalogo] = {
            _base_codigo(d.codigo): d for d in catalogo if d.codigo
        }
        self.catalogo_por_nome: dict[str, DisciplinaCatalogo] = {
            d.nome_norm: d for d in catalogo if d.nome_norm
        }

        self.grade_por_codigo: dict[str, DisciplinaGrade] = {
            g.codigo: g for g in grade if g.codigo
        }
        self.grade_por_base: dict[str, DisciplinaGrade] = {
            _base_codigo(g.codigo): g for g in grade if g.codigo
        }
        self.grade_por_nome: dict[str, DisciplinaGrade] = {
            g.nome_norm: g for g in grade if g.nome_norm
        }

        # Mapa reverso de recomendações: disciplina_norm -> lista de disciplinas da grade que a recomendam
        self.destrava_mapa: dict[str, list[dict[str, str]]] = {}
        self._construir_grafo_destravamento()

    def _construir_grafo_destravamento(self) -> None:
        mapa: dict[str, list[dict[str, str]]] = {}
        for g in self.grade:
            if g.categoria not in ("obrigatoria_bcc", "obrigatoria_bct", "opcao_limitada"):
                continue
            cat = self.buscar_catalogo(g.codigo, g.nome_norm)
            if not cat or not cat.recomendacoes:
                continue
            for rec in cat.recomendacoes:
                rec_norm = normalizar_texto(rec)
                chaves = {rec_norm}
                if rec_norm.endswith(" i"):
                    chaves.add(rec_norm[:-2].strip())
                cat_rec = self.catalogo_por_nome.get(rec_norm)
                if cat_rec and cat_rec.codigo:
                    chaves.add(cat_rec.codigo)
                    chaves.add(_base_codigo(cat_rec.codigo))
                alvo = {"codigo": g.codigo, "nome": g.nome, "categoria": g.categoria}
                for ch in chaves:
                    lista = mapa.setdefault(ch, [])
                    if not any(x["nome"] == alvo["nome"] for x in lista):
                        lista.append(alvo)
        self.destrava_mapa = mapa

    def disciplinas_destravadas(
        self,
        codigo: str,
        nome_norm: str,
        codigos_feitos: set[str],
        bases_feitas: set[str],
        nomes_feitos: set[str],
    ) -> list[dict[str, str]]:
        """Retorna disciplinas pendentes da grade que recomendam esta disciplina."""
        candidatos: list[dict[str, str]] = []
        vistos: set[str] = set()
        for chave in (codigo, _base_codigo(codigo), nome_norm):
            if not chave:
                continue
            for item in self.destrava_mapa.get(chave, []):
                if item["nome"] in vistos:
                    continue
                vistos.add(item["nome"])
                item_norm = normalizar_texto(item["nome"])
                if not self._disciplina_cumprida(
                    item["codigo"], item_norm, codigos_feitos, bases_feitas, nomes_feitos
                ):
                    candidatos.append(item)
        # Ordenar priorizando obrigatórias do BCC
        ordem = {"obrigatoria_bcc": 0, "obrigatoria_bct": 1, "opcao_limitada": 2}
        candidatos.sort(key=lambda x: (ordem.get(x["categoria"], 9), x["nome"]))
        return candidatos

    def buscar_catalogo(self, codigo: str, nome_norm: str) -> Optional[DisciplinaCatalogo]:
        if codigo and codigo in self.catalogo_por_codigo:
            return self.catalogo_por_codigo[codigo]
        if nome_norm and nome_norm in self.catalogo_por_nome:
            return self.catalogo_por_nome[nome_norm]
        base = _base_codigo(codigo)
        if base and base in self.catalogo_por_base:
            return self.catalogo_por_base[base]
        return None

    def buscar_grade(self, codigo: str, nome_norm: str) -> Optional[DisciplinaGrade]:
        if codigo and codigo in self.grade_por_codigo:
            return self.grade_por_codigo[codigo]
        if nome_norm and nome_norm in self.grade_por_nome:
            return self.grade_por_nome[nome_norm]
        base = _base_codigo(codigo)
        if base and base in self.grade_por_base:
            return self.grade_por_base[base]
        return None

    def _indices_historico(
        self,
        historico: Optional[HistoricoSanitizado],
        contar_em_curso: bool = True,
    ) -> tuple[set[str], set[str], set[str], dict[str, str]]:
        codigos_feitos: set[str] = set()
        bases_feitas: set[str] = set()
        nomes_feitos: set[str] = set()
        status_por_chave: dict[str, str] = {}

        if not historico:
            return codigos_feitos, bases_feitas, nomes_feitos, status_por_chave

        status_validos = {"aprovado", "equivalencia"}
        if contar_em_curso:
            status_validos.add("em_curso")

        for item in historico.disciplinas:
            if item.codigo:
                status_por_chave[item.codigo] = item.status
                status_por_chave[_base_codigo(item.codigo)] = item.status
            if item.nome_norm:
                status_por_chave[item.nome_norm] = item.status

            if item.status in status_validos:
                if item.codigo:
                    codigos_feitos.add(item.codigo)
                    bases_feitas.add(_base_codigo(item.codigo))
                if item.nome_norm:
                    nomes_feitos.add(item.nome_norm)

        return codigos_feitos, bases_feitas, nomes_feitos, status_por_chave

    def _disciplina_cumprida(
        self,
        codigo: str,
        nome_norm: str,
        codigos_feitos: set[str],
        bases_feitas: set[str],
        nomes_feitos: set[str],
    ) -> bool:
        if codigo and codigo in codigos_feitos:
            return True
        if nome_norm and nome_norm in nomes_feitos:
            return True
        base = _base_codigo(codigo)
        if base and base in bases_feitas:
            return True
        return False

    def _avaliar_recomendacoes(
        self,
        recomendacoes: list[str],
        codigos_feitos: set[str],
        bases_feitas: set[str],
        nomes_feitos: set[str],
        tem_historico: bool,
    ) -> tuple[str, list[dict[str, Any]]]:
        if not recomendacoes:
            return "sem_recomendacao", []

        detalhes: list[dict[str, Any]] = []
        cumpridas = 0
        for rec in recomendacoes:
            rec_norm = normalizar_texto(rec)
            # Tentar encontrar no catálogo para também checar pelo código
            cat_rec = self.catalogo_por_nome.get(rec_norm)
            cumprida = False
            if tem_historico:
                rec_sem_i = rec_norm[:-2].strip() if rec_norm.endswith(" i") else ""
                if rec_norm in nomes_feitos or (rec_sem_i and rec_sem_i in nomes_feitos):
                    cumprida = True
                elif cat_rec and (
                    cat_rec.codigo in codigos_feitos or _base_codigo(cat_rec.codigo) in bases_feitas
                ):
                    cumprida = True
            if cumprida:
                cumpridas += 1
            detalhes.append({"nome": rec, "cumprida": cumprida})

        if not tem_historico:
            return "desconhecido", detalhes
        if cumpridas == len(recomendacoes):
            return "ok", detalhes
        if cumpridas > 0:
            return "parcial", detalhes
        return "pendente", detalhes

    def analisar_oferta(
        self,
        historico: Optional[HistoricoSanitizado] = None,
        contar_em_curso: bool = True,
        campus: Optional[str] = None,
        turno: Optional[str] = None,
        categoria: Optional[str] = None,
        ocultar_cursadas: bool = True,
        apenas_recomendacoes_ok: bool = False,
        dias_permitidos: Optional[list[str]] = None,
        busca: str = "",
    ) -> list[dict[str, Any]]:
        codigos_feitos, bases_feitas, nomes_feitos, status_map = self._indices_historico(
            historico, contar_em_curso=contar_em_curso
        )
        tem_historico = historico is not None and len(historico.disciplinas) > 0
        busca_norm = normalizar_texto(busca)
        dias_set = set(dias_permitidos) if dias_permitidos is not None else None

        ordem_categoria = {
            "obrigatoria_bcc": 0,
            "obrigatoria_bct": 1,
            "opcao_limitada": 2,
            "livre": 3,
        }
        ordem_rec = {
            "sem_recomendacao": 0,
            "ok": 0,
            "parcial": 1,
            "desconhecido": 2,
            "pendente": 3,
        }

        resultados: list[dict[str, Any]] = []
        for t in self.turmas:
            if campus and campus != "Todos" and t.campus != campus:
                continue
            if turno and turno != "Todos" and t.turno != turno:
                continue
            if dias_set is not None and t.horarios:
                if any(h.dia not in dias_set for h in t.horarios):
                    continue

            grade_info = self.buscar_grade(t.codigo, t.disciplina_norm)
            cat_turma = grade_info.categoria if grade_info else "livre"
            if categoria and categoria != "Todas" and cat_turma != categoria:
                continue

            ja_cursada = self._disciplina_cumprida(
                t.codigo, t.disciplina_norm, codigos_feitos, bases_feitas, nomes_feitos
            )
            if ocultar_cursadas and ja_cursada:
                continue

            status_hist = (
                status_map.get(t.codigo)
                or status_map.get(t.disciplina_norm)
                or status_map.get(_base_codigo(t.codigo))
                or "nao_cursada"
            )

            cat_info = self.buscar_catalogo(t.codigo, t.disciplina_norm)
            recs = cat_info.recomendacoes if cat_info else []
            status_rec, recs_detalhe = self._avaliar_recomendacoes(
                recs, codigos_feitos, bases_feitas, nomes_feitos, tem_historico
            )

            if apenas_recomendacoes_ok and status_rec not in ("sem_recomendacao", "ok"):
                continue

            if busca_norm:
                alvo = normalizar_texto(
                    f"{t.codigo} {t.disciplina} {t.docente_teoria} {t.docente_pratica} {t.id}"
                )
                if busca_norm not in alvo:
                    continue

            destrava = self.disciplinas_destravadas(
                t.codigo, t.disciplina_norm, codigos_feitos, bases_feitas, nomes_feitos
            )

            resultados.append(
                {
                    "id": t.id,
                    "codigo": t.codigo,
                    "disciplina": t.disciplina,
                    "turma": t.turma,
                    "campus": t.campus,
                    "turno": t.turno,
                    "tpi": t.tpi,
                    "creditos": t.creditos or (cat_info.creditos if cat_info else 0),
                    "vagas": t.vagas,
                    "docente_teoria": t.docente_teoria,
                    "docente_pratica": t.docente_pratica,
                    "horarios": [h.model_dump() for h in t.horarios],
                    "horarios_raw": t.horarios_raw,
                    "categoria": cat_turma,
                    "ja_cursada": ja_cursada,
                    "status_historico": status_hist,
                    "status_recomendacao": status_rec,
                    "recomendacoes": recs_detalhe,
                    "destrava": [d["nome"] for d in destrava],
                    "destrava_count": len(destrava),
                    "_sort": (
                        ordem_categoria.get(cat_turma, 9),
                        ordem_rec.get(status_rec, 9),
                        -len(destrava),
                        t.disciplina_norm,
                        t.turma,
                    ),
                }
            )

        resultados.sort(key=lambda r: r["_sort"])
        for r in resultados:
            r.pop("_sort", None)
        return resultados

    def sugerir_grades(
        self,
        historico: Optional[HistoricoSanitizado] = None,
        contar_em_curso: bool = True,
        campus: Optional[str] = "Santo André",
        turno: Optional[str] = "Matutino",
        dias_permitidos: Optional[list[str]] = None,
        apenas_recomendacoes_ok: bool = True,
        min_creditos: int = 12,
        max_creditos: int = 20,
        max_disciplinas: int = 5,
        completar_com_leves: bool = False,
        limite_sugestoes: int = 3,
    ) -> list[dict[str, Any]]:
        """Gera até N sugestões de grade sem conflito priorizando obrigatórias e destravamento.

        Se completar_com_leves=True, preenche os créditos restantes até max_creditos
        com Opções Limitadas ou Livres sem recomendações (mais tranquilas).
        """
        candidatas = self.analisar_oferta(
            historico=historico,
            contar_em_curso=contar_em_curso,
            campus=campus,
            turno=turno,
            categoria="Todas",
            ocultar_cursadas=True,
            apenas_recomendacoes_ok=apenas_recomendacoes_ok,
            dias_permitidos=dias_permitidos,
        )

        # Agrupar por disciplina (mantendo até 3 turmas com horários distintos por disciplina)
        grupos: list[tuple[float, str, list[dict[str, Any]]]] = []
        por_disc: dict[str, list[dict[str, Any]]] = {}
        peso_cat = {
            "obrigatoria_bcc": 100.0,
            "obrigatoria_bct": 80.0,
            "opcao_limitada": 45.0,
            "livre": 15.0,
        }
        peso_rec = {"sem_recomendacao": 15.0, "ok": 15.0, "parcial": 3.0, "desconhecido": 5.0, "pendente": -20.0}

        for c in candidatas:
            if not c["horarios"] or c["creditos"] <= 0:
                continue
            chave = c["codigo"] or normalizar_texto(c["disciplina"])
            por_disc.setdefault(chave, []).append(c)

        for chave, lista_t in por_disc.items():
            # Deduplicar turmas com exatamente o mesmo horário para agilizar a busca
            horarios_vistos: set[str] = set()
            unicas: list[dict[str, Any]] = []
            for t in lista_t:
                sig = t["horarios_raw"]
                if sig not in horarios_vistos:
                    horarios_vistos.add(sig)
                    unicas.append(t)
                if len(unicas) >= 3:
                    break
            rep = unicas[0]
            score = (
                peso_cat.get(rep["categoria"], 10.0)
                + peso_rec.get(rep["status_recomendacao"], 0.0)
                + min(rep["destrava_count"], 8) * 6.0
            )
            grupos.append((score, chave, unicas))

        # Limitar aos 18 melhores grupos (foco principal do curso) para resposta instantânea (< 50ms)
        grupos.sort(key=lambda g: g[0], reverse=True)
        grupos = grupos[:18]

        por_id_obj = {t.id: t for t in self.turmas}
        melhores: list[tuple[float, list[dict[str, Any]]]] = []
        conjuntos_vistos: set[frozenset[str]] = set()
        passos = 0
        MAX_PASSOS = 4000

        def backtrack(
            idx: int,
            escolhidas: list[dict[str, Any]],
            creds: int,
            score_atual: float,
        ) -> None:
            nonlocal passos
            passos += 1
            if passos > MAX_PASSOS:
                return

            if creds >= min_creditos and escolhidas:
                assinatura = frozenset(t["codigo"] or t["disciplina"] for t in escolhidas)
                if assinatura not in conjuntos_vistos:
                    conjuntos_vistos.add(assinatura)
                    # Pequeno bônus por proximidade ao teto de créditos
                    score_final = score_atual + creds * 1.5
                    melhores.append((score_final, list(escolhidas)))

            if idx >= len(grupos) or len(escolhidas) >= max_disciplinas or creds >= max_creditos:
                return

            # Ramo 1: tentar incluir alguma turma deste grupo
            g_score, _, turmas_grupo = grupos[idx]
            for t_dict in turmas_grupo:
                c_t = t_dict["creditos"]
                if creds + c_t > max_creditos:
                    continue
                t_obj = por_id_obj.get(t_dict["id"])
                if not t_obj:
                    continue
                if any(turmas_conflitam(t_obj, por_id_obj[e["id"]]) for e in escolhidas):
                    continue
                escolhidas.append(t_dict)
                backtrack(idx + 1, escolhidas, creds + c_t, score_atual + g_score)
                escolhidas.pop()

            # Ramo 2: pular este grupo
            backtrack(idx + 1, escolhidas, creds, score_atual)

        backtrack(0, [], 0, 0.0)

        # Fallback: se nada atingiu min_creditos, tentar com min_creditos = 1
        if not melhores and min_creditos > 1:
            passos = 0
            min_creditos = 1
            backtrack(0, [], 0, 0.0)

        melhores.sort(key=lambda x: x[0], reverse=True)

        # Pool de disciplinas leves (Opções Limitadas e Livres com 0 recomendações ou poucas)
        pool_leves: list[dict[str, Any]] = []
        if completar_com_leves:
            pool_leves = [
                c
                for c in candidatas
                if c["horarios"]
                and c["creditos"] > 0
                and c["categoria"] in ("opcao_limitada", "livre")
                and c["status_recomendacao"] in ("sem_recomendacao", "ok")
            ]
            # Ordenar: 0 recomendações primeiro -> opção limitada antes de livre -> mais vagas -> menos créditos se empatar
            pool_leves.sort(
                key=lambda c: (
                    len(c["recomendacoes"]),
                    0 if c["categoria"] == "opcao_limitada" else 1,
                    -(c["vagas"] or 0),
                    c["creditos"],
                )
            )

        saida: list[dict[str, Any]] = []
        for idx_s, (_, base_lista) in enumerate(melhores[:limite_sugestoes], start=1):
            lista = [dict(t, preenchimento_leve=False) for t in base_lista]

            if completar_com_leves and pool_leves:
                creds_atual = sum(t["creditos"] for t in lista)
                chaves_usadas = {t["codigo"] or normalizar_texto(t["disciplina"]) for t in lista}
                for cand in pool_leves:
                    if creds_atual >= max_creditos or len(lista) >= max_disciplinas:
                        break
                    chave_c = cand["codigo"] or normalizar_texto(cand["disciplina"])
                    if chave_c in chaves_usadas:
                        continue
                    if creds_atual + cand["creditos"] > max_creditos:
                        continue
                    t_obj = por_id_obj.get(cand["id"])
                    if not t_obj:
                        continue
                    if any(turmas_conflitam(t_obj, por_id_obj[e["id"]]) for e in lista):
                        continue
                    lista.append(dict(cand, preenchimento_leve=True))
                    chaves_usadas.add(chave_c)
                    creds_atual += cand["creditos"]

            dias = sorted({h["dia"] for t in lista for h in t["horarios"]})
            saida.append(
                {
                    "opcao": idx_s,
                    "total_creditos": sum(t["creditos"] for t in lista),
                    "total_disciplinas": len(lista),
                    "dias": dias,
                    "obrigatorias_bcc": sum(1 for t in lista if t["categoria"] == "obrigatoria_bcc"),
                    "complementos_leves": sum(1 for t in lista if t.get("preenchimento_leve")),
                    "turmas": lista,
                }
            )
        return saida

    def resumo_progresso(
        self,
        historico: Optional[HistoricoSanitizado] = None,
        contar_em_curso: bool = True,
    ) -> dict[str, Any]:
        codigos_feitos, bases_feitas, nomes_feitos, _ = self._indices_historico(
            historico, contar_em_curso=contar_em_curso
        )
        ofertadas_cod = {t.codigo for t in self.turmas if t.codigo}
        ofertadas_nome = {t.disciplina_norm for t in self.turmas}

        resumo: dict[str, Any] = {
            "tem_historico": historico is not None and len(historico.disciplinas) > 0,
            "total_historico": len(historico.disciplinas) if historico else 0,
            "obrigatorias_bcc": {"feitas": 0, "total": 0, "pendentes": []},
            "obrigatorias_bct": {"feitas": 0, "total": 0, "pendentes": []},
            "opcoes_limitadas": {"feitas": 0, "total_rol": 0},
        }

        for g in self.grade:
            feita = self._disciplina_cumprida(
                g.codigo, g.nome_norm, codigos_feitos, bases_feitas, nomes_feitos
            )
            ofertada = (g.codigo in ofertadas_cod) or (g.nome_norm in ofertadas_nome)
            if g.categoria == "obrigatoria_bcc":
                resumo["obrigatorias_bcc"]["total"] += 1
                if feita:
                    resumo["obrigatorias_bcc"]["feitas"] += 1
                else:
                    resumo["obrigatorias_bcc"]["pendentes"].append(
                        {"codigo": g.codigo, "nome": g.nome, "ofertada_agora": ofertada}
                    )
            elif g.categoria == "obrigatoria_bct":
                resumo["obrigatorias_bct"]["total"] += 1
                if feita:
                    resumo["obrigatorias_bct"]["feitas"] += 1
                else:
                    resumo["obrigatorias_bct"]["pendentes"].append(
                        {"codigo": g.codigo, "nome": g.nome, "ofertada_agora": ofertada}
                    )
            elif g.categoria == "opcao_limitada":
                resumo["opcoes_limitadas"]["total_rol"] += 1
                if feita:
                    resumo["opcoes_limitadas"]["feitas"] += 1

        return resumo
