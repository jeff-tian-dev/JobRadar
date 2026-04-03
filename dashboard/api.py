"""FastAPI backend for JobRadar dashboard."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from feeds.parser import strip_html_to_plain

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.company_db import (
    get_companies_for_dashboard,
    update_feed_status,
    upsert_company,
)
from pipeline.config_paths import db_path, effective_profile_id, load_profile_for_scoring, load_settings
from pipeline.db import connect, get_listing_by_id, update_listing_notes, update_listing_status, update_scores
from pipeline.scorer import score_listing, scores_to_db_dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    profile_id = effective_profile_id(os.environ.get("JOB_SEARCH_PROFILE_DASHBOARD"))
    profile = load_profile_for_scoring(profile_id, settings)
    dpath = db_path(settings)
    app.state.settings = settings
    app.state.profile_id = profile_id
    app.state.profile = profile
    app.state.db_path = dpath
    yield


app = FastAPI(title="JobRadar API", lifespan=lifespan)

# Serve built React static files in production
_DIST = Path(__file__).parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class StatusBody(BaseModel):
    status: str

class NotesBody(BaseModel):
    notes: str

class AddCompanyRequest(BaseModel):
    name: str
    slug: str
    platform: str
    website: str | None = None


class TailorPdfBody(BaseModel):
    docx_base64: str


class TailorFromTextBody(BaseModel):
    """Paste-a-JD tailoring: same Ollama path as listing-based tailor."""

    job_title: str = Field(..., min_length=2, max_length=500)
    company: str = Field(default="", max_length=300)
    job_description: str = Field(..., min_length=1, max_length=120_000)
    model: str | None = Field(default=None, max_length=200)


class TailorListingBody(BaseModel):
    """Optional body for listing-based tailor (model picker in dashboard)."""

    model: str | None = Field(default=None, max_length=200)


class RebuildProjectBody(BaseModel):
    title: str = ""
    date_range: str = ""
    technologies: str = ""
    bullets: list[str] = Field(default_factory=list)


class RebuildTailorBody(BaseModel):
    best_title: str = ""
    projects: list[RebuildProjectBody]
    skills: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# META
# ---------------------------------------------------------------------------


def _tailor_models_meta(settings: dict) -> tuple[list[dict[str, str]], str]:
    """Return (tailor_models, default_tailor_model) for dashboard picker."""
    raw_tailor = settings.get("ollama_tailor_model")
    tailor_model = raw_tailor.strip() if isinstance(raw_tailor, str) and raw_tailor.strip() else ""
    scoring_model = str(settings.get("ollama_model", "qwen3:14b")).strip() or "qwen3:14b"
    models: list[dict[str, str]] = []
    if tailor_model:
        models.append({"id": tailor_model, "label": tailor_model})
    if scoring_model and scoring_model != tailor_model:
        models.append({"id": scoring_model, "label": scoring_model})
    if not models:
        models.append({"id": scoring_model, "label": scoring_model})
    default = tailor_model if tailor_model else scoring_model
    return models, default


def _settings_with_tailor_model_override(settings: dict, model: str | None) -> dict:
    """Shallow copy of settings; set ollama_tailor_model when model is non-empty."""
    if model is None or not str(model).strip():
        return settings
    out = dict(settings)
    out["ollama_tailor_model"] = str(model).strip()
    return out


@app.get("/api/meta")
async def get_meta(request: Request):
    dpath: Path = request.app.state.db_path
    last_scraped_at: str | None = None
    last_scored_at: str | None = None
    listing_count = 0
    with connect(dpath) as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT MAX(scraped_at) FROM listings) AS last_scraped_at,
                (SELECT MAX(scored_at) FROM listings WHERE scored_at IS NOT NULL) AS last_scored_at,
                (SELECT COUNT(*) FROM listings) AS listing_count
            """
        ).fetchone()
        if row is not None:
            last_scraped_at = row["last_scraped_at"]
            last_scored_at = row["last_scored_at"]
            listing_count = int(row["listing_count"] or 0)
    settings: dict = request.app.state.settings
    tailor_models, default_tailor_model = _tailor_models_meta(settings)
    return {
        "profile_id": request.app.state.profile_id,
        "db_path": str(request.app.state.db_path),
        "last_scraped_at": last_scraped_at,
        "last_scored_at": last_scored_at,
        "listing_count": listing_count,
        "tailor_models": tailor_models,
        "default_tailor_model": default_tailor_model,
    }


