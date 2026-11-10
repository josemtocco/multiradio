#!/usr/bin/env python3
"""
MultiRádio WebTVs → M3U Generator (otimizado para SS IPTV)

- Coleta todos os canais de https://multiradio.com.br/webtvs.php
- Extrai nome, logo, localização e URL HLS (m3u8)
- Mantém canais ativos, remove inativos e adiciona novos
- Gera lista.m3u com group-title por estado (UF)
- Atualiza a cada 6 horas via GitHub Actions
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_URL = "https://multiradio.com.br"
LIST_URL = f"{BASE_URL}/webtvs.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
}
TIMEOUT = 20
STREAM_CHECK_TIMEOUT = 12
MAX_RETRIES = 2
CHANNELS_FILE = Path("channels.json")
M3U_FILE = Path("lista.m3u")
USER_AGENT_STREAM = HEADERS["User-Agent"]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(url: str, sess: requests.Session, retries: int = MAX_RETRIES) -> str | None:
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"[WARN] Falha ao baixar {url} (tentativa {attempt + 1}): {e}")
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return None


def extract_stream_url(html: str) -> str | None:
    """Extrai const streamUrl = "..." do script do player HLS."""
    # Padrão principal
    m = re.search(
        r'const\s+streamUrl\s*=\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Fallback: qualquer .m3u8 no HTML
    m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None


def extract_logo(html: str, soup: BeautifulSoup) -> str | None:
    # Schema.org image
    m = re.search(
        r'"image"\s*:\s*["\'](https?://[^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"].strip()

    # img dentro do header / logo do canal
    for img in soup.select("img"):
        src = img.get("src") or ""
        if any(k in src.lower() for k in ("logo", "banner", "upload", "webtv")):
            return urljoin(BASE_URL, src)
    return None


def extract_location(soup: BeautifulSoup, html: str) -> str:
    # Procura padrão "Cidade - UF"
    text = soup.get_text(" ", strip=True)
    m = re.search(
        r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\.\-]{2,40})\s*[-–]\s*([A-Z]{2})\b",
        text,
    )
    if m:
        return f"{m.group(1).strip()} - {m.group(2)}"

    # Fallback no HTML bruto
    m = re.search(
        r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\.\-]{2,40})\s*[-–]\s*([A-Z]{2})\b",
        html,
    )
    if m:
        return f"{m.group(1).strip()} - {m.group(2)}"
    return "Brasil"


def get_uf(location: str) -> str:
    m = re.search(r"-\s*([A-Z]{2})\b", location)
    return m.group(1) if m else "BR"


def scrape_list_page(sess: requests.Session) -> list[dict[str, str]]:
    """Retorna lista de {slug, name, url} a partir da página principal."""
    html = fetch(LIST_URL, sess)
    if not html:
        print("[ERROR] Não foi possível carregar a lista de WebTVs.")
        return []

    soup = BeautifulSoup(html, "lxml")
    channels: list[dict[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/webtv/" not in href and not href.startswith("webtv/"):
            continue
        # Normaliza
        if href.startswith("webtv/"):
            href = "/" + href
        full = urljoin(BASE_URL, href)
        slug = full.rstrip("/").split("/")[-1]
        if not slug or slug in seen:
            continue
        seen.add(slug)

        # Tenta pegar o nome próximo
        name = a.get_text(strip=True)
        if not name or name.lower() in ("assistir", "assistir agora", "assistir ao vivo", ""):
            # Procura título no card pai
            parent = a.find_parent(["div", "article", "section", "li"])
            if parent:
                h = parent.find(["h2", "h3", "h4", "strong", "span"])
                if h:
                    name = h.get_text(strip=True)
        if not name or len(name) < 3:
            name = slug.replace("-", " ").title()

        channels.append({"slug": slug, "name": name, "url": full})

    print(f"[INFO] Encontrados {len(channels)} canais na listagem.")
    return channels


def scrape_channel(sess: requests.Session, ch: dict[str, str]) -> dict[str, Any] | None:
    html = fetch(ch["url"], sess)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    stream = extract_stream_url(html)
    if not stream:
        print(f"[WARN] Sem stream para {ch['name']} ({ch['slug']})")
        return None

    # Nome mais preciso do título da página
    title = soup.find("h1")
    name = title.get_text(strip=True) if title else ch["name"]
    if " - MultiRádio" in name:
        name = name.replace(" - MultiRádio", "").strip()

    logo = extract_logo(html, soup)
    location = extract_location(soup, html)
    uf = get_uf(location)

    return {
        "slug": ch["slug"],
        "name": name,
        "location": location,
        "uf": uf,
        "logo": logo or "",
        "stream": stream,
        "page_url": ch["url"],
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }


def is_stream_active(url: str, sess: requests.Session) -> bool:
    """Verifica se o m3u8 responde e contém conteúdo válido."""
    try:
        r = sess.get(
            url,
            timeout=STREAM_CHECK_TIMEOUT,
            headers={"User-Agent": USER_AGENT_STREAM, "Referer": BASE_URL + "/"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return False
        text = r.text[:2000].lower()
        # HLS válido costuma ter #EXTM3U ou #EXT-X-
        if "#extm3u" in text or "#ext-x-" in text:
            return True
        # Alguns servidores retornam playlist mínima
        if "playlist" in text or ".ts" in text or "chunk" in text:
            return True
        return len(r.content) > 50
    except Exception:
        return False


def load_previous() -> dict[str, dict[str, Any]]:
    if not CHANNELS_FILE.exists():
        return {}
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        return {c["slug"]: c for c in data.get("channels", [])}
    except Exception as e:
        print(f"[WARN] Erro ao ler channels.json: {e}")
        return {}


def save_state(channels: list[dict[str, Any]]) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": LIST_URL,
        "total": len(channels),
        "channels": channels,
    }
    CHANNELS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[INFO] Estado salvo em {CHANNELS_FILE} ({len(channels)} canais)")


def generate_m3u(channels: list[dict[str, Any]]) -> str:
    """Gera M3U otimizado para SS IPTV."""
    lines = [
        "#EXTM3U",
        "#PLAYLIST: MultiRádio WebTVs",
        f"#EXT-X-SESSION-DATA:DATA-ID=\"com.ssiptv.update\",VALUE=\"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\"",
    ]

    # Ordena por UF e depois por nome
    channels_sorted = sorted(
        channels,
        key=lambda c: (c.get("uf", "ZZ"), c.get("name", "").lower()),
    )

    for ch in channels_sorted:
        name = ch["name"].replace(",", " ")
        logo = ch.get("logo") or ""
        group = f"WebTVs | {ch.get('uf', 'BR')}"
        # SS IPTV gosta de tvg-name limpo e group-title
        extinf = (
            f'#EXTINF:-1 tvg-id="{ch["slug"]}" '
            f'tvg-name="{name}" '
            f'tvg-logo="{logo}" '
            f'group-title="{group}",{name}'
        )
        lines.append(extinf)
        lines.append(ch["stream"])

    return "\n".join(lines) + "\n"


def main() -> int:
    print("=" * 60)
    print("MultiRádio WebTVs → M3U Generator")
    print(f"Início: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    sess = session()
    previous = load_previous()
    print(f"[INFO] Canais anteriores carregados: {len(previous)}")

    # 1. Lista atual de canais no site
    listed = scrape_list_page(sess)
    if not listed:
        print("[ERROR] Nenhum canal encontrado. Abortando.")
        return 1

    current: dict[str, dict[str, Any]] = {}
    for item in listed:
        print(f"[SCRAPE] {item['name']} ({item['slug']}) ...")
        data = scrape_channel(sess, item)
        if data:
            current[data["slug"]] = data
        time.sleep(0.8)  # educado com o servidor

    print(f"[INFO] Canais coletados com sucesso: {len(current)}")

    # 2. Merge: manter ativos, adicionar novos, verificar inativos
    final: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    # Novos + existentes do scrape
    for slug, ch in current.items():
        seen_slugs.add(slug)
        active = is_stream_active(ch["stream"], sess)
        ch["active"] = active
        if active:
            final.append(ch)
            print(f"  [OK]   {ch['name']} → ativo")
        else:
            print(f"  [DOWN] {ch['name']} → stream inativo (não incluído)")
        time.sleep(0.4)

    # Canais antigos que sumiram da listagem: verifica se ainda estão ativos
    for slug, old in previous.items():
        if slug in seen_slugs:
            continue
        stream = old.get("stream")
        if not stream:
            continue
        print(f"[CHECK] Canal antigo fora da listagem: {old.get('name')} ...")
        if is_stream_active(stream, sess):
            old["active"] = True
            old["last_seen"] = datetime.now(timezone.utc).isoformat()
            final.append(old)
            print(f"  [KEEP] {old.get('name')} → ainda ativo, mantido")
        else:
            print(f"  [DROP] {old.get('name')} → inativo, removido")
        time.sleep(0.4)

    # 3. Ordena e salva
    final.sort(key=lambda c: (c.get("uf", "ZZ"), c.get("name", "").lower()))

    save_state(final)
    m3u_content = generate_m3u(final)
    M3U_FILE.write_text(m3u_content, encoding="utf-8")
    print(f"[INFO] M3U gerado: {M3U_FILE} ({len(final)} canais)")

    print("=" * 60)
    print(f"Concluído. Total final: {len(final)} canais ativos")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
