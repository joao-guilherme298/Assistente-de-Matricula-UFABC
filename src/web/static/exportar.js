// Exportação da grade semanal para Calendário (.ics) e Imagem (.png) — 100% client-side

const CORES = ["#2563eb", "#7c3aed", "#0891b2", "#059669", "#d97706", "#db2777", "#4f46e5", "#0d9488"];

const DIA_INFO = {
  segunda: { label: "Seg", ics: "MO", offset: 0 },
  terca: { label: "Ter", ics: "TU", offset: 1 },
  quarta: { label: "Qua", ics: "WE", offset: 2 },
  quinta: { label: "Qui", ics: "TH", offset: 3 },
  sexta: { label: "Sex", ics: "FR", offset: 4 },
  sabado: { label: "Sáb", ics: "SA", offset: 5 },
};

const DIAS_ORDEM = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado"];

function proximaSegunda() {
  const hoje = new Date();
  const diaSemana = hoje.getDay(); // 0=Dom, 1=Seg, ...
  const diff = diaSemana === 0 ? 1 : diaSemana === 1 ? 0 : 8 - diaSemana;
  const seg = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() + diff);
  return seg;
}

function formatarDataICS(date, hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const y = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(h).padStart(2, "0");
  const mm = String(m).padStart(2, "0");
  return `${y}${mo}${d}T${hh}${mm}00`;
}

function escaparICS(texto) {
  return (texto || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
}

function baixarBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Gera um arquivo .ics (Google Calendar / Apple Calendar / Outlook) com as aulas do quadrimestre (12 semanas).
 */
export function exportarGradeICS(turmas, planoNome = "A") {
  const baseSeg = proximaSegunda();
  const stamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const linhas = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Assistente de Matricula UFABC//PT-BR",
    "CALSCALE:GREGORIAN",
    "X-WR-CALNAME:Grade UFABC - Plano " + planoNome,
    "X-WR-TIMEZONE:America/Sao_Paulo",
  ];

  turmas.forEach((t, idxT) => {
    const docentes = [t.docente_teoria, t.docente_pratica].filter(Boolean).join(" / ") || "A definir";
    (t.horarios || []).forEach((h, idxH) => {
      const info = DIA_INFO[h.dia];
      if (!info) return;

      const offsetExtra = h.semanalidade === "quinzenal_2" ? 7 : 0;
      const dataInicio = new Date(
        baseSeg.getFullYear(),
        baseSeg.getMonth(),
        baseSeg.getDate() + info.offset + offsetExtra
      );
      const dtStart = formatarDataICS(dataInicio, h.inicio);
      const dtEnd = formatarDataICS(dataInicio, h.fim);
      const interval = h.semanalidade === "semanal" ? 1 : 2;
      const count = h.semanalidade === "semanal" ? 12 : 6;
      const tipoLabel = h.tipo === "pratica" ? "Prática" : "Teoria";
      const qLabel =
        h.semanalidade === "quinzenal_1"
          ? " (Quinzenal I)"
          : h.semanalidade === "quinzenal_2"
          ? " (Quinzenal II)"
          : "";

      linhas.push("BEGIN:VEVENT");
      linhas.push(`UID:ufabc-${t.id}-${idxT}-${idxH}@assistente-matricula`);
      linhas.push(`DTSTAMP:${stamp}`);
      linhas.push(`DTSTART;TZID=America/Sao_Paulo:${dtStart}`);
      linhas.push(`DTEND;TZID=America/Sao_Paulo:${dtEnd}`);
      linhas.push(`RRULE:FREQ=WEEKLY;INTERVAL=${interval};COUNT=${count};BYDAY=${info.ics}`);
      linhas.push(`SUMMARY:${escaparICS(`${t.disciplina} (${tipoLabel}${qLabel})`)}`);
      linhas.push(`LOCATION:${escaparICS(`UFABC - ${t.campus}`)}`);
      linhas.push(
        `DESCRIPTION:${escaparICS(`Turma: ${t.id}\nTPEI: ${t.tpi || "-"}\nDocente(s): ${docentes}`)}`
      );
      linhas.push("END:VEVENT");
    });
  });

  linhas.push("END:VCALENDAR");
  const blob = new Blob([linhas.join("\r\n")], { type: "text/calendar;charset=utf-8" });
  baixarBlob(blob, `grade_ufabc_plano_${planoNome}.ics`);
}

