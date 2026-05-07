"""Run one resume-tailor iteration for Diligent SWE Intern via qwen3.5:9b (no thinking).

Usage: python scripts/tailor_diligent_once.py [out_label]
Writes JSON to /tmp/diligent_tailor_<label>.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.config_paths import load_settings
from pipeline.resume_tailor import (
    call_tailor_llm,
    extract_resume_structure,
    resume_docx_path,
    _apply_rhythm_polish_if_enabled,
    _read_dossier,
)

import zipfile
from xml.etree import ElementTree as ET

JOB_TITLE = "Software Engineering Intern"
COMPANY = "Diligent Corporation"
JOB_DESCRIPTION = """Position Overview
We are seeking a passionate and well-rounded candidate to join Diligent's AI Platform team. As part of this high-impact group, you will help design, build, and deliver the core services that power Diligent's AI-driven capabilities across our global product suite. The candidate will have the opportunity to learn and practice effective analysis, design, programming, and testing to produce and maintain scaled SaaS software solutions. The successful candidate will work as part of an established team used to working together to achieve excellent results. Our ideal candidate will be someone who is motivated, proactive and takes pride in their code.

It's a 4-month program from May 2026 with the possibility of an extension for another term, depending on performance and mutual interest.

Key Responsibilities:
- Work as part of an agile AI Platform team and contribute to grooming user stories and ensuring work items are clear and testable.
- Develop and maintain existing codebases.
- Take part in the team's ceremonies.
- Work on the team's backlog including planning, implementation, testing and release.

Required Experience/Skills
- Self-driven mindset and strong analytical skills.
- University-level programming coursework or comparable coding boot camp qualification.
- Looking for an education in programming, platform development, and AI systems.
- Ability to work unsupervised for extended periods.
- Ability to be on-site in our Vancouver Office.

Nice to Have Qualifications (not required):
- Exposure to fullstack web applications including frontend and backend components.
- Exposure to AI tools (such as code assistants, AI debuggers, or design copilots) to enhance software development speed, quality, and creativity.
- Exposure to cloud environments (AWS, Azure, or GCP).
- Exposure to AI and LLM applications, including prompt engineering, RAG pipelines, or semantic search.
- Exposure with infrastructure-as-code, CI/CD pipelines, and observability practices.
- Passion for continuous learning and for exploring how AI can transform software engineering.

Pay Range: $21 - $25 CAD / hour. Vancouver, British Columbia, Canada. Hybrid (50% onsite).
"""


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    settings = load_settings()
    settings["ollama_tailor_model"] = "qwen3.5:9b"
    settings["ollama_tailor_think"] = False
    settings["ollama_tailor_temperature"] = 0.28

    profile_id = settings.get("active_profile", "jeff")
    dossier = _read_dossier(profile_id, settings)
    if dossier is None:
        raise SystemExit("No dossier")

    docx_path = resume_docx_path(profile_id, settings)
    with zipfile.ZipFile(docx_path, "r") as z:
        root = ET.fromstring(z.read("word/document.xml").decode("utf-8"))
    ext = extract_resume_structure(root)
    n = len(ext.projects)
    bullets_per_slot = [len(p.bullet_paras) for p in ext.projects]
    print(f"[info] projects={n} bullets_per_slot={bullets_per_slot}", flush=True)

    data, runs, err = call_tailor_llm(
        dossier, JOB_DESCRIPTION, JOB_TITLE, COMPANY, settings,
        expected_projects=n, bullets_per_slot=bullets_per_slot,
    )
    if data is None:
        print(f"[fail] {err}", flush=True)
        summary = {"error": err, "runs": runs}
    else:
        pre_polish = {i: [len(b) for b in p["bullets"]] for i, p in enumerate(data["projects"])}
        polished, polish_runs = _apply_rhythm_polish_if_enabled(data, bullets_per_slot, n, settings)
        post_polish = {i: [len(b) for b in p["bullets"]] for i, p in enumerate(polished["projects"])}
        print(f"[pre-polish  ] bullet chars: {pre_polish}", flush=True)
        print(f"[post-polish ] bullet chars: {post_polish}", flush=True)
        all_runs = runs + polish_runs
        summary = {
            "data": polished,
            "pre_polish_bullets": {i: p["bullets"] for i, p in enumerate(data["projects"])},
            "runs_count": len(all_runs),
            "polish_runs": len(polish_runs),
            "wall_s": sum(float(r.get("total_seconds", 0)) for r in all_runs),
        }
        print(f"[ok] wrote; best_title={polished.get('best_title')!r} projects={len(polished.get('projects', []))}", flush=True)

    out = Path(f"/tmp/diligent_tailor_{label}.json")
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[write] {out}", flush=True)


if __name__ == "__main__":
    main()
