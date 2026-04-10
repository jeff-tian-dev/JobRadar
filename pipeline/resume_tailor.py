"""Tailor résumé via Ollama JSON → ATS HTML → Playwright PDF (Career-Ops–style layout)."""

from __future__ import annotations

import base64
import copy
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import ollama
import yaml
from xml.etree import ElementTree as ET

from pipeline.config_paths import (
    REPO_ROOT,
    load_settings,
    profile_yaml_path,
    profiles_dir,
    prompts_dir,
    read_ollama_repeat_penalty,
)
from pipeline.ats_pdf import tailored_json_to_pdf_bytes
from pipeline.ats_tailor_caps import ats_tailor_caps
from pipeline.ats_tailor_prepare import normalize_ats_date_ranges, prepare_ats_tailor_lists
from pipeline.ats_tailor_validate import validate_ats_tailor_response
from pipeline.models import (
    log_ollama_metrics,
    log_tailor_session_ollama_summary,
    ollama_response_metrics_dict,
)

logger = logging.getLogger(__name__)

# `##` sections that are not selectable projects (same semantics as dossier preview).
_DOSSIER_NON_PROJECT_HEADINGS: frozenset[str] = frozenset(
    {
        "experience dossier",
        "how to use",
        "target roles",
        "boundaries — do not invent",
        "personal skills",
    }
)


def iter_dossier_project_headings(dossier_text: str) -> list[str]:
    """Return top-level ``##`` project names in file order (excludes Personal skills and meta sections)."""
    out: list[str] = []
    for line in dossier_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            name = stripped[3:].strip()
            if not name or name.casefold() in _DOSSIER_NON_PROJECT_HEADINGS:
                continue
            out.append(name)
    return out


def format_dossier_project_catalog_for_prompt(dossier_text: str, num_projects: int) -> str:
    """Checklist of every project heading in an order that is **not** dossier file order (reduces LLM anchoring)."""
    names = iter_dossier_project_headings(dossier_text)
    if not names:
        return (
            f"No distinct `##` project headings were parsed above the dossier body. "
            f"Still read **all** project-like sections in the file, pick the best **{num_projects}** for this job, "
            f"and order JSON `projects` by **descending JD relevance + proof**—**not** by section order top-to-bottom."
        )
    # Reverse alphabetical (case-insensitive) so the list differs from typical "featured first" file order.
    ordered = sorted(names, key=lambda s: s.casefold(), reverse=True)
    lines: list[str] = [
        f"You have **{len(names)}** projects below. You will output **{num_projects}** of them on the resume.",
        "",
        "**Checklist (reverse-alphabetical — not importance, not resume order):** for **each** name, assign a silent **1–10** JD relevance score + one-line dossier-backed rationale **before** comparing projects to each other (see system prompt workflow step 2). "
        "Then pick and order the resume slots from those scores + tie-breakers—not from this list order or dossier file order. "
        "When the JD emphasizes **LLMs / GenAI / RAG / agents / prompts**, weight **inference, structured model output, or prompt pipelines** in each score—not only user or row counts.",
        "",
    ]
    for n in ordered:
        lines.append(f"- {n}")
    return "\n".join(lines)


# Resume JSON can be large (many bullets + long change_summary). Default must avoid mid-JSON truncation.
_DEFAULT_TAILOR_NUM_PREDICT = 24576
_MAX_TAILOR_NUM_PREDICT = 65536

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _paragraph_plain_text(p: ET.Element) -> str:
    """Concatenate all w:t text under a paragraph."""
    parts: list[str] = []
    for t in p.iter(_w("t")):
        if t.text:
            parts.append(t.text)
        if t.tail:
            parts.append(t.tail)
    return "".join(parts)


def _run_is_bold(r: ET.Element) -> bool:
    rpr = r.find(_w("rPr"))
    if rpr is None:
        return False
    b = rpr.find(_w("b"))
    if b is None:
        return False
    for k, v in b.attrib.items():
        if k.endswith("}val") or k == "val":
            return str(v).lower() not in ("0", "false", "off")
    return True


def _bold_segments_text(p: ET.Element) -> str:
    parts: list[str] = []
    for r in p.findall(_w("r")):
        if not _run_is_bold(r):
            continue
        t = r.find(_w("t"))
        if t is not None and t.text:
            parts.append(t.text)
    return "".join(parts).strip()


def _is_bullet_paragraph(p: ET.Element) -> bool:
    ppr = p.find(_w("pPr"))
    if ppr is None:
        return False
    return ppr.find(_w("numPr")) is not None


def _strip_bold_from_run(r: ET.Element) -> ET.Element:
    out = copy.deepcopy(r)
    rpr = out.find(_w("rPr"))
    if rpr is not None:
        for tag in ("b", "bCs", "i", "iCs"):
            el = rpr.find(_w(tag))
            if el is not None:
                rpr.remove(el)
        if len(rpr) == 0:
            out.remove(rpr)
    return out


def _make_empty_run() -> ET.Element:
    r = ET.Element(_w("r"))
    t = ET.SubElement(r, _w("t"))
    t.text = ""
    return r


def _pick_ref_runs(bullet_para: ET.Element) -> tuple[ET.Element, ET.Element | None]:
    """Return (plain_template_run, bold_template_run_or_none) for rebuilding bullets."""
    runs = bullet_para.findall(_w("r"))
    plain_choice: ET.Element | None = None
    bold_choice: ET.Element | None = None
    for r in runs:
        t = r.find(_w("t"))
        tx = (t.text or "") if t is not None else ""
        if not tx.strip():
            continue
        if _run_is_bold(r):
            if bold_choice is None:
                bold_choice = copy.deepcopy(r)
        else:
            if plain_choice is None:
                plain_choice = copy.deepcopy(r)
    if plain_choice is None and runs:
        plain_choice = _strip_bold_from_run(copy.deepcopy(runs[0]))
    if plain_choice is None:
        plain_choice = _make_empty_run()
    return plain_choice, bold_choice


def _first_substantial_plain_run(para: ET.Element) -> ET.Element | None:
    """Pick the longest non-bold w:r text run in a paragraph (for tech line body)."""
    best: ET.Element | None = None
    best_len = -1
    for r in para.findall(_w("r")):
        if _run_is_bold(r):
            continue
        t = r.find(_w("t"))
        tx = (t.text or "") if t is not None else ""
        stripped = tx.strip()
        if len(stripped) > best_len:
            best = r
            best_len = len(stripped)
    return best


def _run_text_content(r: ET.Element) -> str:
    """All ``w:t`` text (and tails) inside one ``w:r``."""
    parts: list[str] = []
    for t in r.findall(_w("t")):
        if t.text:
            parts.append(t.text)
        if t.tail:
            parts.append(t.tail)
    return "".join(parts)


def _looks_like_tailor_date_line(text: str) -> bool:
    """True if ``text`` looks like a project date/range (not a subtitle after the bold name).

    Word templates often use: **Name** (plain) — Subtitle (plain) April 2025 - Present. Without this
    check, the subtitle run is misclassified as ``date_run``, preserved on update, and the docx shows
    the merged title twice (e.g. ``Name — Sub — Name`` when the template repeats the name).
    """
    t = text.strip()
    if not t:
        return False
    if re.search(r"\b(19|20)\d{2}\b", t):
        return True
    if re.search(r"\bPresent\b", t, flags=re.IGNORECASE):
        return True
    if re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\b",
        t,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def _resolve_project_content_runs(
    title_para: ET.Element,
    tech_para: ET.Element | None,
    tech_inline: bool,
) -> tuple[ET.Element | None, ET.Element | None, ET.Element | None]:
    """Return (title_run, date_run, tech_run). tech_run is inside title_para when tech_inline."""
    runs = title_para.findall(_w("r"))
    title_run: ET.Element | None = None
    for r in runs:
        tx = _run_text_content(r)
        if _run_is_bold(r) and tx.strip():
            title_run = r
            break
    if title_run is None:
        for r in runs:
            tx = _run_text_content(r)
            if tx.strip():
                title_run = r
                break

    date_run: ET.Element | None = None
    tech_run_inline: ET.Element | None = None
    if title_run is None:
        tech_run: ET.Element | None = tech_run_inline if tech_inline else None
        if not tech_inline and tech_para is not None:
            tech_run = _first_substantial_plain_run(tech_para)
        return None, None, tech_run

    idx_title = runs.index(title_run)
    for j in range(idx_title + 1, len(runs)):
        r = runs[j]
        tx = _run_text_content(r).strip()
        if not tx:
            continue
        if date_run is None:
            if _run_is_bold(r):
                continue
            if _looks_like_tailor_date_line(tx):
                date_run = r
            continue
        if tech_inline and tech_run_inline is None and not _run_is_bold(r):
            tech_run_inline = r
            break

    if date_run is None:
        for j in range(idx_title + 1, len(runs)):
            r = runs[j]
            tx = _run_text_content(r).strip()
            if not tx or _run_is_bold(r):
                continue
            date_run = r
            if tech_inline:
                for k in range(j + 1, len(runs)):
                    r2 = runs[k]
                    tx2 = _run_text_content(r2).strip()
                    if not tx2 or _run_is_bold(r2):
                        continue
                    tech_run_inline = r2
                    break
            break

    tech_run = tech_run_inline if tech_inline else None
    if not tech_inline and tech_para is not None:
        tech_run = _first_substantial_plain_run(tech_para)
    return title_run, date_run, tech_run


