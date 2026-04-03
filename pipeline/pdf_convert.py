"""Convert .docx bytes to PDF using LibreOffice (headless). Shared by pipeline and dashboard."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def find_soffice() -> str | None:
    """Return path to LibreOffice ``soffice`` binary, or None if not installed."""
    path = shutil.which("soffice")
    if path:
        return path
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if mac.is_file():
        return str(mac)
    return None


def _resolve_converted_pdf(out_dir: Path, docx_stem: str) -> Path | None:
    """Find PDF produced by ``soffice --convert-to`` (name is usually ``<stem>.pdf``)."""
    direct = out_dir / f"{docx_stem}.pdf"
    if direct.is_file():
        return direct
    pdfs = [p for p in out_dir.glob("*.pdf") if p.is_file()]
    if not pdfs:
        return None
    if len(pdfs) == 1:
        return pdfs[0]
    # Prefer exact stem match case-insensitively; else newest file
    stem_cf = docx_stem.casefold()
    for p in pdfs:
        if p.stem.casefold() == stem_cf:
            return p
    return max(pdfs, key=lambda p: p.stat().st_mtime)


def docx_bytes_to_pdf(docx_bytes: bytes, timeout_seconds: float = 120.0) -> bytes:
    """Convert a .docx file in memory to PDF bytes via ``soffice --headless``."""
    soffice = find_soffice()
    if not soffice:
        raise FileNotFoundError(
            "LibreOffice not found. Install with: brew install --cask libreoffice"
        )
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp).resolve()
        # Isolated profile avoids locks when another LibreOffice/GUI instance is running (common on macOS).
        lo_profile = td / ".libreoffice-profile"
        lo_profile.mkdir(parents=True, exist_ok=True)
        user_inst = lo_profile.as_uri().rstrip("/") + "/"

        docx_path = td / "document.docx"
        docx_path.write_bytes(docx_bytes)
        cmd = [
            soffice,
            "--headless",
            f"-env:UserInstallation={user_inst}",
            "--norestore",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(td),
            str(docx_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(td),
            )
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice PDF conversion timed out")
            raise
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            logger.error("soffice failed rc=%s: %s", proc.returncode, err[:4000])
            raise RuntimeError(
                f"LibreOffice failed to convert docx to pdf (exit {proc.returncode}). "
                f"{'Details: ' + err[:1500] if err else 'No stderr/stdout.'}"
            )

        pdf_path = _resolve_converted_pdf(td, docx_path.stem)
        if pdf_path is None:
            listed = sorted(p.name for p in td.iterdir())
            tail_out = (proc.stdout or "").strip()[:1500]
            tail_err = (proc.stderr or "").strip()[:1500]
            logger.error(
                "soffice rc=0 but no PDF in %s; files=%s; stdout=%r; stderr=%r",
                td,
                listed,
                tail_out,
                tail_err,
            )
            raise FileNotFoundError(
                "Expected output PDF not created by LibreOffice. "
                "Try closing other LibreOffice windows, or run: "
                "`soffice --headless --convert-to pdf:writer_pdf_Export --outdir /tmp /path/to/test.docx` "
                f"(tmpdir had: {listed})"
            )
        return pdf_path.read_bytes()
