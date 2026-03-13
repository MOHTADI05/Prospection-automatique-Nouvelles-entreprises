"""
sender.py — Envoi de la brochure aux nouvelles entreprises.

Deux modes contrôlés par CONFIG['mode_envoi'] :

  "email"  (défaut / phase de test) ─────────────────────────────────────────
    Envoie un email avec le PDF en pièce jointe vers EMAIL_DESTINATAIRE_TEST.
    Gratuit, instantané, aucun service tiers payant requis.
    Chaque email représente ce qui serait une vraie lettre en production.

  "postal" (production) ──────────────────────────────────────────────────────
    Envoie une vraie lettre physique via l'API Maileva (La Poste).
    Nécessite MAILEVA_TOKEN et un compte Maileva crédité.

Interface unique (identique dans les deux modes) :
  envoyer_courrier(entreprise, pdf_path, dry_run) -> str (identifiant d'envoi)
"""

import logging
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

from config import CONFIG

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 5


# ── Helpers communs ──────────────────────────────────────────────────────────

def _verifier_pdf(pdf_path: str) -> None:
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"Brochure PDF introuvable : {pdf_path}")


def _avec_retry(fn, *args, **kwargs):
    derniere_exc = None
    for tentative in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except requests.RequestException as exc:
            derniere_exc = exc
            if tentative < _MAX_RETRIES:
                logger.warning(
                    "Tentative %d/%d échouée : %s — nouvel essai dans %ds",
                    tentative, _MAX_RETRIES, exc, _RETRY_DELAY,
                )
                time.sleep(_RETRY_DELAY)
    raise derniere_exc


# ── Mode EMAIL ───────────────────────────────────────────────────────────────

def _envoyer_email(entreprise: dict, pdf_path: str) -> str:
    """
    Envoie un email (SMTP) avec la brochure en pièce jointe.
    Destinataire : EMAIL_DESTINATAIRE_TEST (votre propre boîte pour tester).
    Retourne un identifiant de type 'email_<siret>'.
    """
    smtp_user    = CONFIG["smtp_user"]
    smtp_pass    = CONFIG["smtp_password"]
    destinataire = CONFIG.get("email_destinataire_test") or CONFIG.get("rapport_destinataire")

    if not all([smtp_user, smtp_pass, destinataire]):
        raise EnvironmentError(
            "Variables SMTP manquantes pour le mode email — "
            "définir SMTP_USER, SMTP_PASSWORD et EMAIL_DESTINATAIRE_TEST dans .env"
        )

    siret = entreprise["siret"]
    nom   = entreprise["nom"]

    sujet = f"[PROSPECTION TEST] Brochure → {nom} ({siret})"

    corps = f"""\
Ceci est un envoi de TEST (mode digital).
En production, ce message serait une lettre physique envoyée par La Poste.

─────────────────────────────────────────
DESTINATAIRE (futur courrier physique)
─────────────────────────────────────────
Société     : {nom}
SIRET       : {siret}
Adresse     : {entreprise.get('adresse_ligne1', '')}
              {entreprise.get('adresse_ligne6', '')}
Créée le    : {entreprise.get('date_creation', 'inconnue')}
Code NAF    : {entreprise.get('code_naf', 'inconnu')}

─────────────────────────────────────────
EXPÉDITEUR
─────────────────────────────────────────
{CONFIG['expediteur_nom']}
{CONFIG['expediteur_adresse']}
{CONFIG['expediteur_cp_ville']}

La brochure PDF est en pièce jointe.
─────────────────────────────────────────
"""

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = destinataire
    msg["Subject"] = sujet
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    # Attacher le PDF
    with open(pdf_path, "rb") as f:
        pdf_part = MIMEApplication(f.read(), _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition", "attachment", filename="brochure.pdf"
        )
        msg.attach(pdf_part)

    with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as serveur:
        serveur.ehlo()
        serveur.starttls()
        serveur.login(smtp_user, smtp_pass)
        serveur.sendmail(smtp_user, destinataire, msg.as_string())

    identifiant = f"email_{siret}"
    logger.info("Email envoyé → %s (%s) | id: %s", nom, siret, identifiant)
    return identifiant


# ── Mode POSTAL (Maileva) ────────────────────────────────────────────────────

