"""
maileva.py — Envoi de courriers postaux via l'API Maileva (La Poste).

Flux en 3 étapes pour chaque envoi :
  1. POST /mailings         → crée l'envoi (statut DRAFT), récupère mailing_id
  2. POST /mailings/{id}/documents → upload du PDF
  3. POST /mailings/{id}/submit    → déclenche impression + envoi physique

Fonction principale :
  envoyer_courrier(entreprise, pdf_path, dry_run=False) -> str  (mailing_id)
"""

import logging
import time
from pathlib import Path

import requests

from config import CONFIG

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 5  # secondes entre les tentatives


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {CONFIG['maileva_token']}",
        "Accept": "application/json",
    }


def _avec_retry(fn, *args, **kwargs):
    """
    Exécute fn(*args, **kwargs) avec jusqu'à _MAX_RETRIES tentatives.
    Lève la dernière exception si toutes les tentatives échouent.
    """
    derniere_exc = None
    for tentative in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except requests.RequestException as exc:
            derniere_exc = exc
            if tentative < _MAX_RETRIES:
                logger.warning(
                    "Tentative %d/%d échouée : %s — nouvel essai dans %ds",
                    tentative, _MAX_RETRIES, exc, _RETRY_DELAY
                )
                time.sleep(_RETRY_DELAY)
    raise derniere_exc


def _creer_mailing(entreprise: dict) -> str:
    """
    Étape 1 : crée l'envoi Maileva et retourne le mailing_id.
    """
    cfg = CONFIG
    url = f"{cfg['maileva_base_url']}/mailings"

    body = {
        "name": f"Prospection {entreprise['siret']}",
        "postage_type":    cfg["postage_type"],
        "color_printing":  cfg["color_printing"],
        "duplex_printing": cfg["duplex_printing"],
        # Expéditeur
        "sender_address_line_1": cfg["expediteur_nom"],
        "sender_address_line_2": cfg["expediteur_adresse"],
        "sender_address_line_6": cfg["expediteur_cp_ville"],
        # Destinataire
        "recipient_address_line_1": entreprise["nom"][:38],
        "recipient_address_line_2": entreprise["adresse_ligne1"][:38],
        "recipient_address_line_6": entreprise["adresse_ligne6"][:38],
    }

    def _do():
        r = requests.post(url, json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    data = _avec_retry(_do)
    mailing_id = data["id"]
    logger.debug("Mailing créé : %s (statut: %s)", mailing_id, data.get("status"))
    return mailing_id


def _uploader_pdf(mailing_id: str, pdf_path: str) -> None:
    """
    Étape 2 : upload le fichier PDF dans le mailing.
    """
    url = f"{CONFIG['maileva_base_url']}/mailings/{mailing_id}/documents"

    def _do():
        with open(pdf_path, "rb") as f:
            r = requests.post(
                url,
                headers=_headers(),
                files={"document": ("brochure.pdf", f, "application/pdf")},
                timeout=60,
            )
        r.raise_for_status()

    _avec_retry(_do)
    logger.debug("PDF uploadé pour mailing %s", mailing_id)


def _soumettre_mailing(mailing_id: str) -> dict:
    """
    Étape 3 : soumet le mailing (déclenche impression + envoi postal).
    """
    url = f"{CONFIG['maileva_base_url']}/mailings/{mailing_id}/submit"

    def _do():
        r = requests.post(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    data = _avec_retry(_do)
    logger.debug("Mailing soumis : %s (statut: %s)", mailing_id, data.get("status"))
    return data


def envoyer_courrier(
    entreprise: dict,
    pdf_path: str | None = None,
    dry_run: bool = False,
) -> str:
    """
    Envoie un courrier postal à l'entreprise via Maileva.

    Args:
        entreprise: dict normalisé issu de insee.py
                    (doit contenir: siret, nom, adresse_ligne1, adresse_ligne6)
        pdf_path:   Chemin vers le PDF de la brochure (défaut: config brochure_pdf)
        dry_run:    Si True, simule l'envoi sans appeler l'API Maileva

    Returns:
        mailing_id (str) en cas de succès

    Raises:
        FileNotFoundError: si le PDF est introuvable
        requests.HTTPError: si l'API Maileva retourne une erreur
        PermissionError: si le token Maileva est invalide
    """
    pdf_path = pdf_path or CONFIG["brochure_pdf"]

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"Brochure PDF introuvable : {pdf_path}")

    siret = entreprise["siret"]
    nom   = entreprise["nom"]

    if dry_run:
        logger.info("[DRY-RUN] Courrier simulé — SIRET: %s | %s", siret, nom)
        return f"dry_run_{siret}"

    logger.info("Envoi courrier → %s (%s)", nom, siret)

    try:
        mailing_id = _creer_mailing(entreprise)
        _uploader_pdf(mailing_id, pdf_path)
        _soumettre_mailing(mailing_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            raise PermissionError("Token Maileva invalide ou expiré (HTTP 401)") from exc
        raise

    logger.info("Courrier envoyé avec succès — mailing_id: %s | %s", mailing_id, nom)
    return mailing_id
