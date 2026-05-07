"""Tests for resume tailoring (mocked LLM, minimal .docx)."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest

from pipeline import resume_tailor as rt

MINIMAL_PARTS: dict[str, bytes] = {
    "[Content_Types].xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
    "_rels/.rels": b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
    "word/document.xml": b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t>Test Project</w:t></w:r><w:r><w:t>Jan 2024 - Present</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>First bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Second bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Third bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Fourth bullet line</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Languages: </w:t></w:r><w:r><w:t>Python</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Frameworks &amp; Libraries: </w:t></w:r><w:r><w:t>Flask</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Tools &amp; Technologies: </w:t></w:r><w:r><w:t>Git</w:t></w:r></w:p>
</w:body>
</w:document>""",
}


def _minimal_docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in MINIMAL_PARTS.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def minimal_docx_path(tmp_path: Path) -> Path:
    p = tmp_path / "resume.docx"
    p.write_bytes(_minimal_docx_bytes())
    return p


def test_extract_heading_includes_plain_subtitle_before_date(tmp_path: Path) -> None:
    """Plain `` — Subtitle`` between bold name and date must be part of heading, not mistaken for date."""
    from xml.etree import ElementTree as ET

    parts = dict(MINIMAL_PARTS)
    parts["word/document.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t>JobRadar</w:t></w:r><w:r><w:t> - Template Subtitle</w:t></w:r><w:r><w:t>Jan 2024 - Present</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>First bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Second bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Third bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Fourth bullet line</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Languages: </w:t></w:r><w:r><w:t>Python</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Frameworks &amp; Libraries: </w:t></w:r><w:r><w:t>Flask</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Tools &amp; Technologies: </w:t></w:r><w:r><w:t>Git</w:t></w:r></w:p>
</w:body>
</w:document>""".encode("utf-8")
    p = tmp_path / "sub.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    p.write_bytes(buf.getvalue())
    with zipfile.ZipFile(p, "r") as z:
        root = ET.fromstring(z.read("word/document.xml").decode("utf-8"))
    ext = rt.extract_resume_structure(root)
    assert len(ext.projects) == 1
    assert ext.projects[0].title_text == "JobRadar - Template Subtitle"
    dr = ext.projects[0].date_run
    assert dr is not None
    assert "2024" in rt._run_text_content(dr)


def test_rebuild_docx_clears_plain_subtitle_run_not_duplicate_heading(tmp_path: Path) -> None:
    """Applying tailor JSON must not leave an old plain subtitle run next to the new bold full title."""
    from xml.etree import ElementTree as ET

    parts = dict(MINIMAL_PARTS)
    parts["word/document.xml"] = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t>JobRadar</w:t></w:r><w:r><w:t> - Old Subtitle</w:t></w:r><w:r><w:t>Jan 2024 - Present</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>First bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Second bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Third bullet line</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Fourth bullet line</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Languages: </w:t></w:r><w:r><w:t>Python</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Frameworks &amp; Libraries: </w:t></w:r><w:r><w:t>Flask</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Tools &amp; Technologies: </w:t></w:r><w:r><w:t>Git</w:t></w:r></w:p>
</w:body>
</w:document>""".encode("utf-8")
    p = tmp_path / "sub2.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    p.write_bytes(buf.getvalue())
    edited = {
        "best_title": "Engineer",
        "projects": [
            {
                "dossier_source": "JobRadar",
                "name": "JobRadar",
                "subtitle": "New Subtitle From LLM",
                "date_range": "Jan 2024 - Present",
                "technologies": "Python, SQLite",
                "bullets": ["a", "b", "c", "d"],
            }
        ],
        "skills": {
            "Languages": "Rust, Python, Go, SQL",
            "Frameworks & Libraries": "Tokio, Axum, FastAPI, React, Pandas, NumPy",
            "Tools & Technologies": "Docker, Git, Linux, PostgreSQL, Kubernetes",
        },
    }
    docx_bytes, _, _ = rt.rebuild_docx_from_edits(
        edited,
        "jeff",
        "Someone Else",
        settings={"resume_template_docx": str(p), "tailor_enforce_one_page": False},
    )
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        root = ET.fromstring(z.read("word/document.xml").decode("utf-8"))
    body = root.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body")
    assert body is not None
    first_p = next(c for c in body if c.tag.endswith("}p"))
    para_text = "".join(
        (t.text or "")
        for t in first_p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
    )
    assert "Old Subtitle" not in para_text
    assert para_text.count("JobRadar") == 1
    assert "New Subtitle From LLM" in para_text
    assert "2024" in para_text


def test_extract_and_preview_dict(minimal_docx_path: Path) -> None:
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(minimal_docx_path, "r") as z:
        root = ET.fromstring(z.read("word/document.xml").decode("utf-8"))
    ext = rt.extract_resume_structure(root)
    assert len(ext.projects) == 1
    assert ext.projects[0].title_text == "Test Project"
    assert len(ext.projects[0].bullet_paras) == 4
    assert ext.projects[0].date_run is not None
    prev = rt.extraction_to_preview_dict(ext)
    assert prev["projects"][0]["title"] == "Test Project"
    assert prev["projects"][0]["date_range"] == "Jan 2024 - Present"
    assert prev["projects"][0]["bullets"] == [
        "First bullet line",
        "Second bullet line",
        "Third bullet line",
        "Fourth bullet line",
    ]
    assert "Python" in prev["skills"].get("Languages", "")


def test_validate_tailor_response_without_explanation_fields() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "dossier_source": "Test Project Section",
                "title": "New Title",
                "date_range": "2024 – Present",
                "technologies": "Python, FastAPI",
                "bullets": [
                    "Did **thing** one",
                    "Did two",
                    "Did three",
                    "Did four",
                ],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    assert rt._validate_tailor_response(data, 1, [4]) == (True, "")
    rt._apply_tailor_explanation_defaults(data, 1)
    assert "job_analysis" in data
    assert data["change_summary"] == [""]


def test_validate_tailor_response_rejects_missing_dossier_source() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "title": "T",
                "date_range": "2024",
                "technologies": "Py",
                "bullets": ["a", "b", "c", "d"],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    ok, reason = rt._validate_tailor_response(data, 1, [4])
    assert ok is False
    assert "dossier_source" in reason


def test_validate_tailor_response_rejects_wrong_bullet_count() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "dossier_source": "S",
                "title": "T",
                "date_range": "2024",
                "technologies": "Py",
                "bullets": ["only one"],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    ok, reason = rt._validate_tailor_response(data, 1, [4])
    assert ok is False
    assert "bullets" in reason


def test_validate_tailor_response_rejects_invalid_skills_counts() -> None:
    base_project = {
        "dossier_source": "S",
        "title": "T",
        "date_range": "2024",
        "technologies": "Py",
        "bullets": ["a", "b", "c", "d"],
    }
    ok_fw = "A, B, C, D, E"
    ok_tools = "T1, T2, T3, T4, T5"
    ok, r1 = rt._validate_tailor_response(
        {
            "best_title": "X",
            "projects": [base_project],
            "skills": {
                "Languages": "only, two",
                "Frameworks & Libraries": ok_fw,
                "Tools & Technologies": ok_tools,
            },
        },
        1,
        [4],
    )
    assert ok is False
    assert "Languages" in r1
    ok, r2 = rt._validate_tailor_response(
        {
            "best_title": "X",
            "projects": [base_project],
            "skills": {
                "Languages": "L1, L2, L3, L4, L5, L6, L7",
                "Frameworks & Libraries": ok_fw,
                "Tools & Technologies": ok_tools,
            },
        },
        1,
        [4],
    )
    assert ok is False
    assert "Languages" in r2
    ok, r3 = rt._validate_tailor_response(
        {
            "best_title": "X",
            "projects": [base_project],
            "skills": {
                "Languages": "L1, L2, L3, L4",
                "Frameworks & Libraries": "F1, F2, F3, F4",
                "Tools & Technologies": ok_tools,
            },
        },
        1,
        [4],
    )
    assert ok is False
    assert "Frameworks" in r3


def test_validate_tailor_accepts_name_and_subtitle_without_combined_title() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "dossier_source": "ClashTracker",
                "name": "ClashTracker",
                "subtitle": "Real-Time Game Analytics Dashboard",
                "date_range": "2024",
                "technologies": "Py",
                "bullets": ["a", "b", "c", "d"],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    assert rt._validate_tailor_response(data, 1, [4]) == (True, "")
    prev = rt.llm_json_to_tailored_preview(data)
    assert prev["projects"][0]["title"] == "ClashTracker — Real-Time Game Analytics Dashboard"


def test_validate_tailor_rejects_name_without_subtitle() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "dossier_source": "ClashTracker",
                "name": "ClashTracker",
                "date_range": "2024",
                "technologies": "Py",
                "bullets": ["a", "b", "c", "d"],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    ok, reason = rt._validate_tailor_response(data, 1, [4])
    assert ok is False
    assert "name" in reason.lower() or "subtitle" in reason.lower()


def test_tailor_num_predict_attempts_escalates() -> None:
    assert rt._tailor_num_predict_attempts({"ollama_tailor_num_predict": 8192}) == [8192, 32768, 65536]
    assert rt._tailor_num_predict_attempts({})[0] == rt._DEFAULT_TAILOR_NUM_PREDICT
    assert rt._tailor_num_predict_attempts({"ollama_tailor_num_predict_max": 20000}) == [20000]


def test_clamp_tailor_skills_over_max_trims_frameworks() -> None:
    skills: dict = {
        "Languages": "Python, Go, Java, SQL",
        "Frameworks & Libraries": "A, B, C, D, E, F, G, H, I",
        "Tools & Technologies": "Docker, Git, Linux, PostgreSQL, Kubernetes",
    }
    rt._clamp_tailor_skills_over_max(skills)
    assert rt._skill_line_item_count(skills["Frameworks & Libraries"]) == 7
    assert skills["Frameworks & Libraries"].startswith("A, B, C, D, E, F, G")


def test_clamp_tailor_project_technologies_keeps_first_seven() -> None:
    data: dict = {
        "projects": [
            {
                "technologies": "A, B, C, D, E, F, G, H, I",
            }
        ]
    }
    rt._clamp_tailor_project_technologies(data)
    assert rt._skill_line_item_count(data["projects"][0]["technologies"]) == 7
    assert data["projects"][0]["technologies"] == "A, B, C, D, E, F, G"


def test_prepare_tailor_llm_lists_clamps_skills_and_project_technologies() -> None:
    data: dict = {
        "projects": [{"technologies": "p1, p2, p3, p4, p5, p6, p7, p8"}],
        "skills": {
            "Languages": "A, B, C, D",
            "Frameworks & Libraries": "f1, f2, f3, f4, f5, f6, f7, f8",
            "Tools & Technologies": "t1, t2, t3, t4, t5",
        },
    }
    rt._prepare_tailor_llm_lists_for_resume(data)
    assert data["projects"][0]["technologies"] == "p1, p2, p3, p4, p5, p6, p7"
    assert rt._skill_line_item_count(data["skills"]["Frameworks & Libraries"]) == 7


def test_strip_leading_coursework_label_variants() -> None:
    assert rt._strip_leading_coursework_label("Relevant coursework: DSA, ML") == "DSA, ML"
    assert rt._strip_leading_coursework_label("**Coursework:** Python") == "Python"
    assert rt._strip_leading_coursework_label("COURSEWORK — Graph theory") == "Graph theory"
    assert rt._strip_leading_coursework_label("Built a parser") == "Built a parser"


def test_prepare_tailor_llm_lists_strips_coursework_prefix_from_bullets() -> None:
    data: dict = {
        "projects": [
            {
                "technologies": "Relevant coursework: Python, SQL",
                "bullets": [
                    "Relevant coursework: see algorithms class",
                    "Shipped feature",
                    "Third",
                    "Fourth",
                ],
            }
        ],
        "skills": {
            "Languages": "Coursework: A, B, C, D",
            "Frameworks & Libraries": "f1, f2, f3, f4, f5",
            "Tools & Technologies": "t1, t2, t3, t4, t5",
        },
    }
    rt._prepare_tailor_llm_lists_for_resume(data)
    assert "coursework" not in data["projects"][0]["technologies"].lower()
    assert not data["projects"][0]["bullets"][0].lower().startswith("relevant")
    assert data["skills"]["Languages"].startswith("A, B, C, D")


def test_validate_tailor_response_rejects_eight_project_technologies() -> None:
    data = {
        "best_title": "Software Engineer",
        "projects": [
            {
                "dossier_source": "P",
                "title": "T",
                "date_range": "2024",
                "technologies": "1, 2, 3, 4, 5, 6, 7, 8",
                "bullets": ["a", "b", "c", "d"],
            }
        ],
        "skills": {
            "Languages": "Python, Go, Java, SQL",
            "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
            "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
        },
    }
    ok, reason = rt._validate_tailor_response(data, 1, [4])
    assert ok is False
    assert "technologies" in reason


def test_parse_tailor_raw_clamps_then_validates() -> None:
    raw = json.dumps(
        {
            "best_title": "Eng",
            "job_analysis": "x",
            "change_summary": ["a"],
            "projects": [
                {
                    "dossier_source": "P1",
                    "title": "T1",
                    "date_range": "2023",
                    "technologies": "t1, t2, t3, t4, t5, t6, t7, t8, t9",
                    "bullets": ["b1", "b2", "b3", "b4"],
                }
            ],
            "skills": {
                "Languages": "Python, Go, Java, SQL",
                "Frameworks & Libraries": "one, two, three, four, five, six, seven, eight, nine",
                "Tools & Technologies": "t1, t2, t3, t4, t5",
            },
        }
    )
    out, reason, _thinking = rt._parse_tailor_raw(raw, 1, [4])
    assert reason == ""
    assert out is not None
    assert rt._skill_line_item_count(out["skills"]["Frameworks & Libraries"]) == 7
    assert rt._skill_line_item_count(out["projects"][0]["technologies"]) == 7
    assert out["projects"][0]["technologies"].startswith("t1, t2, t3, t4, t5, t6, t7")


def test_clamp_role_title_to_two_words() -> None:
    assert rt.clamp_role_title_to_two_words("Software Engineer", "") == "Software Engineer"
    assert rt.clamp_role_title_to_two_words("Senior Software Engineer", "") == "Senior Software"
    assert rt.clamp_role_title_to_two_words("Jeff Tian Backend Engineer", "Jeff Tian") == "Backend Engineer"
    assert rt.clamp_role_title_to_two_words("Jeff Tian — ML Engineer", "Jeff Tian") == "ML Engineer"
    assert rt.clamp_role_title_to_two_words("  ", "") == "Resume"


def test_split_resume_header_line() -> None:
    left, right = rt._split_resume_header_line("Jeff Tian — Software Engineer")
    assert left == "Jeff Tian"
    assert right == "Software Engineer"


def test_normalize_tailor_date_range_to_hyphen_and_present() -> None:
    assert rt._normalize_tailor_date_range("June 2025 to present") == "June 2025 - Present"
    assert rt._normalize_tailor_date_range("Sept 2025 TO Present") == "Sept 2025 - Present"
    assert rt._normalize_tailor_date_range("Jan 2024 to Mar 2024") == "Jan 2024 - Mar 2024"
    assert rt._normalize_tailor_date_range("Jan 2025 – Present") == "Jan 2025 - Present"
    assert rt._normalize_tailor_date_range("48-hour hackathon") == "48-hour hackathon"
    assert rt._normalize_tailor_date_range("March 2026") == "March 2026"


def test_skill_line_item_count() -> None:
    assert rt._skill_line_item_count("a, b , c") == 3
    assert rt._skill_line_item_count("") == 0
    assert rt._skill_line_item_count("solo") == 1


def test_split_double_asterisk_segments() -> None:
    segs = rt.split_double_asterisk_segments("a **bold** c")
    assert segs == [("a ", False), ("bold", True), (" c", False)]


def test_tailor_resume_bytes_with_preview_mocked_llm(monkeypatch: pytest.MonkeyPatch, minimal_docx_path: Path) -> None:
    def fake_llm(*_a: object, **_k: object) -> tuple[dict, list, str]:
        return (
            {
                "best_title": "Backend Engineer",
                "job_analysis": "They want APIs and reliability.",
                "change_summary": ["Rewrote bullets for scale keywords."],
                "projects": [
                    {
                        "dossier_source": "Test Project Section",
                        "title": "API Platform",
                        "date_range": "2024 – Present",
                        "technologies": "Python, FastAPI, Redis",
                        "bullets": [
                            "Shipped **REST** services handling 1M req/day",
                            "Cut **latency** by 40% via caching",
                            "Owned **API** design reviews with product",
                            "Automated **deploy** checks in CI",
                        ],
                    }
                ],
                "skills": {
                    "Languages": "Python, Go, Java, TypeScript",
                    "Frameworks & Libraries": "FastAPI, gRPC, Flask, React, Pandas",
                    "Tools & Technologies": "Docker, Kubernetes, Git, PostgreSQL, Linux",
                },
            },
            [],
            "",
        )

    monkeypatch.setattr(rt, "call_tailor_llm", fake_llm)
    monkeypatch.setattr(
        rt,
        "_read_dossier",
        lambda *_a, **_k: "## Test Project Section\n\nSome dossier body.",
    )

    result, err = rt.tailor_resume_bytes_with_preview(
        minimal_docx_path,
        "Build APIs",
        "Backend Engineer",
        "Acme",
        "Jeff Tian",
        "jeff",
        settings={
            "ollama_host": "http://127.0.0.1:11434",
            "tailor_enforce_one_page": False,
        },
    )
    assert err == ""
    assert result is not None
    assert result.filename.endswith(".docx")
    assert "Jeff_Tian" in result.filename or "Jeff" in result.filename
    assert result.original["projects"][0]["title"] == "Test Project Section"
    assert result.original["projects"][0]["bullets"] == []
    assert result.tailored["projects"][0]["title"] == "API Platform"
    assert result.tailored["projects"][0]["date_range"] == "2024 - Present"
    assert result.tailored["projects"][0]["technologies"] == "Python, FastAPI, Redis"
    assert result.explanation["job_analysis"].startswith("They want")
    assert len(result.explanation["change_summary"]) == 1
    assert len(result.docx_bytes) > 100
    api = rt.tailor_result_to_api_dict(result)
    assert "docx_base64" in api
    assert api["tailored"]["best_title"] == "Backend Engineer"
    assert "ollama_metrics" in api
    assert api["ollama_metrics"]["summary"]["llm_calls"] == 0


def test_tailor_one_page_trim_invokes_compress_llm(monkeypatch: pytest.MonkeyPatch, minimal_docx_path: Path) -> None:
    """When PDF reports >1 page, compress LLM runs and final tailored JSON is updated."""
    from io import BytesIO

    from pypdf import PdfWriter

    def fake_llm(*_a: object, **_k: object) -> tuple[dict, list, str]:
        return (
            {
                "best_title": "Backend Engineer",
                "job_analysis": "They want APIs.",
                "change_summary": ["First pass."],
                "projects": [
                    {
                        "dossier_source": "Test Project Section",
                        "title": "API Platform",
                        "date_range": "2024 – Present",
                        "technologies": "Python, FastAPI, Redis",
                        "bullets": [
                            "Shipped **REST** services handling 1M req/day",
                            "Cut **latency** by 40% via caching",
                            "Owned **API** design reviews with product",
                            "Automated **deploy** checks in CI",
                        ],
                    }
                ],
                "skills": {
                    "Languages": "Python, Go, Java, TypeScript",
                    "Frameworks & Libraries": "FastAPI, gRPC, Flask, React, Pandas",
                    "Tools & Technologies": "Docker, Kubernetes, Git, PostgreSQL, Linux",
                },
            },
            [],
            "",
        )

    def _n_page_pdf(n: int) -> bytes:
        buf = BytesIO()
        w = PdfWriter()
        for _ in range(n):
            w.add_blank_page(width=72, height=72)
        w.write(buf)
        return buf.getvalue()

    pdf_seq = iter([_n_page_pdf(2), _n_page_pdf(1)])

    def fake_convert(_docx: bytes, **_kwargs: object) -> bytes:
        return next(pdf_seq)

    compress_pages: list[int] = []

    def fake_compress(
        current: dict,
        pdf_page_count: int,
        _exp: int,
        _slots: list[int],
        _settings: dict,
    ) -> tuple[dict, list]:
        compress_pages.append(pdf_page_count)
        out = copy.deepcopy(current)
        out["projects"][0]["bullets"] = [
            "Compressed **one** with same facts.",
            "Compressed **two** with same facts.",
            "Compressed **three** with same facts.",
            "Compressed **four** with same facts.",
        ]
        return out, []

    monkeypatch.setattr(rt, "call_tailor_llm", fake_llm)
    monkeypatch.setattr(rt, "_read_dossier", lambda *_a, **_k: "## Test Project Section\n\nBody.")
    monkeypatch.setattr(rt, "call_tailor_fit_one_page_llm", fake_compress)
    monkeypatch.setattr("pipeline.pdf_convert.find_soffice", lambda: "/fake/soffice")
    monkeypatch.setattr("pipeline.pdf_convert.docx_bytes_to_pdf", fake_convert)

    result, err = rt.tailor_resume_bytes_with_preview(
        minimal_docx_path,
        "Build APIs",
        "Backend Engineer",
        "Acme",
        "Jeff Tian",
        "jeff",
        settings={
            "ollama_host": "http://127.0.0.1:11434",
            "tailor_enforce_one_page": True,
            "tailor_one_page_max_trim_attempts": 3,
        },
    )
    assert err == ""
    assert result is not None
    assert compress_pages == [2]
    assert result.tailored["projects"][0]["bullets"][0].startswith("Compressed **one**")


def test_normalize_llm_project_title_strips_echoed_em_dash() -> None:
    out = rt._normalize_llm_project_title("Test Project — Cloud API", "Test Project")
    assert out == "Cloud API"


def test_normalize_llm_project_title_keeps_full_line_when_left_is_dossier() -> None:
    out = rt._normalize_llm_project_title(
        "ClashTracker — Real-Time Game Analytics Dashboard",
        "ClashTracker",
        dossier_source="ClashTracker",
    )
    assert out == "ClashTracker — Real-Time Game Analytics Dashboard"


def test_collapse_resume_title_drops_second_subtitle() -> None:
    assert (
        rt._collapse_resume_title_to_name_and_one_subtitle(
            "AutoLoot — Vision-Driven Desktop Automation Bot — OpenCV Game-Client Automation Tool",
            "AutoLoot",
        )
        == "AutoLoot — Vision-Driven Desktop Automation Bot"
    )


def test_collapse_resume_title_prefixes_dossier_when_name_omitted() -> None:
    assert (
        rt._collapse_resume_title_to_name_and_one_subtitle(
            "Vision-Driven Desktop Automation Bot — OpenCV Tool",
            "AutoLoot",
        )
        == "AutoLoot — Vision-Driven Desktop Automation Bot"
    )


def test_iter_dossier_project_headings_skips_inventory_sections() -> None:
    text = """## Personal skills
Languages: Python
## AutoLoot
x
## ClashTracker
y
"""
    assert rt.iter_dossier_project_headings(text) == ["AutoLoot", "ClashTracker"]


def test_format_dossier_project_catalog_reverse_alphabetical() -> None:
    text = """## AutoLoot
a
## ClashTracker
b
## JobRadar
c
"""
    cat = rt.format_dossier_project_catalog_for_prompt(text, 2)
    assert "reverse-alphabetical" in cat.casefold()
    assert "- JobRadar" in cat
    assert "- ClashTracker" in cat
    assert "- AutoLoot" in cat
    # Reverse-alpha order: JobRadar, ClashTracker, AutoLoot
    assert cat.index("- JobRadar") < cat.index("- ClashTracker") < cat.index("- AutoLoot")


def test_dossier_to_original_preview() -> None:
    text = """# Experience Dossier
## Clash AutoLoot
Body
## ReturnClip
More
### Boundaries — do not invent
x
"""
    prev = rt.dossier_to_original_preview(text)
    titles = [p["title"] for p in prev["projects"]]
    assert "Clash AutoLoot" in titles
    assert "ReturnClip" in titles


def test_rebuild_docx_from_edits(minimal_docx_path: Path) -> None:
    edited = {
        "best_title": "Senior Engineer",
        "projects": [
            {
                "title": "Edited Project Title",
                "date_range": "Jan 2025 – Present",
                "technologies": "Rust, Tokio",
                "bullets": [
                    "First **edited** bullet",
                    "Second line",
                    "Third line",
                    "Fourth line",
                ],
            }
        ],
        "skills": {
            "Languages": "Rust, Python, Go, SQL",
            "Frameworks & Libraries": "Tokio, Axum, FastAPI, React, Pandas, NumPy",
            "Tools & Technologies": "Docker, Git, Linux, PostgreSQL, Kubernetes",
        },
    }
    docx_bytes, filename, meta = rt.rebuild_docx_from_edits(
        edited,
        "jeff",
        "Test User",
        settings={
            "resume_template_docx": str(minimal_docx_path),
            "tailor_enforce_one_page": False,
        },
    )
    assert filename.endswith(".docx")
    assert meta["tailored"]["best_title"] == "Senior Engineer"
    assert "job_analysis" in meta["explanation"]
    assert "Senior_Engineer" in filename or "Senior" in filename
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Edited Project Title" in xml
    assert "Jan 2025" in xml
    # Minimal fixture has no dedicated tech run (title + date only); skills still apply.
    assert "Tokio, Axum" in xml
    assert "edited" in xml
    assert "Rust, Python" in xml


def test_hydrate_rebuild_data_for_one_page_trim_sets_dossier_source() -> None:
    data = {
        "projects": [
            {"title": "My Project", "technologies": "A, B", "bullets": ["x"]},
        ]
    }
    rt._hydrate_rebuild_data_for_one_page_trim(data)
    assert data["projects"][0]["dossier_source"] == "My Project"
    data2 = {
        "projects": [
            {"title": "", "dossier_source": "Existing", "technologies": "A, B", "bullets": ["x"]},
        ]
    }
    rt._hydrate_rebuild_data_for_one_page_trim(data2)
    assert data2["projects"][0]["dossier_source"] == "Existing"


def test_rebuild_docx_from_edits_runs_one_page_compress(
    monkeypatch: pytest.MonkeyPatch, minimal_docx_path: Path
) -> None:
    """Rebuild runs the same PDF + compress loop as initial tailor when PDF is multi-page."""
    from io import BytesIO

    from pypdf import PdfWriter

    edited = {
        "best_title": "Senior Engineer",
        "projects": [
            {
                "title": "Edited Project Title",
                "date_range": "Jan 2025 – Present",
                "technologies": "Rust, Tokio",
                "bullets": [
                    "First **edited** bullet",
                    "Second line",
                    "Third line",
                    "Fourth line",
                ],
            }
        ],
        "skills": {
            "Languages": "Rust, Python, Go, SQL",
            "Frameworks & Libraries": "Tokio, Axum, FastAPI, React, Pandas, NumPy",
            "Tools & Technologies": "Docker, Git, Linux, PostgreSQL, Kubernetes",
        },
    }

    def _n_page_pdf(n: int) -> bytes:
        buf = BytesIO()
        w = PdfWriter()
        for _ in range(n):
            w.add_blank_page(width=72, height=72)
        w.write(buf)
        return buf.getvalue()

    pdf_seq = iter([_n_page_pdf(2), _n_page_pdf(1)])

    def fake_convert(_docx: bytes, **_kwargs: object) -> bytes:
        return next(pdf_seq)

    compress_pages: list[int] = []

    def fake_compress(
        current: dict,
        pdf_page_count: int,
        _exp: int,
        _slots: list[int],
        _settings: dict,
    ) -> tuple[dict, list]:
        compress_pages.append(pdf_page_count)
        out = copy.deepcopy(current)
        out["projects"][0]["bullets"] = [
            "Compressed **one** line here.",
            "Compressed **two** line here.",
            "Compressed **three** line here.",
            "Compressed **four** line here.",
        ]
        return out, []

    monkeypatch.setattr(rt, "call_tailor_fit_one_page_llm", fake_compress)
    monkeypatch.setattr("pipeline.pdf_convert.find_soffice", lambda: "/fake/soffice")
    monkeypatch.setattr("pipeline.pdf_convert.docx_bytes_to_pdf", fake_convert)

    docx_bytes, _fn, meta = rt.rebuild_docx_from_edits(
        edited,
        "jeff",
        "Test User",
        settings={
            "resume_template_docx": str(minimal_docx_path),
            "tailor_enforce_one_page": True,
            "tailor_one_page_max_trim_attempts": 3,
        },
    )
    assert compress_pages == [2]
    assert meta["tailored"]["projects"][0]["bullets"][0].startswith("Compressed **one**")
    assert len(docx_bytes) > 100


def test_original_preview_from_tailor_slots() -> None:
    data = {
        "projects": [
            {"dossier_source": "Alpha", "title": "A"},
            {"dossier_source": "Beta", "title": "B"},
        ]
    }
    prev = rt.original_preview_from_tailor_slots(data)
    assert [p["title"] for p in prev["projects"]] == ["Alpha", "Beta"]


def test_call_tailor_llm_substitutes_dossier_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class FakeMsg:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeResp:
        def __init__(self, content: str) -> None:
            self.message = FakeMsg(content)

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def chat(self, model: str = "", messages: list | None = None, format: str | None = None, options: dict | None = None, **kwargs: object) -> FakeResp:
            captured["user"] = (messages or [{}, {}])[1]["content"]
            payload = {
                "best_title": "Eng",
                "job_analysis": "Analysis.",
                "change_summary": ["c1", "c2"],
                "projects": [
                    {
                        "dossier_source": "P1",
                        "title": "T1",
                        "date_range": "2023",
                        "technologies": "Py",
                        "bullets": ["b1", "b2", "b3", "b4"],
                    },
                    {
                        "dossier_source": "P2",
                        "title": "T2",
                        "date_range": "2024",
                        "technologies": "Go",
                        "bullets": ["c1", "c2", "c3", "c4"],
                    },
                ],
                "skills": {
                    "Languages": "Python, Go, Java, SQL",
                    "Frameworks & Libraries": "FastAPI, Flask, Django, React, Pandas",
                    "Tools & Technologies": "Docker, Git, PostgreSQL, Linux, Kubernetes",
                },
            }
            return FakeResp(json.dumps(payload))

    monkeypatch.setattr(rt.ollama, "Client", FakeClient)
    dossier = """## ZebraProj
Zebra details
## AppleProj
Apple details
"""
    out, runs, err = rt.call_tailor_llm(
        dossier,
        "JD text",
        "Title",
        "Co",
        {"ollama_host": "http://127.0.0.1:11434"},
        expected_projects=2,
        bullets_per_slot=[4, 4],
    )
    assert err == ""
    assert out is not None
    assert len(runs) == 1
    assert runs[0]["phase"] == "tailor"
    assert "Zebra details" in captured["user"]
    assert "4 bullets per slot" in captured["user"]
    assert "reverse-alphabetical" in captured["user"].casefold()
    assert "- ZebraProj" in captured["user"]
    assert "- AppleProj" in captured["user"]
    assert captured["user"].index("- ZebraProj") < captured["user"].index("- AppleProj")
    assert out["projects"][0]["dossier_source"] == "P1"