def _heading_line_text_before_date(title_para: ET.Element, date_run: ET.Element | None) -> str:
    """Project heading text: all runs before the date run (bold name + plain subtitle fragments)."""
    parts: list[str] = []
    for r in title_para.findall(_w("r")):
        if date_run is not None and r is date_run:
            break
        parts.append(_run_text_content(r))
    joined = "".join(parts).strip()
    if joined:
        return joined
    return _bold_segments_text(title_para) or _paragraph_plain_text(title_para).strip()


def split_double_asterisk_segments(text: str) -> list[tuple[str, bool]]:
    """Split on **...** into (segment, is_bold) pairs."""
    parts: list[tuple[str, bool]] = []
    bold = False
    buf: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("**", i):
            if buf:
                parts.append(("".join(buf), bold))
                buf = []
            bold = not bold
            i += 2
            continue
        buf.append(text[i])
        i += 1
    if buf:
        parts.append(("".join(buf), bold))
    return parts if parts else [("", False)]


def _body_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [c for c in body if c.tag == _w("p")]


@dataclass
class SkillsExtraction:
    label_to_plain_run: dict[str, ET.Element] = field(default_factory=dict)


@dataclass
class ProjectBlock:
    title_para: ET.Element
    title_text: str
    date_run: ET.Element | None
    tech_run: ET.Element | None
    tech_para: ET.Element | None
    tech_inline: bool
    bullet_paras: list[ET.Element]
    ref_plain_run: ET.Element
    ref_bold_run: ET.Element | None


@dataclass
class ResumeExtraction:
    body: ET.Element
    projects: list[ProjectBlock]
    skills: SkillsExtraction


def _find_skills_runs(body: ET.Element) -> dict[str, ET.Element]:
    """Map skill line keys to the w:r that holds the comma-separated list (after the label)."""
    label_map: dict[str, ET.Element] = {}
    keys = ("Languages", "Frameworks & Libraries", "Tools & Technologies")
    for p in body.iter(_w("p")):
        full = _paragraph_plain_text(p)
        for key in keys:
            if key in label_map:
                continue
            prefix = key + ":"
            if not (full.strip().startswith(prefix) or prefix in full):
                continue
            runs = p.findall(_w("r"))
            best: ET.Element | None = None
            best_len = -1
            seen_label = False
            for r in runs:
                t = r.find(_w("t"))
                tx = (t.text or "") if t is not None else ""
                if prefix.strip() in tx or (key + ":") in tx:
                    seen_label = True
                    continue
                if seen_label and tx.strip() and len(tx) > best_len:
                    best = r
                    best_len = len(tx)
            if best is None:
                for r in reversed(runs):
                    t = r.find(_w("t"))
                    tx = (t.text or "") if t is not None else ""
                    if tx.strip() and len(tx) > best_len and not _run_is_bold(r):
                        best = r
                        best_len = len(tx)
            if best is not None:
                label_map[key] = best
    return label_map


def extract_resume_structure(root: ET.Element) -> ResumeExtraction:
    """Parse w:document body into projects (title, optional tech line, bullets) and skills runs."""
    body = root.find(_w("body"))
    if body is None:
        raise ValueError("Missing w:body")
    paras = _body_paragraphs(body)
    projects: list[ProjectBlock] = []
    i = 0
    while i < len(paras):
        p = paras[i]
        if _is_bullet_paragraph(p):
            i += 1
            continue
        if i + 1 >= len(paras):
            i += 1
            continue

        next_p = paras[i + 1]
        tech_para: ET.Element | None = None
        tech_inline = False
        bullet_start = i + 1

        if _is_bullet_paragraph(next_p):
            tech_inline = True
        else:
            if i + 2 >= len(paras) or not _is_bullet_paragraph(paras[i + 2]):
                i += 1
                continue
            tech_para = next_p
            bullet_start = i + 2

        bullets: list[ET.Element] = []
        j = bullet_start
        while j < len(paras) and _is_bullet_paragraph(paras[j]):
            bullets.append(paras[j])
            j += 1

        if not bullets:
            i += 1
            continue

        _, date_run, tech_run = _resolve_project_content_runs(p, tech_para, tech_inline)
        title_text = _heading_line_text_before_date(p, date_run)
        ref_plain, ref_bold = _pick_ref_runs(bullets[0])
        projects.append(
            ProjectBlock(
                title_para=p,
                title_text=title_text,
                date_run=date_run,
                tech_run=tech_run,
                tech_para=tech_para,
                tech_inline=tech_inline,
                bullet_paras=bullets,
                ref_plain_run=ref_plain,
                ref_bold_run=ref_bold,
            )
        )
        i = j

    skills = SkillsExtraction(label_to_plain_run=_find_skills_runs(body))
    return ResumeExtraction(body=body, projects=projects, skills=skills)


def _run_plain_text(r: ET.Element | None) -> str:
    """Text from a single w:r, or empty."""
    if r is None:
        return ""
    t = r.find(_w("t"))
    return ((t.text if t is not None else None) or "").strip()


def format_resume_content_for_prompt(ext: ResumeExtraction) -> str:
    """Build markdown-like text from template slots (legacy / debugging; tailoring uses the dossier)."""
    lines: list[str] = []
    for proj in ext.projects:
        lines.append(f"### Project: {proj.title_text}")
        dr = _run_plain_text(proj.date_run)
        if dr:
            lines.append(f"Dates: {dr}")
        tv = _run_plain_text(proj.tech_run)
        if tv:
            lines.append(f"Technologies: {tv}")
        for bp in proj.bullet_paras:
            lines.append(f"- {_paragraph_plain_text(bp).strip()}")
        lines.append("")
    lines.append("### Technical Skills")
    order = ["Languages", "Frameworks & Libraries", "Tools & Technologies"]
    for key in order:
        r = ext.skills.label_to_plain_run.get(key)
        if r is None:
            continue
        t = r.find(_w("t"))
        val = (t.text if t is not None else "") or ""
        lines.append(f"{key}: {val.strip()}")
    return "\n".join(lines).strip()


def dossier_to_original_preview(dossier_text: str) -> dict[str, Any]:
    """Top-level ## headings from the dossier as the 'before' view in the tailor diff."""
    projects: list[dict[str, Any]] = []
    for name in iter_dossier_project_headings(dossier_text):
        projects.append(
            {
                "title": name,
                "date_range": "",
                "technologies": "",
                "bullets": [],
            }
        )
    return {"projects": projects, "skills": {}}


def original_preview_from_tailor_slots(llm_data: dict[str, Any]) -> dict[str, Any]:
    """Build the 'before' side of the diff: dossier section name per slot (aligned with tailored order)."""
    projects: list[dict[str, Any]] = []
    for p in llm_data.get("projects", []):
        if not isinstance(p, dict):
            continue
        src = str(p.get("dossier_source", "")).strip() or "Dossier"
        projects.append(
            {
                "title": src,
                "date_range": "",
                "technologies": "",
                "bullets": [],
            }
        )
    return {"projects": projects, "skills": {}}


def build_original_preview_ats(dossier_text: str) -> dict[str, Any]:
    """Original / 'before' view: dossier ## headings as empty project shells; no experience."""
    base = dossier_to_original_preview(dossier_text)
    return {
        "experience": [],
        "projects": base.get("projects") or [],
        "professional_summary": "",
        "core_competencies": [],
        "skills": base.get("skills") or {},
        "best_title": "",
    }


