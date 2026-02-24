# Commercialization Strategy: Subtitle Extractor

## Executive Summary

The subtitle extractor is a production-ready Python CLI tool that batch-extracts embedded
subtitles from video files. It supports 25+ languages, OCR for image-based subtitles (PGS),
subtitle sync correction, multi-threading, YAML config, and JSON/CSV audit reports.

Key commercialization strengths:
- `SubtitleExtractor` is already importable as a library with a clean constructor API
- `process_video_file()` returns structured dicts — a natural API response format
- Optional-dependency architecture means zero mandatory Python deps for the core
- OCR for PGS/dvdsub subtitles is a genuine differentiator (most free tools skip this)
- VAD-based sync correction is a hard problem solved with production-grade logic
- An existing test suite (pytest) reduces the risk of regression during commercialization refactors

---

## Target Customer Segments

### Segment A: Home Server Operators (Plex / Jellyfin / Kodi)
- **Size:** 500K–1M users willing to pay for automation tooling (~5–10% of 10M+ Plex/Jellyfin installs)
- **Pain points:** Large libraries (500–10,000 files), multi-language households, manual subtitle setup
- **Willingness to pay:** $5–20/month or $19–29 one-time

### Segment B: Content Creators and Dubbing Studios
- **Size:** 50K+ studios/channels processing 10–500 videos/month for localization
- **Pain points:** Track selection from multi-language MKVs, OCR for broadcast PGS subtitles, format conversion (ASS → SRT), sync on dubbed tracks
- **Willingness to pay:** $50–200/month

### Segment C: Enterprise Media Archives and Broadcasters
- **Size:** ~7,000 organizations (broadcasters, universities, streaming services)
- **Pain points:** Audit trails, preserve-directory-structure output, pipeline integration, scale
- **Willingness to pay:** $500–5,000/month

### Segment D: Accessibility Platform Integrators
- **Size:** Niche but growing (SDH requirements, WCAG compliance, closed-caption archiving)
- **Willingness to pay:** $100–1,000/month

---

## Product Models (Prioritized by Effort vs. Revenue)

### 1. PyPI Pro Package — QUICK WIN

**Timeline:** 2–4 weeks, ~30 hours
**Revenue potential:** $5K–$20K/year in year 1

Free tier (`subtitle-extractor`) stays on PyPI. A `subtitle-extractor-pro` package unlocks
multi-threading, sync detection, OCR, and JSON reports behind a runtime license key.

**Implementation:**
- Add `license_key` to `config.py:_VALID_KEYS`; `load_config()` already reads it from YAML
- Inject key validation at top of `cli.py:main()` before `SubtitleExtractor` is instantiated
- Gate: `threads > 1`, `check_sync`/`fix_sync`, OCR (`pgsrip`), and `report_format`
- Publish `subtitle-extractor-pro` as a separate PyPI package that imports and extends the free package

**Pricing:**
| Tier | Price | Limits |
|------|-------|--------|
| Free | $0 | Single-threaded, English only, no sync/OCR/reports |
| Pro | $9/month or $79/year | Unlimited threads, all languages, sync, OCR, reports |
| Team | $49/month | 5 seats |

---

### 2. Desktop GUI App — QUICK WIN

**Timeline:** 3–6 weeks, ~60 hours
**Revenue potential:** $10K–$50K/year

Native GUI (PyQt6 or Tauri) wrapping the existing CLI. Drag-and-drop folder, visual
language/sync config, progress bar, results summary screen. Bundled with ffmpeg + mkvtoolnix
via PyInstaller as a single executable.

**Critical code change required first:**
The `logging.info` calls inside `_print_progress()` and the hot loops in
`_process_sequential()` / `_process_parallel()` must be replaced with a pluggable
`on_progress(current, total, result)` callback. Currently progress is tied to logging and
cannot be redirected to a GUI event loop. This is the single most impactful change.

