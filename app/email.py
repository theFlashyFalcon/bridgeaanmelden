import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not SMTP_HOST or not SMTP_USER:
        raise RuntimeError("SMTP niet geconfigureerd. Stel SMTP_HOST en SMTP_USER in via .env.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())


def send_invitation_email(to_email: str, invite_url: str) -> None:
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo,</p>
        <p>Je bent uitgenodigd om je aan te melden voor de <strong>Bridge Club Aanmeldingsapp</strong>.</p>
        <p>Klik op de knop hieronder om een account aan te maken:</p>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{invite_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Account aanmaken
          </a>
        </p>
        <p style="font-size: .85rem; color: #666;">Of kopieer deze link: <span style="word-break: break-all;">{invite_url}</span></p>
        <p style="font-size: .85rem; color: #666;">Deze uitnodigingslink is eenmalig te gebruiken.</p>
      </div>
    </body></html>
    """
    text_body = (
        f"Je bent uitgenodigd voor de Bridge Club Aanmeldingsapp.\n\n"
        f"Klik op de volgende link om een account aan te maken:\n{invite_url}\n\n"
        f"Deze link is eenmalig te gebruiken."
    )
    _send(to_email, "Uitnodiging Bridge Club Aanmeldingsapp", html_body, text_body)


def send_partner_request_approved_email(to_email: str, voornaam: str, event_naam: str, partner_naam: str) -> None:
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {voornaam},</p>
        <p>Je verzoek om je aan te melden voor <strong>{event_naam}</strong> samen met <strong>{partner_naam}</strong> is goedgekeurd door de wedstrijdleider.</p>
        <p>Je staat nu op de deelnemerslijst.</p>
      </div>
    </body></html>
    """
    text_body = (
        f"Hallo {voornaam},\n\n"
        f"Je verzoek om je aan te melden voor {event_naam} samen met {partner_naam} is goedgekeurd.\n\n"
        f"Je staat nu op de deelnemerslijst."
    )
    _send(to_email, f"Verzoek goedgekeurd — {event_naam}", html_body, text_body)


def send_password_reset_email(to_email: str, voornaam: str, reset_url: str) -> None:
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {voornaam},</p>
        <p>We hebben een verzoek ontvangen om je wachtwoord te resetten voor de <strong>Bridge Club Aanmeldingsapp</strong>.</p>
        <p>Klik op de knop hieronder om een nieuw wachtwoord in te stellen:</p>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{reset_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Wachtwoord resetten
          </a>
        </p>
        <p style="font-size: .85rem; color: #666;">Of kopieer deze link: <span style="word-break: break-all;">{reset_url}</span></p>
        <p style="font-size: .85rem; color: #666;">Deze link is 1 uur geldig. Heb je dit niet aangevraagd? Dan kun je deze mail negeren.</p>
      </div>
    </body></html>
    """
    text_body = (
        f"Hallo {voornaam},\n\n"
        f"Klik op de volgende link om je wachtwoord te resetten:\n{reset_url}\n\n"
        f"Deze link is 1 uur geldig. Heb je dit niet aangevraagd? Negeer dan deze mail."
    )
    _send(to_email, "Wachtwoord resetten — Bridge Club", html_body, text_body)


def send_admin_new_request_email(
    to_email: str,
    aanvrager_voornaam: str,
    aanvrager_achternaam: str,
    aanvrager_email: str,
    reden: str,
    base_url: str,
) -> None:
    beheer_url = f"{base_url}/beheer/aanvragen"
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo beheerder,</p>
        <p>Er is een nieuwe accountaanvraag binnengekomen die jouw goedkeuring vereist.</p>
        <table style="border-collapse: collapse; width: 100%; margin: 1rem 0;">
          <tr><td style="padding: .3rem .6rem; font-weight: 600;">Naam</td><td style="padding: .3rem .6rem;">{aanvrager_voornaam} {aanvrager_achternaam}</td></tr>
          <tr style="background:#f5f5f5"><td style="padding: .3rem .6rem; font-weight: 600;">E-mail</td><td style="padding: .3rem .6rem;">{aanvrager_email}</td></tr>
          <tr><td style="padding: .3rem .6rem; font-weight: 600;">Reden</td><td style="padding: .3rem .6rem;">{reden}</td></tr>
        </table>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{beheer_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Aanvraag beoordelen
          </a>
        </p>
      </div>
    </body></html>
    """
    text_body = (
        f"Nieuwe accountaanvraag van {aanvrager_voornaam} {aanvrager_achternaam} ({aanvrager_email}).\n"
        f"Reden: {reden}\n\n"
        f"Beoordeel de aanvraag op: {beheer_url}"
    )
    _send(to_email, f"Nieuwe accountaanvraag — {aanvrager_voornaam} {aanvrager_achternaam}", html_body, text_body)


def send_approval_email(to_email: str, voornaam: str, login_url: str) -> None:
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {voornaam},</p>
        <p>Je aanvraag voor de <strong>Bridge Club Aanmeldingsapp</strong> is goedgekeurd!</p>
        <p>Je kunt nu inloggen met je e-mailadres en het wachtwoord dat je hebt opgegeven bij de aanvraag.</p>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{login_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Inloggen
          </a>
        </p>
      </div>
    </body></html>
    """
    text_body = (
        f"Hallo {voornaam},\n\n"
        f"Je aanvraag voor de Bridge Club Aanmeldingsapp is goedgekeurd!\n\n"
        f"Je kunt nu inloggen met je e-mailadres en het wachtwoord dat je hebt opgegeven:\n{login_url}"
    )
    _send(to_email, "Aanvraag goedgekeurd — Bridge Club", html_body, text_body)
