import asyncio
import html
import logging
import secrets
import smtplib
import ssl
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_html(email_to: str, subject: str, body: str) -> bool:
    """Envío SMTP bloqueante (se llama desde un hilo para no frenar el event loop)."""
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_USER
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))
    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, email_to, msg.as_string())
        return True
    except Exception as e:
        # No se loguea el destinatario completo ni el código
        logger.error("Error enviando email (%s): %s", subject, type(e).__name__)
        return False


def _layout(title_html: str, intro: str, code: str, footer: str, accent: str = "#60a5fa") -> str:
    return f"""
    <html>
      <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; border: 1px solid #e2e8f0;">
            <h2 style="color: #0f172a; margin-top: 0;">{title_html}</h2>
            <p style="color: #64748b; font-size: 16px; line-height: 1.5;">{intro}</p>
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; text-align: center; margin: 25px 0;">
                <span style="display: block; font-size: 12px; text-transform: uppercase; color: #94a3b8; font-weight: bold; letter-spacing: 1px; margin-bottom: 5px;">Tu código es</span>
                <h1 style="color: {accent}; letter-spacing: 8px; font-size: 36px; margin: 0; font-weight: 800;">{code}</h1>
            </div>
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">{footer}</p>
        </div>
      </body>
    </html>
    """


class EmailService:
    @staticmethod
    def generate_code() -> str:
        """Código de 4 dígitos para v1 (generador criptográfico)."""
        return "".join(secrets.choice(string.digits) for _ in range(4))

    # --- v1 ---

    @staticmethod
    async def send_verification_email(email_to: str, username: str, code: str) -> bool:
        body = _layout(
            f'¡Hola, <span style="color: #45d4bf;">{html.escape(username)}</span>! 👋',
            "Gracias por unirte a <strong>FilmStack</strong>. Para proteger tu cuenta, necesitamos verificar tu correo electrónico.",
            code,
            "Este código expira en 10 minutos. Si no solicitaste esto, puedes ignorar este correo.",
        )
        return await asyncio.to_thread(_send_html, email_to, "Tu código de verificación - FilmStack", body)

    @staticmethod
    async def send_reset_password_email(email_to: str, username: str, code: str) -> bool:
        body = _layout(
            f"Hola, {html.escape(username)}",
            "Recibimos una solicitud para restablecer tu contraseña.",
            code,
            "Si no fuiste tú, ignora este correo. Tu cuenta sigue segura.",
            accent="#dc2626",
        )
        return await asyncio.to_thread(_send_html, email_to, "Restablecer Contraseña - FilmStack", body)

    # --- v2 ---

    @staticmethod
    async def send_signup_code(email_to: str, username: str, code: str, ttl_minutes: int) -> bool:
        body = _layout(
            f'¡Hola, <span style="color: #45d4bf;">{html.escape(username)}</span>! 👋',
            "Gracias por unirte a <strong>FilmStack</strong>. Para proteger tu cuenta, necesitamos verificar tu correo electrónico.",
            code,
            f"Este código expira en {ttl_minutes} minutos. Si no solicitaste esto, puedes ignorar este correo.",
        )
        return await asyncio.to_thread(_send_html, email_to, "Tu código de verificación - FilmStack", body)

    @staticmethod
    async def send_reset_code(email_to: str, username: str, code: str, ttl_minutes: int) -> bool:
        body = _layout(
            f"Hola, {html.escape(username)}",
            "Recibimos una solicitud para restablecer tu contraseña.",
            code,
            f"Este código expira en {ttl_minutes} minutos. Si no fuiste tú, ignora este correo: tu cuenta sigue segura.",
            accent="#dc2626",
        )
        return await asyncio.to_thread(_send_html, email_to, "Restablecer Contraseña - FilmStack", body)

    @staticmethod
    async def send_account_exists_notice(email_to: str) -> bool:
        """Se envía cuando alguien intenta registrarse con un email ya registrado
        (la API responde igual que un registro normal para no revelar qué emails existen)."""
        body = """
        <html><body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 20px;">
          <div style="max-width: 500px; margin: 0 auto; background-color: #fff; border-radius: 10px; padding: 30px; border: 1px solid #e2e8f0;">
            <h2 style="color: #0f172a;">Ya tienes una cuenta en FilmStack</h2>
            <p style="color: #64748b;">Alguien intentó registrarse con este correo. Si fuiste tú, inicia sesión o usa
            "Olvidé mi contraseña". Si no fuiste tú, puedes ignorar este mensaje.</p>
          </div>
        </body></html>
        """
        return await asyncio.to_thread(_send_html, email_to, "Intento de registro - FilmStack", body)
