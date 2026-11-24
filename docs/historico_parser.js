// Parser 100% client-side do Histórico Escolar SIGAA UFABC (PDF.js + fallback texto)
// Nenhum byte do PDF sai do navegador do usuário.

import { normalizarTexto } from "./engine.js";

const CODIGO_UFABC_RE = /\b([A-Z]{2,5}\d{3,4}-\d{2})\b/;
const CPF_RE = /\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/;

const SIT_APROVADO = new Set(["APR", "APRN", "CUMP", "APROVADO", "APROVADA", "CUMPRIU"]);
const SIT_EQUIV = new Set(["DISP", "TRANS", "INCORP", "DISPENSADO", "TRANSFERIDO", "INCORPORADO"]);
const SIT_EM_CURSO = new Set(["MATR", "REC", "MATRICULADO", "CURSANDO"]);
const SIT_REPROVADO = new Set([
  "REP",
  "REPF",
  "REPMF",
  "REPN",
  "REPNF",
  "TRANC",
  "CANC",
  "REPROVADO",
  "TRANCADO",
  "CANCELADO",
]);
const TODAS_SITUACOES = new Set([...SIT_APROVADO, ...SIT_EQUIV, ...SIT_EM_CURSO, ...SIT_REPROVADO]);
const PRIORIDADE = { aprovado: 4, equivalencia: 3, em_curso: 2, reprovado: 1 };

function classificarSigla(siglaRaw, conceito = "") {
  const s = (siglaRaw || "").toUpperCase().replace(/[^A-Z]/g, "");
  if (SIT_APROVADO.has(s)) return "aprovado";
  if (SIT_EQUIV.has(s)) return "equivalencia";
  if (SIT_EM_CURSO.has(s)) return "em_curso";
  if (SIT_REPROVADO.has(s)) return "reprovado";
  const c = (conceito || "").trim().toUpperCase();
  if (["A", "B", "C", "D", "E"].includes(c)) return "aprovado";
  if (["F", "O"].includes(c)) return "reprovado";
  return null;
}

function adicionarItem(mapa, item) {
  const chave = item.codigo || item.nome_norm;
  if (!chave) return;
  const ant = mapa.get(chave);
  if (!ant || PRIORIDADE[item.status] >= PRIORIDADE[ant.status]) {
    mapa.set(chave, item);
  }
}

export function sanitizarTextoHistorico(texto, nomesPorCodigo = new Map()) {
  // Rejuntar códigos quebrados em duas linhas (ex: "BCL030\n6-15" -> "BCL0306-15")
  const norm = (texto || "").replace(/([A-Z]{2,5}\d{2,4})\s*\n\s*(\d{0,2}-\d{2})/g, "$1$2");
  const linhas = norm.split(/\r?\n/);
  const mapa = new Map();

  for (let i = 0; i < linhas.length; i++) {
    const linha = linhas[i].replace(/\s+/g, " ").trim();
    if (!linha) continue;
    const mCod = linha.match(CODIGO_UFABC_RE);
    if (!mCod) continue;

    const codigo = mCod[1];
    const pos = linha.slice(mCod.index + codigo.length).trim();
    let contexto = pos;
    if (i + 1 < linhas.length) {
      const prox = linhas[i + 1].replace(/\s+/g, " ").trim();
      if (prox && !CODIGO_UFABC_RE.test(prox) && prox.length < 120) {
        const toks = contexto.toUpperCase().match(/\b[A-Z]+\b/g) || [];
        if (!toks.some((t) => TODAS_SITUACOES.has(t))) {
          contexto = `${contexto} ${prox}`;
        }
      }
    }

    const toksUp = contexto.toUpperCase().match(/\b[A-Z]+\b/g) || [];
    const sitTok = [...toksUp].reverse().find((t) => TODAS_SITUACOES.has(t)) || "";
    const conceito = [...toksUp].reverse().find((t) => ["A", "B", "C", "D", "E", "F", "O"].includes(t)) || "";
    const status = classificarSigla(sitTok, conceito) || (contexto.includes("--") ? "em_curso" : "aprovado");

    let nome = pos
      .replace(/\b20\d{2}\s*[./-]\s*[123]\b.*$/, "")
      .replace(
        /\b(APROVAD[OA]?|REPROVAD[OA]?|MATRICULAD[OA]?|TRANCAD[OA]?|DISPENSAD[OA]?|EQUIVAL[EÊ]NCIA|EM CURSO|CURSANDO|APRN?|REPM?F?|REPNF?|MATR|DISP|TRANS|INCORP|CUMP|TRANC|CANC|REC|OBR|OL|LIV|ATC)\b.*$/i,
        ""
      )
      .replace(/\s+\d{1,3}h?\s*$/, "")
      .replace(/\s+[A-FO]\s*$/, "")
      .trim();

    if ((!nome || nome.length < 3 || CPF_RE.test(nome)) && nomesPorCodigo.has(codigo)) {
      nome = nomesPorCodigo.get(codigo);
    }
    if (!nome || CPF_RE.test(nome)) nome = codigo;

    adicionarItem(mapa, {
      codigo,
      nome,
      nome_norm: normalizarTexto(nome),
      status,
      conceito,
    });
  }

  const disciplinas = [...mapa.values()].sort((a, b) => a.nome_norm.localeCompare(b.nome_norm));
  return {
    gerado_em: new Date().toISOString(),
    total_disciplinas: disciplinas.length,
    disciplinas,
  };
}

