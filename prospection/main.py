"""
main.py — Point d'entrée principal du script de prospection.

Usage :
  python main.py              # run normal
  python main.py --dry-run    # simule sans envoyer de courriers
  python main.py --test-connexion  # vérifie la connexion à l'API INSEE

Le script :
  1. Valide la configuration (.env, fichiers)
  2. Initialise la base SQLite
  3. Récupère les nouvelles entreprises (INSEE)
  4. Filtre celles déjà contactées (base locale)
  5. Envoie les courriers (Maileva) dans la limite du quota par run
  6. Enregistre chaque résultat dans la base
  7. Affiche un résumé et envoie un rapport email (si configuré)
"""

import argparse
import logging
import sys
import time

from config import CONFIG, valider_config
from database import init_db, deja_envoye, enregistrer_envoi, stats
from insee import recuperer_nouvelles_entreprises, tester_connexion_insee
from sender import envoyer_courrier
from rapport import envoyer_rapport_email


def _configurer_logging() -> None:
    """Configure le logging vers fichier + console simultanément."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(CONFIG["log_path"], encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prospection automatique — envoi de courriers aux nouvelles entreprises"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule l'exécution sans envoyer de courriers ni écrire en base",
    )
    parser.add_argument(
        "--test-connexion",
        action="store_true",
        help="Teste uniquement la connexion à l'API INSEE puis quitte",
    )
    return parser.parse_args()


def run(dry_run: bool = False) -> dict:
    """
    Exécution principale du script.

    Returns:
        dict avec les compteurs du run : envoyes, ignores, erreurs
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    mode = CONFIG.get("mode_envoi", "email").upper()
    logger.info(
        "Démarrage du run de prospection [mode: %s]%s",
        mode, " [DRY-RUN]" if dry_run else "",
    )

    # ── 1. Validation configuration ─────────────────────────────────────────
    erreurs_config = valider_config()
    if erreurs_config:
        for err in erreurs_config:
            logger.error("Config invalide : %s", err)
        if not dry_run:
            logger.error("Arrêt — corriger la configuration avant de continuer")
            return {"envoyes": 0, "ignores": 0, "erreurs": len(erreurs_config)}

    # ── 2. Init base de données ─────────────────────────────────────────────
    if not dry_run:
        init_db()

    # ── 3. Récupération INSEE ───────────────────────────────────────────────
    try:
        entreprises = recuperer_nouvelles_entreprises()
    except Exception as exc:
        logger.error("Impossible de récupérer les données INSEE : %s", exc)
        return {"envoyes": 0, "ignores": 0, "erreurs": 1}

    if not entreprises:
        logger.info("Aucune nouvelle entreprise trouvée — run terminé")
        return {"envoyes": 0, "ignores": 0, "erreurs": 0}

    # ── 4. Boucle d'envoi ───────────────────────────────────────────────────
    max_envois = CONFIG["nb_max_envois_par_run"]
    pause      = CONFIG["pause_entre_envois"]

    compteurs = {"envoyes": 0, "ignores": 0, "erreurs": 0}

    for entreprise in entreprises:
        if compteurs["envoyes"] >= max_envois:
            logger.info("Quota atteint (%d envois) — arrêt du run", max_envois)
            break

        siret = entreprise["siret"]

        # Vérifier l'historique (skip si déjà envoyé avec succès)
        if not dry_run and deja_envoye(siret):
            logger.debug("Doublon ignoré — SIRET: %s", siret)
            compteurs["ignores"] += 1
            continue

        try:
            envoyer_courrier(entreprise, dry_run=dry_run)

            if not dry_run:
                enregistrer_envoi(
                    siret=siret,
                    nom=entreprise["nom"],
                    adresse=entreprise["adresse_complete"],
                    date_creation=entreprise["date_creation"],
                    statut="envoyé",
                )
            compteurs["envoyes"] += 1

        except FileNotFoundError as exc:
            logger.error("PDF manquant — arrêt immédiat : %s", exc)
            return compteurs

        except PermissionError as exc:
            logger.error("Token invalide — arrêt immédiat : %s", exc)
            return compteurs

        except Exception as exc:
            logger.error("Erreur envoi SIRET %s : %s", siret, exc)
            compteurs["erreurs"] += 1

            if not dry_run:
                enregistrer_envoi(
                    siret=siret,
                    nom=entreprise["nom"],
                    adresse=entreprise["adresse_complete"],
                    date_creation=entreprise["date_creation"],
                    statut="erreur",
                )

        # Pause entre envois (rate limiting Maileva)
        if compteurs["envoyes"] < max_envois:
            time.sleep(pause)

    # ── 5. Résumé ───────────────────────────────────────────────────────────
    logger.info(
        "Run terminé — Envoyés: %d | Ignorés (doublons): %d | Erreurs: %d",
        compteurs["envoyes"], compteurs["ignores"], compteurs["erreurs"]
    )

    if not dry_run:
        s = stats()
        logger.info(
            "Historique total — %d envois réussis, %d erreurs",
            s["envoyes"], s["erreurs"]
        )
        # Rapport email (si SMTP configuré)
        try:
            envoyer_rapport_email(compteurs)
        except Exception as exc:
            logger.warning("Rapport email non envoyé : %s", exc)

    return compteurs


def main() -> None:
    _configurer_logging()
    args = _parse_args()
    logger = logging.getLogger(__name__)

    if args.test_connexion:
        ok = tester_connexion_insee()
        sys.exit(0 if ok else 1)

    result = run(dry_run=args.dry_run)
    sys.exit(1 if result["erreurs"] > 0 else 0)


if __name__ == "__main__":
    main()