# ---------------------------------------------------------------------------
# LISTINGS
# ---------------------------------------------------------------------------

@app.get("/api/listings")
async def get_listings(request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        rows = conn.execute(
            """
            SELECT id, hash, source, source_url, title, company, location_raw, remote_status,
                   fit_score, pref_score, comp_score, overall_score,
                   status, scraped_at, scored_at, posted_date
            FROM listings ORDER BY overall_score DESC, created_at DESC
            """
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@app.get("/api/listings/{listing_id}")
async def get_listing(listing_id: int, request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        row = get_listing_by_id(conn, listing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _row_to_dict(row)


@app.patch("/api/listings/{listing_id}/status")
async def patch_listing_status(listing_id: int, body: StatusBody, request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        update_listing_status(conn, listing_id, body.status)
    return {"ok": True}


@app.patch("/api/listings/{listing_id}/notes")
async def patch_listing_notes(listing_id: int, body: NotesBody, request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        update_listing_notes(conn, listing_id, body.notes)
    return {"ok": True}


@app.post("/api/listings/{listing_id}/rescore")
async def rescore_listing(listing_id: int, request: Request):
    dpath: Path = request.app.state.db_path
    profile = request.app.state.profile
    settings = request.app.state.settings

    with connect(dpath) as conn:
        row = get_listing_by_id(conn, listing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    sal_display = "Not specified"
    if row["salary_min"] is not None:
        sal_display = f"{row['salary_min']}-{row['salary_max']} {row['salary_currency'] or ''}"
    remote_display = row["remote_status"] or "Not specified"

    def _do_score():
        return score_listing(
            profile,
            row["title"] or "",
            row["company"] or "",
            row["location_raw"] or "Not specified",
            sal_display,
            remote_display,
            row["description"] or "",
            settings=settings,
        )

    sr = await anyio.to_thread.run_sync(_do_score)
    if sr is None:
        return {"error": "Re-score failed (Ollama unreachable or parse error)"}

    scores = scores_to_db_dict(sr)
    with connect(dpath) as conn:
        update_scores(conn, row["hash"], scores)

    return {
        "fit_score": sr.fit_score,
        "fit_reason": sr.fit_reason,
        "pref_score": sr.pref_score,
        "pref_reason": sr.pref_reason,
        "comp_score": sr.comp_score,
        "comp_reason": sr.comp_reason,
        "overall_score": sr.overall_score,
    }


@app.post("/api/listings/{listing_id}/tailor-resume")
async def tailor_listing_resume(listing_id: int, body: TailorListingBody, request: Request):
    """Run ollama resume tailoring; returns JSON with preview + base64 docx."""
    from pipeline.resume_tailor import (
        dossier_path,
        load_full_name_for_profile,
        resume_docx_path,
        tailor_resume,
        tailor_result_to_api_dict,
    )

    dpath: Path = request.app.state.db_path
    profile_id: str = request.app.state.profile_id
    settings = _settings_with_tailor_model_override(request.app.state.settings, body.model)

    with connect(dpath) as conn:
        row = get_listing_by_id(conn, listing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    desc = _job_description_for_tailor(row)
    if not desc:
        raise HTTPException(
            status_code=400,
            detail="Listing has no job description to tailor against",
        )
    logger.info(
        "Tailor resume: listing id=%s jd_chars=%s title=%r",
        listing_id,
        len(desc),
        (row["title"] or "")[:80],
    )

    def _run():
        full_name = load_full_name_for_profile(profile_id, settings)
        return tailor_resume(
            desc,
            row["title"] or "",
            row["company"] or "",
            profile_id,
            full_name,
            settings,
        )

    result, tailor_err = await anyio.to_thread.run_sync(_run)
    if result is None:
        rpath = resume_docx_path(profile_id, settings)
        dpath_dossier = dossier_path(profile_id, settings)
        om = settings.get("ollama_tailor_model") or settings.get("ollama_model")
        raise HTTPException(
            status_code=502,
            detail={
                "title": "Resume tailoring failed",
                "reason": tailor_err or "Unknown tailoring error.",
                "paths": {
                    "experience_dossier": str(dpath_dossier),
                    "resume_template": str(rpath),
                },
                "ollama_model": om if isinstance(om, str) else str(om),
                "debug_hint": "Check the API server log for lines starting with 'Tailor attempt' or 'Tailor failed'.",
            },
        )

    return tailor_result_to_api_dict(result)


@app.post("/api/tailor/from-text")
async def tailor_resume_from_text(body: TailorFromTextBody, request: Request):
    """Tailor resume from pasted job title, optional company, and description (no listing row)."""
    from pipeline.resume_tailor import (
        dossier_path,
        load_full_name_for_profile,
        resume_docx_path,
        tailor_resume,
        tailor_result_to_api_dict,
    )

    profile_id: str = request.app.state.profile_id
    settings = _settings_with_tailor_model_override(request.app.state.settings, body.model)

    desc = strip_html_to_plain(body.job_description).strip()
    if len(desc) < 40:
        raise HTTPException(
            status_code=400,
            detail="Job description is too short after stripping markup (need at least 40 characters).",
        )
    title = body.job_title.strip()
    company = (body.company or "").strip()
    logger.info(
        "Tailor resume from text: jd_chars=%s title=%r company=%r",
        len(desc),
        title[:80],
        company[:80],
    )

    def _run():
        full_name = load_full_name_for_profile(profile_id, settings)
        return tailor_resume(desc, title, company, profile_id, full_name, settings)

    result, tailor_err = await anyio.to_thread.run_sync(_run)
    if result is None:
        rpath = resume_docx_path(profile_id, settings)
        dpath_dossier = dossier_path(profile_id, settings)
        om = settings.get("ollama_tailor_model") or settings.get("ollama_model")
        raise HTTPException(
            status_code=502,
            detail={
                "title": "Resume tailoring failed",
                "reason": tailor_err or "Unknown tailoring error.",
                "paths": {
                    "experience_dossier": str(dpath_dossier),
                    "resume_template": str(rpath),
                },
                "ollama_model": om if isinstance(om, str) else str(om),
                "debug_hint": "Check the API server log for lines starting with 'Tailor attempt' or 'Tailor failed'.",
            },
        )

    return tailor_result_to_api_dict(result)


@app.post("/api/tailor/rebuild")
async def tailor_rebuild(body: RebuildTailorBody, request: Request):
    """Rebuild tailored .docx from edited preview fields (no LLM)."""
    import base64

    from pipeline.resume_tailor import load_full_name_for_profile, rebuild_docx_from_edits

    profile_id: str = request.app.state.profile_id
    settings = request.app.state.settings
    full_name = load_full_name_for_profile(profile_id, settings)

    data: dict = {
        "best_title": body.best_title,
        "projects": [p.model_dump() for p in body.projects],
        "skills": dict(body.skills),
    }

    def _run() -> tuple[bytes, str, dict]:
        return rebuild_docx_from_edits(data, profile_id, full_name, settings)

    try:
        docx_bytes, filename, meta = await anyio.to_thread.run_sync(_run)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Resume template not found: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "filename": filename,
        "docx_base64": base64.b64encode(docx_bytes).decode("ascii"),
        "tailored": meta["tailored"],
        "explanation": meta["explanation"],
        "ollama_metrics": meta.get("ollama_metrics", {}),
    }


@app.post("/api/tailor/convert-pdf")
async def tailor_convert_pdf(body: TailorPdfBody):
    """Convert a tailored .docx (base64) to PDF using LibreOffice."""
    import base64

    from dashboard.pdf_convert import docx_bytes_to_pdf

    try:
        raw = base64.b64decode(body.docx_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 docx payload") from None

    def _convert() -> bytes:
        return docx_bytes_to_pdf(raw)

    try:
        pdf = await anyio.to_thread.run_sync(_convert)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("PDF conversion failed")
        raise HTTPException(status_code=500, detail=f"PDF conversion failed: {e}") from e

    return Response(content=pdf, media_type="application/pdf")


# ---------------------------------------------------------------------------
# COMPANIES
# ---------------------------------------------------------------------------

@app.get("/api/companies")
async def get_companies(request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        rows = get_companies_for_dashboard(conn)
    return [_row_to_dict(r) for r in rows]


@app.patch("/api/companies/{company_id}/feed-status")
async def patch_company_feed_status(company_id: int, body: StatusBody, request: Request):
    dpath: Path = request.app.state.db_path
    with connect(dpath) as conn:
        update_feed_status(conn, company_id, body.status)
    return {"ok": True}


@app.post("/api/companies/discover")
async def run_seed_discovery(request: Request):
    dpath: Path = request.app.state.db_path
    settings = request.app.state.settings

    from discovery.sources.seed import discover_from_seed

    def _sync_wrapper():
        with connect(dpath) as conn:
            return asyncio.run(discover_from_seed(conn, settings))

    count = await anyio.to_thread.run_sync(_sync_wrapper)
    return {"count": count}


@app.post("/api/companies")
async def add_company(body: AddCompanyRequest, request: Request):
    dpath: Path = request.app.state.db_path

    import httpx
    from feeds.resolver import try_resolve_feed

    async def _resolve():
        async with httpx.AsyncClient() as client:
            return await try_resolve_feed(client, body.slug, platform=body.platform)

    resolved = await _resolve()

    record: dict = {
        "name": body.name,
        "slug": body.slug,
        "website": body.website or None,
        "discovery_source": "manual",
    }

    if resolved and resolved.status == "ok":
        record["feed_url"] = resolved.url
        record["feed_platform"] = resolved.platform
        record["feed_status"] = "active"
        msg = f"Added {body.name} with active {resolved.platform} feed ({resolved.entry_count} entries)"
        feed_found = True
        entry_count = resolved.entry_count
        feed_platform = resolved.platform
    else:
        record["feed_status"] = "no_feed"
        msg = f"Added {body.name} but no feed found at {body.platform}/{body.slug}"
        feed_found = False
        entry_count = 0
        feed_platform = None

    with connect(dpath) as conn:
        company_id = upsert_company(conn, record)

    return {
        "ok": True,
        "message": msg,
        "company_id": company_id,
        "feed_found": feed_found,
        "feed_platform": feed_platform,
        "entry_count": entry_count,
    }


# ---------------------------------------------------------------------------
# SPA fallback (production)
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    index = _DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"detail": "React build not found. Run: cd dashboard/frontend && npm run build"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_description_for_tailor(row: sqlite3.Row) -> str:
    """Prefer listings.description; if very short, append stripped raw_html."""
    desc = (row["description"] or "").strip()
    raw_html = row["raw_html"] or ""
    if len(desc) < 200 and raw_html.strip():
        extra = strip_html_to_plain(raw_html)
        if extra and extra not in desc:
            desc = f"{desc}\n\n{extra}".strip() if desc else extra
            logger.info(
                "Tailor: augmented short description with raw_html (listing id=%s)",
                row["id"],
            )
    return desc


def _row_to_dict(row) -> dict:
    try:
        return dict(row)
    except Exception:
        return {}
