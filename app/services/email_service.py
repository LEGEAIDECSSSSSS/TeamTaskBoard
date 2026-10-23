import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from html import escape
from urllib.parse import quote

from fastapi import BackgroundTasks

from app.config.settings import settings

logger = logging.getLogger("taskboard.email")


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class ConsoleEmailBackend:
    """Development backend: prints the message (and its links) to the server log. Also keeps an outbox for tests."""

    def __init__(self):
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        logger.warning("\n--- EMAIL to %s ---\nSubject: %s\n\n%s\n--- end email ---", message.to, message.subject, message.text)


class SmtpEmailBackend:
    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = settings.SMTP_FROM
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                if settings.SMTP_STARTTLS:
                    server.starttls()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(mime)
        except Exception:  # never let a mail failure break the request that triggered it
            logger.exception("Could not send email to %s", message.to)


_backend = SmtpEmailBackend() if settings.EMAIL_BACKEND == "smtp" else ConsoleEmailBackend()


def get_email_backend():
    return _backend


class Mailer:
    """Queues messages on FastAPI's background tasks so a slow mail server never slows a request."""

    def __init__(self, background_tasks: BackgroundTasks):
        self._background = background_tasks

    def send(self, message: EmailMessage) -> None:
        self._background.add_task(get_email_backend().send, message)

    # -- templates ---------------------------------------------------------
    def send_verification(self, name: str, email: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/verify-email?token={quote(token)}"
        self.send(
            _build(
                email,
                "Confirm your email address",
                f"Hi {name},",
                "Confirm your email address to finish setting up your TaskBoard account.",
                "Confirm email address",
                link,
                f"This link works for {settings.EMAIL_VERIFICATION_HOURS} hours. If you didn't create an account, ignore this email.",
            )
        )

    def send_password_reset(self, name: str, email: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/reset-password?token={quote(token)}"
        self.send(
            _build(
                email,
                "Reset your password",
                f"Hi {name},",
                "Use the button below to choose a new password.",
                "Choose a new password",
                link,
                f"This link works for {settings.PASSWORD_RESET_MINUTES} minutes. If you didn't ask for it, ignore this email and your password stays the same.",
            )
        )

    def send_invitation(self, email: str, inviter: str, organisation: str, role: str) -> None:
        link = f"{settings.FRONTEND_URL}/invitations?email={quote(email)}"
        self.send(
            _build(
                email,
                f"{inviter} invited you to {organisation}",
                "Hello,",
                f"{inviter} invited you to join {organisation} on TaskBoard as {role}. "
                f"Log in, or create an account with this email address ({email}), to accept.",
                "View invitation",
                link,
                "You can decline the invitation from the same page.",
            )
        )


def _build(to: str, subject: str, greeting: str, body: str, button: str, link: str, footer: str) -> EmailMessage:
    text = f"{greeting}\n\n{body}\n\n{button}: {link}\n\n{footer}\n"
    html = f"""<!doctype html><html><body style="margin:0;background:#f2f4f3;padding:32px 16px;font-family:Arial,Helvetica,sans-serif;color:#16211e">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="480" cellspacing="0" cellpadding="0" style="max-width:480px;background:#ffffff;border-radius:12px;padding:32px">
<tr><td style="font-size:20px;font-weight:700;color:#12332d;padding-bottom:20px">TaskBoard</td></tr>
<tr><td style="font-size:15px;line-height:1.6">{escape(greeting)}<br><br>{escape(body)}</td></tr>
<tr><td style="padding:24px 0"><a href="{escape(link)}" style="background:#12332d;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:600;display:inline-block">{escape(button)}</a></td></tr>
<tr><td style="font-size:13px;line-height:1.5;color:#5c6b66">{escape(footer)}<br><br>Button not working? Paste this link into your browser:<br>{escape(link)}</td></tr>
</table></td></tr></table></body></html>"""
    return EmailMessage(to=to, subject=subject, text=text, html=html)
