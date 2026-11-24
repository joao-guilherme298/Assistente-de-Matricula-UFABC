from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

PROGRAD_URLS = {
    "matriculas": "https://prograd.ufabc.edu.br/matriculas",
    "catalogo": "https://prograd.ufabc.edu.br/catalogos-de-disciplinas",
    "bcc": "https://prograd.ufabc.edu.br/cursos/17",
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UFABCMatriculaHelper/1.0; +local)"
}


def _extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Retorna lista de (texto_normalizado, url_absoluta) para todos os links da página."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        text = " ".join(a.get_text(" ", strip=True).split())
        links.append((text, full_url))
    return links


def _score_year(text: str, url: str) -> tuple[int, int]:
    """Extrai (ano, quadrimestre) para ordenar links do mais recente para o mais antigo."""
    combined = f"{text} {url}"
    m_q = re.search(r"(20\d{2})\s*[._/-]\s*([123])", combined)
    if m_q:
        return int(m_q.group(1)), int(m_q.group(2))
    years = [int(y) for y in re.findall(r"20\d{2}", combined)]
    return (max(years) if years else 0, 0)


def descobrir_url_turmas_ofertadas(client: httpx.Client) -> Optional[str]:
    resp = client.get(PROGRAD_URLS["matriculas"], follow_redirects=True)
    resp.raise_for_status()
    links = _extract_links(resp.text, str(resp.url))
    candidatos = []
    for text, url in links:
        low = f"{text} {url}".lower()
        if ".pdf" in low and ("ofert" in low or "turma" in low or "matricula" in low):
            candidatos.append((_score_year(text, url), text, url))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][2] if candidatos else None


def descobrir_url_catalogo(client: httpx.Client) -> Optional[str]:
    resp = client.get(PROGRAD_URLS["catalogo"], follow_redirects=True)
    resp.raise_for_status()
    links = _extract_links(resp.text, str(resp.url))
    candidatos = []
    for text, url in links:
        low = f"{text} {url}".lower()
        if ".pdf" in low and ("catalogo" in low or "catálogo" in low or "disciplina" in low):
            if "extensionista" in low:
                continue
            bonus = 1 if ("graduacao" in low or "graduação" in low or "202" in low) else 0
            candidatos.append(((*_score_year(text, url), bonus), text, url))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][2] if candidatos else None


def descobrir_url_opcoes_limitadas_bcc(client: httpx.Client) -> Optional[str]:
    resp = client.get(PROGRAD_URLS["bcc"], follow_redirects=True)
    resp.raise_for_status()
    links = _extract_links(resp.text, str(resp.url))
    for text, url in links:
        low = f"{text} {url}".lower()
        if ".pdf" in low and ("limitada" in low or "rol de disciplinas" in low):
            return url
    return None


def descobrir_url_ppc_bcc(client: httpx.Client) -> Optional[str]:
    resp = client.get(PROGRAD_URLS["bcc"], follow_redirects=True)
    resp.raise_for_status()
    links = _extract_links(resp.text, str(resp.url))
    candidatos = []
    for text, url in links:
        low = f"{text} {url}".lower()
        if ".pdf" in low and (
            "ppc" in low
            or "projeto" in low
            or "pedagogico" in low
            or "pedagógico" in low
            or "bcc" in low
            or "computacao" in low
            or "computação" in low
        ):
            # Priorizar matriz 2023 ou mais recente
            bonus = 2 if ("ppc" in low or "projeto" in low) else 0
            candidatos.append(((*_score_year(text, url), bonus), text, url))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][2] if candidatos else None


def baixar_arquivo(client: httpx.Client, url: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        with destino.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return destino


def sincronizar_documentos_publicos(
    data_dir: Path,
    forcar_download: bool = False,
) -> dict[str, str]:
    """Baixa os PDFs públicos mais recentes da PROGRAD para data/publico."""
    data_dir.mkdir(parents=True, exist_ok=True)
    resultado: dict[str, str] = {}

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=60.0, verify=True) as client:
        # 1. Turmas ofertadas (mantém o arquivo local se já existir e não forçar)
        ofertas_locais = sorted(data_dir.glob("*turmas_ofertadas*.pdf"), reverse=True)
        if ofertas_locais and not forcar_download:
            resultado["oferta"] = str(ofertas_locais[0])
        else:
            url_oferta = descobrir_url_turmas_ofertadas(client)
            if url_oferta:
                dest = data_dir / "turmas_ofertadas_atual.pdf"
                baixar_arquivo(client, url_oferta, dest)
                resultado["oferta"] = str(dest)

        # 2. Catálogo de disciplinas
        catalogo_path = data_dir / "catalogo_disciplinas.pdf"
        if catalogo_path.exists() and not forcar_download:
            resultado["catalogo"] = str(catalogo_path)
        else:
            url_cat = descobrir_url_catalogo(client)
            if url_cat:
                baixar_arquivo(client, url_cat, catalogo_path)
                resultado["catalogo"] = str(catalogo_path)

        # 3. PPC do BCC
        ppc_path = data_dir / "ppc_bcc.pdf"
        if ppc_path.exists() and not forcar_download:
            resultado["ppc_bcc"] = str(ppc_path)
        else:
            url_ppc = descobrir_url_ppc_bcc(client)
            if url_ppc:
                baixar_arquivo(client, url_ppc, ppc_path)
                resultado["ppc_bcc"] = str(ppc_path)

        # 4. Rol de disciplinas de opção limitada do BCC
        ol_path = data_dir / "opcoes_limitadas_bcc.pdf"
        if ol_path.exists() and not forcar_download:
            resultado["opcoes_limitadas_bcc"] = str(ol_path)
        else:
            url_ol = descobrir_url_opcoes_limitadas_bcc(client)
            if url_ol:
                baixar_arquivo(client, url_ol, ol_path)
                resultado["opcoes_limitadas_bcc"] = str(ol_path)

    return resultado
