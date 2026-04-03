"""Notifications: ntfy, Slack, optional SMTP digest."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _profile_settings(settings: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profiles = settings.get("profiles") or {}
    if not isinstance(profiles, dict):
        return {}
    p = profiles.get(profile_id) or {}
    return p if isinstance(p, dict) else {}


def send_ntfy(
    topic: str,
    title: str,
    company: str,
    overall: float,
    fit: int,
    pref: int,
    comp: int,
    url: str | None,
    timeout: float = 30.0,
) -> None:
    """POST to ntfy.sh topic."""
    endpoint = f"https://ntfy.sh/{topic}"
    headers: dict[str, str] = {
        "Title": f"Job match: {overall:.0f}% — {title}",
        "Tags": "briefcase",
        "Priority": "high" if overall >= 90 else "default",
    }
    if url:
        headers["Click"] = url
    body = f"{company}\nFit: {fit} | Pref: {pref} | Comp: {comp}"
    try:
        r = httpx.post(endpoint, headers=headers, content=body, timeout=timeout)
        r.raise_for_status()
    except Exception:
        logger.exception("ntfy send failed for topic %s", topic)


def send_slack_webhook(
    webhook_url: str,
    text: str,
    timeout: float = 30.0,
) -> None:
    try:
        r = httpx.post(webhook_url, json={"text": text}, timeout=timeout)
        r.raise_for_status()
    except Exception:
        logger.exception("Slack webhook failed")


def send_smtp_digest(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    use_tls: bool = True,
    timeout: float = 60.0,
) -> None:
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception:
        logger.exception("SMTP digest failed")


def maybe_alert_listing(
    settings: dict[str, Any],
    profile_id: str,
    profile: dict[str, Any],
    title: str,
    company: str,
    overall: float,
    fit: int,
    pref: int,
    comp: int,
    source_url: str | None,
) -> None:
    """Send ntfy/Slack if configured and overall meets profile alert_threshold."""
    threshold = float(profile.get("alert_threshold", 78))
    if overall < threshold:
        return
    ps = _profile_settings(settings, profile_id)
    topic = ps.get("ntfy_topic")
    if isinstance(topic, str) and topic.strip():
        send_ntfy(topic.strip(), title, company, overall, fit, pref, comp, source_url)

    slack = ps.get("slack_webhook_url")
    if isinstance(slack, str) and slack.strip():
        text = (
            f"*Job match {overall:.0f}%* — {title} at {company}\n"
            f"Fit {fit} | Pref {pref} | Comp {comp}\n"
            f"{source_url or ''}"
        )
        send_slack_webhook(slack.strip(), text)


def send_daily_email_digest_if_enabled(
    settings: dict[str, Any],
    profile_id: str,
    lines: list[str],
) -> None:
    """If smtp_enabled and listings lines non-empty, send one email."""
    if not lines:
        return
    ps = _profile_settings(settings, profile_id)
    if not ps.get("smtp_enabled"):
        return
    host = ps.get("smtp_host")
    port = int(ps.get("smtp_port") or 587)
    user = ps.get("smtp_user")
    password = ps.get("smtp_password")
    from_addr = ps.get("smtp_from")
    to_addr = ps.get("smtp_to")
    if not all(isinstance(x, str) and x for x in (host, from_addr, to_addr)):
        logger.warning("SMTP enabled but missing host/from/to; skipping digest")
        return
    body = "High-scoring listings:\n\n" + "\n".join(lines)
    send_smtp_digest(
        str(host),
        port,
        str(user) if user else None,
        str(password) if password else None,
        str(from_addr),
        str(to_addr),
        subject=f"JobRadar digest ({profile_id})",
        body=body,
        use_tls=bool(ps.get("smtp_use_tls", True)),
    )