def extraction_to_preview_dict(ext: ResumeExtraction) -> dict[str, Any]:
    """Structured template slots for dashboard diff (plain text from the .docx)."""
    projects = []
    for proj in ext.projects:
        projects.append(
            {
                "title": proj.title_text,
                "date_range": _run_plain_text(proj.date_run),
                "technologies": _run_plain_text(proj.tech_run),
                "bullets": [_paragraph_plain_text(bp).strip() for bp in proj.bullet_paras],
            }
        )
    skills: dict[str, str] = {}
    for key in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
        r = ext.skills.label_to_plain_run.get(key)
        if r is None:
            continue
        t = r.find(_w("t"))
        skills[key] = ((t.text if t is not None else "") or "").strip()
    return {"projects": projects, "skills": skills}


def _normalize_whitespace_casefold(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _normalize_tailor_date_range(s: str) -> str:
    """Normalize date lines: ``to``/en-dash → spaced hyphen; ``present`` → ``Present``.

    Single-phrase dates (e.g. ``March 2026``) pass through unchanged. Does not validate month-year shape;
    the tailor prompts require ``Month Year``, ``Month Year - Month Year``, or ``Month Year - Present``.
    """
    t = str(s).strip()
    if not t:
        return t
    t = re.sub(r"\s+to\s+", " - ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*[–—]\s*", " - ", t)
    t = re.sub(r"\bpresent\b", "Present", t)
    return t


def _normalize_project_date_ranges_in_data(data: dict[str, Any]) -> None:
    """Mutate ``projects[*].date_range`` in tailor JSON in place."""
    projs = data.get("projects")
    if not isinstance(projs, list):
        return
    for p in projs:
        if not isinstance(p, dict):
            continue
        dr = p.get("date_range")
        if isinstance(dr, str) and dr.strip():
            p["date_range"] = _normalize_tailor_date_range(dr)


# Split on em/en dash or spaced hyphen (not bare hyphens inside tokens).
_DASH_SPLIT_RE = re.compile(r"\s*(?:\u2014|\u2013|–)\s*|\s+-\s+")


def _split_resume_header_line(text: str) -> tuple[str, str]:
    """Split ``Name — Role`` into left and right segments (first dash run only)."""
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(str(text).strip()) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def clamp_role_title_to_two_words(role: str, full_name: str) -> str:
    """Resume target role for ``best_title``: at most two whitespace-separated words; strip a leading full name."""
    s = str(role or "").strip()
    fn = (full_name or "").strip()
    if fn:
        if s.casefold().startswith(fn.casefold()):
            s = s[len(fn) :].lstrip(" \t-\u2014\u2013:—|").strip()
        inner = f"({fn})"
        if s.casefold().startswith(inner.casefold()):
            s = s[len(inner) :].lstrip(" \t-\u2014\u2013:—|").strip()
    parts = s.split()
    if not parts:
        return "Resume"
    return " ".join(parts[:2])


def _clamp_best_title_in_data(data: dict[str, Any], full_name: str) -> None:
    """Mutate ``data['best_title']`` to at most two role words (name excluded)."""
    bt = data.get("best_title")
    if not isinstance(bt, str):
        return
    data["best_title"] = clamp_role_title_to_two_words(bt, full_name)


def _first_dash_segment(text: str) -> str:
    """If text contains multiple dash-separated phrases, keep only the first segment."""
    if not isinstance(text, str):
        return ""
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts[0] if parts else ""


def _collapse_resume_title_to_name_and_one_subtitle(full: str, dossier_name: str) -> str:
    """Normalize to ``{dossier_name} — {first subtitle segment}`` when the model emits extra dashes."""
    dn = dossier_name.strip()
    s = full.strip().replace("*", "").strip()
    if not s:
        return dn
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(s) if p.strip()]
    if not parts:
        return dn
    if dn and _normalize_whitespace_casefold(parts[0]) == _normalize_whitespace_casefold(dn):
        if len(parts) >= 2:
            return f"{dn} — {parts[1]}"
        return dn
    if dn:
        return f"{dn} — {parts[0]}"
    return parts[0]


def _normalize_llm_project_title(
    raw: str,
    template_line: str,
    dossier_source: str | None = None,
) -> str:
    """Strip echoed template heading from LLM title when it duplicates the Word template.

    If ``dossier_source`` is set and matches the left side of ``Name — Subtitle``, keep the
    **full** string so the resume line stays ``ProjectName — subtitle`` (do not drop the name).
    """
    s = raw.strip().replace("*", "").strip()
    ds = (dossier_source or "").strip()
    for sep in ("\u2014", "\u2013", " - ", " – "):
        if sep in s:
            left, right = s.split(sep, 1)
            if ds and _normalize_whitespace_casefold(left) == _normalize_whitespace_casefold(ds):
                return s
            if _normalize_whitespace_casefold(left) == _normalize_whitespace_casefold(template_line):
                return right.strip()
    return s


def _resolved_project_title_from_llm(pout: dict[str, Any], block: ProjectBlock) -> str:
    ds = pout.get("dossier_source")
    ds_str = ds.strip() if isinstance(ds, str) else ""
    raw_title = pout.get("title")
    if isinstance(raw_title, str) and raw_title.strip():
        collapsed = (
            _collapse_resume_title_to_name_and_one_subtitle(raw_title, ds_str)
            if ds_str
            else raw_title.strip()
        )
        return _normalize_llm_project_title(collapsed, block.title_text, ds_str or None)
    name = pout.get("name")
    sub = pout.get("subtitle")
    if isinstance(name, str) and name.strip():
        base = name.strip()
        if isinstance(sub, str) and sub.strip():
            sub_one = _first_dash_segment(sub.strip())
            if not sub_one:
                return _normalize_llm_project_title(base, block.title_text, ds_str or None)
            merged = f"{base} — {sub_one}"
            return _normalize_llm_project_title(merged, block.title_text, ds_str or None)
        return _normalize_llm_project_title(base, block.title_text, ds_str or None)
    return block.title_text


def _clear_run_text(r: ET.Element) -> None:
    t = r.find(_w("t"))
    if t is None:
        t = ET.SubElement(r, _w("t"))
    t.text = ""
    t.tail = None


def _set_run_text(r: ET.Element, text: str) -> None:
    t = r.find(_w("t"))
    if t is None:
        t = ET.SubElement(r, _w("t"))
    t.text = text
    t.tail = None


def _ensure_bold_run(r: ET.Element) -> None:
    rpr = r.find(_w("rPr"))
    if rpr is None:
        rpr = ET.Element(_w("rPr"))
        r.insert(0, rpr)
    if rpr.find(_w("b")) is None:
        ET.SubElement(rpr, _w("b"))


def _update_project_title_para(
    title_para: ET.Element,
    full_title: str,
    preserve_runs: set[ET.Element] | None = None,
) -> None:
    """Set the first bold w:r's text to full_title; if none, first w:r with text. Do not clear preserved runs."""
    preserve = preserve_runs or set()
    target: ET.Element | None = None
    for r in title_para.findall(_w("r")):
        if _run_is_bold(r):
            target = r
            break
    if target is None:
        for r in title_para.findall(_w("r")):
            t = r.find(_w("t"))
            if t is not None and (t.text or "").strip():
                target = r
                break
    if target is None:
        target = ET.SubElement(title_para, _w("r"))
        _ensure_bold_run(target)
        ET.SubElement(target, _w("t")).text = full_title
        return
    _ensure_bold_run(target)
    _set_run_text(target, full_title)
    for r in title_para.findall(_w("r")):
        if r is not target and r not in preserve:
            _clear_run_text(r)


def _body_index_of_child(body: ET.Element, child: ET.Element) -> int:
    for idx, c in enumerate(body):
        if c is child:
            return idx
    raise ValueError("Child not in body")


def _build_bullet_paragraph(
    template_p: ET.Element,
    bullet_text: str,
    ref_plain: ET.Element,
    ref_bold: ET.Element | None,
) -> ET.Element:
    new_p = copy.deepcopy(template_p)
    for r in list(new_p.findall(_w("r"))):
        new_p.remove(r)
    segments = split_double_asterisk_segments(bullet_text)
    for seg, is_bold in segments:
        if not seg:
            continue
        if is_bold and ref_bold is not None:
            r = copy.deepcopy(ref_bold)
        else:
            r = copy.deepcopy(ref_plain)
        _set_run_text(r, seg)
        new_p.append(r)
    return new_p


