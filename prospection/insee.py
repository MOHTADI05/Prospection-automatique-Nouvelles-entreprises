"""
insee.py — Récupération des entreprises via l'API Recherche d'entreprises (api.gouv.fr).

API : https://recherche-entreprises.api.gouv.fr
  - Totalement ouverte, aucun token requis
  - Limite : 7 requêtes/seconde
  - Pagination : max 25 résultats par page

Endpoint utilisé : GET /search
  Filtres appliqués :
    - departement  : codes de département ciblés
    - etat_administratif : "A" (entreprises actives uniquement)
  Filtre client-side :
    - date_creation du siège >= date_debut (N derniers jours)

Chaque dict retourné a la forme :
  {
    "siret":           "12345678900012",
    "siren":           "123456789",
    "nom":             "ACME SAS",
    "adresse_ligne1":  "10 RUE DE LA PAIX",
    "adresse_ligne6":  "75001 PARIS",
    "adresse_complete": "10 RUE DE LA PAIX, 75001 PARIS",
    "date_creation":   "2026-03-10",
    "code_naf":        "6201Z",
  }
"""

import logging
import time
from datetime import date, timedelta

import requests

from config import CONFIG

logger = logging.getLogger(__name__)

_BASE_URL   = "https://recherche-entreprises.api.gouv.fr"
_USER_AGENT = "Prospection-Automatique/1.0 (contact@votre-societe.fr)"

# Nombre max de pages à parcourir par département pour éviter des appels excessifs
# 25 résultats/page × 40 pages = 1 000 entreprises max par département par run
_MAX_PAGES = 40


def _normaliser_result(result: dict) -> dict | None:
    """
    Transforme un objet `result` de l'API Recherche d'entreprises en dict propre.
    Retourne None si les données obligatoires sont manquantes.
    """
    try:
        siege = result.get("siege", {})
        if not siege:
            return None

        siret = siege.get("siret", "").strip()
        if not siret:
            return None

        # Nom : nom_complet > nom_raison_sociale > fallback
        nom = (
            result.get("nom_raison_sociale")
            or result.get("nom_complet")
            or "ENTREPRISE INCONNUE"
        ).strip().upper()

        # Adresse : le champ `adresse` est déjà formaté par l'API
        adresse_brute = siege.get("adresse", "").strip()
        code_postal   = siege.get("code_postal", "").strip()
        libelle_ville = siege.get("libelle_commune", "").strip()

        if not code_postal or not libelle_ville:
            logger.debug("Adresse incomplète pour SIRET %s — ignoré", siret)
            return None

        # Reconstruire lignes 1 et 6 depuis l'adresse brute
        # adresse_brute = "10 RUE DE LA PAIX 75001 PARIS 1"
        # ligne6 = "{code_postal} {ville}"
        ligne6 = f"{code_postal} {libelle_ville}"
        # ligne1 = tout ce qui précède le code postal dans l'adresse brute
        idx_cp = adresse_brute.upper().find(code_postal)
        ligne1 = adresse_brute[:idx_cp].strip() if idx_cp > 0 else adresse_brute

        date_creation = siege.get("date_creation") or result.get("date_creation") or ""
        code_naf      = siege.get("activite_principale") or result.get("activite_principale") or ""

        return {
            "siret":            siret,
            "siren":            result.get("siren", ""),
            "nom":              nom,
            "adresse_ligne1":   ligne1,
            "adresse_ligne6":   ligne6,
            "adresse_complete": f"{ligne1}, {ligne6}".strip(", "),
            "date_creation":    date_creation,
            "code_naf":         code_naf,
        }

    except Exception as exc:
        logger.warning("Erreur normalisation résultat : %s", exc)
        return None