**Pricing:**
- Personal: $29 one-time (impulse buy price point)
- Commercial: $79 one-time
- 30-day free trial or 10-file batch limit as demo

---

### 3. "Sync Fixer" Standalone Tool — QUICK WIN

**Timeline:** 2–3 weeks, ~20 hours
**Revenue potential:** $4K–$15K/year

The `sync.py` module solves a specific, viral problem independently of subtitle extraction.
Repackage as `sync-subs video.mkv subtitle.srt` — one command, one purpose, highly marketable.

This targets a *larger* audience than batch extraction users: anyone who already has subtitles
but finds them out of sync. "Your subtitles are 2 seconds off? Fix them automatically" is more
searchable and shareable than batch extraction.

**Pricing:** $4.99 one-time or bundled into the Pro tier.

---

### 4. Jellyfin / Plex Plugin — MEDIUM TERM

**Timeline:** 2–4 months
**Revenue potential:** Recurring revenue from Segment A; highest retention

A local daemon (FastAPI) wrapping a new `process_single_file(path: Path) -> Dict` public
method on `SubtitleExtractor`. The media server plugin calls `POST /extract` on library scan
events and writes subtitle files back to the media directory automatically.

**Why this is the recurring revenue moat:** Plugin users are highly sticky — the tool becomes
invisible infrastructure running in the background. Once installed, they renew indefinitely.

**Implementation steps:**
1. Add `process_single_file()` to `extractor.py` — a public method for single-file extraction
   without requiring `process_directory()` setup
