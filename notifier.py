from __future__ import annotations

import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from models import Briefing

logger = logging.getLogger(__name__)


def format_briefing_html(briefing: Briefing) -> str:
    content = briefing.content

    # Convert markdown headers
    content = re.sub(r"^### (.+)$", r"<h3>\1</h3>", content, flags=re.MULTILINE)
    content = re.sub(r"^## (.+)$", r"<h2>\1</h2>", content, flags=re.MULTILINE)
    content = re.sub(r"^# (.+)$", r"<h1>\1</h1>", content, flags=re.MULTILINE)

    # Bold
    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)

    # Italic
    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)

    # Bullet lists
    content = re.sub(r"^- (.+)$", r"<li>\1</li>", content, flags=re.MULTILINE)
    content = re.sub(r"(<li>.*?</li>(\n|$))+", _wrap_ul, content)

    # Line breaks for remaining plain text
    content = re.sub(r"\n\n", "</p><p>", content)
    content = re.sub(r"\n", "<br>", content)

    change_str = ""
    if briefing.daily_change_pct is not None:
        color = "#22c55e" if briefing.daily_change_pct >= 0 else "#ef4444"
        change_str = f' <span style="color:{color}">({briefing.daily_change_pct:+.2f}%)</span>'

    return f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 680px; margin: 0 auto; padding: 20px; color: #1a1a1a;">
    <div style="border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 20px;">
        <h1 style="margin: 0; color: #2563eb;">Portfolio Briefing</h1>
        <p style="margin: 4px 0 0; color: #666;">{briefing.date}</p>
        <p style="margin: 4px 0 0; font-size: 1.2em;">
            Portfolio Value: <strong>${briefing.portfolio_value:,.2f}</strong>{change_str}
        </p>
    </div>
    <div style="line-height: 1.6;">
        <p>{content}</p>
    </div>
    <div style="border-top: 1px solid #e5e7eb; margin-top: 24px; padding-top: 12px;
                font-size: 0.85em; color: #999;">
        {briefing.suggestion_count} trade suggestion(s) generated &middot; AI Portfolio Advisor
    </div>
</body>
</html>"""


def send_briefing(briefing: Briefing) -> bool:
    from config import EMAIL_TO, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

    if not all([SMTP_USER, SMTP_PASSWORD, EMAIL_TO]):
        logger.warning("SMTP credentials not configured, skipping email")
        return False

    html = format_briefing_html(briefing)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Portfolio Briefing — {briefing.date}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(briefing.content, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        logger.info("Briefing email sent to %s", EMAIL_TO)
        return True
    except Exception:
        logger.error("Failed to send briefing email", exc_info=True)
        return False


def _wrap_ul(match: re.Match) -> str:
    return f"<ul>{match.group(0).strip()}</ul>\n"
