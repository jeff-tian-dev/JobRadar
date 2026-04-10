"""Convert .docx bytes to PDF using LibreOffice (headless). Shared by pipeline and dashboard."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_MAC_SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def find_soffice() -> str | None:
    """Return path to LibreOffice ``soffice`` binary, or None if not installed.

    On macOS, prefer the binary inside ``LibreOffice.app`` so we do not rely on the
    Homebrew shim (same target, but a direct path is easier to reason about for support).
    """
    if sys.platform == "darwin" and _MAC_SOFFICE.is_file():
        return str(_MAC_SOFFICE)
    path = shutil.which("soffice")
    if path:
        return path
    if _MAC_SOFFICE.is_file():
        return str(_MAC_SOFFICE)
    return None


def _libreoffice_subprocess_env(home_dir: Path | None = None) -> dict[str, str]:
    """Environment for headless ``soffice``; avoids common macOS SIGABRT / abort-trap crashes.

    When ``home_dir`` is set, it becomes ``HOME`` for the child only so LaunchAgents,
    SSH, or daemons with a non-writable HOME still get a profile/cache tree under the
    temp job dir (and stray reads of the real ``~/Library`` are avoided).
    """
    env = os.environ.copy()
    # Required for many headless/SSH/no-WindowServer scenarios on macOS; also helps some local runs.
    env["SAL_NO_DISPLAY_CHECK"] = "1"
    # OpenCL in headless mode has triggered native aborts on some macOS + LO builds.
    env.setdefault("SAL_DISABLE_OPENCL", "1")
    if home_dir is not None:
        env["HOME"] = str(home_dir)
        # LibreOffice / bundled libs may honor XDG on some code paths.
        env["XDG_CONFIG_HOME"] = str(home_dir / ".config")
        env["XDG_CACHE_HOME"] = str(home_dir / ".cache")
    return env


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
        fake_home = td / "lo-home"
        fake_home.mkdir(parents=True, exist_ok=True)
        # Isolated profile avoids locks when another LibreOffice/GUI instance is running (common on macOS).
        lo_profile = td / ".libreoffice-profile"
        lo_profile.mkdir(parents=True, exist_ok=True)
        user_inst = lo_profile.as_uri().rstrip("/") + "/"

        docx_path = td / "document.docx"
        docx_path.write_bytes(docx_bytes)

        def _build_cmd(*, safe_mode: bool) -> list[str]:
            head = [soffice, "--headless"]
            if safe_mode:
                head.append("--safe-mode")
            # Explicitly avoid attaching to the menu-bar quick starter (common abort source on macOS).
            head.append("--quickstart=no")
            return [
                *head,
                f"-env:UserInstallation={user_inst}",
                "--norestore",
                "--nologo",
                "--nofirststartwizard",
                "--nolockcheck",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(td),
                str(docx_path),
            ]

        env = _libreoffice_subprocess_env(home_dir=fake_home)
        last_proc: subprocess.CompletedProcess[str] | None = None
        for attempt_safe in (False, True):
            cmd = _build_cmd(safe_mode=attempt_safe)
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=str(td),
                    env=env,
                )
            except subprocess.TimeoutExpired:
                logger.error("LibreOffice PDF conversion timed out")
                raise
            last_proc = proc
            sigabrt_mac = sys.platform == "darwin" and proc.returncode in (134, -6)
            if proc.returncode == 0 or not sigabrt_mac or attempt_safe:
                break
            logger.warning(
                "soffice SIGABRT (rc=%s); retrying with --safe-mode once",
                proc.returncode,
            )

        assert last_proc is not None
        proc = last_proc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            logger.error("soffice failed rc=%s: %s", proc.returncode, err[:4000])
            hint = ""
            if sys.platform == "darwin" and proc.returncode in (134, -6):
                hint = (
                    " On macOS, quit the LibreOffice GUI (including menu-bar quick starter), "
                    "update LibreOffice, open the app once from Finder to clear any gatekeeper prompt, "
                    "then retry."
                )
                if not err:
                    hint += (
                        " If stderr is empty, open Console.app and filter for soffice or soffice.bin "
                        "crash logs."
                    )
            raise RuntimeError(
                f"LibreOffice failed to convert docx to pdf (exit {proc.returncode}). "
                f"{'Details: ' + err[:1500] if err else 'No stderr/stdout.'}"
                f"{hint}"
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
