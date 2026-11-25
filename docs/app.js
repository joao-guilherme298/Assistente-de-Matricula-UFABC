import { MotorMatriculaWeb, horaParaMin, horariosConflitam } from "./engine.js";
import { exportarGradeICS, exportarGradePNG } from "./exportar.js";
import { sanitizarPdfHistoricoBrowser, sanitizarTextoHistorico } from "./historico_parser.js";

const DIAS = [
  { key: "segunda", label: "Seg" },
  { key: "terca", label: "Ter" },
  { key: "quarta", label: "Qua" },
  { key: "quinta", label: "Qui" },
  { key: "sexta", label: "Sex" },
  { key: "sabado", label: "Sáb" },
];

const HORAS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
const CORES = ["#2563eb", "#7c3aed", "#0891b2", "#059669", "#d97706", "#db2777", "#4f46e5", "#0d9488"];

const CAT_LABELS = {
  obrigatoria_bcc: "Obrigatória BCC",
  obrigatoria_bct: "Obrigatória BC&T",
  opcao_limitada: "Opção Limitada",
  livre: "Livre",
};

const REC_LABELS = {
  sem_recomendacao: "🟢 Sem recomendação",
  ok: "🟢 Recomendações OK",
  parcial: "🟡 Parcial",
  pendente: "🔴 Falta recomendação",
  desconhecido: "⚪ Importe histórico p/ checar",
};

let motor = null;
let metaDados = null;
let historico = null;
let turmasVisiveis = [];
let diasAtivos = new Set(DIAS.map((d) => d.key));
let planoAtual = "A";
let semanaVisual = "todas";
let planos = { A: new Map(), B: new Map(), C: new Map() };
let ultimoProgresso = null;

function selecionadas() {
  return planos[planoAtual];
}

function chaveDisciplina(t) {
  return t.codigo || t.disciplina;
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3200);
}

function conflitoComSelecionadas(turma) {
  const conflitos = [];
  for (const sel of selecionadas().values()) {
    if (sel.id === turma.id) continue;
    if (chaveDisciplina(sel) === chaveDisciplina(turma)) continue;
    for (const h1 of turma.horarios || []) {
      for (const h2 of sel.horarios || []) {
        if (horariosConflitam(h1, h2)) {
          conflitos.push(sel.disciplina);
          break;
        }
      }
    }
  }
  return [...new Set(conflitos)];
}

function salvarPlanosLocal() {
  localStorage.setItem(
    "ufabc_web_planos_v1",
    JSON.stringify({
      planoAtual,
      A: [...planos.A.values()],
      B: [...planos.B.values()],
      C: [...planos.C.values()],
    })
  );
}

function restaurarEstadoLocal() {
  try {
    const rawHist = localStorage.getItem("ufabc_web_historico_v1");
    if (rawHist) historico = JSON.parse(rawHist);
  } catch (_) {}
  try {
    const rawPlanos = localStorage.getItem("ufabc_web_planos_v1");
    if (rawPlanos) {
      const obj = JSON.parse(rawPlanos);
      ["A", "B", "C"].forEach((k) => (obj[k] || []).forEach((t) => planos[k].set(t.id, t)));
      if (obj.planoAtual && planos[obj.planoAtual]) planoAtual = obj.planoAtual;
      atualizarAbasPlano();
    }
  } catch (_) {}
}

function atualizarAbasPlano() {
  document.querySelectorAll("#planTabs .plan-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.plan === planoAtual);
  });
}

function atualizarMetaUI() {
  if (!metaDados) return;
  const histTxt =
    historico && historico.disciplinas.length
      ? `Histórico local: ${historico.disciplinas.length} disciplinas`
      : "Histórico não importado";
  document.getElementById("metaInfo").textContent =
    `🔒 100% no navegador • Oferta: ${metaDados.oferta_arquivo} • ${metaDados.total_turmas} turmas • ${histTxt}`;
}

