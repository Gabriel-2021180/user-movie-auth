import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

class EmailService:
    @staticmethod
    def generate_code() -> str:
        """Genera un código numérico de 4 dígitos."""
        return ''.join(random.choices(string.digits, k=4))

    @staticmethod
    async def send_verification_email(email_to: str, code: str):
        """
        Envía el código de verificación usando Gmail SMTP.
        """
        try:
            # Configurar el mensaje
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_USER
            msg['To'] = email_to
            msg['Subject'] = "Código de Verificación - Movie Explorer"

            body = f"""
            <html>
              <body>
                <h2>¡Hola, Tilín! 🎬</h2>
                <p>Gracias por registrarte en Movie Explorer.</p>
                <p>Tu código de verificación es:</p>
                <h1 style="color: #EAB308; letter-spacing: 5px;">{code}</h1>
                <p>Este código expira en 10 minutos.</p>
              </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))

            # Conexión con Gmail
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls() # Encriptar la conexión
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
            # Enviar
            text = msg.as_string()
            server.sendmail(settings.SMTP_USER, email_to, text)
            server.quit()
            
            print(f"✅ Email enviado correctamente a {email_to}")
            return True

        except Exception as e:
            print(f"❌ Error enviando email: {e}")
            # No detenemos la app, pero logueamos el error
            return False