def _apply_skills(ext: ResumeExtraction, skills_obj: dict[str, Any]) -> None:
    for key in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
        r = ext.skills.label_to_plain_run.get(key)
        if r is None:
            continue
        val = skills_obj.get(key)
        if not isinstance(val, str):
            continue
        _set_run_text(r, val.strip())


def apply_tailor_json_to_document(
    ext: ResumeExtraction,
    data: dict[str, Any],
    full_name: str = "",
) -> None:
    """Mutate document body in place from validated LLM JSON."""
    projects_out = data.get("projects")
    if not isinstance(projects_out, list):
        raise ValueError("LLM JSON missing projects list")
    n = min(len(projects_out), len(ext.projects))
    first_doc_k = min(
        range(n),
        key=lambda i: _body_index_of_child(ext.body, ext.projects[i].bullet_paras[0]),
    )
    fn_stripped = full_name.strip()
    ordered = sorted(
        range(n),
        key=lambda k: _body_index_of_child(ext.body, ext.projects[k].bullet_paras[0]),
        reverse=True,
    )
    for k in ordered:
        block = ext.projects[k]
        pout = projects_out[k]
        if not isinstance(pout, dict):
            continue
        full_title = _resolved_project_title_from_llm(pout, block)
        if fn_stripped and k == first_doc_k and isinstance(data.get("best_title"), str):
            bt = str(data["best_title"]).strip()
            if bt:
                tpl_left, _tpl_right = _split_resume_header_line(block.title_text)
                if tpl_left and _normalize_whitespace_casefold(tpl_left) == _normalize_whitespace_casefold(
                    fn_stripped
                ):
                    full_title = f"{fn_stripped} — {bt}"
        raw_bullets = pout.get("bullets")
        if isinstance(raw_bullets, tuple):
            raw_bullets = list(raw_bullets)
        if not isinstance(raw_bullets, list):
            raw_bullets = []
        bullets = [str(b) for b in raw_bullets]
        preserve_runs = {r for r in (block.date_run, block.tech_run) if r is not None}
        _update_project_title_para(block.title_para, full_title, preserve_runs)
        if block.date_run is not None:
            dr = pout.get("date_range")
            if isinstance(dr, str) and dr.strip():
                _set_run_text(block.date_run, _normalize_tailor_date_range(dr.strip()))
        if block.tech_run is not None:
            tv = pout.get("technologies")
            if isinstance(tv, str) and tv.strip():
                _set_run_text(block.tech_run, tv.strip())
        parent = ext.body
        first = block.bullet_paras[0]
        idx = _body_index_of_child(parent, first)
        template = block.bullet_paras[0]
        # Snapshot text before removing nodes (fallback if incoming bullets are all empty).
        fallback_texts = [_paragraph_plain_text(bp).strip() for bp in block.bullet_paras]
        for bp in block.bullet_paras:
            parent.remove(bp)
        new_ps = [
            _build_bullet_paragraph(template, b.strip(), block.ref_plain_run, block.ref_bold_run)
            for b in bullets
            if b.strip()
        ]
        if not new_ps:
            for fb in fallback_texts:
                new_ps.append(
                    _build_bullet_paragraph(
                        template,
                        fb,
                        block.ref_plain_run,
                        block.ref_bold_run,
                    )
                )
        for j, np in enumerate(new_ps):
            parent.insert(idx + j, np)
    skills_obj = data.get("skills")
    if isinstance(skills_obj, dict):
        _apply_skills(ext, skills_obj)


_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


def _strip_think_block(content: str) -> tuple[str, str]:
    """Remove ``<think>…</think>`` block if embedded in content (fallback). Returns (cleaned, thinking_text)."""
    m = _THINK_RE.search(content)
    if m is None:
        return content, ""
    thinking = m.group(0)[len("<think>"):-len("</think>")].strip()
    return (content[: m.start()] + content[m.end() :]).strip(), thinking


def _extract_thinking_from_response(resp: Any) -> str:
    """Pull thinking text from Ollama's ``message.thinking`` field (native API), falling back to tag stripping."""
    msg = getattr(resp, "message", None)
    if msg is not None:
        thinking = getattr(msg, "thinking", None)
        if isinstance(thinking, str) and thinking.strip():
            return thinking.strip()
    if isinstance(resp, dict):
        msg = resp.get("message") or {}
        thinking = msg.get("thinking")
        if isinstance(thinking, str) and thinking.strip():
            return thinking.strip()
    return ""


def _strip_json_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content


def _skill_line_item_count(line: str) -> int:
    """Count comma-separated skill tokens (non-empty after strip)."""
    parts = [p.strip() for p in str(line).split(",")]
    return len([p for p in parts if p])


_SKILL_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Languages", 4, 6),
    ("Frameworks & Libraries", 5, 7),
    ("Tools & Technologies", 5, 7),
)

# Per-project ``technologies`` line in JSON (comma-separated); JD-first order from the model.
_MAX_PROJECT_TECHNOLOGIES = 7


def _skill_line_tokens(line: str) -> list[str]:
    return [p.strip() for p in str(line).split(",") if p.strip()]


def _join_skill_tokens(tokens: list[str]) -> str:
    return ", ".join(tokens)


def _prepare_tailor_llm_lists_for_resume(data: dict[str, Any]) -> None:
    """After LLM JSON parse: clamp skills + per-project ``technologies`` to resume limits.

    The model should order each comma-separated list **most relevant and impressive → least**;
    we **keep the prefix** and **drop the tail** so JD-critical tokens survive.
    """
    sk = data.get("skills")
    if isinstance(sk, dict):
        _clamp_tailor_skills_over_max(sk)
    _clamp_tailor_project_technologies(data)


def _clamp_tailor_project_technologies(data: dict[str, Any]) -> None:
    """Trim each project ``technologies`` string to at most ``_MAX_PROJECT_TECHNOLOGIES`` tokens.

    Keeps the **leading** tokens (model orders best-first; we discard the rest from the end).
    Mutates ``data`` in place.
    """
    projs = data.get("projects")
    if not isinstance(projs, list):
        return
    for p in projs:
        if not isinstance(p, dict):
            continue
        t = p.get("technologies")
        if not isinstance(t, str):
            continue
        toks = _skill_line_tokens(t)
        if len(toks) > _MAX_PROJECT_TECHNOLOGIES:
            p["technologies"] = _join_skill_tokens(toks[:_MAX_PROJECT_TECHNOLOGIES])
            logger.info(
                "Tailor project technologies: trimmed from %s to %s items",
                len(toks),
                _MAX_PROJECT_TECHNOLOGIES,
            )


def _clamp_tailor_skills_over_max(skills: dict[str, Any]) -> None:
    """Trim skill lines that exceed band maximums (mutates ``skills`` in place).

    Keeps the **leading** N tokens per line (model orders most relevant / impressive first;
    excess is dropped from the **end**).
    """
    for key, _lo, hi in _SKILL_BANDS:
        v = skills.get(key)
        if not isinstance(v, str):
            continue
        toks = _skill_line_tokens(v)
        if len(toks) > hi:
            skills[key] = _join_skill_tokens(toks[:hi])
            logger.info("Tailor skills: trimmed %s from %s to %s items", key, len(toks), hi)