function formatarNomeCurso(c) {
  return (c || "")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (l) => l.toUpperCase())
    .replace(/\b(Em|De|Da|Do|Das|Dos|E)\b/g, (w) => w.toLowerCase())
    .replace(/^./, (l) => l.toUpperCase());
}

function cursoAtual() {
  return document.getElementById("fCurso").value || "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO";
}

function labelCategoria(cat) {
  if (!ultimoProgresso) return CAT_LABELS[cat] || cat;
  if (cat === "obrigatoria_bcc") return `Obrigatória ${ultimoProgresso.curso_sigla}`;
  if (cat === "obrigatoria_bct") return `Obrigatória ${ultimoProgresso.label_base || "Base"}`;
  return CAT_LABELS[cat] || cat;
}

function popularCursos(listaCursos) {
  const select = document.getElementById("fCurso");
  const salvo = localStorage.getItem("ufabc_web_curso_v1") || "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO";
  select.innerHTML = listaCursos
    .map((c) => `<option value="${c}">${formatarNomeCurso(c)}</option>`)
    .join("");
  if (listaCursos.includes(salvo)) {
    select.value = salvo;
  }
}

function atualizarTela() {
  if (!motor) return;
  const contarEmCurso = document.getElementById("fContarEmCurso").checked;
  const curso = cursoAtual();
  localStorage.setItem("ufabc_web_curso_v1", curso);

  turmasVisiveis = motor.analisarOferta({
    historico,
    contarEmCurso,
    curso,
    campus: document.getElementById("fCampus").value,
    turno: document.getElementById("fTurno").value,
    categoria: document.getElementById("fCategoria").value,
    ocultarCursadas: document.getElementById("fOcultarCursadas").checked,
    apenasRecomendacoesOk: document.getElementById("fApenasRecOk").checked,
    diasPermitidos: [...diasAtivos],
    busca: document.getElementById("fBusca").value.trim(),
  });
  ultimoProgresso = motor.resumoProgresso(historico, contarEmCurso, curso);

  atualizarMetaUI();
  renderProgresso();
  renderListaTurmas();
  renderGradeSemanal();
}

function renderProgresso() {
  if (!ultimoProgresso) return;
  const p = ultimoProgresso;
  const temCursoObrig = p.obrigatorias_curso.total > 0;
  const temBaseObrig = p.obrigatorias_base.total > 0;
  const temOl = p.opcoes_limitadas.total_rol > 0;

  document.getElementById("cardStatBcc").style.display = temCursoObrig ? "" : "none";
  document.getElementById("cardStatBct").style.display = temBaseObrig ? "" : "none";
  document.getElementById("cardStatOl").style.display = temOl ? "" : "none";
  document.getElementById("btnVerPendentes").style.display = temCursoObrig || temBaseObrig ? "" : "none";

  document.getElementById("labelStatCurso").textContent = `Obrigatórias — ${p.curso_sigla}`;
  document.getElementById("statBcc").textContent = `${p.obrigatorias_curso.feitas} / ${p.obrigatorias_curso.total}`;
  document.getElementById("statBccSub").textContent = p.tem_historico
    ? `${p.obrigatorias_curso.pendentes.length} pendentes (${p.obrigatorias_curso.pendentes.filter((x) => x.ofertada_agora).length} ofertadas agora)`
    : "Importe seu histórico para calcular";

  document.getElementById("labelStatBase").textContent = `Obrigatórias — ${p.label_base || "Base"}`;
  document.getElementById("statBct").textContent = `${p.obrigatorias_base.feitas} / ${p.obrigatorias_base.total}`;
  document.getElementById("statBctSub").textContent = p.tem_historico
    ? `${p.obrigatorias_base.pendentes.length} pendentes (${p.obrigatorias_base.pendentes.filter((x) => x.ofertada_agora).length} ofertadas agora)`
    : p.eh_ingresso
    ? "Curso de ingresso"
    : "Ciclo básico";

  document.getElementById("labelStatOl").textContent = `Opções Limitadas — ${p.curso_sigla}`;
  document.getElementById("statOl").textContent = `${p.opcoes_limitadas.feitas}`;
  document.getElementById("statOlSub").textContent = `de ${p.opcoes_limitadas.total_rol} no rol do curso`;

  // Atualizar labels do filtro de categoria dinamicamente
  const selCat = document.getElementById("fCategoria");
  if (selCat && selCat.options.length >= 4) {
    selCat.options[1].text = p.eh_ingresso ? "Do Curso" : `Obrigatórias ${p.curso_sigla}`;
    selCat.options[2].text = `Obrigatórias ${p.label_base || "Base"}`;
  }
}

