from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

# Email
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# Database
DB_PATH = os.getenv("DB_PATH", "portfolio.db")
