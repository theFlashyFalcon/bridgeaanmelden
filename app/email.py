import html as _html
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

def smtp_geconfigureerd() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not host or not user:
        raise RuntimeError("SMTP niet geconfigureerd. Stel SMTP_HOST en SMTP_USER in via .env.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, to_email, msg.as_string())


def send_invitation_email(to_email: str, invite_url: str) -> None:
    _invite_url = _html.escape(invite_url)
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
          <a href="{_invite_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Account aanmaken
          </a>
        </p>
        <p style="font-size: .85rem; color: #666;">Of kopieer deze link: <span style="word-break: break-all;">{_invite_url}</span></p>
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
    _voornaam = _html.escape(voornaam)
    _event_naam = _html.escape(event_naam)
    _partner_naam = _html.escape(partner_naam)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {_voornaam},</p>
        <p>Je verzoek om je aan te melden voor <strong>{_event_naam}</strong> samen met <strong>{_partner_naam}</strong> is goedgekeurd door de wedstrijdleider.</p>
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
    _voornaam = _html.escape(voornaam)
    _reset_url = _html.escape(reset_url)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {_voornaam},</p>
        <p>We hebben een verzoek ontvangen om je wachtwoord te resetten voor de <strong>Bridge Club Aanmeldingsapp</strong>.</p>
        <p>Klik op de knop hieronder om een nieuw wachtwoord in te stellen:</p>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{_reset_url}"
             style="background: #2e6da4; color: #fff; padding: .75rem 1.5rem; border-radius: 8px;
                    text-decoration: none; font-weight: 600; display: inline-block;">
            Wachtwoord resetten
          </a>
        </p>
        <p style="font-size: .85rem; color: #666;">Of kopieer deze link: <span style="word-break: break-all;">{_reset_url}</span></p>
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
    _voornaam = _html.escape(aanvrager_voornaam)
    _achternaam = _html.escape(aanvrager_achternaam)
    _email = _html.escape(aanvrager_email)
    _reden = _html.escape(reden)
    _beheer_url = _html.escape(beheer_url)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo beheerder,</p>
        <p>Er is een nieuwe accountaanvraag binnengekomen die jouw goedkeuring vereist.</p>
        <table style="border-collapse: collapse; width: 100%; margin: 1rem 0;">
          <tr><td style="padding: .3rem .6rem; font-weight: 600;">Naam</td><td style="padding: .3rem .6rem;">{_voornaam} {_achternaam}</td></tr>
          <tr style="background:#f5f5f5"><td style="padding: .3rem .6rem; font-weight: 600;">E-mail</td><td style="padding: .3rem .6rem;">{_email}</td></tr>
          <tr><td style="padding: .3rem .6rem; font-weight: 600;">Reden</td><td style="padding: .3rem .6rem;">{_reden}</td></tr>
        </table>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{_beheer_url}"
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


def send_afmelding_wedstrijdleider_email(
    to_email: str,
    wedstrijdleider_voornaam: str,
    lid_naam: str,
    event_naam: str,
    event_datum,
) -> None:
    datum_str = event_datum.strftime("%d-%m-%Y") if hasattr(event_datum, "strftime") else str(event_datum)
    _wl_voornaam = _html.escape(wedstrijdleider_voornaam)
    _lid_naam = _html.escape(lid_naam)
    _event_naam = _html.escape(event_naam)
    _datum_str = _html.escape(datum_str)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {_wl_voornaam},</p>
        <p><strong>{_lid_naam}</strong> heeft zich afgemeld voor <strong>{_event_naam}</strong> op <strong>{_datum_str}</strong>.</p>
      </div>
    </body></html>
    """
    text_body = (
        f"Hallo {wedstrijdleider_voornaam},\n\n"
        f"{lid_naam} heeft zich afgemeld voor {event_naam} op {datum_str}."
    )
    _send(to_email, f"Afmelding {lid_naam} — {event_naam}", html_body, text_body)


def send_bulk_afmelding_wedstrijdleider_email(
    to_email: str,
    wedstrijdleider_voornaam: str,
    lid_naam: str,
    events: list,
) -> None:
    rijen = "".join(
        f"<tr{'  style=\"background:#f5f5f5\"' if i % 2 else ''}>"
        f"<td style='padding:.3rem .6rem;'>{_html.escape(naam)}</td>"
        f"<td style='padding:.3rem .6rem;'>{_html.escape(datum.strftime('%d-%m-%Y') if hasattr(datum, 'strftime') else str(datum))}</td>"
        f"</tr>"
        for i, (naam, datum) in enumerate(events)
    )
    events_text = "\n".join(
        f"- {naam} ({datum.strftime('%d-%m-%Y') if hasattr(datum, 'strftime') else datum})"
        for naam, datum in events
    )
    _wl_voornaam = _html.escape(wedstrijdleider_voornaam)
    _lid_naam = _html.escape(lid_naam)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {_wl_voornaam},</p>
        <p><strong>{_lid_naam}</strong> heeft zich afgemeld voor de volgende {len(events)} evenement(en):</p>
        <table style="border-collapse: collapse; width: 100%; margin: 1rem 0;">
          <thead><tr>
            <th style="padding:.3rem .6rem; text-align:left;">Evenement</th>
            <th style="padding:.3rem .6rem; text-align:left;">Datum</th>
          </tr></thead>
          <tbody>{rijen}</tbody>
        </table>
      </div>
    </body></html>
    """
    text_body = (
        f"Hallo {wedstrijdleider_voornaam},\n\n"
        f"{lid_naam} heeft zich afgemeld voor de volgende {len(events)} evenement(en):\n{events_text}"
    )
    _send(to_email, f"Bulk afmelding {lid_naam} ({len(events)} evenementen)", html_body, text_body)


def send_approval_email(to_email: str, voornaam: str, login_url: str) -> None:
    _voornaam = _html.escape(voornaam)
    _login_url = _html.escape(login_url)
    html_body = f"""
    <html><body style="font-family: system-ui, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto;">
      <div style="background: #1e3a5f; padding: 1rem 1.5rem; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 1.3rem;">&#9824; Bridge Club</h1>
      </div>
      <div style="background: #fff; padding: 1.5rem; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
        <p>Hallo {_voornaam},</p>
        <p>Je aanvraag voor de <strong>Bridge Club Aanmeldingsapp</strong> is goedgekeurd!</p>
        <p>Je kunt nu inloggen met je e-mailadres en het wachtwoord dat je hebt opgegeven bij de aanvraag.</p>
        <p style="text-align: center; margin: 1.5rem 0;">
          <a href="{_login_url}"
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