function agruparPorDisciplina(lista) {
  const grupos = new Map();
  for (const t of lista) {
    const chave = chaveDisciplina(t);
    if (!grupos.has(chave)) grupos.set(chave, { rep: t, turmas: [] });
    grupos.get(chave).turmas.push(t);
  }
  return [...grupos.values()];
}

function renderListaTurmas() {
  const container = document.getElementById("listaTurmas");
  const grupos = agruparPorDisciplina(turmasVisiveis);
  document.getElementById("contadorTurmas").textContent =
    `${grupos.length} disciplina${grupos.length === 1 ? "" : "s"} (${turmasVisiveis.length} turmas)`;

  if (!grupos.length) {
    container.innerHTML = `<div style="padding:24px;text-align:center;color:var(--muted);">Nenhuma disciplina encontrada com esses filtros.</div>`;
    return;
  }

  const selMap = selecionadas();
  const discsSel = new Map();
  for (const s of selMap.values()) discsSel.set(chaveDisciplina(s), s.id);

  const fragment = document.createDocumentFragment();
  grupos.slice(0, 120).forEach(({ rep, turmas }) => {
    const turmaSelId = discsSel.get(chaveDisciplina(rep));
    const card = document.createElement("div");
    card.className = `turma-card ${turmaSelId ? "selected" : ""}`;

    const recsHtml = rep.recomendacoes.length
      ? `<div class="recs-box"><strong>Recomendações:</strong> ${rep.recomendacoes
          .map((r) => `<span class="${r.cumprida ? "rec-item-ok" : "rec-item-miss"}">${r.cumprida ? "✓" : "•"} ${r.nome}</span>`)
          .join("")}</div>`
      : "";

    const unlockHtml =
      rep.destrava_count > 0
        ? `<span class="badge badge-unlock" title="Destrava: ${rep.destrava.join(", ")}">🔓 Destrava ${rep.destrava_count}</span>`
        : "";

    card.innerHTML = `
      <div class="turma-top">
        <div>
          <div class="turma-title turma-title-link" title="Clique para ver objetivos e ementa">${rep.disciplina} <span style="font-size:0.74rem;color:var(--muted);font-weight:500;">📖</span></div>
          <div class="turma-code">${rep.codigo || "—"} • TPEI ${rep.tpi || "—"} (${rep.creditos} créd.) • ${turmas.length} turma${turmas.length === 1 ? "" : "s"}</div>
        </div>
      </div>
      <div class="badges">
        <span class="badge cat-${rep.categoria}">${labelCategoria(rep.categoria)}</span>
        <span class="badge rec-${rep.status_recomendacao}">${REC_LABELS[rep.status_recomendacao] || rep.status_recomendacao}</span>
        ${unlockHtml}
        ${rep.status_historico === "em_curso" ? `<span class="badge" style="background:rgba(59,130,246,0.2);color:#93c5fd;">Em curso</span>` : ""}
      </div>
      ${recsHtml}
      <div class="turmas-sublist"></div>
    `;

    card.querySelector(".turma-title-link").addEventListener("click", () => abrirModalEmenta(rep));

    const sublist = card.querySelector(".turmas-sublist");
    turmas.forEach((t) => {
      const isSel = selMap.has(t.id);
      const conflitos = isSel ? [] : conflitoComSelecionadas(t);
      const outraTurmaDaMesma = Boolean(turmaSelId && turmaSelId !== t.id);

      const row = document.createElement("div");
      row.className = `turma-row ${isSel ? "selected" : ""} ${conflitos.length ? "conflict" : ""}`;

      const btnLabel = isSel ? "✓ Remover" : conflitos.length ? "Conflito" : outraTurmaDaMesma ? "Trocar" : "+ Adicionar";
      const btnClass = isSel ? "btn-danger btn-sm" : outraTurmaDaMesma ? "btn-secondary btn-sm" : "btn-primary btn-sm";
      const docentes = [t.docente_teoria, t.docente_pratica].filter(Boolean).join(" | ") || "Docente não informado";

      row.innerHTML = `
        <div class="turma-row-info">
          <div class="turma-row-main">${t.turma || t.turno} • ${t.campus} • ${t.vagas ?? "?"} vagas <span style="font-family:monospace;font-weight:400;color:var(--muted);">(${t.id})</span></div>
          <div class="turma-row-sub">🕒 ${t.horarios_raw || "Horário não informado"}</div>
          <div class="turma-row-sub">👩‍🏫 ${docentes}</div>
          ${conflitos.length ? `<div class="turma-row-sub" style="color:#fca5a5;">⚠️ Conflita com: ${conflitos.join(", ")}</div>` : ""}
        </div>
        <button class="${btnClass}" ${!isSel && conflitos.length ? "disabled" : ""}>${btnLabel}</button>
      `;

      row.querySelector("button").addEventListener("click", () => toggleTurma(t));
      sublist.appendChild(row);
    });

    fragment.appendChild(card);
  });

  container.innerHTML = "";
  container.appendChild(fragment);
}

