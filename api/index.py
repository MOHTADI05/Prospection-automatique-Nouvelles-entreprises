"""
api/index.py — FastAPI backend for Vercel deployment.

Endpoints:
  GET  /api/health         → ping / connexion check
  GET  /api/entreprises    → search companies with filters
  GET  /api/stats          → DB statistics (history)
  GET  /api/departements   → list of French departments
  GET  /api/sections_naf   → list of NAF sections
"""

import os
import time
from datetime import date, timedelta
from typing import Optional

import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# ── Paths ────────────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))   # api/
_ROOT   = os.path.dirname(_HERE)                        # project root
_PUBLIC = os.path.join(_ROOT, "public")

# Pre-load HTML at startup so FileSystem issues surface immediately at build time
_HTML_CONTENT: str = ""
_html_path = os.path.join(_PUBLIC, "index.html")
if os.path.exists(_html_path):
    with open(_html_path, encoding="utf-8") as _f:
        _HTML_CONTENT = _f.read()
else:
    _HTML_CONTENT = (
        "<!DOCTYPE html><html><body>"
        "<h2>Frontend not bundled.</h2>"
        "<p>Check includeFiles in vercel.json</p>"
        "<p>API docs: <a href='/docs'>/docs</a></p>"
        "</body></html>"
    )

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Prospection Automatique API",
    description="Recherche d'entreprises nouvellement créées via l'API Recherche d'entreprises (api.gouv.fr)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Serve frontend ────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    """Serve the single-page frontend (HTML pre-loaded at startup)."""
    return HTMLResponse(_HTML_CONTENT)

_API_BASE = "https://recherche-entreprises.api.gouv.fr"
_USER_AGENT = "Prospection-Automatique/1.0"

# ── Static data ──────────────────────────────────────────────────────────────

SECTIONS_NAF = [
    {"code": "A", "label": "Agriculture, sylviculture et pêche"},
    {"code": "B", "label": "Industries extractives"},
    {"code": "C", "label": "Industrie manufacturière"},
    {"code": "D", "label": "Électricité, gaz, vapeur"},
    {"code": "E", "label": "Eau, assainissement, déchets"},
    {"code": "F", "label": "Construction"},
    {"code": "G", "label": "Commerce, réparation automobiles"},
    {"code": "H", "label": "Transports et entreposage"},
    {"code": "I", "label": "Hébergement et restauration"},
    {"code": "J", "label": "Information et communication"},
    {"code": "K", "label": "Activités financières et d'assurance"},
    {"code": "L", "label": "Activités immobilières"},
    {"code": "M", "label": "Activités spécialisées, scientifiques et techniques"},
    {"code": "N", "label": "Services administratifs et de soutien"},
    {"code": "O", "label": "Administration publique"},
    {"code": "P", "label": "Enseignement"},
    {"code": "Q", "label": "Santé humaine et action sociale"},
    {"code": "R", "label": "Arts, spectacles et activités récréatives"},
    {"code": "S", "label": "Autres activités de services"},
    {"code": "T", "label": "Activités des ménages"},
    {"code": "U", "label": "Activités extra-territoriales"},
]

DEPARTEMENTS = [
    {"code": "01", "label": "Ain"}, {"code": "02", "label": "Aisne"},
    {"code": "03", "label": "Allier"}, {"code": "04", "label": "Alpes-de-Haute-Provence"},
    {"code": "05", "label": "Hautes-Alpes"}, {"code": "06", "label": "Alpes-Maritimes"},
    {"code": "07", "label": "Ardèche"}, {"code": "08", "label": "Ardennes"},
    {"code": "09", "label": "Ariège"}, {"code": "10", "label": "Aube"},
    {"code": "11", "label": "Aude"}, {"code": "12", "label": "Aveyron"},
    {"code": "13", "label": "Bouches-du-Rhône"}, {"code": "14", "label": "Calvados"},
    {"code": "15", "label": "Cantal"}, {"code": "16", "label": "Charente"},
    {"code": "17", "label": "Charente-Maritime"}, {"code": "18", "label": "Cher"},
    {"code": "19", "label": "Corrèze"}, {"code": "2A", "label": "Corse-du-Sud"},
    {"code": "2B", "label": "Haute-Corse"}, {"code": "21", "label": "Côte-d'Or"},
    {"code": "22", "label": "Côtes-d'Armor"}, {"code": "23", "label": "Creuse"},
    {"code": "24", "label": "Dordogne"}, {"code": "25", "label": "Doubs"},
    {"code": "26", "label": "Drôme"}, {"code": "27", "label": "Eure"},
    {"code": "28", "label": "Eure-et-Loir"}, {"code": "29", "label": "Finistère"},
    {"code": "30", "label": "Gard"}, {"code": "31", "label": "Haute-Garonne"},
    {"code": "32", "label": "Gers"}, {"code": "33", "label": "Gironde"},
    {"code": "34", "label": "Hérault"}, {"code": "35", "label": "Ille-et-Vilaine"},
    {"code": "36", "label": "Indre"}, {"code": "37", "label": "Indre-et-Loire"},
    {"code": "38", "label": "Isère"}, {"code": "39", "label": "Jura"},
    {"code": "40", "label": "Landes"}, {"code": "41", "label": "Loir-et-Cher"},
    {"code": "42", "label": "Loire"}, {"code": "43", "label": "Haute-Loire"},
    {"code": "44", "label": "Loire-Atlantique"}, {"code": "45", "label": "Loiret"},
    {"code": "46", "label": "Lot"}, {"code": "47", "label": "Lot-et-Garonne"},
    {"code": "48", "label": "Lozère"}, {"code": "49", "label": "Maine-et-Loire"},
    {"code": "50", "label": "Manche"}, {"code": "51", "label": "Marne"},
    {"code": "52", "label": "Haute-Marne"}, {"code": "53", "label": "Mayenne"},
    {"code": "54", "label": "Meurthe-et-Moselle"}, {"code": "55", "label": "Meuse"},
    {"code": "56", "label": "Morbihan"}, {"code": "57", "label": "Moselle"},
    {"code": "58", "label": "Nièvre"}, {"code": "59", "label": "Nord"},
    {"code": "60", "label": "Oise"}, {"code": "61", "label": "Orne"},
    {"code": "62", "label": "Pas-de-Calais"}, {"code": "63", "label": "Puy-de-Dôme"},
    {"code": "64", "label": "Pyrénées-Atlantiques"}, {"code": "65", "label": "Hautes-Pyrénées"},
    {"code": "66", "label": "Pyrénées-Orientales"}, {"code": "67", "label": "Bas-Rhin"},
    {"code": "68", "label": "Haut-Rhin"}, {"code": "69", "label": "Rhône"},
    {"code": "70", "label": "Haute-Saône"}, {"code": "71", "label": "Saône-et-Loire"},
    {"code": "72", "label": "Sarthe"}, {"code": "73", "label": "Savoie"},
    {"code": "74", "label": "Haute-Savoie"}, {"code": "75", "label": "Paris"},
    {"code": "76", "label": "Seine-Maritime"}, {"code": "77", "label": "Seine-et-Marne"},
    {"code": "78", "label": "Yvelines"}, {"code": "79", "label": "Deux-Sèvres"},
    {"code": "80", "label": "Somme"}, {"code": "81", "label": "Tarn"},
    {"code": "82", "label": "Tarn-et-Garonne"}, {"code": "83", "label": "Var"},
    {"code": "84", "label": "Vaucluse"}, {"code": "85", "label": "Vendée"},
    {"code": "86", "label": "Vienne"}, {"code": "87", "label": "Haute-Vienne"},
    {"code": "88", "label": "Vosges"}, {"code": "89", "label": "Yonne"},
    {"code": "90", "label": "Territoire de Belfort"}, {"code": "91", "label": "Essonne"},
    {"code": "92", "label": "Hauts-de-Seine"}, {"code": "93", "label": "Seine-Saint-Denis"},
    {"code": "94", "label": "Val-de-Marne"}, {"code": "95", "label": "Val-d'Oise"},
    {"code": "971", "label": "Guadeloupe"}, {"code": "972", "label": "Martinique"},
    {"code": "973", "label": "Guyane"}, {"code": "974", "label": "La Réunion"},
    {"code": "976", "label": "Mayotte"},
]

TRANCHES_EFFECTIF = [
    {"code": "NN", "label": "Non renseigné"},
    {"code": "00", "label": "0 salarié"},
    {"code": "01", "label": "1 à 2 salariés"},
    {"code": "02", "label": "3 à 5 salariés"},
    {"code": "03", "label": "6 à 9 salariés"},
    {"code": "11", "label": "10 à 19 salariés"},
    {"code": "12", "label": "20 à 49 salariés"},
    {"code": "21", "label": "50 à 99 salariés"},
    {"code": "22", "label": "100 à 199 salariés"},
    {"code": "31", "label": "200 à 249 salariés"},
    {"code": "32", "label": "250 à 499 salariés"},
    {"code": "41", "label": "500 à 999 salariés"},
    {"code": "42", "label": "1 000 à 1 999 salariés"},
    {"code": "51", "label": "2 000 à 4 999 salariés"},
    {"code": "52", "label": "5 000 à 9 999 salariés"},
    {"code": "53", "label": "10 000 salariés et plus"},
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normaliser(result: dict, date_debut: str | None = None) -> dict | None:
    """Normalise un résultat brut de l'API Recherche d'entreprises."""
    siege = result.get("siege", {})
    if not siege:
        return None

    siret = siege.get("siret", "").strip()
    if not siret:
        return None

    # date_creation de l'UNITÉ LÉGALE (entité juridique) — c'est ce qui nous intéresse
    date_creation = result.get("date_creation") or siege.get("date_creation") or ""

    # Filtre date côté client (si date_debut fourni)
    if date_debut and date_creation and date_creation < date_debut:
        return None

    cp    = siege.get("code_postal", "") or ""
    ville = siege.get("libelle_commune", "") or ""
    ligne6 = f"{cp} {ville}".strip()

    # Adresse ligne 1 : extraire depuis siege.adresse en retirant la partie CP+ville
    adresse_brute = siege.get("adresse", "").strip()
    if cp and cp in adresse_brute:
        idx = adresse_brute.index(cp)
        ligne1 = adresse_brute[:idx].strip()
    else:
        ligne1 = adresse_brute

    return {
        "siret":          siret,
        "siren":          result.get("siren", ""),
        "nom":            (result.get("nom_raison_sociale") or result.get("nom_complet") or "").strip().upper(),
        "adresse_ligne1": ligne1,
        "adresse_ligne6": ligne6,
        "adresse":        adresse_brute,  # use the pre-formatted full address from API
        "date_creation":  date_creation,
        "code_naf":       siege.get("activite_principale") or result.get("activite_principale") or "",
        "section_naf":    result.get("section_activite_principale", ""),
        "categorie":      result.get("categorie_entreprise", ""),
        "departement":    siege.get("departement", ""),
        "nb_etablissements": result.get("nombre_etablissements_ouverts", 1),
        "est_ei":         (result.get("complements") or {}).get("est_entrepreneur_individuel", False),
        "est_ess":        (result.get("complements") or {}).get("est_ess", False),
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    try:
        r = requests.get(
            f"{_API_BASE}/search",
            params={"q": "test", "per_page": 1},
            headers={"User-Agent": _USER_AGENT},
            timeout=5,
        )
        api_ok = r.status_code == 200
    except Exception:
        api_ok = False
    return {"status": "ok", "api_insee": api_ok}


@app.get("/api/departements")
def get_departements():
    return DEPARTEMENTS


@app.get("/api/sections_naf")
def get_sections_naf():
    return SECTIONS_NAF


@app.get("/api/tranches_effectif")
def get_tranches_effectif():
    return TRANCHES_EFFECTIF


@app.get("/api/entreprises")
def get_entreprises(
    departements: str = Query(default="75,92,93,94", description="Codes département séparés par virgules"),
    jours: int = Query(default=7, ge=0, le=90, description="Entreprises créées dans les N derniers jours (0 = pas de filtre date)"),
    section_naf: Optional[str] = Query(default=None, description="Section NAF (A-U)"),
    code_naf: Optional[str] = Query(default=None, description="Code(s) NAF (ex: 6201Z,6202A)"),
    categorie: Optional[str] = Query(default=None, description="PME, ETI ou GE"),
    tranche_effectif: Optional[str] = Query(default=None, description="Tranche effectif salarié"),
    est_ei: Optional[bool] = Query(default=None, description="Uniquement entrepreneurs individuels"),
    est_ess: Optional[bool] = Query(default=None, description="Uniquement entreprises ESS"),
    per_page: int = Query(default=25, ge=1, le=25, description="Résultats par page (max 25)"),
    page: int = Query(default=1, ge=1, description="Numéro de page"),
):
    # jours=0 means no date filter (show all active companies)
    date_debut = (date.today() - timedelta(days=jours)).strftime("%Y-%m-%d") if jours > 0 else None

    deps = [d.strip() for d in departements.split(",") if d.strip()]
    if not deps:
        raise HTTPException(status_code=400, detail="Au moins un département requis")

    all_results = []
    errors = []

    for dep in deps:
        params: dict = {
            "departement":        dep,
            "etat_administratif": "A",
            "per_page":           per_page,
            "page":               page,
            "minimal":            "true",
            "include":            "siege,complements",
        }
        if section_naf:
            params["section_activite_principale"] = section_naf
        if code_naf:
            params["activite_principale"] = code_naf
        if categorie:
            params["categorie_entreprise"] = categorie
        if tranche_effectif:
            params["tranche_effectif_salarie"] = tranche_effectif
        if est_ei is not None:
            params["est_entrepreneur_individuel"] = str(est_ei).lower()
        if est_ess is not None:
            params["est_ess"] = str(est_ess).lower()

        try:
            t0 = time.time()
            r = requests.get(
                f"{_API_BASE}/search",
                params=params,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=15,
            )
            elapsed = round(time.time() - t0, 2)

            if r.status_code == 429:
                errors.append(f"Département {dep} : rate limit — réessayez dans quelques secondes")
                continue
            r.raise_for_status()
            data = r.json()

        except requests.RequestException as exc:
            errors.append(f"Département {dep} : erreur réseau ({exc})")
            continue

        for res in data.get("results", []):
            normalise = _normaliser(res, date_debut)
            if normalise:
                all_results.append(normalise)

    # Dédoublonner par SIRET
    seen = set()
    unique = []
    for e in all_results:
        if e["siret"] not in seen:
            seen.add(e["siret"])
            unique.append(e)

    # Trier par date de création décroissante
    unique.sort(key=lambda x: x["date_creation"] or "", reverse=True)

    return {
        "entreprises":  unique,
        "total":        len(unique),
        "date_debut":   date_debut or "—",
        "departements": deps,
        "errors":       errors,
    }


@app.get("/api/stats")
def get_stats():
    """Retourne les statistiques de la base de données locale (si disponible)."""
    try:
        import sqlite3
        # DB_PATH env var for cloud; fall back to the local default path
        db_path = os.getenv("DB_PATH", os.path.join(_ROOT, "prospection", "prospection.db"))
        if not os.path.exists(db_path):
            return {"disponible": False, "message": "Base de données non initialisée (run main.py au moins une fois en local)"}

        conn = sqlite3.connect(db_path)
        total   = conn.execute("SELECT COUNT(*) FROM envois").fetchone()[0]
        envoyes = conn.execute("SELECT COUNT(*) FROM envois WHERE statut='envoyé'").fetchone()[0]
        erreurs = conn.execute("SELECT COUNT(*) FROM envois WHERE statut='erreur'").fetchone()[0]
        dernier = conn.execute(
            "SELECT date_envoi FROM envois ORDER BY date_envoi DESC LIMIT 1"
        ).fetchone()
        conn.close()

        return {
            "disponible":    True,
            "total":         total,
            "envoyes":       envoyes,
            "erreurs":       erreurs,
            "dernier_envoi": dernier[0] if dernier else None,
        }
    except Exception as exc:
        return {"disponible": False, "message": str(exc)}
