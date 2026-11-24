import { exportarGradeICS, exportarGradePNG } from "/static/exportar.js";

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

let turmasVisiveis = [];
let diasAtivos = new Set(DIAS.map((d) => d.key));
let planoAtual = "A";
let planos = { A: new Map(), B: new Map(), C: new Map() };
let ultimoProgresso = null;

function selecionadas() {
  return planos[planoAtual];
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3200);
}

function horaParaMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function horariosConflitam(h1, h2) {
  if (h1.dia !== h2.dia) return false;
  if (
    (h1.semanalidade === "quinzenal_1" && h2.semanalidade === "quinzenal_2") ||
    (h1.semanalidade === "quinzenal_2" && h2.semanalidade === "quinzenal_1")
  ) {
    return false;
  }
  return horaParaMin(h1.inicio) < horaParaMin(h2.fim) && horaParaMin(h2.inicio) < horaParaMin(h1.fim);
}

function conflitoComSelecionadas(turma) {
  const conflitos = [];
  for (const sel of selecionadas().values()) {
    if (sel.id === turma.id) continue;
    // Se for outra turma da mesma disciplina, o usuário pode trocar diretamente
    if (chaveDisciplina(sel) === chaveDisciplina(turma)) continue;
    for (const h1 of turma.horarios) {
      for (const h2 of sel.horarios) {
        if (horariosConflitam(h1, h2)) {
          conflitos.push(sel.disciplina);
          break;
        }
      }
    }
  }
  return [...new Set(conflitos)];
}

function chaveDisciplina(t) {
  return t.codigo || t.disciplina;
}

function salvarPlanosLocal() {
  const obj = {
    planoAtual,
    A: [...planos.A.values()],
    B: [...planos.B.values()],
    C: [...planos.C.values()],
  };
  localStorage.setItem("ufabc_planos_v2", JSON.stringify(obj));
}

function restaurarPlanosLocal() {
  try {
    const rawV2 = localStorage.getItem("ufabc_planos_v2");
    if (rawV2) {
      const obj = JSON.parse(rawV2);
      ["A", "B", "C"].forEach((k) => {
        (obj[k] || []).forEach((t) => planos[k].set(t.id, t));
      });
      if (obj.planoAtual && planos[obj.planoAtual]) planoAtual = obj.planoAtual;
      atualizarAbasPlano();
      return;
    }
    // Migração suave da seleção v1 para o Plano A
    const rawV1 = localStorage.getItem("ufabc_selecao_v1");
    if (rawV1) {
      JSON.parse(rawV1).forEach((t) => planos.A.set(t.id, t));
      salvarPlanosLocal();
    }
  } catch (_) {}
}

function atualizarAbasPlano() {
  document.querySelectorAll("#planTabs .plan-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.plan === planoAtual);
  });
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
  if (cat === "obrigatoria_bcc") {
    return cursoAtual() === "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO" ? "Obrigatória BCC" : "Do Curso";
  }
  return CAT_LABELS[cat] || cat;
}

function popularCursos(listaCursos) {
  if (!listaCursos || !listaCursos.length) return;
  const select = document.getElementById("fCurso");
  const salvo = localStorage.getItem("ufabc_curso_v1") || "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO";
  select.innerHTML = listaCursos
    .map((c) => {
      const sufixo = c === "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO" ? " (PPC 2023)" : "";
      return `<option value="${c}">${formatarNomeCurso(c)}${sufixo}</option>`;
    })
    .join("");
  if (listaCursos.includes(salvo)) select.value = salvo;
}

async function carregarMeta() {
  const res = await fetch("/api/meta");
  const meta = await res.json();
  if (!meta.pronto) {
    document.getElementById("metaInfo").textContent = meta.erro || "Base não carregada.";
    return;
  }
  popularCursos(meta.cursos);
  document.getElementById("metaInfo").textContent =
    `Oferta: ${meta.oferta_arquivo} • ${meta.total_turmas} turmas • ${meta.total_catalogo} no catálogo • ` +
    (meta.tem_historico ? `Histórico: ${meta.total_historico} disciplinas` : "Histórico não importado");
}

async function carregarTurmas() {
  const curso = cursoAtual();
  localStorage.setItem("ufabc_curso_v1", curso);
  const params = new URLSearchParams({
    curso,
    campus: document.getElementById("fCampus").value,
    turno: document.getElementById("fTurno").value,
    categoria: document.getElementById("fCategoria").value,
    ocultar_cursadas: document.getElementById("fOcultarCursadas").checked,
    contar_em_curso: document.getElementById("fContarEmCurso").checked,
    apenas_recomendacoes_ok: document.getElementById("fApenasRecOk").checked,
    dias: [...diasAtivos].join(","),
    busca: document.getElementById("fBusca").value.trim(),
  });

  const res = await fetch(`/api/turmas?${params.toString()}`);
  const data = await res.json();
  turmasVisiveis = data.turmas || [];
  ultimoProgresso = data.progresso;

  renderProgresso();
  renderListaTurmas();
  renderGradeSemanal();
}