/**
 * Extrai a tabela do Histórico SIGAA UFABC diretamente no navegador usando PDF.js.
 * Reagrupa linhas por coordenada Y e junta códigos quebrados verticalmente (ex: BCL030 + 6-15).
 */
export async function sanitizarPdfHistoricoBrowser(file, nomesPorCodigo = new Map()) {
  if (!window.pdfjsLib) {
    throw new Error("PDF.js não carregou. Verifique sua conexão ou use a opção de colar o texto.");
  }

  const arrayBuffer = await file.arrayBuffer();
  const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const mapa = new Map();
  let textoFallback = "";

  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const tc = await page.getTextContent();

    // Coletar itens com coordenadas (x, y)
    const itens = tc.items
      .map((it) => ({
        str: (it.str || "").trim(),
        x: it.transform[4],
        y: it.transform[5],
      }))
      .filter((it) => it.str.length > 0);

    // Agrupar em linhas visuais (tolerância vertical de 4px)
    itens.sort((a, b) => b.y - a.y || a.x - b.x);
    const linhasVisuais = [];
    for (const it of itens) {
      let grupo = linhasVisuais.find((g) => Math.abs(g.y - it.y) <= 4.5);
      if (!grupo) {
        grupo = { y: it.y, items: [] };
        linhasVisuais.push(grupo);
      }
      grupo.items.push(it);
    }
    linhasVisuais.forEach((g) => g.items.sort((a, b) => a.x - b.x));
    textoFallback += linhasVisuais.map((g) => g.items.map((i) => i.str).join(" ")).join("\n") + "\n";

    // Identificar blocos de registros da tabela:
    // Cada linha de disciplina no SIGAA contém uma sigla de Situação (APR, DISP, MATR, REP, REPF, TRANS, etc.)
    // e eventualmente o código UFABC quebrado em 2 linhas adjacentes na mesma faixa X!
    for (let i = 0; i < linhasVisuais.length; i++) {
      const linhaAtual = linhasVisuais[i];
      const sitItem = [...linhaAtual.items]
        .reverse()
        .find((it) => TODAS_SITUACOES.has(it.str.toUpperCase().replace(/[^A-Z]/g, "")));
      if (!sitItem) continue;

      const situacaoRaw = sitItem.str.toUpperCase().replace(/[^A-Z]/g, "");
      const status = classificarSigla(situacaoRaw);
      if (!status) continue;

      // Coletar itens desta linha e das linhas imediatamente acima/abaixo (distância <= 14px)
      // para capturar códigos quebrados em 2 linhas (ex: "BCJ0204" em cima e "-15" embaixo)
      const vizinhos = [linhaAtual];
      if (i > 0 && Math.abs(linhasVisuais[i - 1].y - linhaAtual.y) <= 13) {
        const temSitAcima = linhasVisuais[i - 1].items.some((it) =>
          TODAS_SITUACOES.has(it.str.toUpperCase().replace(/[^A-Z]/g, ""))
        );
        if (!temSitAcima) vizinhos.unshift(linhasVisuais[i - 1]);
      }
      if (i + 1 < linhasVisuais.length && Math.abs(linhasVisuais[i + 1].y - linhaAtual.y) <= 13) {
        const temSitAbaixo = linhasVisuais[i + 1].items.some((it) =>
          TODAS_SITUACOES.has(it.str.toUpperCase().replace(/[^A-Z]/g, ""))
        );
        if (!temSitAbaixo) vizinhos.push(linhasVisuais[i + 1]);
      }

      // Procurar código na faixa esquerda (x < 210px tipicamente, antes do nome da disciplina)
      const itensEsquerda = vizinhos
        .flatMap((l) => l.items)
        .filter((it) => it.x < sitItem.x - 120)
        .sort((a, b) => a.x - b.x || b.y - a.y);

      // Agrupar tokens na coluna do código (mesma faixa X ~ +-18px) para rejuntar quebras verticais
      let codigo = "";
      const colunasX = [];
      for (const it of itensEsquerda) {
        const limpo = it.str.toUpperCase().replace(/\s+/g, "");
        if (!limpo || limpo === "OBR" || limpo === "OL" || limpo === "LIV" || limpo === "ATC" || /^20\d{2}\.[123]$/.test(limpo)) {
          continue;
        }
        let col = colunasX.find((c) => Math.abs(c.x - it.x) <= 22);
        if (!col) {
          col = { x: it.x, partes: [] };
          colunasX.push(col);
        }
        col.partes.push({ y: it.y, str: limpo });
      }

      for (const col of colunasX) {
        col.partes.sort((a, b) => b.y - a.y);
        const junto = col.partes.map((p) => p.str).join("");
        const m = junto.match(CODIGO_UFABC_RE);
        if (m) {
          codigo = m[1];
          break;
        }
      }

      // Extrair nome da disciplina (itens entre o código e a coluna de créditos/turma)
      const textoLinha = vizinhos
        .map((l) =>
          l.items
            .filter((it) => it.x > 110 && it.x < sitItem.x - 80)
            .map((it) => it.str)
            .join(" ")
        )
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();

      let nome = textoLinha
        .replace(/\b\d{1,2}\s+\d{1,3}\s+\d{1,2}\b.*$/, "")
        .replace(/\b(DA|DB|DC|NA|NB|NC)\d[A-Z0-9-]+\b.*$/i, "")
        .replace(/--.*$/, "")
        .trim();

      if (codigo && nomesPorCodigo.has(codigo)) {
        nome = nomesPorCodigo.get(codigo);
      }
      if (!codigo && (!nome || nome.length < 4)) continue;
      if (codigo === "ENADE" || nome.toUpperCase().includes("ENADE")) continue;
      if (CPF_RE.test(nome)) nome = codigo;

      adicionarItem(mapa, {
        codigo,
        nome: nome || codigo,
        nome_norm: normalizarTexto(nome || codigo),
        status,
        conceito: "",
      });
    }
  }

  if (mapa.size === 0) {
    return sanitizarTextoHistorico(textoFallback, nomesPorCodigo);
  }

  const disciplinas = [...mapa.values()].sort((a, b) => a.nome_norm.localeCompare(b.nome_norm));
  return {
    gerado_em: new Date().toISOString(),
    total_disciplinas: disciplinas.length,
    disciplinas,
  };
}
