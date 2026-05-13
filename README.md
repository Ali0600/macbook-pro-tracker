[![Track listings](https://github.com/Ali0600/macbook-pro-tracker/actions/workflows/track.yml/badge.svg)](https://github.com/Ali0600/macbook-pro-tracker/actions/workflows/track.yml)
[![Live dashboard](https://img.shields.io/badge/GitHub%20Pages-live-2ea44f?logo=github)](https://ali0600.github.io/macbook-pro-tracker/)
[![Python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)](https://www.python.org/)

Update: I found a Macbook Pro M1 16GB RAM 512GB storage, so this program is no longer needed.

Live dashboard: https://ali0600.github.io/macbook-pro-tracker/

Problem: I wanted to automate looking for Macbook Pro deals. It filters Kleinanziegen for deals based on my criteria and if it finds deals, it will open a chrome tab with the link.

## Showable things I did

- Built a Python web scraper (`requests` + `BeautifulSoup`) that parses Kleinanzeigen listing markup and extracts ad id, title, and price across multiple search pages.
- Designed a small rules engine that filters listings by chip generation (M1/M2/M3) against per-chip price ceilings, using word-boundary regex to avoid false-positive substring matches.
- Implemented idempotent de-duplication with a persisted `seen.json` so each listing only triggers an alert once.
- Set up a GitHub Actions cron workflow (`*/30 * * * *`) that runs the scraper unattended and auto-commits updated results back to the repo.
- Wrote a static dashboard (HTML/CSS/JS) that reads the committed `matches.js` and renders recent finds with relative timestamps, chip badges, and XSS-escaped output.
- Handled cross-platform browser launching, including WSL → Windows interop via `cmd.exe /c start`, with graceful fallback to Python's `webbrowser` module and a CI-aware no-op.
- Added a proper CLI with `argparse` supporting one-shot, long-running loop, custom interval, and dry-run modes, plus a timestamped log file.