def _maileva_headers() -> dict:
    return {
        "Authorization": f"Bearer {CONFIG['maileva_token']}",
        "Accept": "application/json",
    }


def _creer_mailing(entreprise: dict) -> str:
    url  = f"{CONFIG['maileva_base_url']}/mailings"
    body = {
        "name":            f"Prospection {entreprise['siret']}",
        "postage_type":    CONFIG["postage_type"],
        "color_printing":  CONFIG["color_printing"],
        "duplex_printing": CONFIG["duplex_printing"],
        "sender_address_line_1": CONFIG["expediteur_nom"],
        "sender_address_line_2": CONFIG["expediteur_adresse"],
        "sender_address_line_6": CONFIG["expediteur_cp_ville"],
        "recipient_address_line_1": entreprise["nom"][:38],
        "recipient_address_line_2": entreprise["adresse_ligne1"][:38],
        "recipient_address_line_6": entreprise["adresse_ligne6"][:38],
    }

    def _do():
        r = requests.post(url, json=body, headers=_maileva_headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    data = _avec_retry(_do)
    return data["id"]


def _uploader_pdf(mailing_id: str, pdf_path: str) -> None:
    url = f"{CONFIG['maileva_base_url']}/mailings/{mailing_id}/documents"

    def _do():
        with open(pdf_path, "rb") as f:
            r = requests.post(
                url,
                headers=_maileva_headers(),
                files={"document": ("brochure.pdf", f, "application/pdf")},
                timeout=60,
            )
        r.raise_for_status()

    _avec_retry(_do)


def _soumettre_mailing(mailing_id: str) -> None:
    url = f"{CONFIG['maileva_base_url']}/mailings/{mailing_id}/submit"

    def _do():
        r = requests.post(url, headers=_maileva_headers(), timeout=30)
        r.raise_for_status()

    _avec_retry(_do)


def _envoyer_postal(entreprise: dict, pdf_path: str) -> str:
    """
    Envoie une lettre physique via Maileva (La Poste).
    Nécessite MAILEVA_TOKEN et un compte crédité.
    """
    if not CONFIG.get("maileva_token"):
        raise EnvironmentError(
            "MAILEVA_TOKEN manquant — nécessaire pour le mode postal"
        )

    try:
        mailing_id = _creer_mailing(entreprise)
        _uploader_pdf(mailing_id, pdf_path)
        _soumettre_mailing(mailing_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            raise PermissionError("Token Maileva invalide ou expiré (HTTP 401)") from exc
        raise

    logger.info(
        "Courrier postal envoyé → %s (%s) | mailing_id: %s",
        entreprise["nom"], entreprise["siret"], mailing_id,
    )
    return mailing_id


# ── Point d'entrée unique ────────────────────────────────────────────────────

def envoyer_courrier(
    entreprise: dict,
    pdf_path: str | None = None,
    dry_run: bool = False,
) -> str:
    """
    Envoie la brochure à une entreprise (email ou lettre physique selon config).

    Args:
        entreprise: dict normalisé depuis insee.py
                    (siret, nom, adresse_ligne1, adresse_ligne6, ...)
        pdf_path:   Chemin vers le PDF de la brochure (défaut: config brochure_pdf)
        dry_run:    Si True, simule sans envoyer ni appeler aucune API

    Returns:
        Identifiant de l'envoi (str)

    Config :
        CONFIG['mode_envoi'] = "email"   → envoi par email SMTP (test)
        CONFIG['mode_envoi'] = "postal"  → envoi par lettre Maileva (production)
    """
    pdf_path = pdf_path or CONFIG["brochure_pdf"]
    mode     = CONFIG.get("mode_envoi", "email")
    siret    = entreprise["siret"]
    nom      = entreprise["nom"]

    _verifier_pdf(pdf_path)

    if dry_run:
        logger.info(
            "[DRY-RUN][%s] Envoi simulé → %s (%s)", mode.upper(), nom, siret
        )
        return f"dry_run_{siret}"

    if mode == "email":
        return _envoyer_email(entreprise, pdf_path)
    elif mode == "postal":
        return _envoyer_postal(entreprise, pdf_path)
    else:
        raise ValueError(
            f"mode_envoi invalide : '{mode}' — valeurs acceptées : 'email' | 'postal'"
        )
