"""Validate flexible ATS tailor JSON from Ollama."""

from __future__ import annotations

from typing import Any

_MAX_PROJECT_TECHNOLOGIES = 7
_MAX_SUMMARY_CHARS = 2800
_MAX_BULLET_CHARS = 400
_MAX_COMPETENCY_LEN = 120


def _skill_line_item_count(s: str) -> int:
    return len([x for x in s.split(",") if x.strip()])


def _validate_skills(skills: Any) -> tuple[bool, str]:
    if not isinstance(skills, dict):
        return False, "skills must be an object"
    for key in ("Languages", "Frameworks & Libraries", "Tools & Technologies"):
        if key not in skills or not isinstance(skills[key], str):
            return False, f"skills[{key!r}] must be a string"
    lang_n = _skill_line_item_count(str(skills["Languages"]))
    if not (4 <= lang_n <= 6):
        return False, f"skills.Languages: need 4–6 comma-separated items, got {lang_n}"
    fw_n = _skill_line_item_count(str(skills["Frameworks & Libraries"]))
    if not (5 <= fw_n <= 7):
        return False, f"skills['Frameworks & Libraries']: need 5–7 items, got {fw_n}"
    tools_n = _skill_line_item_count(str(skills["Tools & Technologies"]))
    if not (5 <= tools_n <= 7):
        return False, f"skills['Tools & Technologies']: need 5–7 items, got {tools_n}"
    return True, ""


def _block_title_ok(p: dict[str, Any]) -> bool:
    has_title = isinstance(p.get("title"), str) and str(p.get("title")).strip()
    nm = p.get("name")
    st = p.get("subtitle")
    has_name_sub = (
        isinstance(nm, str)
        and nm.strip()
        and isinstance(st, str)
        and st.strip()
    )
    return bool(has_title or has_name_sub)


def _validate_block(
    p: Any,
    index: int,
    section: str,
    max_bullets: int,
) -> tuple[bool, str]:
    if not isinstance(p, dict):
        return False, f"{section}[{index}] must be an object"
    if not _block_title_ok(p):
        return False, f"{section}[{index}] needs non-empty title or both name and subtitle"
    ds = p.get("dossier_source")
    if not isinstance(ds, str) or not ds.strip():
        return False, f"{section}[{index}].dossier_source must be non-empty"
    dr = p.get("date_range")
    if not isinstance(dr, str) or not dr.strip():
        return False, f"{section}[{index}].date_range must be non-empty"
    tech = p.get("technologies", "")
    if tech is not None and not isinstance(tech, str):
        return False, f"{section}[{index}].technologies must be a string"
    tech_s = str(tech).strip()
    if tech_s:
        tech_n = _skill_line_item_count(tech_s)
        if not (1 <= tech_n <= _MAX_PROJECT_TECHNOLOGIES):
            return (
                False,
                f"{section}[{index}].technologies: need 1–{_MAX_PROJECT_TECHNOLOGIES} items or empty",
            )
    bullets = p.get("bullets")
    if not isinstance(bullets, list) or len(bullets) < 1:
        return False, f"{section}[{index}].bullets: need at least 1 item"
    if len(bullets) > max_bullets:
        return False, f"{section}[{index}].bullets: at most {max_bullets} items, got {len(bullets)}"
    for j, b in enumerate(bullets):
        if not isinstance(b, str) or not b.strip():
            return False, f"{section}[{index}].bullets[{j}] must be non-empty"
        if len(b) > _MAX_BULLET_CHARS:
            return False, f"{section}[{index}].bullets[{j}] too long"
    return True, ""


def validate_ats_tailor_response(data: dict[str, Any], caps: dict[str, int]) -> tuple[bool, str]:
    """Return (True, \"\") if JSON satisfies ATS flexible schema."""

    if not isinstance(data.get("best_title"), str) or not str(data["best_title"]).strip():
        return False, "best_title must be non-empty"
    bt = str(data["best_title"]).strip()
    if len(bt.split()) > 2:
        return False, "best_title must be at most 2 words (role only)"

    summary = data.get("professional_summary")
    if not isinstance(summary, str) or not summary.strip():
        return False, "professional_summary must be non-empty"
    if len(summary) > _MAX_SUMMARY_CHARS:
        return False, "professional_summary too long"

    cc = data.get("core_competencies")
    if not isinstance(cc, list) or len(cc) < 4:
        return False, "core_competencies must be a list with at least 4 items"
    if len(cc) > 12:
        return False, "core_competencies: at most 12 items"
    for i, c in enumerate(cc):
        if not isinstance(c, str) or not c.strip():
            return False, f"core_competencies[{i}] must be non-empty"
        if len(c) > _MAX_COMPETENCY_LEN:
            return False, f"core_competencies[{i}] too long"

    exp = data.get("experience")
    if not isinstance(exp, list):
        return False, "experience must be a list"
    if len(exp) > caps["max_experience"]:
        return False, f"experience: at most {caps['max_experience']} entries"

    proj = data.get("projects")
    if not isinstance(proj, list):
        return False, "projects must be a list"
    if len(proj) > caps["max_projects"]:
        return False, f"projects: at most {caps['max_projects']} entries"

    if len(exp) == 0 and len(proj) == 0:
        return False, "at least one of experience or projects must be non-empty"

    ok, reason = _validate_skills(data.get("skills"))
    if not ok:
        return False, reason

    ja = data.get("job_analysis")
    if not isinstance(ja, str) or not ja.strip():
        return False, "job_analysis must be non-empty"

    cs = data.get("change_summary")
    if not isinstance(cs, list) or len(cs) < 1:
        return False, "change_summary must be a non-empty list of strings"
    for i, line in enumerate(cs):
        if not isinstance(line, str):
            return False, f"change_summary[{i}] must be a string"

    for i, p in enumerate(exp):
        ok_b, msg = _validate_block(p, i, "experience", caps["max_bullets_experience"])
        if not ok_b:
            return False, msg
    for i, p in enumerate(proj):
        ok_b, msg = _validate_block(p, i, "projects", caps["max_bullets_project"])
        if not ok_b:
            return False, msg

    return True, ""
