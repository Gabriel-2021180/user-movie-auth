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
    # CAMBIO: Ahora recibimos 'username' como argumento
    async def send_verification_email(email_to: str, username: str, code: str):
        """
        Envía el código de verificación con diseño profesional.
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_USER
            msg['To'] = email_to
            msg['Subject'] = "Tu código de verificación - FilmStack"

            # CAMBIO: Diseño HTML profesional con colores pastel (Menta/Azul)
            body = f"""
            <html>
              <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                    
                    <h2 style="color: #0f172a; margin-top: 0;">¡Hola, <span style="color: #45d4bf;">{username}</span>! 👋</h2>
                    
                    <p style="color: #64748b; font-size: 16px; line-height: 1.5;">
                        Gracias por unirte a <strong>FilmStack</strong>. Para proteger tu cuenta, necesitamos verificar tu correo electrónico.
                    </p>
                    
                    <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; text-align: center; margin: 25px 0;">
                        <span style="display: block; font-size: 12px; text-transform: uppercase; color: #94a3b8; font-weight: bold; letter-spacing: 1px; margin-bottom: 5px;">Tu código es</span>
                        <h1 style="color: #60a5fa; letter-spacing: 8px; font-size: 36px; margin: 0; font-weight: 800;">{code}</h1>
                    </div>
                    
                    <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                        Este código expira en 10 minutos. Si no solicitaste esto, puedes ignorar este correo.
                    </p>
                    
                    <div style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 20px; text-align: center;">
                        <p style="color: #cbd5e1; font-size: 10px;">© 2025 FilmStack. Todos los derechos reservados.</p>
                    </div>
                </div>
              </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))

            # Conexión SMTP
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
            text = msg.as_string()
            server.sendmail(settings.SMTP_USER, email_to, text)
            server.quit()
            
            print(f"✅ Email enviado a {username} ({email_to})")
            return True

        except Exception as e:
            print(f"❌ Error enviando email: {e}")
            return False
        
    @staticmethod
    async def send_reset_password_email(email_to: str, username: str, code: str):
        """
        Envía el código para restablecer contraseña.
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_USER
            msg['To'] = email_to
            msg['Subject'] = "Restablecer Contraseña - FilmStack"

            # Diseño Rojo/Alerta para diferenciarlo del registro
            body = f"""
            <html>
              <body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background-color: #fff; border-radius: 10px; padding: 30px; border: 1px solid #e2e8f0;">
                    <h2 style="color: #0f172a;">Hola, {username}</h2>
                    <p style="color: #64748b;">Recibimos una solicitud para restablecer tu contraseña.</p>
                    
                    <div style="background-color: #fef2f2; border-radius: 8px; padding: 15px; text-align: center; margin: 20px 0; border: 1px solid #fee2e2;">
                        <span style="display: block; font-size: 12px; color: #ef4444; font-weight: bold; margin-bottom: 5px;">CÓDIGO DE SEGURIDAD</span>
                        <h1 style="color: #dc2626; letter-spacing: 5px; margin: 0; font-size: 32px;">{code}</h1>
                    </div>
                    
                    <p style="color: #94a3b8; font-size: 12px;">Si no fuiste tú, ignora este correo. Tu cuenta sigue segura.</p>
                </div>
              </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))

            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, email_to, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"❌ Error email reset: {e}")
            return False