function toggleTurma(turma) {
  const selMap = selecionadas();
  if (selMap.has(turma.id)) {
    selMap.delete(turma.id);
  } else {
    const conflitos = conflitoComSelecionadas(turma);
    if (conflitos.length) {
      toast(`Conflito de horário com: ${conflitos.join(", ")}`);
      return;
    }
    const discKey = chaveDisciplina(turma);
    for (const [idExistente, tExistente] of selMap.entries()) {
      if (chaveDisciplina(tExistente) === discKey) selMap.delete(idExistente);
    }
    selMap.set(turma.id, turma);
  }
  salvarPlanosLocal();
  renderListaTurmas();
  renderGradeSemanal();
}

function renderGradeSemanal() {
  const table = document.getElementById("gradeSemanal");
  const listaSel = document.getElementById("listaSelecionadas");

  const selArr = [...selecionadas().values()];
  const totalCreds = selArr.reduce((acc, t) => acc + (t.creditos || 0), 0);
  document.getElementById("statGrade").textContent = `Plano ${planoAtual}: ${selArr.length} turma${selArr.length === 1 ? "" : "s"}`;
  document.getElementById("statCreditos").textContent = `${totalCreds} créditos selecionados`;

  const corPorId = new Map();
  selArr.forEach((t, idx) => corPorId.set(t.id, CORES[idx % CORES.length]));

  let html = `<thead><tr><th class="hora-col">Hora</th>${DIAS.map((d) => `<th>${d.label}</th>`).join("")}</tr></thead><tbody>`;
  for (const h of HORAS) {
    html += `<tr><td class="hora-col">${String(h).padStart(2, "0")}:00</td>`;
    for (const d of DIAS) {
      const blocos = [];
      for (const t of selArr) {
        for (const hr of t.horarios || []) {
          if (hr.dia !== d.key) continue;
          if (semanaVisual !== "todas" && hr.semanalidade !== "semanal" && hr.semanalidade !== semanaVisual) {
            continue;
          }
          const iniH = Math.floor(horaParaMin(hr.inicio) / 60);
          const fimH = Math.ceil(horaParaMin(hr.fim) / 60);
          if (h >= iniH && h < fimH) {
            const sem = hr.semanalidade === "quinzenal_1" ? " • Q1" : hr.semanalidade === "quinzenal_2" ? " • Q2" : "";
            const qClass = hr.semanalidade === "quinzenal_1" ? " q1" : hr.semanalidade === "quinzenal_2" ? " q2" : "";
            const tipo = hr.tipo === "pratica" ? "P" : "T";
            blocos.push(
              `<div class="slot-block${qClass}" style="background:${corPorId.get(t.id)}" title="${t.disciplina} (${hr.inicio}-${hr.fim}${sem})">${t.disciplina.slice(0, 18)}${t.disciplina.length > 18 ? "…" : ""} [${tipo}${sem}]</div>`
            );
          }
        }
      }
      html += `<td class="slot">${blocos.join("")}</td>`;
    }
    html += `</tr>`;
  }
  html += `</tbody>`;
  table.innerHTML = html;

  if (!selArr.length) {
    listaSel.innerHTML = `<div style="font-size:0.82rem;color:var(--muted);text-align:center;">Clique em "+ Adicionar" à esquerda ou em "✨ Sugerir grade" para montar o Plano ${planoAtual}.</div>`;
    return;
  }

  listaSel.innerHTML = selArr
    .map(
      (t) => `
      <div class="selected-item">
        <div>
          <strong style="color:${corPorId.get(t.id)}">●</strong>
          <strong>${t.disciplina}</strong> (${t.turma || t.turno})
          <div style="font-size:0.75rem;color:var(--muted);font-family:monospace;">${t.id} • ${t.horarios_raw}</div>
        </div>
        <button class="btn-danger btn-sm" data-remove-id="${t.id}">Remover</button>
      </div>`
    )
    .join("");

  listaSel.querySelectorAll("[data-remove-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selecionadas().delete(btn.dataset.removeId);
      salvarPlanosLocal();
      renderListaTurmas();
      renderGradeSemanal();
    });
  });
}