2. Build a minimal FastAPI daemon wrapping this method
3. Build a Jellyfin plugin (.NET/C#) that calls `POST /extract` on `LibraryChanged` events
4. The `list_tracks_in_file()` output becomes a `/preview` endpoint for the plugin settings UI

**Pricing:**
- Free plugin + $4.99/month subscription for the daemon backend (preferred — recurring revenue)
- Or $19 one-time for the full package

---

### 5. SaaS REST API — MEDIUM TERM

**Timeline:** 4–8 months
**Revenue potential:** $50K–$500K ARR

Users upload a video or provide a URL; they receive subtitle files as a download or via webhook.
The `process_video_file()` return dict (`{"file": ..., "status": ..., "subtitles": [...], "errors": [...]}`)
maps directly to an API response body.

**Architecture:**
- FastAPI application + Celery/Redis job queue (extraction is long-running — minutes per file)
- Docker image bundling ffmpeg, mkvtoolnix, Tesseract, pgsrip, ffsubsync
- S3-compatible storage for input/output; the `output_dir` abstraction in `_get_output_path()`
  is extended to accept S3 URIs
- PostgreSQL jobs table replaces the `resume` pickle state; job UUID replaces the processed-files set
- API key authentication, per-tier rate limiting, webhook callbacks

**Pricing:**
| Tier | Price | Volume | Features |
|------|-------|--------|----------|
| Free | $0 | 5 files/month, 500MB | Text subtitles only |
| Starter | $19/month | 100 files, 2GB | All languages |
| Pro | $79/month | 1,000 files, 5GB | + OCR, sync, webhooks, JSON reports |
| Business | $299/month | 10,000 files, SLA | + Priority OCR, 99.9% uptime |
| Overage | — | — | $0.05 per file beyond plan limit |

---

### 6. Enterprise On-Premise — LONG TERM

**Timeline:** 6–12 months post-SaaS API
**Revenue potential:** $100K–$1M ARR

Docker Compose / Kubernetes Helm chart sold to broadcasters and streaming services. Includes
SLA, audit logs, GPU-accelerated Tesseract workers, and S3/GCS/Azure connectors.

The existing JSON report format (`subtitle_extraction_TIMESTAMP.json`) is already structured
for audit ingestion. The `stats` dict maps directly to Prometheus metrics counters/gauges.
The `ThreadPoolExecutor` scales to multi-worker Kubernetes pods for OCR-heavy workloads.

**Pricing:**
- $500/month: up to 5,000 files/month, on-premise Docker deployment
- $2,000/month: unlimited volume, dedicated OCR workers, SLA, custom connectors
- $2,000–10,000 one-time implementation/onboarding fee

---

## Go-to-Market Sequencing

```
Month 1:    PyPI Pro + license gating
             → validates willingness to pay with zero infrastructure investment

Month 2–3:  Desktop GUI app
             → targets largest accessible segment (home users) with one-time purchase

Month 3–4:  Sync Fixer standalone
             → captures broader audience, generates separate SEO surface area

Month 4–6:  Plugin daemon + Jellyfin plugin
             → builds recurring revenue moat; sticky Segment A users

Month 7–12: SaaS API
             → infrastructure investment justified by validated pricing and demand

Month 12+:  Enterprise outreach
             → IBC (Amsterdam), NAB Show (Las Vegas), direct broadcaster sales
```

### Community Launch Tactics (Before Building Anything)

- Post on **r/selfhosted**, **r/Jellyfin**, **r/DataHoarder** with a demo of sync-fix
  (this is the most visual/dramatic capability — showing +2.34s offset corrected is compelling)
- The PGS→SRT OCR pipeline is rare among free tools; target subtitle communities and OpenSubtitles forums
- Submit to **Awesome-Selfhosted** GitHub list and **AlternativeTo.net** as an alternative
  to SubtitleEdit (dominant desktop tool, but Windows-only and no batch CLI)
- SEO content: "convert PGS subtitles to SRT" — current top results are manual/GUI solutions;
  a CLI+API solution with a hosted version ranks well for technical users

---

## Required Code Changes (by Priority)

### Phase 1 — Prerequisite for all models (2–4 weeks)

| Change | File | Purpose |
|--------|------|---------|
| Add `license_key` to valid config keys | `config.py` | License gating |
| Inject license validation in `main()` | `cli.py` | Gate Pro features |
| Replace logging-based progress with `on_progress` callback | `extractor.py` | GUI + API integration |
| Add `process_single_file(path) -> Dict` method | `extractor.py` | Plugin daemon + API |
| Add `Dockerfile` bundling system deps | new file | SaaS + Enterprise |

### Phase 2 — SaaS API (4–8 weeks)

| Change | File | Purpose |
|--------|------|---------|
| Extend `_get_output_path()` to support S3 URIs | `extractor.py` | Cloud storage |
| Replace pickle resume state with DB-backed job table | `extractor.py` | Stateless API jobs |
| FastAPI app + Celery/Redis job queue | `api/` (new) | Async API |
| API key auth + rate limiting | `api/` (new) | Multi-tenancy |

### Phase 3 — Plugin (parallel with Phase 2, 2–3 weeks)

| Change | File | Purpose |
|--------|------|---------|
| FastAPI daemon wrapping `process_single_file()` | `daemon/` (new) | Plugin backend |
| Jellyfin plugin (.NET/C#) | separate repo | User acquisition |

### Phase 4 — Enterprise (post-SaaS, 8–12 weeks)

| Change | File | Purpose |
|--------|------|---------|
| Prometheus metrics endpoint | `api/` | Ops monitoring |
| S3/GCS/Azure storage connectors | `extractor.py` | Enterprise integrations |
| Kubernetes Helm chart | `deploy/` (new) | On-premise deployment |

---

## Critical Files Reference

| File | Commercialization Role |
|------|----------------------|
| `subtitle_extractor/extractor.py` | Core engine; add progress callback, `process_single_file()`, storage abstraction |
| `subtitle_extractor/cli.py` | Entry point; inject license validation in `main()` |
| `subtitle_extractor/sync.py` | Most unique/differentiable feature; extract as standalone product |
| `subtitle_extractor/config.py` | Add `license_key` to `_VALID_KEYS`; `load_config()` already reads YAML |
| `pyproject.toml` | Optional-dep groups (`yaml`, `ocr`, `sync`, `all`) map directly to tier gates |