function horaParaFloat(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h + m / 60;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * Renderiza a grade semanal em alta resolução via Canvas e baixa como PNG.
 */
export function exportarGradePNG(turmas, planoNome = "A", cursoNome = "UFABC", semanaVisual = "todas") {
  const horarioVisivel = (h) =>
    semanaVisual === "todas" || h.semanalidade === "semanal" || h.semanalidade === semanaVisual;

  const horasUsadas = [];
  for (const t of turmas) {
    for (const h of t.horarios || []) {
      if (!horarioVisivel(h)) continue;
      horasUsadas.push(Math.floor(horaParaFloat(h.inicio)), Math.ceil(horaParaFloat(h.fim)));
    }
  }
  const minHora = horasUsadas.length ? Math.max(7, Math.min(...horasUsadas)) : 8;
  const maxHora = horasUsadas.length ? Math.min(23, Math.max(...horasUsadas)) : 18;
  const totalHoras = Math.max(4, maxHora - minHora);

  const semanaTitulo =
    semanaVisual === "quinzenal_1"
      ? " — Quinzenal I"
      : semanaVisual === "quinzenal_2"
      ? " — Quinzenal II"
      : "";
  const semanaArquivo =
    semanaVisual === "quinzenal_1" ? "_Q1" : semanaVisual === "quinzenal_2" ? "_Q2" : "";

  const scale = 2;
  const W = 1120;
  const headerH = 74;
  const colHoraW = 74;
  const colDiaW = (W - colHoraW - 32) / 6;
  const rowH = 44;
  const tableTop = headerH + 34;
  const tableH = totalHoras * rowH;
  const legendTop = tableTop + tableH + 24;
  const legendH = Math.max(44, turmas.length * 24 + 28);
  const H = legendTop + legendH + 24;

  const canvas = document.createElement("canvas");
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);

  // Fundo
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, W, H);

  // Cabeçalho
  const totalCreds = turmas.reduce((acc, t) => acc + (t.creditos || 0), 0);
  ctx.fillStyle = "#f1f5f9";
  ctx.font = "700 22px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText(`Grade UFABC — Plano ${planoNome}${semanaTitulo}`, 24, 36);

  ctx.fillStyle = "#94a3b8";
  ctx.font = "500 13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText(`${cursoNome}  •  ${turmas.length} disciplinas  •  ${totalCreds} créditos`, 24, 58);

  // Cabeçalho dos dias
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(16, headerH, W - 32, 34);
  ctx.fillStyle = "#cbd5e1";
  ctx.font = "600 13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  DIAS_ORDEM.forEach((diaKey, idx) => {
    const cx = 16 + colHoraW + idx * colDiaW + colDiaW / 2;
    ctx.fillText(DIA_INFO[diaKey].label, cx, headerH + 22);
  });

  // Grade de linhas
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 1;
  for (let i = 0; i <= totalHoras; i++) {
    const y = tableTop + i * rowH;
    ctx.beginPath();
    ctx.moveTo(16, y);
    ctx.lineTo(W - 16, y);
    ctx.stroke();

    if (i < totalHoras) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "500 12px monospace";
      ctx.textAlign = "right";
      ctx.fillText(`${String(minHora + i).padStart(2, "0")}:00`, 16 + colHoraW - 10, y + 18);
    }
  }
  for (let d = 0; d <= 6; d++) {
    const x = 16 + colHoraW + d * colDiaW;
    ctx.beginPath();
    ctx.moveTo(x, headerH);
    ctx.lineTo(x, tableTop + tableH);
    ctx.stroke();
  }

  // Blocos de aula
  const corPorId = new Map();
  turmas.forEach((t, idx) => corPorId.set(t.id, CORES[idx % CORES.length]));

  turmas.forEach((t) => {
    const cor = corPorId.get(t.id);
    (t.horarios || []).forEach((h) => {
      if (!horarioVisivel(h)) return;
      const idxDia = DIAS_ORDEM.indexOf(h.dia);
      if (idxDia === -1) return;
      const ini = horaParaFloat(h.inicio);
      const fim = horaParaFloat(h.fim);
      const x = 16 + colHoraW + idxDia * colDiaW + 4;
      const y = tableTop + (ini - minHora) * rowH + 3;
      const bw = colDiaW - 8;
      const bh = Math.max(24, (fim - ini) * rowH - 6);

      ctx.fillStyle = cor;
      roundRect(ctx, x, y, bw, bh, 6);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "left";
      ctx.font = "700 11.5px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      const titulo = t.disciplina.length > 22 ? t.disciplina.slice(0, 21) + "…" : t.disciplina;
      ctx.fillText(titulo, x + 7, y + 16);

      const sem = h.semanalidade === "quinzenal_1" ? " • Q1" : h.semanalidade === "quinzenal_2" ? " • Q2" : "";
      const tipo = h.tipo === "pratica" ? "Prática" : "Teoria";
      ctx.font = "500 10.5px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.88)";
      ctx.fillText(`${h.inicio}-${h.fim} • ${tipo}${sem}`, x + 7, y + 31);
    });
  });

  // Legenda embaixo
  ctx.textAlign = "left";
  ctx.fillStyle = "#cbd5e1";
  ctx.font = "600 12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText("Códigos de matrícula:", 24, legendTop + 12);

  turmas.forEach((t, idx) => {
    const y = legendTop + 34 + idx * 22;
    ctx.fillStyle = corPorId.get(t.id);
    ctx.beginPath();
    ctx.arc(30, y - 4, 5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#f1f5f9";
    ctx.font = "600 12px monospace";
    ctx.fillText(t.id, 44, y);

    ctx.fillStyle = "#94a3b8";
    ctx.font = "500 12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.fillText(`— ${t.disciplina} (${t.creditos} créd.)`, 185, y);
  });

  canvas.toBlob((blob) => {
    if (blob) baixarBlob(blob, `grade_ufabc_plano_${planoNome}${semanaArquivo}.png`);
  }, "image/png");
}