function nomesCatalogoMap() {
  const m = new Map();
  if (motor) {
    for (const c of motor.catalogo) {
      if (c.codigo) m.set(c.codigo, c.nome);
    }
  }
  return m;
}

// Eventos
["fCurso", "fCampus", "fTurno", "fCategoria", "fOcultarCursadas", "fContarEmCurso", "fApenasRecOk"].forEach((id) => {
  document.getElementById(id).addEventListener("change", atualizarTela);
});
let buscaTimer = null;
document.getElementById("fBusca").addEventListener("input", () => {
  clearTimeout(buscaTimer);
  buscaTimer = setTimeout(atualizarTela, 180);
});

document.querySelectorAll("#diasPills .dia-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    const dia = btn.dataset.dia;
    if (diasAtivos.has(dia)) {
      if (diasAtivos.size === 1) return toast("Mantenha pelo menos 1 dia ativo.");
      diasAtivos.delete(dia);
      btn.classList.remove("active");
    } else {
      diasAtivos.add(dia);
      btn.classList.add("active");
    }
    atualizarTela();
  });
});

document.querySelectorAll("#planTabs .plan-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    planoAtual = btn.dataset.plan;
    atualizarAbasPlano();
    salvarPlanosLocal();
    renderListaTurmas();
    renderGradeSemanal();
  });
});

document.querySelectorAll("#semanaTabs .plan-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    semanaVisual = btn.dataset.semana;
    document.querySelectorAll("#semanaTabs .plan-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.semana === semanaVisual);
    });
    renderGradeSemanal();
  });
});

document.getElementById("btnExportarPng").addEventListener("click", () => {
  const selArr = [...selecionadas().values()];
  if (!selArr.length) return toast("Adicione pelo menos uma turma para exportar.");
  exportarGradePNG(selArr, planoAtual, formatarNomeCurso(cursoAtual()), semanaVisual);
  toast(`Imagem do Plano ${planoAtual} baixada!`);
});

document.getElementById("btnExportarIcs").addEventListener("click", () => {
  const selArr = [...selecionadas().values()];
  if (!selArr.length) return toast("Adicione pelo menos uma turma para exportar.");
  exportarGradeICS(selArr, planoAtual);
  toast(`Calendário .ics do Plano ${planoAtual} baixado!`);
});

