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
let turmasCachePorId = new Map();
let selecionadas = new Map(); // id -> turma
let ultimoProgresso = null;

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
  for (const sel of selecionadas.values()) {
    if (sel.id === turma.id) continue;
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

function salvarSelecaoLocal() {
  localStorage.setItem("ufabc_selecao_v1", JSON.stringify([...selecionadas.values()]));
}

function restaurarSelecaoLocal() {
  try {
    const raw = localStorage.getItem("ufabc_selecao_v1");
    if (!raw) return;
    const arr = JSON.parse(raw);
    arr.forEach((t) => selecionadas.set(t.id, t));
  } catch (_) {}
}

async function carregarMeta() {
  const res = await fetch("/api/meta");
  const meta = await res.json();
  if (!meta.pronto) {
    document.getElementById("metaInfo").textContent = meta.erro || "Base não carregada.";
    return;
  }
  document.getElementById("metaInfo").textContent =
    `Oferta: ${meta.oferta_arquivo} • ${meta.total_turmas} turmas • ${meta.total_catalogo} no catálogo • ` +
    (meta.tem_historico ? `Histórico: ${meta.total_historico} disciplinas` : "Histórico não importado");
}

async function carregarTurmas() {
  const params = new URLSearchParams({
    campus: document.getElementById("fCampus").value,
    turno: document.getElementById("fTurno").value,
    categoria: document.getElementById("fCategoria").value,
    ocultar_cursadas: document.getElementById("fOcultarCursadas").checked,
    contar_em_curso: document.getElementById("fContarEmCurso").checked,
    apenas_recomendacoes_ok: document.getElementById("fApenasRecOk").checked,
    busca: document.getElementById("fBusca").value.trim(),
  });

  const res = await fetch(`/api/turmas?${params.toString()}`);
  const data = await res.json();
  turmasVisiveis = data.turmas || [];
  ultimoProgresso = data.progresso;
  turmasVisiveis.forEach((t) => turmasCachePorId.set(t.id, t));

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

function renderListaTurmas() {
  const container = document.getElementById("listaTurmas");
  document.getElementById("contadorTurmas").textContent = `${turmasVisiveis.length} encontradas`;

  if (!turmasVisiveis.length) {
    container.innerHTML = `<div style="padding:24px;text-align:center;color:var(--muted);">Nenhuma turma encontrada com esses filtros.</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();
  turmasVisiveis.slice(0, 180).forEach((t) => {
    const isSel = selecionadas.has(t.id);
    const conflitos = isSel ? [] : conflitoComSelecionadas(t);

    const card = document.createElement("div");
    card.className = `turma-card ${isSel ? "selected" : ""} ${conflitos.length ? "conflict" : ""}`;

    const recsHtml = t.recomendacoes.length
      ? `<div class="recs-box"><strong>Recomendações:</strong> ${t.recomendacoes
          .map((r) => `<span class="${r.cumprida ? "rec-item-ok" : "rec-item-miss"}">${r.cumprida ? "✓" : "•"} ${r.nome}</span>`)
          .join("")}</div>`
      : "";

    const conflitoHtml = conflitos.length
      ? `<div style="margin-top:6px;font-size:0.78rem;color:#fca5a5;">⚠️ Conflita com: ${conflitos.join(", ")}</div>`
      : "";

    const btnLabel = isSel ? "✓ Remover" : conflitos.length ? "Conflito" : "+ Adicionar";
    const btnClass = isSel ? "btn-danger btn-sm" : "btn-primary btn-sm";

    card.innerHTML = `
      <div class="turma-top">
        <div>
          <div class="turma-title">${t.disciplina} ${t.turma ? `(${t.turma})` : ""}</div>
          <div class="turma-code">${t.id} • ${t.campus} • ${t.turno} • TPEI ${t.tpi || "—"} (${t.creditos} créd.) • ${t.vagas ?? "?"} vagas</div>
        </div>
        <button class="${btnClass}" data-id="${t.id}" ${!isSel && conflitos.length ? "disabled" : ""}>${btnLabel}</button>
      </div>
      <div class="badges">
        <span class="badge cat-${t.categoria}">${CAT_LABELS[t.categoria] || t.categoria}</span>
        <span class="badge rec-${t.status_recomendacao}">${REC_LABELS[t.status_recomendacao] || t.status_recomendacao}</span>
        ${t.status_historico === "em_curso" ? `<span class="badge" style="background:rgba(59,130,246,0.2);color:#93c5fd;">Em curso</span>` : ""}
      </div>
      <div class="turma-meta">
        <div>🕒 ${t.horarios_raw || "Horário não informado"}</div>
        <div>👩‍🏫 ${[t.docente_teoria, t.docente_pratica].filter(Boolean).join(" | ") || "Docente não informado"}</div>
      </div>
      ${recsHtml}
      ${conflitoHtml}
    `;

    card.querySelector("button").addEventListener("click", () => toggleTurma(t));
    fragment.appendChild(card);
  });

  container.innerHTML = "";
  container.appendChild(fragment);
}

function toggleTurma(turma) {
  if (selecionadas.has(turma.id)) {
    selecionadas.delete(turma.id);
  } else {
    const conflitos = conflitoComSelecionadas(turma);
    if (conflitos.length) {
      toast(`Conflito de horário com: ${conflitos.join(", ")}`);
      return;
    }
    selecionadas.set(turma.id, turma);
  }
  salvarSelecaoLocal();
  renderListaTurmas();
  renderGradeSemanal();
}

function renderGradeSemanal() {
  const table = document.getElementById("gradeSemanal");
  const listaSel = document.getElementById("listaSelecionadas");

  const selArr = [...selecionadas.values()];
  const totalCreds = selArr.reduce((acc, t) => acc + (t.creditos || 0), 0);
  document.getElementById("statGrade").textContent = `${selArr.length} turma${selArr.length === 1 ? "" : "s"}`;
  document.getElementById("statCreditos").textContent = `${totalCreds} créditos selecionados`;

  // Mapear cor por disciplina selecionada
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
    listaSel.innerHTML = `<div style="font-size:0.82rem;color:var(--muted);text-align:center;">Clique em "+ Adicionar" nas turmas à esquerda para montar sua grade.</div>`;
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
  selecionadas.delete(id);
  salvarSelecaoLocal();
  renderListaTurmas();
  renderGradeSemanal();
};

// Eventos de filtros
["fCampus", "fTurno", "fCategoria", "fOcultarCursadas", "fContarEmCurso", "fApenasRecOk"].forEach((id) => {
  document.getElementById(id).addEventListener("change", carregarTurmas);
});
let buscaTimer = null;
document.getElementById("fBusca").addEventListener("input", () => {
  clearTimeout(buscaTimer);
  buscaTimer = setTimeout(carregarTurmas, 220);
});

// Copiar códigos e limpar grade
document.getElementById("btnCopiarCodigos").addEventListener("click", async () => {
  const selArr = [...selecionadas.values()];
  if (!selArr.length) return toast("Nenhuma turma selecionada.");
  const texto = selArr.map((t) => `${t.id} - ${t.disciplina} (${t.horarios_raw})`).join("\n");
  await navigator.clipboard.writeText(texto);
  toast("Códigos copiados para a área de transferência!");
});

document.getElementById("btnLimparGrade").addEventListener("click", () => {
  selecionadas.clear();
  salvarSelecaoLocal();
  renderListaTurmas();
  renderGradeSemanal();
  toast("Grade limpa.");
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
restaurarSelecaoLocal();
carregarMeta().then(carregarTurmas);
