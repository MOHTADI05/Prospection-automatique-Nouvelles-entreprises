"""
config.py — Configuration centralisée du projet.
Toutes les constantes et paramètres sont définis ici.
Les secrets (tokens) sont lus depuis les variables d'environnement / .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Charger le fichier .env s'il existe
_BASE_DIR = Path(__file__).parent
load_dotenv(_BASE_DIR / ".env")


CONFIG = {
    # ── Mode d'envoi ────────────────────────────────────────────────────────
    # "email"  → envoie un email avec le PDF en PJ (gratuit, pour tester)
    # "postal" → envoie une vraie lettre physique via Maileva (production)
    "mode_envoi": os.getenv("MODE_ENVOI", "email"),

    # ── Tokens API ──────────────────────────────────────────────────────────
    # INSEE_TOKEN n'est pas nécessaire : API Recherche d'entreprises est ouverte.
    # MAILEVA_TOKEN uniquement requis quand mode_envoi = "postal"
    "maileva_token": os.getenv("MAILEVA_TOKEN"),

    # ── URLs de base ────────────────────────────────────────────────────────
    "insee_base_url":   "https://recherche-entreprises.api.gouv.fr",
    "maileva_base_url": "https://api.maileva.com/mail/v2",

    # ── Filtres de prospection ───────────────────────────────────────────────
    "departements":          ["75", "92", "93", "94"],
    "jours_retroactifs":     7,
    "nb_max_envois_par_run": 50,
    "pause_entre_envois":    2,

    # ── Identité expéditeur ──────────────────────────────────────────────────
    "expediteur_nom":      "Votre Société SAS",
    "expediteur_adresse":  "10 rue de la Paix",
    "expediteur_cp_ville": "75001 Paris",

    # ── Options courrier postal (Maileva) ────────────────────────────────────
    # ECONOMIC (~0,73€), PRIORITAIRE (~0,85€), REGISTERED (~4,50€)
    "postage_type":   "ECONOMIC",
    "color_printing": False,
    "duplex_printing": False,

    # ── SMTP — utilisé pour : mode email ET rapport hebdomadaire ─────────────
    "smtp_host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port":     int(os.getenv("SMTP_PORT", "587")),
    "smtp_user":     os.getenv("SMTP_USER"),
    "smtp_password": os.getenv("SMTP_PASSWORD"),

    # Destinataire des emails de test (un email par entreprise trouvée)
    "email_destinataire_test": os.getenv("EMAIL_DESTINATAIRE_TEST"),
    # Destinataire du rapport de run hebdomadaire (peut être le même)
    "rapport_destinataire":    os.getenv("RAPPORT_DESTINATAIRE"),

    # ── Fichiers locaux ──────────────────────────────────────────────────────
    "brochure_pdf": str(_BASE_DIR / "brochure.pdf"),
    "db_path":      str(_BASE_DIR / "prospection.db"),
    "log_path":     str(_BASE_DIR / "prospection.log"),
}


def valider_config() -> list[str]:
    """Retourne la liste des erreurs de configuration selon le mode d'envoi."""
    erreurs = []
    mode = CONFIG["mode_envoi"]

    if mode == "email":
        # Mode test digital — SMTP requis
        for var in ("smtp_user", "smtp_password"):
            if not CONFIG[var]:
                erreurs.append(
                    f"{var.upper()} manquant — requis pour mode_envoi='email'"
                )
        if not CONFIG["email_destinataire_test"]:
            erreurs.append(
                "EMAIL_DESTINATAIRE_TEST manquant — "
                "adresse email où recevoir les brochures de test"
            )

    elif mode == "postal":
        # Mode production — Maileva token requis
        if not CONFIG["maileva_token"]:
            erreurs.append(
                "MAILEVA_TOKEN manquant — requis pour mode_envoi='postal'"
            )
    else:
        erreurs.append(
            f"MODE_ENVOI invalide : '{mode}' — valeurs acceptées : 'email' | 'postal'"
        )

    if not Path(CONFIG["brochure_pdf"]).exists():
        erreurs.append(f"Brochure PDF introuvable : {CONFIG['brochure_pdf']}")

    return erreurs