document.getElementById("btnCopiarCodigos").addEventListener("click", async () => {
  const selArr = [...selecionadas().values()];
  if (!selArr.length) return toast("Nenhuma turma selecionada.");
  const texto = selArr.map((t) => `${t.id} - ${t.disciplina} (${t.horarios_raw})`).join("\n");
  await navigator.clipboard.writeText(texto);
  toast(`Códigos do Plano ${planoAtual} copiados!`);
});

document.getElementById("btnLimparGrade").addEventListener("click", () => {
  selecionadas().clear();
  salvarPlanosLocal();
  renderListaTurmas();
  renderGradeSemanal();
  toast(`Plano ${planoAtual} limpo.`);
});

// Modal Sugerir Grade
const modalSug = document.getElementById("modalSugerir");
document.getElementById("btnAbrirSugerir").addEventListener("click", () => {
  document.getElementById("resultadoSugestoes").innerHTML = "";
  modalSug.classList.add("open");
});
document.getElementById("btnFecharSugerir").addEventListener("click", () => modalSug.classList.remove("open"));

document.getElementById("btnGerarSugestoes").addEventListener("click", () => {
  if (!motor) return;
  const container = document.getElementById("resultadoSugestoes");
  const manterAtuais = document.getElementById("sugManterAtuais").checked;
  const sugs = motor.sugerirGrades({
    historico,
    contarEmCurso: document.getElementById("fContarEmCurso").checked,
    curso: cursoAtual(),
    campus: document.getElementById("fCampus").value,
    turno: document.getElementById("fTurno").value,
    diasPermitidos: [...diasAtivos],
    apenasRecomendacoesOk: document.getElementById("sugSoRecOk").checked,
    minCreditos: parseInt(document.getElementById("sugMinCred").value, 10) || 12,
    maxCreditos: parseInt(document.getElementById("sugMaxCred").value, 10) || 20,
    maxDisciplinas: parseInt(document.getElementById("sugMaxDisc").value, 10) || 5,
    completarComLeves: document.getElementById("sugCompletarLeves").checked,
    turmasFixas: manterAtuais ? [...selecionadas().values()] : [],
  });

  if (!sugs.length) {
    container.innerHTML = `<div style="font-size:0.82rem;color:#fca5a5;">Nenhuma combinação encontrada. Tente ampliar os créditos ou desmarcar "Somente recomendações cumpridas".</div>`;
    return;
  }

  container.innerHTML = "";
  sugs.forEach((s) => {
    const card = document.createElement("div");
    card.className = "sugestao-card";
    card.innerHTML = `
      <div class="sugestao-head">
        <div>
          <strong>Opção ${s.opcao}</strong>
          <span style="font-size:0.78rem;color:var(--muted);margin-left:6px;">
            ${s.total_disciplinas} matérias • ${s.total_creditos} créditos • ${s.obrigatorias_curso} obrig.
          </span>
        </div>
        <button class="btn-primary btn-sm">Aplicar no Plano ${planoAtual}</button>
      </div>
      <ul class="sugestao-list">
        ${s.turmas
          .map(
            (t) =>
              `<li><strong>${t.disciplina}</strong> (${t.turma || t.turno}) ${
                t.fixa
                  ? `<span class="badge rec-ok" style="font-size:0.68rem;">Mantida</span>`
                  : t.preenchimento_leve
                  ? `<span class="badge cat-${t.categoria}" style="font-size:0.68rem;">Complemento leve</span>`
                  : ""
              } — ${t.creditos} créd. • ${t.horarios_raw}</li>`
          )
          .join("")}
      </ul>
    `;
    card.querySelector("button").addEventListener("click", () => {
      const selMap = selecionadas();
      selMap.clear();
      s.turmas.forEach((t) => selMap.set(t.id, t));
      salvarPlanosLocal();
      modalSug.classList.remove("open");
      renderListaTurmas();
      renderGradeSemanal();
      toast(`Opção ${s.opcao} aplicada no Plano ${planoAtual}!`);
    });
    container.appendChild(card);
  });
});

