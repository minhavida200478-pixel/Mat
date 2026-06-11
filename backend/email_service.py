"""Transactional email via Resend.

If RESEND_API_KEY is not configured, the service runs in DEV mode: instead of
sending a real email it logs the message (the password-reset code is written to
the backend log) so the full flow is testable without a provider key. The moment
a real key is added to backend/.env, emails are sent for real.
"""
import logging
import os

import resend

logger = logging.getLogger(__name__)

FROM_EMAIL = os.environ.get("RESET_FROM_EMAIL", "onboarding@resend.dev")
APP_NAME = "Cycle"


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def is_email_configured() -> bool:
    return bool(_api_key())


def _reset_html(code: str, minutes: int) -> str:
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
                max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a;">
      <h2 style="margin:0 0 8px;">Reset your {APP_NAME} password</h2>
      <p style="color:#555;margin:0 0 20px;">
        Use the code below to reset your password. It expires in {minutes} minutes.
      </p>
      <div style="font-size:32px;font-weight:800;letter-spacing:8px;
                  background:#f4f4f5;border-radius:12px;padding:18px;text-align:center;
                  color:#0f766e;">{code}</div>
      <p style="color:#888;font-size:13px;margin-top:20px;">
        If you didn't request this, you can safely ignore this email — your password
        won't change.
      </p>
    </div>
    """


def _verify_html(code: str, minutes: int) -> str:
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
                max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a;">
      <h2 style="margin:0 0 8px;">Verify your {APP_NAME} email</h2>
      <p style="color:#555;margin:0 0 20px;">
        Welcome to {APP_NAME}! Use the code below to verify your email and finish
        setting up your account. It expires in {minutes} minutes.
      </p>
      <div style="font-size:32px;font-weight:800;letter-spacing:8px;
                  background:#f4f4f5;border-radius:12px;padding:18px;text-align:center;
                  color:#0f766e;">{code}</div>
      <p style="color:#888;font-size:13px;margin-top:20px;">
        If you didn't create a {APP_NAME} account, you can safely ignore this email.
      </p>
    </div>
    """


def send_verification_email(to_email: str, code: str, minutes: int) -> bool:
    """Send (or DEV-log) an email verification code. Never raises."""
    subject = f"{APP_NAME} email verification code: {code}"
    html = _verify_html(code, minutes)

    if not is_email_configured():
        logger.warning(
            "[EMAIL DEV MODE] RESEND_API_KEY not set. Verification code for %s: %s "
            "(expires in %d min). Add RESEND_API_KEY to backend/.env to send real emails.",
            to_email, code, minutes,
        )
        return True

    try:
        resend.api_key = _api_key()
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info("Verification email sent to %s", to_email)
        return True
    except Exception as e:  # noqa: BLE001 - never break the request flow
        logger.error("Failed to send verification email to %s: %s", to_email, e)
        return False


def send_password_reset_email(to_email: str, code: str, minutes: int) -> bool:
    """Send (or DEV-log) a password reset code. Never raises."""
    subject = f"{APP_NAME} password reset code: {code}"
    html = _reset_html(code, minutes)

    if not is_email_configured():
        logger.warning(
            "[EMAIL DEV MODE] RESEND_API_KEY not set. Password reset code for %s: %s "
            "(expires in %d min). Add RESEND_API_KEY to backend/.env to send real emails.",
            to_email, code, minutes,
        )
        return True

    try:
        resend.api_key = _api_key()
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info("Password reset email sent to %s", to_email)
        return True
    except Exception as e:  # noqa: BLE001 - never break the request flow
        logger.error("Failed to send reset email to %s: %s", to_email, e)
        return False
