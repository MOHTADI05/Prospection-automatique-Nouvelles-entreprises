"""
database.py — Gestion de l'historique des envois en SQLite.

Fonctions principales :
  - init_db()             : crée la table 'envois' si elle n'existe pas
  - deja_envoye(siret)    : vérifie si un courrier a déjà été envoyé à ce SIRET
  - enregistrer_envoi()   : enregistre un envoi (succès ou erreur)
  - stats()               : retourne des statistiques d'envoi
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager
from config import CONFIG

logger = logging.getLogger(__name__)


@contextmanager
def _connexion():
    """Gestionnaire de contexte pour la connexion SQLite."""
    conn = sqlite3.connect(CONFIG["db_path"])
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialise la base de données et crée la table 'envois' si elle n'existe pas.
    Appeler une seule fois au démarrage du script.
    """
    with _connexion() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS envois (
                siret           TEXT PRIMARY KEY,
                nom             TEXT,
                adresse         TEXT,
                date_creation   TEXT,
                date_envoi      TEXT,
                statut          TEXT
            )
        """)
    logger.info("Base de données initialisée : %s", CONFIG["db_path"])


def deja_envoye(siret: str) -> bool:
    """
    Retourne True si un courrier a déjà été envoyé avec succès à ce SIRET.
    Les entrées en statut 'erreur' sont considérées comme non envoyées
    (l'envoi peut être retentié).
    """
    with _connexion() as conn:
        row = conn.execute(
            "SELECT statut FROM envois WHERE siret = ?", (siret,)
        ).fetchone()

    if row is None:
        return False
    return row["statut"] == "envoyé"


def enregistrer_envoi(
    siret: str,
    nom: str,
    adresse: str,
    date_creation: str,
    statut: str = "envoyé",
) -> None:
    """
    Insère ou met à jour l'enregistrement d'un envoi.

    Args:
        siret:          Numéro SIRET (14 chiffres)
        nom:            Dénomination légale de l'entreprise
        adresse:        Adresse postale complète
        date_creation:  Date de création de l'établissement (YYYY-MM-DD)
        statut:         'envoyé' ou 'erreur'
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    with _connexion() as conn:
        conn.execute(
            """
            INSERT INTO envois (siret, nom, adresse, date_creation, date_envoi, statut)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(siret) DO UPDATE SET
                date_envoi = excluded.date_envoi,
                statut     = excluded.statut
            """,
            (siret, nom, adresse, date_creation, now, statut),
        )

    logger.debug("Envoi enregistré — SIRET: %s | statut: %s", siret, statut)


def stats() -> dict:
    """Retourne un dict avec les compteurs d'envois (total, succès, erreurs)."""
    with _connexion() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM envois").fetchone()[0]
        envoyes = conn.execute(
            "SELECT COUNT(*) FROM envois WHERE statut = 'envoyé'"
        ).fetchone()[0]
        erreurs = conn.execute(
            "SELECT COUNT(*) FROM envois WHERE statut = 'erreur'"
        ).fetchone()[0]

    return {"total": total, "envoyes": envoyes, "erreurs": erreurs}