def _validate_tailor_response(
    data: dict[str, Any],
    expected_projects: int,
    bullets_per_slot: list[int],
) -> tuple[bool, str]:
    """Return (True, \"\") if JSON matches template constraints; else (False, short reason for logs)."""
    if not isinstance(data.get("best_title"), str) or not str(data["best_title"]).strip():
        return False, "best_title must be a non-empty string"
    projs = data.get("projects")
    if not isinstance(projs, list):
        return False, "projects must be a list"
    if len(projs) != expected_projects:
        return (
            False,
            f"projects length must be {expected_projects} (got {len(projs)})",
        )
    if len(bullets_per_slot) != expected_projects:
        return (
            False,
            f"bullets_per_slot length {len(bullets_per_slot)} != expected_projects {expected_projects}",
        )
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return False, "skills must be an object"
    for key in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
        if key not in skills or not isinstance(skills[key], str):
            return False, f"skills[{key!r}] must be a string"
    for i, p in enumerate(projs):
        if not isinstance(p, dict):
            return False, f"projects[{i}] must be an object"
        has_title = isinstance(p.get("title"), str) and str(p.get("title")).strip()
        nm = p.get("name")
        st = p.get("subtitle")
        has_name_and_subtitle = (
            isinstance(nm, str)
            and nm.strip()
            and isinstance(st, str)
            and st.strip()
        )
        if not has_title and not has_name_and_subtitle:
            return (
                False,
                f"projects[{i}] needs non-empty title or both name and subtitle",
            )
        ds = p.get("dossier_source")
        if not isinstance(ds, str) or not ds.strip():
            return False, f"projects[{i}].dossier_source must be a non-empty string"
        dr = p.get("date_range")
        if not isinstance(dr, str) or not dr.strip():
            return False, f"projects[{i}].date_range must be a non-empty string"
        tech = p.get("technologies")
        if not isinstance(tech, str) or not tech.strip():
            return False, f"projects[{i}].technologies must be a non-empty string"
        tech_n = _skill_line_item_count(tech.strip())
        if not (1 <= tech_n <= _MAX_PROJECT_TECHNOLOGIES):
            return (
                False,
                f"projects[{i}].technologies: need 1–{_MAX_PROJECT_TECHNOLOGIES} comma-separated items, got {tech_n}",
            )
        bullets = p.get("bullets")
        need = bullets_per_slot[i]
        if not isinstance(bullets, list) or len(bullets) != need:
            got = len(bullets) if isinstance(bullets, list) else "non-list"
            return (
                False,
                f"projects[{i}].bullets: need {need} items, got {got}",
            )
        for j, b in enumerate(bullets):
            if not isinstance(b, str) or not b.strip():
                return False, f"projects[{i}].bullets[{j}] must be a non-empty string"
    lang_n = _skill_line_item_count(str(skills["Languages"]))
    if not (4 <= lang_n <= 6):
        return False, f"skills.Languages: need 4–6 comma-separated items, got {lang_n}"
    fw_n = _skill_line_item_count(str(skills["Frameworks & Libraries"]))
    if not (5 <= fw_n <= 7):
        return (
            False,
            f"skills['Frameworks & Libraries']: need 5–7 comma-separated items, got {fw_n}",
        )
    tools_n = _skill_line_item_count(str(skills["Tools & Technologies"]))
    if not (5 <= tools_n <= 7):
        return (
            False,
            f"skills['Tools & Technologies']: need 5–7 comma-separated items, got {tools_n}",
        )
    return True, ""


def _apply_tailor_explanation_defaults(data: dict[str, Any], expected_projects: int) -> None:
    ja = data.get("job_analysis")
    if not isinstance(ja, str) or not ja.strip():
        data["job_analysis"] = "No analysis available."
    cs = data.get("change_summary")
    if not isinstance(cs, list):
        data["change_summary"] = [""] * expected_projects
        return
    out: list[str] = []
    for i in range(expected_projects):
        if i < len(cs) and isinstance(cs[i], str):
            out.append(cs[i].strip())
        else:
            out.append("")
    data["change_summary"] = out


def _preview_project_title(p: dict[str, Any]) -> str:
    """Display title for dashboard: combined ``title``, or ``name — subtitle``, or ``name``."""
    raw = p.get("title")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    name = p.get("name")
    sub = p.get("subtitle")
    if isinstance(name, str) and name.strip():
        if isinstance(sub, str) and sub.strip():
            return f"{name.strip()} — {sub.strip()}"
        return name.strip()
    return ""


def _preview_block(p: dict[str, Any]) -> dict[str, Any]:
    title = _preview_project_title(p)
    bullets = [str(b).strip() for b in p.get("bullets", []) if isinstance(b, str) and str(b).strip()]
    ds = str(p.get("dossier_source", "")).strip()
    return {
        "title": title,
        "date_range": _normalize_tailor_date_range(str(p.get("date_range", "")).strip()),
        "technologies": str(p.get("technologies", "")).strip(),
        "bullets": bullets,
        "dossier_source": ds or title,
    }


def llm_json_to_tailored_preview(data: dict[str, Any]) -> dict[str, Any]:
    """Tailored résumé fields for API + dashboard (ATS JSON shape)."""
    experience: list[dict[str, Any]] = []
    for p in data.get("experience", []) or []:
        if isinstance(p, dict):
            experience.append(_preview_block(p))
    projects: list[dict[str, Any]] = []
    for p in data.get("projects", []) or []:
        if isinstance(p, dict):
            projects.append(_preview_block(p))
    skills_obj = data.get("skills")
    skills: dict[str, str] = {}
    if isinstance(skills_obj, dict):
        for key in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
            v = skills_obj.get(key)
            if isinstance(v, str):
                skills[key] = v.strip()
    cc_raw = data.get("core_competencies") or []
    core_competencies = [str(c).strip() for c in cc_raw if isinstance(c, str) and str(c).strip()]
    return {
        "experience": experience,
        "projects": projects,
        "professional_summary": str(data.get("professional_summary", "")).strip(),
        "core_competencies": core_competencies,
        "skills": skills,
        "best_title": str(data.get("best_title", "")).strip(),
    }


def _resolved_tailor_num_predict_cap(settings: dict[str, Any]) -> int:
    """Upper bound for tailor output tokens (Ollama ``num_predict``)."""
    raw = settings.get("ollama_tailor_num_predict_max")
    if raw is None:
        return _MAX_TAILOR_NUM_PREDICT
    try:
        v = int(raw)
        if v > 0:
            return min(v, _MAX_TAILOR_NUM_PREDICT)
    except (TypeError, ValueError):
        pass
    return _MAX_TAILOR_NUM_PREDICT


def _tailor_num_predict_attempts(settings: dict[str, Any]) -> list[int]:
    """Escalating ``num_predict`` values so long JSON is not truncated mid-stream."""
    cap = _resolved_tailor_num_predict_cap(settings)
    raw = settings.get("ollama_tailor_num_predict")
    if raw is not None:
        try:
            base = int(raw)
            if base <= 0:
                base = _DEFAULT_TAILOR_NUM_PREDICT
        except (TypeError, ValueError):
            base = _DEFAULT_TAILOR_NUM_PREDICT
    else:
        base = _DEFAULT_TAILOR_NUM_PREDICT
    base = min(max(base, 1), cap)
    mid = min(max(base * 2, 32768), cap)
    seq = [base, mid, cap]
    out: list[int] = []
    for p in seq:
        p = min(max(p, 1), cap)
        if p not in out:
            out.append(p)
    return out


def _tailor_client_timeout_seconds(settings: dict[str, Any], max_num_predict: int) -> float:
    """Scale HTTP timeout with largest planned output (long generations need more wall time)."""
    base = float(
        settings.get(
            "ollama_tailor_timeout_seconds",
            settings.get("ollama_timeout_seconds", 120),
        )
    )
    if base < 90:
        base = 120.0
    # Rough budget: extra time for large num_predict (local GPU can still take minutes).
    scaled = 90.0 + float(max_num_predict) / 120.0
    return max(base, min(900.0, scaled))


