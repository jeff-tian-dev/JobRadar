"""Build ATS resume HTML (Career-Ops–style layout) from tailor JSON + profile."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.config_paths import REPO_ROOT, profile_yaml_path

logger = logging.getLogger(__name__)

ATS_CV_DIR = REPO_ROOT / "templates" / "ats_cv"


def resolve_ats_pdf_format(profile: dict[str, Any], settings: dict[str, Any]) -> str:
    """Return ``letter`` or ``a4``."""
    raw = settings.get("ats_pdf_format")
    if isinstance(raw, str) and raw.strip().lower() in ("letter", "a4"):
        return raw.strip().lower()
    loc = str(profile.get("location", "")).lower()
    country = str(profile.get("country", "")).lower()
    prefs = str(profile.get("preferences", "")).lower() if isinstance(profile.get("preferences"), str) else ""
    if any(
        x in loc
        for x in (
            "canada",
            "united states",
            "usa",
            "u.s.",
            "toronto",
            "mississauga",
            "california",
        )
    ):
        return "letter"
    if country in ("us", "usa", "ca", "can"):
        return "letter"
    if "remote (canada)" in prefs or "ontario" in loc:
        return "letter"
    return "a4"


def page_width_for_format(fmt: str) -> str:
    return "8.5in" if fmt == "letter" else "210mm"


def load_profile_dict(profile_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    path = profile_yaml_path(profile_id, settings)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _contact_dict(profile: dict[str, Any]) -> dict[str, str]:
    """Flatten optional ``contact:`` block + top-level fallbacks."""
    c = profile.get("contact")
    base: dict[str, Any] = dict(c) if isinstance(c, dict) else {}

    def pick(*keys: str) -> str:
        for k in keys:
            v = base.get(k) if k in base else profile.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    return {
        "email": pick("email"),
        "phone": pick("phone"),
        "linkedin": pick("linkedin", "linkedin_url"),
        "github": pick("github", "github_url"),
        "portfolio_url": pick("portfolio_url", "portfolio"),
        "location": pick("location", "city"),
    }


def _linkedin_url(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("linkedin.com") or s.startswith("www.linkedin.com"):
        return f"https://{s}"
    if "/" not in s and "linkedin" not in s.lower():
        return f"https://linkedin.com/in/{s.lstrip('/')}"
    return s if s.startswith("http") else f"https://{s}"


def _github_url(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return f"https://github.com/{s.lstrip('/')}"


def _contact_row_html(profile: dict[str, Any]) -> str:
    c = _contact_dict(profile)
    parts: list[str] = []
    if c["email"]:
        parts.append(f'<span>{html.escape(c["email"])}</span>')
    if c["phone"]:
        if parts:
            parts.append('<span class="separator">|</span>')
        parts.append(f'<span>{html.escape(c["phone"])}</span>')
    if c["linkedin"]:
        if parts:
            parts.append('<span class="separator">|</span>')
        url = _linkedin_url(c["linkedin"])
        disp = "LinkedIn" if "linkedin.com" in c["linkedin"].lower() else html.escape(c["linkedin"][:40])
        parts.append(f'<a href="{html.escape(url, quote=True)}">{disp}</a>')
    if c["github"]:
        if parts:
            parts.append('<span class="separator">|</span>')
        url = _github_url(c["github"])
        handle = c["github"].split("/")[-1]
        parts.append(f'<a href="{html.escape(url, quote=True)}">GitHub: {html.escape(handle)}</a>')
    if c["portfolio_url"]:
        if parts:
            parts.append('<span class="separator">|</span>')
        url = c["portfolio_url"]
        if not url.startswith("http"):
            url = f"https://{url}"
        parts.append(f'<a href="{html.escape(url, quote=True)}">Portfolio</a>')
    if c["location"]:
        if parts:
            parts.append('<span class="separator">|</span>')
        parts.append(f'<span>{html.escape(c["location"])}</span>')
    return f'<div class="contact-row">{"".join(parts)}</div>' if parts else ""


def _entry_display_title(p: dict[str, Any]) -> str:
    raw = p.get("title")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    name = p.get("name")
    sub = p.get("subtitle")
    if isinstance(name, str) and name.strip():
        if isinstance(sub, str) and sub.strip():
            return f"{name.strip()} — {sub.strip()}"
        return name.strip()
    return "Role"


def _bullet_html(text: str) -> str:
    """Escape and turn ``**bold**`` into ``<strong>`` (no other HTML)."""
    parts = str(text).split("**")
    out: list[str] = []
    for i, part in enumerate(parts):
        esc = html.escape(part, quote=True)
        if i % 2 == 0:
            out.append(esc)
        else:
            out.append(f"<strong>{esc}</strong>")
    return "".join(out)


def _render_job_block(p: dict[str, Any], css_prefix: str) -> str:
    title = html.escape(_entry_display_title(p), quote=True)
    period = html.escape(str(p.get("date_range", "")).strip(), quote=True)
    tech = str(p.get("technologies", "")).strip()
    tech_html = (
        f'<div class="{css_prefix}-tech">{html.escape(tech, quote=True)}</div>' if tech else ""
    )
    bullets = p.get("bullets") or []
    lis = "".join(
        f'<li>{_bullet_html(str(b))}</li>'
        for b in bullets
        if isinstance(b, str) and b.strip()
    )
    ul = f"<ul>{lis}</ul>" if lis else ""
    if css_prefix == "job":
        return (
            f'<div class="job avoid-break">'
            f'<div class="job-header">'
            f'<span class="job-company">{title}</span>'
            f'<span class="job-period">{period}</span></div>'
            f"{tech_html}{ul}</div>"
        )
    return (
        f'<div class="project avoid-break">'
        f'<div class="project-title">{title}</div>'
        f"{tech_html}{ul}</div>"
    )


def _section_experience(llm_data: dict[str, Any]) -> str:
    exp = llm_data.get("experience") or []
    if not isinstance(exp, list) or len(exp) == 0:
        return ""
    blocks = "".join(
        _render_job_block(p, "job") for p in exp if isinstance(p, dict)
    )
    return (
        '<div class="section avoid-break">'
        '<div class="section-title">Work Experience</div>'
        f"{blocks}</div>"
    )


def _section_projects(llm_data: dict[str, Any]) -> str:
    proj = llm_data.get("projects") or []
    if not isinstance(proj, list) or len(proj) == 0:
        return ""
    blocks = "".join(
        _render_job_block(p, "project") for p in proj if isinstance(p, dict)
    )
    return (
        '<div class="section avoid-break">'
        '<div class="section-title">Projects</div>'
        f"{blocks}</div>"
    )


def _section_competencies(llm_data: dict[str, Any]) -> str:
    cc = llm_data.get("core_competencies") or []
    if not isinstance(cc, list) or not cc:
        return ""
    tags = "".join(
        f'<span class="competency-tag">{html.escape(str(c).strip(), quote=True)}</span>'
        for c in cc
        if isinstance(c, str) and c.strip()
    )
    if not tags:
        return ""
    return (
        '<div class="section">'
        '<div class="section-title">Core Competencies</div>'
        f'<div class="competencies-grid">{tags}</div></div>'
    )


def _section_education(profile: dict[str, Any]) -> str:
    edu = profile.get("education")
    if not isinstance(edu, list) or not edu:
        return ""
    parts: list[str] = []
    for row in edu:
        if not isinstance(row, dict):
            continue
        deg = str(row.get("degree", "")).strip()
        school = str(row.get("school", "")).strip()
        if not deg and not school:
            continue
        parts.append(
            '<div class="edu-item avoid-break">'
            '<div class="edu-header">'
            f'<span class="edu-title">{html.escape(deg, quote=True)}</span>'
            f'<span class="edu-org">{html.escape(school, quote=True)}</span>'
            "</div></div>"
        )
    if not parts:
        return ""
    return (
        '<div class="section avoid-break">'
        '<div class="section-title">Education</div>'
        f'{"".join(parts)}</div>'
    )


def _section_certifications(profile: dict[str, Any]) -> str:
    certs = profile.get("certifications")
    if not isinstance(certs, list) or not certs:
        return ""
    parts: list[str] = []
    for row in certs:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", row.get("name", ""))).strip()
        org = str(row.get("org", row.get("issuer", ""))).strip()
        year = str(row.get("year", "")).strip()
        if not title:
            continue
        parts.append(
            '<div class="cert-item avoid-break">'
            f'<span class="cert-title">{html.escape(title, quote=True)}</span>'
            f'<span class="cert-org">{html.escape(org, quote=True)}</span>'
            f'<span class="cert-year">{html.escape(year, quote=True)}</span>'
            "</div>"
        )
    if not parts:
        return ""
    return (
        '<div class="section avoid-break">'
        '<div class="section-title">Certifications</div>'
        f'{"".join(parts)}</div>'
    )


def _section_skills(llm_data: dict[str, Any]) -> str:
    sk = llm_data.get("skills")
    if not isinstance(sk, dict):
        return ""
    lines: list[str] = []
    for label in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
        v = sk.get(label)
        if not isinstance(v, str) or not v.strip():
            continue
        lines.append(
            '<div class="skill-item">'
            f'<span class="skill-category">{html.escape(label, quote=True)}: </span>'
            f"{html.escape(v.strip(), quote=True)}</div>"
        )
    if not lines:
        return ""
    return (
        '<div class="section avoid-break">'
        '<div class="section-title">Skills</div>'
        f'<div class="skills-grid">{"".join(lines)}</div></div>'
    )


def build_ats_resume_body_html(llm_data: dict[str, Any], profile: dict[str, Any]) -> str:
    """Inner HTML inside ``<div class="page">`` (no outer wrapper)."""
    name = str(profile.get("name", "Candidate")).strip() or "Candidate"
    header = (
        '<div class="header avoid-break">'
        f"<h1>{html.escape(name, quote=True)}</h1>"
        '<div class="header-gradient"></div>'
        f"{_contact_row_html(profile)}</div>"
    )
    summary = str(llm_data.get("professional_summary", "")).strip()
    summary_sec = (
        '<div class="section avoid-break">'
        '<div class="section-title">Professional Summary</div>'
        f'<div class="summary-text">{html.escape(summary, quote=True)}</div></div>'
    )
    inner = [
        header,
        summary_sec,
        _section_competencies(llm_data),
        _section_experience(llm_data),
        _section_projects(llm_data),
        _section_education(profile),
        _section_certifications(profile),
        _section_skills(llm_data),
    ]
    return "\n".join(x for x in inner if x)


def build_ats_resume_html(
    llm_data: dict[str, Any],
    profile_id: str,
    settings: dict[str, Any],
) -> str:
    """Full HTML document string for Playwright PDF."""
    profile = load_profile_dict(profile_id, settings)
    fmt = resolve_ats_pdf_format(profile, settings)
    pw = page_width_for_format(fmt)
    styles_path = ATS_CV_DIR / "ats_styles.css"
    if not styles_path.is_file():
        logger.error("Missing ATS styles at %s", styles_path)
        styles = ""
    else:
        styles = styles_path.read_text(encoding="utf-8").replace("__PAGE_WIDTH__", pw)
    body = build_ats_resume_body_html(llm_data, profile)
    name = str(profile.get("name", "Candidate")).strip() or "Candidate"
    env = Environment(
        loader=FileSystemLoader(str(ATS_CV_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template("cv.html.j2")
    return tpl.render(
        lang="en",
        title=f"{name} — Résumé",
        styles=styles,
        body=body,
    )


def ats_template_base_url() -> str:
    """``base_url`` for Playwright ``set_content`` (fonts resolve relative to this directory)."""
    return ATS_CV_DIR.as_uri() + "/"
