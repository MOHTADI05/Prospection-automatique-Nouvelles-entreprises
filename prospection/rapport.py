"""
rapport.py — Rapport email hebdomadaire via smtplib.

Envoie un email récapitulatif après chaque run si les variables SMTP sont configurées.
"""

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import CONFIG

logger = logging.getLogger(__name__)


def envoyer_rapport_email(compteurs: dict) -> None:
    """
    Envoie un email récapitulatif du run.

    Args:
        compteurs: dict avec clés 'envoyes', 'ignores', 'erreurs'

    Ne fait rien (et ne lève pas d'exception) si SMTP n'est pas configuré.
    """
    smtp_user   = CONFIG.get("smtp_user")
    smtp_pass   = CONFIG.get("smtp_password")
    destinataire = CONFIG.get("rapport_destinataire")

    # Si SMTP non configuré, on skip silencieusement
    if not all([smtp_user, smtp_pass, destinataire]):
        logger.debug("Rapport email non configuré — skip")
        return

    maintenant = datetime.now().strftime("%d/%m/%Y %H:%M")

    sujet = (
        f"[Prospection] Run du {maintenant} — "
        f"{compteurs['envoyes']} envoyés, {compteurs['erreurs']} erreurs"
    )

    corps = f"""\
Rapport d'exécution — Prospection automatique
=============================================
Date du run   : {maintenant}

Résultats :
  ✓ Courriers envoyés    : {compteurs['envoyes']}
  ↩ Doublons ignorés     : {compteurs['ignores']}
  ✗ Erreurs              : {compteurs['erreurs']}

Configuration actuelle :
  Départements ciblés   : {', '.join(CONFIG['departements'])}
  Fenêtre de recherche  : {CONFIG['jours_retroactifs']} jours
  Quota par run         : {CONFIG['nb_max_envois_par_run']} envois max

---
Script de prospection automatique — INSEE × Maileva
"""

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = destinataire
    msg["Subject"] = sujet
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    try:
        with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as serveur:
            serveur.ehlo()
            serveur.starttls()
            serveur.login(smtp_user, smtp_pass)
            serveur.sendmail(smtp_user, destinataire, msg.as_string())

        logger.info("Rapport email envoyé à %s", destinataire)

    except smtplib.SMTPException as exc:
        logger.warning("Impossible d'envoyer le rapport email : %s", exc)
        raise
