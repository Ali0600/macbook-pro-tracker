"""
Kleinanzeigen MacBook Pro tracker.

Scrapes the Berlin MacBook Pro listings page and alerts when a listing title
mentions an M1 / M2 / M3 chip under a target price:

    m1 < 500 €
    m2 < 600 €
    m3 < 700 €

Matched listings are opened in the default Windows browser (Chrome if default)
and remembered in seen.json so we only alert once per listing.

Usage:
    python3 tracker.py              # single run
    python3 tracker.py --loop       # runs forever, every 30 minutes
    python3 tracker.py --loop --interval 900   # custom interval (seconds)
    python3 tracker.py --dry-run    # print matches, don't open browser
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.kleinanzeigen.de/s-berlin/macbook-pro/k0l3331",
    "https://www.kleinanzeigen.de/s-direktkaufen:aktiv/versand:ja/macbook-pro/k0",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# chip token -> max price (exclusive)
RULES = {
    "m1": 500,
    "m2": 600,
    "m3": 700,
}

BASE_DIR = Path(__file__).resolve().parent
SEEN_FILE = BASE_DIR / "seen.json"
LOG_FILE = BASE_DIR / "tracker.log"
MATCHES_FILE = BASE_DIR / "matches.js"
MAX_MATCHES = 100

MATCHES_PREFIX = "window.MATCHES = "
MATCHES_SUFFIX = ";\n"


@dataclass
class Listing:
    ad_id: str
    title: str
    price: int | None  # euros, None if unpriced / "VB" only / "Zu verschenken"
    url: str


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def load_matches() -> list[dict]:
    if not MATCHES_FILE.exists():
        return []
    try:
        text = MATCHES_FILE.read_text(encoding="utf-8").strip()
        if text.startswith(MATCHES_PREFIX):
            text = text[len(MATCHES_PREFIX):]
        text = text.rstrip(";").strip()
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_matches(matches: list[dict]) -> None:
    body = json.dumps(matches, ensure_ascii=False, indent=2)
    MATCHES_FILE.write_text(MATCHES_PREFIX + body + MATCHES_SUFFIX, encoding="utf-8")


def parse_price(raw: str) -> int | None:
    """'660 €' -> 660, '1.299 €' -> 1299, 'VB' -> None, '' -> None."""
    if not raw:
        return None
    # strip thousand separators and non-digits
    digits = re.sub(r"[^\d]", "", raw.split("€")[0])
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def fetch_listings(url: str) -> list[Listing]:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    listings: list[Listing] = []
    for art in soup.select("article.aditem"):
        ad_id = art.get("data-adid") or ""
        href = art.get("data-href") or ""
        if not ad_id or not href:
            continue

        title_el = art.select_one("h2.text-module-begin a.ellipsis")
        if not title_el:
            continue
        title = html.unescape(title_el.get_text(strip=True))

        price_el = art.select_one("p.aditem-main--middle--price-shipping--price")
        price_raw = price_el.get_text(" ", strip=True) if price_el else ""
        price = parse_price(price_raw)

        full_url = "https://www.kleinanzeigen.de" + href
        listings.append(Listing(ad_id=ad_id, title=title, price=price, url=full_url))

    return listings


def matches_rule(title: str, price: int | None) -> str | None:
    """Return the chip key ('m1'/'m2'/'m3') if the listing matches a rule."""
    if price is None or price < 200:
        return None
    lowered = title.lower()
    for chip, max_price in RULES.items():
        # \bmN\b — avoid matching e.g. 'HDMI1' or stray substrings
        if re.search(rf"\b{chip}\b", lowered) and price < max_price:
            return chip
    return None


def open_in_browser(url: str) -> None:
    """Open the URL in the Windows default browser from WSL or native Windows.

    Best-effort: failures are logged but never raised, so a flaky WSL interop
    setup can't kill the tracker loop. The URL is already in the log above,
    so the user can always click it from there.
    """
    if os.environ.get("CI"):
        return
    # WSL: hand off to cmd.exe start. We must WAIT for cmd to return — if the
    # Python process exits before cmd has dispatched ShellExecute, the child is
    # torn down mid-handoff and no browser window appears. `start` itself is
    # async on the Windows side, so cmd exits quickly once the URL is queued.
    # binfmt_misc for .exe can also be transiently broken (raising OSError
    # ENOEXEC) even when cmd.exe is on PATH, so catch OSError broadly —
    # FileNotFoundError is a subclass and still handled.
    if "microsoft" in os.uname().release.lower():
        try:
            subprocess.run(
                ["cmd.exe", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
            return
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"cmd.exe launch failed ({e}); falling back to webbrowser")

    # Fallback: Python webbrowser module (may also fail in headless WSL)
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception as e:
        log(f"webbrowser fallback also failed ({e}); open the URL manually")


def run_once(dry_run: bool = False) -> int:
    listings: list[Listing] = []
    seen_ids: set[str] = set()
    for url in URLS:
        try:
            for l in fetch_listings(url):
                if l.ad_id in seen_ids:
                    continue
                seen_ids.add(l.ad_id)
                listings.append(l)
        except requests.RequestException as e:
            log(f"fetch failed for {url}: {e}")

    log(f"fetched {len(listings)} listings across {len(URLS)} pages")

    seen = load_seen()
    matches = load_matches()
    new_matches = 0

    for l in listings:
        chip = matches_rule(l.title, l.price)
        if not chip:
            continue
        if l.ad_id in seen:
            continue

        new_matches += 1
        log(f"MATCH [{chip}] {l.price} € — {l.title}")
        log(f"       {l.url}")
        if not dry_run:
            open_in_browser(l.url)
        seen.add(l.ad_id)
        matches.insert(0, {
            "ad_id": l.ad_id,
            "chip": chip,
            "title": l.title,
            "price": l.price,
            "url": l.url,
            "found_at": datetime.now().isoformat(timespec="seconds"),
        })

    if not dry_run:
        save_seen(seen)
        if new_matches:
            save_matches(matches[:MAX_MATCHES])

    if new_matches == 0:
        log("no new matches")
    return new_matches


def run_loop(interval: int, dry_run: bool) -> None:
    log(f"loop mode — interval {interval}s")
    while True:
        try:
            run_once(dry_run=dry_run)
        except Exception as e:  # keep the loop alive
            log(f"unexpected error: {e}")
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="keep running on a timer")
    parser.add_argument(
        "--interval",
        type=int,
        default=30 * 60,
        help="loop interval in seconds (default 1800 = 30 min)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log matches but don't open the browser or persist seen.json",
    )
    args = parser.parse_args()

    if args.loop:
        run_loop(args.interval, args.dry_run)
        return 0
    return 0 if run_once(dry_run=args.dry_run) >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