def _tailor_ollama_model(settings: dict[str, Any]) -> str:
    """Model for resume tailor + one-page compress; falls back to ``ollama_model`` for scoring."""
    raw = settings.get("ollama_tailor_model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return str(settings.get("ollama_model", "qwen3:14b"))


def _model_supports_thinking(model: str) -> bool:
    """True when the Ollama model tag implies native ``<think>`` support (Qwen 3 family)."""
    tag = model.strip().lower()
    return tag.startswith("qwen3:") or tag.startswith("qwen3-") or tag == "qwen3"


def _tailor_think_param(settings: dict[str, Any], model: str) -> bool | None:
    """Return ``True`` to enable Ollama's ``think`` API for the tailor call, ``None`` to leave default.

    Auto-detection: Qwen 3 models get ``True`` so the model reasons through project
    scoring before emitting JSON (thinking goes into ``message.thinking``, content stays
    clean JSON). Other models get ``None`` (server default). Override via
    ``ollama_tailor_think`` in settings (``true`` / ``false``).
    """
    override = settings.get("ollama_tailor_think")
    if override is not None:
        if isinstance(override, bool):
            return override or None
        if isinstance(override, str):
            return True if override.strip().lower() in ("1", "true", "yes", "on") else None
    return True if _model_supports_thinking(model) else None


def _parse_tailor_raw(
    raw: str, expected_projects: int, bullets_per_slot: list[int]
) -> tuple[dict[str, Any] | None, str, str]:
    """Return (parsed dict, failure reason, thinking_text) for logging."""
    cleaned, thinking = _strip_think_block(raw)
    try:
        obj = json.loads(_strip_json_fences(cleaned))
    except json.JSONDecodeError as e:
        return None, f"json_decode:{e}", thinking
    if not isinstance(obj, dict):
        return None, "not_a_dict", thinking
    _prepare_tailor_llm_lists_for_resume(obj)
    ok, vreason = _validate_tailor_response(obj, expected_projects, bullets_per_slot)
    if not ok:
        return None, f"validation_failed:{vreason}", thinking
    _normalize_project_date_ranges_in_data(obj)
    _apply_tailor_explanation_defaults(obj, expected_projects)
    return obj, "", thinking


def _apply_ats_tailor_explanation_defaults(data: dict[str, Any]) -> None:
    ja = data.get("job_analysis")
    if not isinstance(ja, str) or not ja.strip():
        data["job_analysis"] = "No analysis available."
    cs = data.get("change_summary")
    if not isinstance(cs, list) or len(cs) == 0:
        data["change_summary"] = ["Tailoring notes not provided."]
    else:
        data["change_summary"] = [
            str(x).strip() if isinstance(x, str) else "" for x in cs
        ]


def _parse_ats_tailor_raw(
    raw: str, settings: dict[str, Any]
) -> tuple[dict[str, Any] | None, str, str]:
    """Parse and validate flexible ATS tailor JSON."""
    cleaned, thinking = _strip_think_block(raw)
    try:
        obj = json.loads(_strip_json_fences(cleaned))
    except json.JSONDecodeError as e:
        return None, f"json_decode:{e}", thinking
    if not isinstance(obj, dict):
        return None, "not_a_dict", thinking
    normalize_ats_date_ranges(obj)
    prepare_ats_tailor_lists(obj)
    caps = ats_tailor_caps(settings)
    ok, vreason = validate_ats_tailor_response(obj, caps)
    if not ok:
        return None, f"validation_failed:{vreason}", thinking
    _apply_ats_tailor_explanation_defaults(obj)
    return obj, "", thinking


def _format_bullets_per_slot(bullets_per_slot: list[int]) -> str:
    if len(set(bullets_per_slot)) <= 1 and bullets_per_slot:
        return f"{bullets_per_slot[0]} bullets per slot"
    return "; ".join(f"slot {k + 1}: {c} bullets" for k, c in enumerate(bullets_per_slot))


def _tailored_docx_bytes_from_template_path(
    docx_path: Path,
    llm_data: dict[str, Any],
    full_name: str = "",
) -> bytes:
    """Build a full .docx from the template file and tailored JSON (opens a fresh zip each call)."""
    _normalize_project_date_ranges_in_data(llm_data)
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml_bytes = zin.read("word/document.xml")
        root = ET.fromstring(doc_xml_bytes.decode("utf-8"))
        ext = extract_resume_structure(root)
        apply_tailor_json_to_document(ext, llm_data, full_name)
        new_doc_bytes = _serialize_document_xml(root)
        out_buf = BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                payload = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    payload = new_doc_bytes
                zout.writestr(info, payload)
    return out_buf.getvalue()


def _tailor_enforce_one_page(settings: dict[str, Any]) -> bool:
    v = settings.get("tailor_enforce_one_page")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _tailor_one_page_max_attempts(settings: dict[str, Any]) -> int:
    raw = settings.get("tailor_one_page_max_trim_attempts", 5)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 5
    return max(1, min(12, n))


def _summarize_tailor_ollama_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate token counts and wall time across sequential tailor / compress LLM calls."""
    tp = sum(int(r["prompt_tokens"]) for r in runs if isinstance(r.get("prompt_tokens"), int))
    to = sum(int(r["output_tokens"]) for r in runs if isinstance(r.get("output_tokens"), int))
    wall = sum(float(r["total_seconds"]) for r in runs if isinstance(r.get("total_seconds"), (int, float)))
    gen_speeds = [
        float(r["output_tokens_per_second"])
        for r in runs
        if isinstance(r.get("output_tokens_per_second"), (int, float))
    ]
    models = list({str(r["model"]) for r in runs if isinstance(r.get("model"), str) and r["model"]})
    summary: dict[str, Any] = {
        "llm_calls": len(runs),
        "total_prompt_tokens": tp,
        "total_output_tokens": to,
        "total_tokens": tp + to,
        "total_wall_seconds": round(wall, 3),
        "models": models,
    }
    if gen_speeds:
        summary["output_tokens_per_second_min"] = round(min(gen_speeds), 1)
        summary["output_tokens_per_second_max"] = round(max(gen_speeds), 1)
        summary["output_tokens_per_second_avg"] = round(sum(gen_speeds) / len(gen_speeds), 1)
    return summary


def _tailor_pdf_convert_timeout(settings: dict[str, Any]) -> float:
    raw = settings.get("tailor_pdf_convert_timeout_seconds", 120)
    try:
        t = float(raw)
    except (TypeError, ValueError):
        return 120.0
    return max(30.0, min(300.0, t))


def call_tailor_fit_one_page_llm(
    current: dict[str, Any],
    pdf_page_count: int,
    settings: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return shorter validated ATS tailor JSON so the PDF fits one page.

    Second element is one metrics dict per ollama HTTP response (including failed parse attempts).
    """
    model = _tailor_ollama_model(settings)
    host = str(settings.get("ollama_host", "http://127.0.0.1:11434"))

    fit_predict_raw = settings.get("ollama_tailor_fit_one_page_num_predict")
    if fit_predict_raw is not None:
        try:
            num_predict_a = max(1024, min(_MAX_TAILOR_NUM_PREDICT, int(fit_predict_raw)))
        except (TypeError, ValueError):
            num_predict_a = 12288
    else:
        first = _tailor_num_predict_attempts(settings)[0]
        num_predict_a = max(4096, min(first, 24576))

    predict_attempts_fit = [num_predict_a]
    if num_predict_a < _MAX_TAILOR_NUM_PREDICT:
        predict_attempts_fit.append(min(num_predict_a * 2, _MAX_TAILOR_NUM_PREDICT))

    timeout = _tailor_client_timeout_seconds(settings, predict_attempts_fit)

    fit_temp = settings.get("ollama_tailor_fit_one_page_temperature")
    if fit_temp is not None:
        temperature = max(0.0, min(2.0, float(fit_temp)))
    else:
        base = settings.get("ollama_tailor_temperature")
        try:
            bt = float(base) if base is not None else 0.28
        except (TypeError, ValueError):
            bt = 0.28
        temperature = max(0.0, min(0.25, bt))

    base_options: dict[str, Any] = {
        "temperature": temperature,
        "repeat_penalty": read_ollama_repeat_penalty(settings),
    }
    num_ctx_raw = settings.get("ollama_tailor_num_ctx")
    if num_ctx_raw is not None:
        try:
            nctx = int(num_ctx_raw)
            if nctx > 0:
                base_options["num_ctx"] = nctx
        except (TypeError, ValueError):
            pass

    system_prompt = _read_text(prompts_dir() / "resume_tailor_fit_one_page.txt")
    try:
        current_json = json.dumps(current, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.error("Failed to serialise tailor JSON for one-page pass")
        return None, []

    user_template = _read_text(prompts_dir() / "resume_tailor_fit_one_page_user.txt")
    user_prompt = user_template.replace("{{pdf_page_count}}", str(pdf_page_count)).replace(
        "{{current_json}}", current_json
    )

    think_param = _tailor_think_param(settings, model)

    client = ollama.Client(host=host, timeout=timeout)
    metrics_runs: list[dict[str, Any]] = []

    for num_predict in predict_attempts_fit:
        opts = {**base_options, "num_predict": num_predict}
        chat_kwargs: dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options=opts,
        )
        if think_param is not None:
            chat_kwargs["think"] = think_param
        try:
            resp = client.chat(**chat_kwargs)
        except Exception:
            logger.exception("Ollama one-page tailor request failed (num_predict=%s)", num_predict)
            continue
        thinking = _extract_thinking_from_response(resp)
        if thinking:
            logger.info("One-page trim thinking: %s", thinking[:2000])
        m = ollama_response_metrics_dict(resp)
        m.update(
            {
                "phase": "one_page_trim",
                "model": model,
                "num_predict": num_predict,
                "pdf_page_count": pdf_page_count,
            }
        )
        metrics_runs.append(m)
        log_ollama_metrics(resp, f"one-page-trim num_predict={num_predict}")
        msg = getattr(resp, "message", None)
        content = getattr(msg, "content", None) if msg is not None else None
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            content = msg.get("content", content)
        if not content:
            logger.error("Empty ollama one-page tailor response (num_predict=%s)", num_predict)
            continue
        out, reason, _extra_think = _parse_ats_tailor_raw(str(content), settings)
        if out is not None:
            return out, metrics_runs
        logger.warning(
            "One-page tailor parse/validation failed (%s) num_predict=%s head=%r",
            reason,
            num_predict,
            str(content)[:200].replace("\n", " "),
        )
    return None, metrics_runs


def _hydrate_rebuild_data_for_one_page_trim(data: dict[str, Any]) -> None:
    """Set ``dossier_source`` on each experience/project block when missing (dashboard rebuild)."""
    for key in ("experience", "projects"):
        arr = data.get(key)
        if not isinstance(arr, list):
            continue
        for p in arr:
            if not isinstance(p, dict):
                continue
            ds = p.get("dossier_source")
            if isinstance(ds, str) and ds.strip():
                continue
            title = p.get("title")
            p["dossier_source"] = (
                title.strip() if isinstance(title, str) and title.strip() else "Resume block"
            )


def _maybe_trim_ats_tailor_to_one_page(
    llm_data: dict[str, Any],
    profile_id: str,
    full_name: str,
    settings: dict[str, Any],
    initial_pdf_bytes: bytes,
) -> tuple[bytes, dict[str, Any], list[dict[str, Any]]]:
    """If enabled, measure Playwright PDF pages and run compress LLM until one page or max rounds."""
    from pipeline.pdf_pages import count_pdf_pages

    trim_metrics: list[dict[str, Any]] = []

    if not _tailor_enforce_one_page(settings):
        return initial_pdf_bytes, llm_data, trim_metrics

    max_trims = _tailor_one_page_max_attempts(settings)
    pdf_bytes = initial_pdf_bytes
    data = llm_data
    trim_round = 0

    while True:
        try:
            pages = count_pdf_pages(pdf_bytes)
        except Exception:
            logger.exception("One-page enforcement: failed to count PDF pages")
            return pdf_bytes, data, trim_metrics

        if pages <= 1:
            if trim_round > 0:
                logger.info("Tailor one-page trim succeeded after %s round(s)", trim_round)
            return pdf_bytes, data, trim_metrics

        if trim_round >= max_trims:
            logger.warning(
                "Tailored resume PDF still has %s page(s) after %s trim round(s) (target: 1)",
                pages,
                max_trims,
            )
            return pdf_bytes, data, trim_metrics

        trim_round += 1
        logger.info(
            "Tailored resume PDF has %s pages; running one-page compress LLM (round %s/%s)",
            pages,
            trim_round,
            max_trims,
        )
        shrunk, compress_runs = call_tailor_fit_one_page_llm(data, pages, settings)
        for m in compress_runs:
            m["trim_round"] = trim_round
        trim_metrics.extend(compress_runs)
        if shrunk is None:
            logger.warning("One-page compress LLM returned no valid JSON; keeping previous version")
            return pdf_bytes, data, trim_metrics
        data = shrunk
        _clamp_best_title_in_data(data, full_name)
        try:
            pdf_bytes = tailored_json_to_pdf_bytes(data, profile_id, settings)
        except Exception:
            logger.exception("One-page enforcement: failed to rebuild PDF after trim")
            return pdf_bytes, data, trim_metrics


def call_tailor_llm(
    dossier_content: str,
    job_description: str,
    job_title: str,
    company: str,
    settings: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """Call ollama with JSON output; retry with higher ``num_predict`` if parse/validation fails.

    Second element is one metrics dict per successful HTTP response (including failed validations).
    Third element is empty on success; on failure, a short reason for HTTP APIs (e.g.
    ``validation_failed:…``, ``json_decode:…``, or ``ollama_no_response``).
    """
    model = _tailor_ollama_model(settings)
    host = str(settings.get("ollama_host", "http://127.0.0.1:11434"))
    predict_attempts = _tailor_num_predict_attempts(settings)
    timeout = _tailor_client_timeout_seconds(settings, max(predict_attempts))

    tailor_temp = settings.get("ollama_tailor_temperature")
    temperature = float(tailor_temp) if tailor_temp is not None else 0.28
    temperature = max(0.0, min(2.0, temperature))

    base_options: dict[str, Any] = {
        "temperature": temperature,
        "repeat_penalty": read_ollama_repeat_penalty(settings),
    }
    num_ctx_raw = settings.get("ollama_tailor_num_ctx")
    if num_ctx_raw is not None:
        try:
            nctx = int(num_ctx_raw)
            if nctx > 0:
                base_options["num_ctx"] = nctx
        except (TypeError, ValueError):
            pass

    caps = ats_tailor_caps(settings)
    system_prompt = _read_text(prompts_dir() / "resume_tailor.txt")
    user_template = _read_text(prompts_dir() / "resume_tailor_user.txt")
    project_catalog = format_dossier_project_catalog_for_prompt(
        dossier_content, caps["max_projects"]
    )
    user_prompt = (
        user_template.replace("{{project_catalog}}", project_catalog)
        .replace("{{dossier}}", dossier_content)
        .replace("{{max_experience}}", str(caps["max_experience"]))
        .replace("{{max_projects}}", str(caps["max_projects"]))
        .replace("{{max_bullets_experience}}", str(caps["max_bullets_experience"]))
        .replace("{{max_bullets_project}}", str(caps["max_bullets_project"]))
        .replace("{{title}}", job_title)
        .replace("{{company}}", company)
        .replace("{{description}}", job_description)
    )

    think_param = _tailor_think_param(settings, model)
    if think_param:
        logger.info("Tailor: thinking mode enabled for model %s", model)

    client = ollama.Client(host=host, timeout=timeout)
    metrics_runs: list[dict[str, Any]] = []

    def _call_with_predict(num_predict: int) -> tuple[str | None, str]:
        """Returns (content, thinking_text)."""
        opts = {**base_options, "num_predict": num_predict}
        chat_kwargs: dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options=opts,
        )
        if think_param is not None:
            chat_kwargs["think"] = think_param
        try:
            resp = client.chat(**chat_kwargs)
        except Exception:
            logger.exception("Ollama tailor request failed (num_predict=%s)", num_predict)
            return None, ""
        thinking = _extract_thinking_from_response(resp)
        m = ollama_response_metrics_dict(resp)
        m.update({"phase": "tailor", "model": model, "num_predict": num_predict})
        metrics_runs.append(m)
        log_ollama_metrics(resp, f"tailor num_predict={num_predict}")
        msg = getattr(resp, "message", None)
        content = getattr(msg, "content", None) if msg is not None else None
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            content = msg.get("content", content)
        if not content:
            logger.error("Empty ollama tailor response (num_predict=%s)", num_predict)
            return None, thinking
        return str(content), thinking

    last_raw: str | None = None
    last_reason = ""
    for attempt_i, num_predict in enumerate(predict_attempts):
        raw, thinking = _call_with_predict(num_predict)
        if thinking:
            logger.info("Tailor thinking (attempt %s): %s", attempt_i + 1, thinking[:2000])
        if raw is None:
            continue
        last_raw = raw
        out, reason, _extra_think = _parse_ats_tailor_raw(raw, settings)
        if out is not None:
            if attempt_i > 0:
                logger.info(
                    "Tailor succeeded on attempt %s with num_predict=%s",
                    attempt_i + 1,
                    num_predict,
                )
            return out, metrics_runs, ""
        last_reason = reason
        logger.warning(
            "Tailor attempt %s/%s failed (%s) num_predict=%s; raw_len=%s head=%r",
            attempt_i + 1,
            len(predict_attempts),
            reason,
            num_predict,
            len(raw),
            raw[:240].replace("\n", " "),
        )
    if last_raw is not None:
        tail = last_raw[-400:].replace("\n", " ")
        logger.error(
            "Tailor failed after %s attempts (%s). Raw tail: %s",
            len(predict_attempts),
            last_reason,
            tail,
        )
        fail = last_reason.strip() if last_reason else "validation_failed"
        return None, metrics_runs, fail
    return (
        None,
        metrics_runs,
        "Ollama returned no usable JSON body after all attempts (connection error, timeout, or empty "
        f"content). Check `ollama serve`, model {model!r}, and host {host!r}.",
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _safe_filename_part(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_") or "resume"


def dossier_path(profile_id: str, settings: dict[str, Any] | None = None) -> Path:
    """Path to the experience dossier markdown for tailoring."""
    settings = settings or load_settings()
    raw = settings.get("experience_dossier")
    if isinstance(raw, str) and raw.strip():
        p = Path(raw.strip())
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p.resolve()
    base = profiles_dir(settings)
    return (base / profile_id / "experience-dossier.md").resolve()


def _read_dossier(profile_id: str, settings: dict[str, Any] | None = None) -> str | None:
    """Load dossier text, or None if missing."""
    p = dossier_path(profile_id, settings)
    if not p.is_file():
        logger.error("Experience dossier not found: %s", p)
        return None
    return p.read_text(encoding="utf-8")


def resume_docx_path(profile_id: str, settings: dict[str, Any] | None = None) -> Path:
    """Path to Word resume template used for tailoring."""
    settings = settings or load_settings()
    for key in ("resume_template_docx", "resume_docx"):
        raw = settings.get(key)
        if isinstance(raw, str) and raw.strip():
            p = Path(raw.strip())
            if not p.is_absolute():
                p = REPO_ROOT / p
            return p.resolve()
    base = profiles_dir(settings)
    candidates = [
        base / profile_id / "jeff resume template.docx",
        base / profile_id / "Jeff Tian Resume.docx",
        base / "Jeff Tian Resume.docx",
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return (base / profile_id / "Jeff Tian Resume.docx").resolve()


def _serialize_document_xml(root: ET.Element) -> bytes:
    ET.register_namespace("w", W_NS)
    buf = BytesIO()
    tree = ET.ElementTree(root)
    tree.write(buf, encoding="UTF-8", xml_declaration=True, default_namespace=None)
    return buf.getvalue()


_TAILOR_OLLAMA_MEMORY_HINT = (
    "GPU/ANE memory is used by the Ollama server process, not the JobRadar API. "
    "After a run, check Activity Monitor (ollama) or run `ollama ps` for loaded models."
)


@dataclass
class TailorPreviewResult:
    """Result of tailoring for API + dashboard preview (ATS PDF)."""

    pdf_bytes: bytes
    filename: str
    original: dict[str, Any]
    tailored: dict[str, Any]
    explanation: dict[str, Any]
    ollama_metrics: dict[str, Any] = field(default_factory=dict)


def tailor_resume_bytes_with_preview(
    job_description: str,
    job_title: str,
    company: str,
    full_name: str,
    profile_id: str,
    settings: dict[str, Any] | None = None,
) -> tuple[TailorPreviewResult | None, str]:
    """Read dossier, call Ollama, build ATS PDF. Return ``(result, error)``."""
    settings = settings or load_settings()
    dossier_text = _read_dossier(profile_id, settings)
    if dossier_text is None:
        dp = dossier_path(profile_id, settings)
        return None, f"Could not read experience dossier at {dp} (missing file or unreadable)."

    llm_data, tailor_runs, tailor_err = call_tailor_llm(
        dossier_text,
        job_description,
        job_title,
        company,
        settings,
    )
    if llm_data is None:
        return None, tailor_err

    _clamp_best_title_in_data(llm_data, full_name)
    original_preview = build_original_preview_ats(dossier_text)
    try:
        pdf_bytes = tailored_json_to_pdf_bytes(llm_data, profile_id, settings)
    except Exception:
        logger.exception("Failed to build tailored PDF")
        return None, "Failed to build PDF (install Playwright: pip install playwright && playwright install chromium)"

    pdf_bytes, llm_data, trim_runs = _maybe_trim_ats_tailor_to_one_page(
        llm_data,
        profile_id,
        full_name,
        settings,
        pdf_bytes,
    )
    _clamp_best_title_in_data(llm_data, full_name)
    best_title = str(llm_data["best_title"]).strip()
    fn = f"{_safe_filename_part(full_name)}_{_safe_filename_part(best_title)}.pdf"

    all_runs = tailor_runs + trim_runs
    ollama_metrics: dict[str, Any] = {
        "runs": all_runs,
        "summary": _summarize_tailor_ollama_runs(all_runs),
        "memory_note": _TAILOR_OLLAMA_MEMORY_HINT,
    }
    log_tailor_session_ollama_summary(ollama_metrics["summary"])

    tailored_preview = llm_json_to_tailored_preview(llm_data)
    explanation = {
        "job_analysis": str(llm_data.get("job_analysis", "")).strip(),
        "change_summary": list(llm_data.get("change_summary") or []),
    }
    return (
        TailorPreviewResult(
            pdf_bytes=pdf_bytes,
            filename=fn,
            original=original_preview,
            tailored=tailored_preview,
            explanation=explanation,
            ollama_metrics=ollama_metrics,
        ),
        "",
    )


def rebuild_tailored_pdf_from_edits(
    edited_data: dict[str, Any],
    profile_id: str,
    full_name: str,
    settings: dict[str, Any] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Rebuild tailored PDF from user-edited full ATS JSON (no initial LLM).

    ``edited_data`` must include ``experience``, ``projects``, ``skills``, ``best_title``,
    ``professional_summary``, ``core_competencies``, ``job_analysis``, ``change_summary``.

    Raises:
        ValueError: Validation failed.
    """
    settings = settings or load_settings()
    _hydrate_rebuild_data_for_one_page_trim(edited_data)
    normalize_ats_date_ranges(edited_data)
    prepare_ats_tailor_lists(edited_data)
    caps = ats_tailor_caps(settings)
    ok, reason = validate_ats_tailor_response(edited_data, caps)
    if not ok:
        raise ValueError(reason)
    _apply_ats_tailor_explanation_defaults(edited_data)
    _clamp_best_title_in_data(edited_data, full_name)
    try:
        pdf_bytes = tailored_json_to_pdf_bytes(edited_data, profile_id, settings)
    except Exception as e:
        raise RuntimeError(
            "Failed to build PDF. Install Playwright: pip install playwright && playwright install chromium"
        ) from e

    pdf_bytes, final_llm, trim_runs = _maybe_trim_ats_tailor_to_one_page(
        edited_data,
        profile_id,
        full_name,
        settings,
        pdf_bytes,
    )
    _clamp_best_title_in_data(final_llm, full_name)
    best_title = str(final_llm.get("best_title", "")).strip() or "resume"
    fn = f"{_safe_filename_part(full_name)}_{_safe_filename_part(best_title)}.pdf"
    om_summary = _summarize_tailor_ollama_runs(trim_runs)
    meta = {
        "tailored": llm_json_to_tailored_preview(final_llm),
        "explanation": {
            "job_analysis": str(final_llm.get("job_analysis", "")).strip(),
            "change_summary": list(final_llm.get("change_summary") or []),
        },
        "ollama_metrics": {
            "runs": trim_runs,
            "summary": om_summary,
            "memory_note": _TAILOR_OLLAMA_MEMORY_HINT,
        },
    }
    if trim_runs:
        log_tailor_session_ollama_summary(om_summary)
    return pdf_bytes, fn, meta


def tailor_resume(
    job_description: str,
    job_title: str,
    company: str,
    profile_id: str,
    full_name: str,
    settings: dict[str, Any] | None = None,
) -> tuple[TailorPreviewResult | None, str]:
    """Tailor résumé to ATS PDF; return ``(result, error)`` with empty ``error`` on success."""
    settings = settings or load_settings()
    return tailor_resume_bytes_with_preview(
        job_description,
        job_title,
        company,
        full_name,
        profile_id,
        settings,
    )


def load_full_name_for_profile(profile_id: str, settings: dict[str, Any] | None = None) -> str:
    settings = settings or load_settings()
    path = profile_yaml_path(profile_id, settings)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(data, dict):
        return "Candidate"
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "Candidate"


def tailor_result_to_api_dict(result: TailorPreviewResult) -> dict[str, Any]:
    """JSON-serializable payload for POST /tailor-resume."""
    return {
        "filename": result.filename,
        "pdf_base64": base64.b64encode(result.pdf_bytes).decode("ascii"),
        "original": result.original,
        "tailored": result.tailored,
        "explanation": result.explanation,
        "ollama_metrics": result.ollama_metrics,
    }