// Modal Histórico (100% client-side)
const modalHist = document.getElementById("modalHistorico");
document.getElementById("btnAbrirHistorico").addEventListener("click", () => modalHist.classList.add("open"));
document.getElementById("btnFecharHistorico").addEventListener("click", () => modalHist.classList.remove("open"));

document.getElementById("btnEnviarPdf").addEventListener("click", async () => {
  const fileInput = document.getElementById("inputPdfHistorico");
  if (!fileInput.files.length) return toast("Selecione um arquivo PDF primeiro.");
  const statusEl = document.getElementById("historicoStatusModal");
  statusEl.textContent = "Lendo PDF localmente no seu navegador...";
  try {
    historico = await sanitizarPdfHistoricoBrowser(fileInput.files[0], nomesCatalogoMap());
    localStorage.setItem("ufabc_web_historico_v1", JSON.stringify(historico));
    const aprov = historico.disciplinas.filter((d) => d.status === "aprovado" || d.status === "equivalencia").length;
    const curso = historico.disciplinas.filter((d) => d.status === "em_curso").length;
    statusEl.textContent = `✅ ${historico.total_disciplinas} disciplinas extraídas (${aprov} aprovadas/dispensadas, ${curso} em curso). Nenhum dado saiu do seu navegador.`;
    toast("Histórico importado com privacidade total!");
    atualizarTela();
  } catch (err) {
    statusEl.textContent = `Erro ao ler PDF: ${err.message}`;
  }
});

document.getElementById("btnEnviarTexto").addEventListener("click", () => {
  const txt = document.getElementById("inputTextoHistorico").value.trim();
  if (!txt) return toast("Cole o texto das disciplinas primeiro.");
  historico = sanitizarTextoHistorico(txt, nomesCatalogoMap());
  localStorage.setItem("ufabc_web_historico_v1", JSON.stringify(historico));
  const aprov = historico.disciplinas.filter((d) => d.status === "aprovado" || d.status === "equivalencia").length;
  const curso = historico.disciplinas.filter((d) => d.status === "em_curso").length;
  document.getElementById("historicoStatusModal").textContent =
    `✅ ${historico.total_disciplinas} disciplinas extraídas (${aprov} aprovadas/dispensadas, ${curso} em curso).`;
  toast("Histórico processado!");
  atualizarTela();
});

document.getElementById("btnRemoverHistorico").addEventListener("click", () => {
  historico = null;
  localStorage.removeItem("ufabc_web_historico_v1");
  document.getElementById("historicoStatusModal").textContent = "Histórico apagado do navegador.";
  toast("Histórico removido.");
  atualizarTela();
});

// Modal Ementa
const modalEmenta = document.getElementById("modalEmenta");
document.getElementById("btnFecharEmenta").addEventListener("click", () => modalEmenta.classList.remove("open"));

function abrirModalEmenta(turma) {
  const cat = motor ? motor.buscarCatalogo(turma.codigo, turma.disciplina_norm) : null;
  document.getElementById("ementaTitulo").textContent = turma.disciplina;
  document.getElementById("ementaMeta").textContent =
    `${turma.codigo || "Sem código"} • TPEI ${turma.tpi || "—"} • ${turma.creditos} créditos`;

  const partes = [];
  if (cat && cat.recomendacoes && cat.recomendacoes.length) {
    partes.push(`<div><strong>Recomendações:</strong><p style="color:var(--muted);margin-top:4px;">${cat.recomendacoes.join("; ")}</p></div>`);
  }
  if (cat && cat.objetivos) {
    partes.push(`<div><strong>Objetivos:</strong><p style="color:var(--muted);margin-top:4px;">${cat.objetivos}</p></div>`);
  }
  if (cat && cat.ementa) {
    partes.push(`<div><strong>Ementa:</strong><p style="color:var(--muted);margin-top:4px;">${cat.ementa}</p></div>`);
  }
  if (!partes.length) {
    partes.push(`<p style="color:var(--muted);">Ementa não encontrada no Catálogo 2025–2026 para esta disciplina.</p>`);
  }
  document.getElementById("ementaConteudo").innerHTML = partes.join("");
  modalEmenta.classList.add("open");
}