function renderProgresso() {
  if (!ultimoProgresso) return;
  const p = ultimoProgresso;
  document.getElementById("statBcc").textContent = `${p.obrigatorias_bcc.feitas} / ${p.obrigatorias_bcc.total}`;
  document.getElementById("statBccSub").textContent = p.tem_historico
    ? `${p.obrigatorias_bcc.pendentes.length} pendentes (${p.obrigatorias_bcc.pendentes.filter((x) => x.ofertada_agora).length} ofertadas agora)`
    : "Importe seu histórico para calcular";

  document.getElementById("statBct").textContent = `${p.obrigatorias_bct.feitas} / ${p.obrigatorias_bct.total}`;
  document.getElementById("statBctSub").textContent = p.tem_historico
    ? `${p.obrigatorias_bct.pendentes.length} pendentes`
    : "Ciclo básico";

  document.getElementById("statOl").textContent = `${p.opcoes_limitadas.feitas}`;
}

function agruparPorDisciplina(lista) {
  const grupos = new Map();
  for (const t of lista) {
    const chave = chaveDisciplina(t);
    if (!grupos.has(chave)) {
      grupos.set(chave, { rep: t, turmas: [] });
    }
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
  const discsSelecionadas = new Map(); // chaveDisciplina -> turmaId
  for (const s of selMap.values()) {
    discsSelecionadas.set(chaveDisciplina(s), s.id);
  }

  const fragment = document.createDocumentFragment();
  grupos.slice(0, 120).forEach(({ rep, turmas }) => {
    const discKey = chaveDisciplina(rep);
    const turmaSelId = discsSelecionadas.get(discKey);

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
          <div class="turma-title">${rep.disciplina}</div>
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

    const sublist = card.querySelector(".turmas-sublist");
    turmas.forEach((t) => {
      const isSel = selMap.has(t.id);
      const conflitos = isSel ? [] : conflitoComSelecionadas(t);
      const outraTurmaDaMesma = Boolean(turmaSelId && turmaSelId !== t.id);

      const row = document.createElement("div");
      row.className = `turma-row ${isSel ? "selected" : ""} ${conflitos.length ? "conflict" : ""}`;

      const btnLabel = isSel
        ? "✓ Remover"
        : conflitos.length
        ? "Conflito"
        : outraTurmaDaMesma
        ? "Trocar"
        : "+ Adicionar";
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
    // Se já havia outra turma da mesma disciplina no plano, substitui automaticamente
    const discKey = chaveDisciplina(turma);
    for (const [idExistente, tExistente] of selMap.entries()) {
      if (chaveDisciplina(tExistente) === discKey) {
        selMap.delete(idExistente);
      }
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
        for (const hr of t.horarios) {
          if (hr.dia !== d.key) continue;
          const iniH = Math.floor(horaParaMin(hr.inicio) / 60);
          const fimH = Math.ceil(horaParaMin(hr.fim) / 60);
          if (h >= iniH && h < fimH) {
            const sem = hr.semanalidade === "quinzenal_1" ? " (Q1)" : hr.semanalidade === "quinzenal_2" ? " (Q2)" : "";
            const tipo = hr.tipo === "pratica" ? "P" : "T";
            blocos.push(
              `<div class="slot-block" style="background:${corPorId.get(t.id)}" title="${t.disciplina} (${hr.inicio}-${hr.fim})">${t.disciplina.slice(0, 18)}${t.disciplina.length > 18 ? "…" : ""} [${tipo}${sem}]</div>`
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
        <button class="btn-danger btn-sm" onclick="removerSelecionada('${t.id}')">Remover</button>
      </div>`
    )
    .join("");
}

window.removerSelecionada = function (id) {
  selecionadas().delete(id);
  salvarPlanosLocal();
  renderListaTurmas();
  renderGradeSemanal();
};

// Filtros principais
["fCurso", "fCampus", "fTurno", "fCategoria", "fOcultarCursadas", "fContarEmCurso", "fApenasRecOk"].forEach((id) => {
  document.getElementById(id).addEventListener("change", carregarTurmas);
});
let buscaTimer = null;
document.getElementById("fBusca").addEventListener("input", () => {
  clearTimeout(buscaTimer);
  buscaTimer = setTimeout(carregarTurmas, 220);
});

// Pílulas de dias da semana
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
    carregarTurmas();
  });
});

// Abas Plano A / B / C
document.querySelectorAll("#planTabs .plan-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    planoAtual = btn.dataset.plan;
    atualizarAbasPlano();
    salvarPlanosLocal();
    renderListaTurmas();
    renderGradeSemanal();
  });
});

document.getElementById("btnExportarPng").addEventListener("click", () => {
  const selArr = [...selecionadas().values()];
  if (!selArr.length) return toast("Adicione pelo menos uma turma para exportar.");
  exportarGradePNG(selArr, planoAtual, formatarNomeCurso(cursoAtual()));
  toast(`Imagem do Plano ${planoAtual} baixada!`);
});

document.getElementById("btnExportarIcs").addEventListener("click", () => {
  const selArr = [...selecionadas().values()];
  if (!selArr.length) return toast("Adicione pelo menos uma turma para exportar.");
  exportarGradeICS(selArr, planoAtual);
  toast(`Calendário .ics do Plano ${planoAtual} baixado!`);
});

// Copiar códigos e limpar grade
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

document.getElementById("btnGerarSugestoes").addEventListener("click", async () => {
  const container = document.getElementById("resultadoSugestoes");
  container.innerHTML = `<div style="font-size:0.82rem;color:var(--muted);">Calculando combinações sem conflito...</div>`;

  const body = {
    curso: cursoAtual(),
    campus: document.getElementById("fCampus").value,
    turno: document.getElementById("fTurno").value,
    dias_permitidos: [...diasAtivos],
    contar_em_curso: document.getElementById("fContarEmCurso").checked,
    apenas_recomendacoes_ok: document.getElementById("sugSoRecOk").checked,
    min_creditos: parseInt(document.getElementById("sugMinCred").value, 10) || 12,
    max_creditos: parseInt(document.getElementById("sugMaxCred").value, 10) || 20,
    max_disciplinas: parseInt(document.getElementById("sugMaxDisc").value, 10) || 5,
    completar_com_leves: document.getElementById("sugCompletarLeves").checked,
  };

  const res = await fetch("/api/sugerir-grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  const sugs = data.sugestoes || [];

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
            ${s.total_disciplinas} matérias • ${s.total_creditos} créditos • ${s.obrigatorias_bcc} obrig. BCC
          </span>
        </div>
        <button class="btn-primary btn-sm">Aplicar no Plano ${planoAtual}</button>
      </div>
      <ul class="sugestao-list">
        ${s.turmas
          .map(
            (t) =>
              `<li><strong>${t.disciplina}</strong> (${t.turma || t.turno}) ${
                t.preenchimento_leve
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

// Modal Histórico
const modalHist = document.getElementById("modalHistorico");
document.getElementById("btnAbrirHistorico").addEventListener("click", () => modalHist.classList.add("open"));
document.getElementById("btnFecharHistorico").addEventListener("click", () => modalHist.classList.remove("open"));

document.getElementById("btnEnviarPdf").addEventListener("click", async () => {
  const fileInput = document.getElementById("inputPdfHistorico");
  if (!fileInput.files.length) return toast("Selecione um arquivo PDF primeiro.");
  const fd = new FormData();
  fd.append("arquivo", fileInput.files[0]);
  document.getElementById("historicoStatusModal").textContent = "Processando localmente em memória...";
  const res = await fetch("/api/historico/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) {
    document.getElementById("historicoStatusModal").textContent = `Erro: ${data.detail}`;
    return;
  }
  document.getElementById("historicoStatusModal").textContent =
    `✅ ${data.total_disciplinas} disciplinas extraídas (${data.aprovadas} aprovadas/equiv., ${data.em_curso} em curso). Nenhum dado pessoal foi salvo.`;
  toast("Histórico importado com segurança!");
  await carregarMeta();
  await carregarTurmas();
});

document.getElementById("btnEnviarTexto").addEventListener("click", async () => {
  const txt = document.getElementById("inputTextoHistorico").value.trim();
  if (!txt) return toast("Cole o texto das disciplinas primeiro.");
  const fd = new FormData();
  fd.append("texto", txt);
  const res = await fetch("/api/historico/texto", { method: "POST", body: fd });
  const data = await res.json();
  document.getElementById("historicoStatusModal").textContent =
    `✅ ${data.total_disciplinas} disciplinas extraídas (${data.aprovadas} aprovadas/equiv., ${data.em_curso} em curso).`;
  toast("Histórico processado!");
  await carregarMeta();
  await carregarTurmas();
});

document.getElementById("btnRemoverHistorico").addEventListener("click", async () => {
  await fetch("/api/historico", { method: "DELETE" });
  document.getElementById("historicoStatusModal").textContent = "Histórico apagado.";
  toast("Histórico removido.");
  await carregarMeta();
  await carregarTurmas();
});

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
  document.getElementById("conteudoPendentes").innerHTML =
    renderGrupo("Obrigatórias do BCC", ultimoProgresso.obrigatorias_bcc.pendentes) +
    renderGrupo("Obrigatórias do BC&T", ultimoProgresso.obrigatorias_bct.pendentes);
  modalPend.classList.add("open");
});
document.getElementById("btnFecharPendentes").addEventListener("click", () => modalPend.classList.remove("open"));

// Sincronizar PROGRAD
document.getElementById("btnSincronizar").addEventListener("click", async () => {
  toast("Buscando PDFs mais recentes na PROGRAD...");
  const res = await fetch("/api/sincronizar?forcar=true", { method: "POST" });
  if (res.ok) {
    toast("PDFs da PROGRAD atualizados!");
    await carregarMeta();
    await carregarTurmas();
  } else {
    const err = await res.json();
    toast(`Erro ao atualizar: ${err.detail}`);
  }
});

// Inicialização
restaurarPlanosLocal();
carregarMeta().then(carregarTurmas);
