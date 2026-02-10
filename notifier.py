from __future__ import annotations

import logging
import re
from typing import Optional

from models import Briefing

logger = logging.getLogger(__name__)


def format_briefing_html(briefing: Briefing) -> str:
    content = briefing.content

    # Horizontal rules
    content = re.sub(r"^-{3,}$", "<hr>", content, flags=re.MULTILINE)

    # Convert markdown headers
    content = re.sub(r"^### (.+)$", r"<h3>\1</h3>", content, flags=re.MULTILINE)
    content = re.sub(r"^## (.+)$", r"<h2>\1</h2>", content, flags=re.MULTILINE)
    content = re.sub(r"^# (.+)$", r"<h1>\1</h1>", content, flags=re.MULTILINE)

    # Bold
    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)

    # Italic
    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)

    # Bullet lists (- and • styles)
    content = re.sub(r"^[-•] (.+)$", r"<li>\1</li>", content, flags=re.MULTILINE)
    content = re.sub(r"(<li>.*?</li>(\n|$))+", _wrap_ul, content)

    # Line breaks for remaining plain text
    content = re.sub(r"\n\n", "</p><p>", content)
    content = re.sub(r"\n", "<br>", content)

    return f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 680px; margin: 0 auto; padding: 20px; color: #1a1a1a;">
    <div style="line-height: 1.6;">
        {content}
    </div>
    <div style="border-top: 1px solid #e5e7eb; margin-top: 24px; padding-top: 12px;
                font-size: 0.85em; color: #999;">
        {briefing.date} &middot; AI Portfolio Advisor
    </div>
</body>
</html>"""


def _extract_subject(briefing: Briefing) -> str:
    match = re.search(r"^#\s+(.+)$", briefing.content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return f"Portfolio Briefing — {briefing.date}"


def send_briefing(briefing: Briefing) -> bool:
    import resend

    from config import EMAIL_FROM, EMAIL_TO, RESEND_API_KEY

    if not all([RESEND_API_KEY, EMAIL_TO]):
        logger.warning("Resend credentials not configured, skipping email")
        return False

    resend.api_key = RESEND_API_KEY
    html = format_briefing_html(briefing)
    subject = _extract_subject(briefing)

    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": EMAIL_TO,
            "subject": subject,
            "html": html,
            "text": briefing.content,
        })
        logger.info("Briefing email sent to %s", EMAIL_TO)
        return True
    except Exception:
        logger.error("Failed to send briefing email", exc_info=True)
        return False


def _wrap_ul(match: re.Match) -> str:
    return f"<ul>{match.group(0).strip()}</ul>\n"
