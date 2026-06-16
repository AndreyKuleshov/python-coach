"""Email client — sends the confirmation link via SMTP, or logs it as a fallback.

External upstream (an SMTP server), so it lives in `clients/` per api-layers.
When SMTP is not configured (`smtp_host` empty) we log the confirmation link
through structlog instead of sending — that keeps registration/confirmation
usable and testable locally without SMTP credentials. The blocking stdlib
`smtplib` call runs via `asyncio.to_thread` so the event loop never stalls.

One class so the sender is swappable; no Protocol/ABC while there is one impl.
"""

import asyncio
import smtplib
from email.message import EmailMessage

import structlog

from python_coach.settings import Settings

log = structlog.get_logger(__name__)


class EmailClient:
    """Delivers transactional email; falls back to logging when SMTP is unset."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_confirmation(self, to_email: str, confirm_url: str) -> None:
        """Send (or log) the email-confirmation link for a freshly-registered user."""
        subject = "Confirm your python-coach account"
        body = (
            "Welcome to python-coach.\n\n"
            f"Confirm your email by opening this link:\n{confirm_url}\n\n"
            "If you did not register, you can ignore this message.\n"
        )

        # Fallback path: no SMTP host configured -> log the link so it is usable
        # locally (and grabbable by tests) without real SMTP credentials.
        if not self._settings.smtp_host:
            log.info("email.confirmation_link", to=to_email, confirm_url=confirm_url)
            return

        await asyncio.to_thread(self._send_smtp, to_email, subject, body)
        log.info("email.confirmation_sent", to=to_email)

    def _send_smtp(self, to_email: str, subject: str, body: str) -> None:
        """Blocking SMTP send (run off the event loop via asyncio.to_thread)."""
        s = self._settings
        message = EmailMessage()
        message["From"] = s.smtp_from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(s.smtp_host, s.smtp_port) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(message)
