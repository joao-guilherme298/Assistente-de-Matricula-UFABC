// Motor de cruzamento, grafo de destravamento e sugestão de grades — 100% client-side (Multi-curso UFABC)

export function normalizarTexto(texto) {
  if (!texto) return "";
  return texto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function baseCodigo(codigo) {
  if (!codigo) return "";
  return codigo.split("-")[0].trim().toUpperCase();
}

export function horaParaMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

export function horariosConflitam(h1, h2) {
  if (h1.dia !== h2.dia) return false;
  if (
    (h1.semanalidade === "quinzenal_1" && h2.semanalidade === "quinzenal_2") ||
    (h1.semanalidade === "quinzenal_2" && h2.semanalidade === "quinzenal_1")
  ) {
    return false;
  }
  return horaParaMin(h1.inicio) < horaParaMin(h2.fim) && horaParaMin(h2.inicio) < horaParaMin(h1.fim);
}

export function turmasConflitam(t1, t2) {
  for (const h1 of t1.horarios || []) {
    for (const h2 of t2.horarios || []) {
      if (horariosConflitam(h1, h2)) return true;
    }
  }
  return false;
}

const BASE_NOMES = {
  bct: "BC&T",
  bch: "BC&H",
  lcne: "LCNE",
  lch: "LCH",
};

export class MotorMatriculaWeb {
  constructor(turmas, catalogo, gradeBcc, gradesCursos = null) {
    this.turmas = turmas.map((t) => ({
      ...t,
      disciplina_norm: t.disciplina_norm || normalizarTexto(t.disciplina),
    }));
    this.catalogo = catalogo.map((c) => ({
      ...c,
      nome_norm: normalizarTexto(c.nome),
    }));
    this.gradeBcc = (gradeBcc || []).map((g) => ({
      ...g,
      nome_norm: normalizarTexto(g.nome),
    }));
    this.gradesCursos = gradesCursos || { bases: {}, cursos: {} };

    this.catPorCod = new Map();
    this.catPorBase = new Map();
    this.catPorNome = new Map();
    for (const c of this.catalogo) {
      if (c.codigo) {
        this.catPorCod.set(c.codigo, c);
        this.catPorBase.set(baseCodigo(c.codigo), c);
      }
      if (c.nome_norm) this.catPorNome.set(c.nome_norm, c);
    }

    // Cache de índices por curso selecionado
    this._cacheCurso = new Map();
  }

  buscarCatalogo(codigo, nomeNorm) {
    if (codigo && this.catPorCod.has(codigo)) return this.catPorCod.get(codigo);
    if (nomeNorm && this.catPorNome.has(nomeNorm)) return this.catPorNome.get(nomeNorm);
    const base = baseCodigo(codigo);
    if (base && this.catPorBase.has(base)) return this.catPorBase.get(base);
    return null;
  }

  listarCursosDisponiveis() {
    const cursos = new Set([
      "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
      "BACHARELADO EM CIÊNCIA E TECNOLOGIA",
      ...Object.keys(this.gradesCursos.cursos || {}),
    ]);
    for (const t of this.turmas) {
      for (const c of t.cursos_oferta || []) {
        if (c && c.toUpperCase() !== "ENGENHARIAS") cursos.add(c);
      }
    }
    return [...cursos].sort((a, b) => a.localeCompare(b, "pt-BR"));
  }

  _resolverNomeCodigo(cod) {
    const cat = this.buscarCatalogo(cod, "");
    if (cat) return cat.nome;
    const t = this.turmas.find((x) => x.codigo === cod || baseCodigo(x.codigo) === baseCodigo(cod));
    return t ? t.disciplina : cod;
  }

  obterConfigCurso(cursoNome) {
    const chave = (cursoNome || "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO").trim().toUpperCase();
    if (this._cacheCurso.has(chave)) return this._cacheCurso.get(chave);

    const info = (this.gradesCursos.cursos || {})[chave] || null;
    const tipoBase = info ? info.tipo_base : "nenhum";
    const sigla = info ? info.sigla : chave;
    const baseCodigos = tipoBase !== "nenhum" ? (this.gradesCursos.bases || {})[tipoBase] || [] : [];
    const obrigCodigos = info ? info.obrigatorias || [] : [];
    const olCodigos = info ? info.opcoes_limitadas || [] : [];

    // Construir conjuntos rápidos (código exato + código-base + nome normalizado)
    const montarIndice = (listaCod) => {
      const cods = new Set();
      const bases = new Set();
      const nomes = new Set();
      const itens = [];
      for (const cod of listaCod) {
        const nome = this._resolverNomeCodigo(cod);
        const nomeNorm = normalizarTexto(nome);
        cods.add(cod);
        bases.add(baseCodigo(cod));
        if (nomeNorm) nomes.add(nomeNorm);
        itens.push({ codigo: cod, nome, nome_norm: nomeNorm });
      }
      return { cods, bases, nomes, itens };
    };

    const idxObrig = montarIndice(obrigCodigos);
    const idxBase = montarIndice(baseCodigos);
    const idxOl = montarIndice(olCodigos);

    // Grafo de destravamento específico para este curso
    const destravaMapa = new Map();
    const todasDaGrade = [
      ...idxObrig.itens.map((x) => ({ ...x, categoria: "obrigatoria_bcc" })),
      ...idxBase.itens.map((x) => ({ ...x, categoria: "obrigatoria_bct" })),
      ...idxOl.itens.map((x) => ({ ...x, categoria: "opcao_limitada" })),
    ];

    for (const g of todasDaGrade) {
      const cat = this.buscarCatalogo(g.codigo, g.nome_norm);
      if (!cat || !cat.recomendacoes || !cat.recomendacoes.length) continue;
      for (const rec of cat.recomendacoes) {
        const recNorm = normalizarTexto(rec);
        const chavesRec = new Set([recNorm]);
        if (recNorm.endsWith(" i")) chavesRec.add(recNorm.slice(0, -2).trim());
        const catRec = this.catPorNome.get(recNorm);
        if (catRec && catRec.codigo) {
          chavesRec.add(catRec.codigo);
          chavesRec.add(baseCodigo(catRec.codigo));
        }
        const alvo = { codigo: g.codigo, nome: g.nome, categoria: g.categoria };
        for (const ch of chavesRec) {
          if (!destravaMapa.has(ch)) destravaMapa.set(ch, []);
          const lista = destravaMapa.get(ch);
          if (!lista.some((x) => x.nome === alvo.nome)) lista.push(alvo);
        }
      }
    }

    const cfg = {
      curso: chave,
      sigla,
      tipoBase,
      labelBase: BASE_NOMES[tipoBase] || "",
      ehIngresso: tipoBase === "nenhum",
      temPpcObrig: obrigCodigos.length > 0,
      temBase: baseCodigos.length > 0,
      temOl: olCodigos.length > 0,
      idxObrig,
      idxBase,
      idxOl,
      destravaMapa,
    };
    this._cacheCurso.set(chave, cfg);
    return cfg;
  }

  _pertenceAoIndice(codigo, nomeNorm, idx) {
    if (codigo && idx.cods.has(codigo)) return true;
    if (nomeNorm && idx.nomes.has(nomeNorm)) return true;
    const base = baseCodigo(codigo);
    if (base && idx.bases.has(base)) return true;
    return false;
  }

  _categoriaParaCurso(turma, cfg) {
    // Se for curso de ingresso (ex: BC&T, BC&H, LCNE, LCH), suas obrigatórias vão em obrigatoria_bct
    if (cfg.ehIngresso) {
      if (this._pertenceAoIndice(turma.codigo, turma.disciplina_norm, cfg.idxObrig)) return "obrigatoria_bct";
      if (this._pertenceAoIndice(turma.codigo, turma.disciplina_norm, cfg.idxOl)) return "opcao_limitada";
      const cursosT = new Set((turma.cursos_oferta || []).map((c) => c.toUpperCase()));
      if (!cfg.temPpcObrig && cursosT.has(cfg.curso)) return "obrigatoria_bct";
      return "livre";
    }

    // Curso específico (ex: BCC, Eng. Informação, BCD, Economia...)
    if (this._pertenceAoIndice(turma.codigo, turma.disciplina_norm, cfg.idxObrig)) return "obrigatoria_bcc";
    if (this._pertenceAoIndice(turma.codigo, turma.disciplina_norm, cfg.idxBase)) return "obrigatoria_bct";
    if (this._pertenceAoIndice(turma.codigo, turma.disciplina_norm, cfg.idxOl)) return "opcao_limitada";

    // Fallback pela oferta PROGRAD se o PPC desse curso não tinha códigos (ex: Economia)
    if (!cfg.temPpcObrig) {
      const cursosT = new Set((turma.cursos_oferta || []).map((c) => c.toUpperCase()));
      if (cursosT.has(cfg.curso)) return "obrigatoria_bcc";
    }
    return "livre";
  }

  _indicesHistorico(historico, contarEmCurso = true) {
    const codigosFeitos = new Set();
    const basesFeitas = new Set();
    const nomesFeitos = new Set();
    const statusMap = new Map();

    if (!historico || !historico.disciplinas) {
      return { codigosFeitos, basesFeitas, nomesFeitos, statusMap };
    }

    const validos = new Set(["aprovado", "equivalencia"]);
    if (contarEmCurso) validos.add("em_curso");

    for (const item of historico.disciplinas) {
      const nomeNorm = item.nome_norm || normalizarTexto(item.nome);
      if (item.codigo) {
        statusMap.set(item.codigo, item.status);
        statusMap.set(baseCodigo(item.codigo), item.status);
      }
      if (nomeNorm) statusMap.set(nomeNorm, item.status);

      if (validos.has(item.status)) {
        if (item.codigo) {
          codigosFeitos.add(item.codigo);
          basesFeitas.add(baseCodigo(item.codigo));
        }
        if (nomeNorm) nomesFeitos.add(nomeNorm);
      }
    }

    return { codigosFeitos, basesFeitas, nomesFeitos, statusMap };
  }

  _disciplinaCumprida(codigo, nomeNorm, idx) {
    if (codigo && idx.codigosFeitos.has(codigo)) return true;
    if (nomeNorm && idx.nomesFeitos.has(nomeNorm)) return true;
    const base = baseCodigo(codigo);
    if (base && idx.basesFeitas.has(base)) return true;
    return false;
  }

  _disciplinasDestravadas(codigo, nomeNorm, idxHist, cfg) {
    const candidatos = [];
    const vistos = new Set();
    for (const ch of [codigo, baseCodigo(codigo), nomeNorm]) {
      if (!ch || !cfg.destravaMapa.has(ch)) continue;
      for (const item of cfg.destravaMapa.get(ch)) {
        if (vistos.has(item.nome)) continue;
        vistos.add(item.nome);
        if (!this._disciplinaCumprida(item.codigo, normalizarTexto(item.nome), idxHist)) {
          candidatos.push(item);
        }
      }
    }
    const ordem = { obrigatoria_bcc: 0, obrigatoria_bct: 1, opcao_limitada: 2 };
    candidatos.sort((a, b) => (ordem[a.categoria] ?? 9) - (ordem[b.categoria] ?? 9) || a.nome.localeCompare(b.nome));
    return candidatos;
  }

  _avaliarRecomendacoes(recomendacoes, idxHist, temHistorico) {
    if (!recomendacoes || !recomendacoes.length) return { status: "sem_recomendacao", detalhes: [] };

    const detalhes = [];
    let cumpridas = 0;
    for (const rec of recomendacoes) {
      const recNorm = normalizarTexto(rec);
      const catRec = this.catPorNome.get(recNorm);
      let ok = false;
      if (temHistorico) {
        const recSemI = recNorm.endsWith(" i") ? recNorm.slice(0, -2).trim() : "";
        if (idxHist.nomesFeitos.has(recNorm) || (recSemI && idxHist.nomesFeitos.has(recSemI))) {
          ok = true;
        } else if (
          catRec &&
          (idxHist.codigosFeitos.has(catRec.codigo) || idxHist.basesFeitas.has(baseCodigo(catRec.codigo)))
        ) {
          ok = true;
        }
      }
      if (ok) cumpridas++;
      detalhes.push({ nome: rec, cumprida: ok });
    }

    if (!temHistorico) return { status: "desconhecido", detalhes };
    if (cumpridas === recomendacoes.length) return { status: "ok", detalhes };
    if (cumpridas > 0) return { status: "parcial", detalhes };
    return { status: "pendente", detalhes };
  }

  analisarOferta({
    historico = null,
    contarEmCurso = true,
    curso = "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
    campus = "Santo André",
    turno = "Matutino",
    categoria = "Todas",
    ocultarCursadas = true,
    apenasRecomendacoesOk = false,
    diasPermitidos = null,
    busca = "",
  } = {}) {
    const cfg = this.obterConfigCurso(curso);
    const idxHist = this._indicesHistorico(historico, contarEmCurso);
    const temHistorico = Boolean(historico && historico.disciplinas && historico.disciplinas.length > 0);
    const buscaNorm = normalizarTexto(busca);
    const diasSet = diasPermitidos ? new Set(diasPermitidos) : null;

    const ordemCat = { obrigatoria_bcc: 0, obrigatoria_bct: 1, opcao_limitada: 2, livre: 3 };
    const ordemRec = { sem_recomendacao: 0, ok: 0, parcial: 1, desconhecido: 2, pendente: 3 };

    const resultados = [];
    for (const t of this.turmas) {
      if (campus && campus !== "Todos" && t.campus !== campus) continue;
      if (turno && turno !== "Todos" && t.turno !== turno) continue;
      if (diasSet && t.horarios && t.horarios.length) {
        if (t.horarios.some((h) => !diasSet.has(h.dia))) continue;
      }

      const catTurma = this._categoriaParaCurso(t, cfg);
      if (categoria && categoria !== "Todas" && catTurma !== categoria) continue;

      const jaCursada = this._disciplinaCumprida(t.codigo, t.disciplina_norm, idxHist);
      if (ocultarCursadas && jaCursada) continue;

      const statusHist =
        idxHist.statusMap.get(t.codigo) ||
        idxHist.statusMap.get(t.disciplina_norm) ||
        idxHist.statusMap.get(baseCodigo(t.codigo)) ||
        "nao_cursada";

      const catInfo = this.buscarCatalogo(t.codigo, t.disciplina_norm);
      const recs = catInfo ? catInfo.recomendacoes : [];
      const { status: statusRec, detalhes: recsDetalhe } = this._avaliarRecomendacoes(recs, idxHist, temHistorico);

      if (apenasRecomendacoesOk && statusRec !== "sem_recomendacao" && statusRec !== "ok") continue;

      if (buscaNorm) {
        const alvo = normalizarTexto(`${t.codigo} ${t.disciplina} ${t.docente_teoria} ${t.docente_pratica} ${t.id}`);
        if (!alvo.includes(buscaNorm)) continue;
      }

      const destrava = this._disciplinasDestravadas(t.codigo, t.disciplina_norm, idxHist, cfg);

      resultados.push({
        ...t,
        creditos: t.creditos || (catInfo ? catInfo.creditos : 0),
        categoria: catTurma,
        ja_cursada: jaCursada,
        status_historico: statusHist,
        status_recomendacao: statusRec,
        recomendacoes: recsDetalhe,
        destrava: destrava.map((d) => d.nome),
        destrava_count: destrava.length,
        _sortCat: ordemCat[catTurma] ?? 9,
        _sortRec: ordemRec[statusRec] ?? 9,
      });
    }

    resultados.sort(
      (a, b) =>
        a._sortCat - b._sortCat ||
        a._sortRec - b._sortRec ||
        b.destrava_count - a.destrava_count ||
        a.disciplina_norm.localeCompare(b.disciplina_norm) ||
        (a.turma || "").localeCompare(b.turma || "")
    );
    return resultados;
  }

  resumoProgresso(historico = null, contarEmCurso = true, curso = "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO") {
    const cfg = this.obterConfigCurso(curso);
    const idxHist = this._indicesHistorico(historico, contarEmCurso);
    const ofertadasCod = new Set(this.turmas.map((t) => t.codigo).filter(Boolean));
    const ofertadasBase = new Set(this.turmas.map((t) => baseCodigo(t.codigo)).filter(Boolean));
    const ofertadasNome = new Set(this.turmas.map((t) => t.disciplina_norm));

    const estaOfertada = (g) =>
      ofertadasCod.has(g.codigo) || ofertadasBase.has(baseCodigo(g.codigo)) || ofertadasNome.has(g.nome_norm);

    const contarLista = (itens) => {
      let feitas = 0;
      const pendentes = [];
      for (const g of itens) {
        if (this._disciplinaCumprida(g.codigo, g.nome_norm, idxHist)) {
          feitas++;
        } else {
          pendentes.push({ codigo: g.codigo, nome: g.nome, ofertada_agora: estaOfertada(g) });
        }
      }
      return { feitas, total: itens.length, pendentes };
    };

    const obrigCurso = cfg.ehIngresso ? { feitas: 0, total: 0, pendentes: [] } : contarLista(cfg.idxObrig.itens);
    const obrigBase = cfg.ehIngresso ? contarLista(cfg.idxObrig.itens) : contarLista(cfg.idxBase.itens);

    let olFeitas = 0;
    for (const g of cfg.idxOl.itens) {
      if (this._disciplinaCumprida(g.codigo, g.nome_norm, idxHist)) olFeitas++;
    }

    // Somar créditos reais e CH de Extensão do histórico (por categoria OBR / OL / LIV / ATC)
    const creditosHist = { total: 0, obr: 0, ol: 0, liv: 0, atc: 0, ch_ext: 0 };
    if (historico && historico.disciplinas) {
      const validos = new Set(["aprovado", "equivalencia"]);
      if (contarEmCurso) validos.add("em_curso");
      for (const item of historico.disciplinas) {
        if (!validos.has(item.status)) continue;
        let cred = item.creditos || 0;
        if (!cred) {
          const catInfo = this.buscarCatalogo(item.codigo, item.nome_norm || normalizarTexto(item.nome));
          if (catInfo) cred = catInfo.creditos || 0;
        }
        const chExt = item.ch_ext || 0;
        creditosHist.total += cred;
        creditosHist.ch_ext += chExt;
        const chCat = (item.categoria_hist || "").toUpperCase();
        if (chCat === "OBR") creditosHist.obr += cred;
        else if (chCat === "OL") creditosHist.ol += cred;
        else if (chCat === "LIV") creditosHist.liv += cred;
        else if (chCat === "ATC") creditosHist.atc += cred;
      }
    }

    return {
      curso_sigla: cfg.sigla,
      eh_ingresso: cfg.ehIngresso,
      label_base: cfg.ehIngresso ? cfg.sigla : cfg.labelBase,
      tem_historico: Boolean(historico && historico.disciplinas && historico.disciplinas.length > 0),
      total_historico: historico && historico.disciplinas ? historico.disciplinas.length : 0,
      obrigatorias_curso: obrigCurso,
      obrigatorias_base: obrigBase,
      opcoes_limitadas: { feitas: olFeitas, total_rol: cfg.idxOl.itens.length },
      creditos_historico: creditosHist,
      metas_ppc:
        cfg.curso === "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO"
          ? { obr: 204, ol: 24, liv: 12, ch_ext: 320 }
          : null,
    };
  }

  sugerirGrades({
    historico = null,
    contarEmCurso = true,
    curso = "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
    campus = "Santo André",
    turno = "Matutino",
    diasPermitidos = null,
    apenasRecomendacoesOk = true,
    minCreditos = 12,
    maxCreditos = 20,
    maxDisciplinas = 5,
    completarComLeves = false,
    turmasFixas = [],
    limiteSugestoes = 3,
  } = {}) {
    const candidatas = this.analisarOferta({
      historico,
      contarEmCurso,
      curso,
      campus,
      turno,
      categoria: "Todas",
      ocultarCursadas: true,
      apenasRecomendacoesOk,
      diasPermitidos,
    });

    const fixasList = (turmasFixas || []).map((t) => ({ ...t, fixa: true }));
    const chavesFixas = new Set(fixasList.map((t) => t.codigo || normalizarTexto(t.disciplina)));
    const credsFixos = fixasList.reduce((acc, t) => acc + (t.creditos || 0), 0);

    const pesoCat = { obrigatoria_bcc: 100, obrigatoria_bct: 80, opcao_limitada: 45, livre: 15 };
    const pesoRec = { sem_recomendacao: 15, ok: 15, parcial: 3, desconhecido: 5, pendente: -20 };

    const porDisc = new Map();
    for (const c of candidatas) {
      if (!c.horarios || !c.horarios.length || c.creditos <= 0) continue;
      const chave = c.codigo || c.disciplina_norm;
      if (chavesFixas.has(chave)) continue;
      if (!porDisc.has(chave)) porDisc.set(chave, []);
      porDisc.get(chave).push(c);
    }

    let grupos = [];
    for (const [chave, lista] of porDisc.entries()) {
      const horariosVistos = new Set();
      const unicas = [];
      for (const t of lista) {
        if (!horariosVistos.has(t.horarios_raw)) {
          horariosVistos.add(t.horarios_raw);
          unicas.push(t);
        }
        if (unicas.length >= 3) break;
      }
      const rep = unicas[0];
      const score =
        (pesoCat[rep.categoria] ?? 10) +
        (pesoRec[rep.status_recomendacao] ?? 0) +
        Math.min(rep.destrava_count, 8) * 6;
      grupos.push({ score, chave, turmas: unicas });
    }

    grupos.sort((a, b) => b.score - a.score);
    grupos = grupos.slice(0, 18);

    const melhores = [];
    const conjuntosVistos = new Set();
    let passos = 0;
    const MAX_PASSOS = 4000;
    let minCredAlvo = minCreditos;

    const backtrack = (idx, escolhidas, creds, scoreAtual) => {
      passos++;
      if (passos > MAX_PASSOS) return;

      if (creds >= minCredAlvo && escolhidas.length) {
        const sig = escolhidas
          .map((t) => t.codigo || t.disciplina)
          .sort()
          .join("|");
        if (!conjuntosVistos.has(sig)) {
          conjuntosVistos.add(sig);
          melhores.push({ score: scoreAtual + creds * 1.5, lista: [...escolhidas] });
        }
      }

      if (idx >= grupos.length || escolhidas.length >= maxDisciplinas || creds >= maxCreditos) return;

      const g = grupos[idx];
      for (const t of g.turmas) {
        if (creds + t.creditos > maxCreditos) continue;
        if (escolhidas.some((e) => turmasConflitam(t, e))) continue;
        escolhidas.push(t);
        backtrack(idx + 1, escolhidas, creds + t.creditos, scoreAtual + g.score);
        escolhidas.pop();
      }
      backtrack(idx + 1, escolhidas, creds, scoreAtual);
    };

    backtrack(0, [...fixasList], credsFixos, 0);
    if (!melhores.length && minCredAlvo > 1) {
      passos = 0;
      minCredAlvo = 1;
      backtrack(0, [...fixasList], credsFixos, 0);
    }

    melhores.sort((a, b) => b.score - a.score);

    let poolLeves = [];
    if (completarComLeves) {
      poolLeves = candidatas
        .filter(
          (c) =>
            c.horarios &&
            c.horarios.length &&
            c.creditos > 0 &&
            (c.categoria === "opcao_limitada" || c.categoria === "livre") &&
            (c.status_recomendacao === "sem_recomendacao" || c.status_recomendacao === "ok")
        )
        .sort(
          (a, b) =>
            a.recomendacoes.length - b.recomendacoes.length ||
            (a.categoria === "opcao_limitada" ? 0 : 1) - (b.categoria === "opcao_limitada" ? 0 : 1) ||
            (b.vagas || 0) - (a.vagas || 0) ||
            a.creditos - b.creditos
        );
    }

    return melhores.slice(0, limiteSugestoes).map((m, idxS) => {
      const lista = m.lista.map((t) => ({ ...t, preenchimento_leve: false }));
      if (completarComLeves && poolLeves.length) {
        let credsAtual = lista.reduce((acc, t) => acc + t.creditos, 0);
        const usadas = new Set(lista.map((t) => t.codigo || t.disciplina_norm));
        for (const cand of poolLeves) {
          if (credsAtual >= maxCreditos || lista.length >= maxDisciplinas) break;
          const ch = cand.codigo || cand.disciplina_norm;
          if (usadas.has(ch)) continue;
          if (credsAtual + cand.creditos > maxCreditos) continue;
          if (lista.some((e) => turmasConflitam(cand, e))) continue;
          lista.push({ ...cand, preenchimento_leve: true });
          usadas.add(ch);
          credsAtual += cand.creditos;
        }
      }
      return {
        opcao: idxS + 1,
        total_creditos: lista.reduce((acc, t) => acc + t.creditos, 0),
        total_disciplinas: lista.length,
        obrigatorias_curso: lista.filter((t) => t.categoria === "obrigatoria_bcc" || t.categoria === "obrigatoria_bct").length,
        turmas: lista,
      };
    });
  }
}