def _appel_api(params: dict) -> dict:
    """
    Effectue un appel GET /search et retourne le JSON.
    Gère les codes HTTP 400, 429, et les erreurs réseau.
    """
    url = f"{_BASE_URL}/search"
    headers = {
        "Accept":     "application/json",
        "User-Agent": _USER_AGENT,
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        logger.warning("Rate limit atteint (HTTP 429) — attente %ds", retry_after)
        time.sleep(retry_after)
        # Relancer une seule fois après la pause
        response = requests.get(url, headers=headers, params=params, timeout=30)

    if response.status_code == 400:
        logger.error("Requête invalide (HTTP 400) : %s", response.text)
        return {"results": [], "total_results": 0, "total_pages": 0}

    response.raise_for_status()
    return response.json()


def _recuperer_par_departement(
    departement: str,
    date_debut: str,
) -> list[dict]:
    """
    Récupère toutes les entreprises actives d'un département
    créées depuis date_debut, en paginant sur l'API.
    """
    entreprises: list[dict] = []
    params_base = {
        "departement":       departement,
        "etat_administratif": "A",
        "per_page":          25,
        "minimal":           "true",
        "include":           "siege",
    }

    for page in range(1, _MAX_PAGES + 1):
        params = {**params_base, "page": page}

        try:
            data = _appel_api(params)
        except requests.RequestException as exc:
            logger.error("Erreur réseau API (dep %s, page %d) : %s", departement, page, exc)
            break

        results    = data.get("results", [])
        total_pages = data.get("total_pages", 1)

        if not results:
            break

        nb_avant = len(entreprises)

        for result in results:
            normalise = _normaliser_result(result)
            if not normalise:
                continue

            # Filtre client-side : date de création dans la fenêtre
            dc = normalise.get("date_creation", "")
            if dc and dc >= date_debut:
                entreprises.append(normalise)

        logger.debug(
            "Dept %s — page %d/%d → %d nouvelles (cumul: %d)",
            departement, page, total_pages, len(entreprises) - nb_avant, len(entreprises)
        )

        # Arrêt si dernière page atteinte
        if page >= total_pages:
            break

        # Pause légère entre les pages (max 7 req/s)
        time.sleep(0.2)

    return entreprises


def recuperer_nouvelles_entreprises(
    jours: int | None = None,
    departements: list[str] | None = None,
) -> list[dict]:
    """
    Récupère les entreprises créées dans les N derniers jours pour les départements cibles.

    Utilise l'API Recherche d'entreprises (api.gouv.fr) — sans authentification.
    Le filtre par date de création est appliqué côté client.

    Args:
        jours:        Override de CONFIG['jours_retroactifs']
        departements: Override de CONFIG['departements']

    Returns:
        Liste de dicts normalisés, dédoublonnés par SIRET.
    """
    jours        = jours or CONFIG["jours_retroactifs"]
    departements = departements or CONFIG["departements"]

    date_debut = (date.today() - timedelta(days=jours)).strftime("%Y-%m-%d")

    logger.info(
        "Recherche entreprises — depuis %s | départements: %s",
        date_debut, ", ".join(departements)
    )

    toutes: dict[str, dict] = {}  # keyed by SIRET pour dédoublonner

    for dep in departements:
        logger.info("→ Traitement département %s", dep)
        resultats = _recuperer_par_departement(dep, date_debut)
        for e in resultats:
            toutes[e["siret"]] = e
        logger.info("  %d entreprises récentes trouvées (dept %s)", len(resultats), dep)

    entreprises = list(toutes.values())
    logger.info(
        "Total : %d entreprises créées depuis %s (sur %d départements)",
        len(entreprises), date_debut, len(departements)
    )
    return entreprises


def tester_connexion_insee() -> bool:
    """
    Test rapide de l'API Recherche d'entreprises (pas de token, juste un ping).
    """
    try:
        data = _appel_api({"q": "test", "per_page": 1, "page": 1})
        if "results" in data:
            logger.info("Connexion API Recherche d'entreprises : OK")
            return True
        logger.error("Réponse inattendue : %s", data)
        return False
    except Exception as exc:
        logger.error("Connexion API Recherche d'entreprises ÉCHOUÉE : %s", exc)
        return False