// Modal Obrigatórias Pendentes
const modalPend = document.getElementById("modalPendentes");
document.getElementById("btnVerPendentes").addEventListener("click", () => {
  if (!ultimoProgresso) return;
  const renderGrupo = (titulo, lista) => {
    if (!lista.length) return `<p style="margin-bottom:12px;"><strong>${titulo}:</strong> 🎉 Todas concluídas!</p>`;
    return `
      <h4 style="margin:10px 0 6px;">${titulo} (${lista.length})</h4>
      <ul style="padding-left:18px;margin-bottom:12px;">
        ${lista
          .map(
            (d) =>
              `<li style="margin-bottom:4px;"><code>${d.codigo}</code> — ${d.nome} ${
                d.ofertada_agora
                  ? '<span class="badge rec-ok">Ofertada agora</span>'
                  : '<span class="badge rec-desconhecido">Sem oferta</span>'
              }</li>`
          )
          .join("")}
      </ul>`;
  };
  const p = ultimoProgresso;
  let html = "";
  if (p.tem_historico && p.creditos_historico) {
    const ch = p.creditos_historico;
    const m = p.metas_ppc;
    const fmt = (val, meta, unit = "créd.") =>
      meta ? `<strong>${val}</strong> / ${meta} ${unit}` : `<strong>${val}</strong> ${unit}`;
    html += `
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:14px;">
        <div style="font-weight:700;margin-bottom:6px;">📊 Créditos contabilizados do seu histórico</div>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;font-size:0.82rem;color:var(--muted);">
          <div>Obrigatórias (OBR): ${fmt(ch.obr, m?.obr)}</div>
          <div>Opções Limitadas (OL): ${fmt(ch.ol, m?.ol)}</div>
          <div>Livres (LIV): ${fmt(ch.liv, m?.liv)}</div>
          <div>Extensão (CH EXT): ${fmt(ch.ch_ext, m?.ch_ext, "h")}</div>
        </div>
        <div style="font-size:0.75rem;color:var(--muted);margin-top:6px;">
          Total acumulado no histórico: <strong>${ch.total} créditos</strong>${m ? " • Metas exibidas: PPC BCC 2023" : ""}
        </div>
      </div>`;
  }
  if (p.obrigatorias_curso.total > 0) {
    html += renderGrupo(`Obrigatórias — ${p.curso_sigla}`, p.obrigatorias_curso.pendentes);
  }
  if (p.obrigatorias_base.total > 0) {
    html += renderGrupo(`Obrigatórias — ${p.label_base}`, p.obrigatorias_base.pendentes);
  }
  document.getElementById("conteudoPendentes").innerHTML = html || "<p>Nenhuma obrigatória cadastrada para este curso.</p>";
  modalPend.classList.add("open");
});
document.getElementById("btnFecharPendentes").addEventListener("click", () => modalPend.classList.remove("open"));

// Inicialização: carrega os JSONs estáticos públicos da PROGRAD
async function init() {
  restaurarEstadoLocal();
  try {
    const [metaRes, ofertaRes, catRes, gradeRes, cursosRes] = await Promise.all([
      fetch("./data/meta.json"),
      fetch("./data/oferta.json"),
      fetch("./data/catalogo.json"),
      fetch("./data/grade_bcc.json"),
      fetch("./data/grades_cursos.json"),
    ]);
    metaDados = await metaRes.json();
    const [oferta, catalogo, grade, gradesCursos] = await Promise.all([
      ofertaRes.json(),
      catRes.json(),
      gradeRes.json(),
      cursosRes.ok ? cursosRes.json() : Promise.resolve(null),
    ]);
    motor = new MotorMatriculaWeb(oferta, catalogo, grade, gradesCursos);
    popularCursos(motor.listarCursosDisponiveis());
    atualizarTela();
  } catch (err) {
    document.getElementById("metaInfo").textContent = `Erro ao carregar dados: ${err.message}`;
  }
}

init();
