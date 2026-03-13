# Prospection automatique — Nouvelles entreprises

> Script desktop Python qui récupère chaque semaine les entreprises nouvellement créées via l'API INSEE SIRENE et envoie automatiquement votre brochure par courrier physique via l'API Maileva (La Poste).

---

## Contexte du projet

Des sociétés parviennent à contacter par courrier toutes les entreprises nouvellement créées pour leur proposer des services. Ce projet reproduit ce système de façon automatisée :

1. Récupérer les nouvelles entreprises (source : INSEE SIRENE, open data)
2. Filtrer selon des critères métier (département, secteur, date de création)
3. Envoyer la brochure de l'entreprise par courrier postal automatique (Maileva)
4. Garder un historique local pour éviter les doublons d'envoi

**Contrainte PO principale :** coût par envoi < 1 € si possible (objectif : ~0,80–1,20 € tout compris).

---

## Stack recommandée

| Composant | Choix | Raison |
|---|---|---|
| Langage | Python 3.11+ | Simple, librairies HTTP robustes |
| HTTP client | `requests` | Standard, stable |
| Base de données | SQLite (built-in) | Zéro dépendance, suffisant pour ce volume |
| Scheduler | `cron` (Mac/Linux) ou Planificateur Windows | Natif OS, pas de dépendance supplémentaire |
| Source données | API INSEE SIRENE v3.11 | Officielle, gratuite, open data |
| Envoi courrier | API Maileva (La Poste) | Impression + envoi postal automatisé par API |

---

## Architecture du projet

```
prospection/
├── main.py                  # Point d'entrée principal
├── config.py                # Toute la configuration centralisée
├── insee.py                 # Module : récupération des entreprises
├── maileva.py               # Module : envoi courrier
├── database.py              # Module : SQLite (historique, dédoublonnage)
├── brochure.pdf             # Votre brochure à envoyer (à placer ici)
├── prospection.db           # Généré automatiquement au premier run
├── prospection.log          # Journal d'exécution
├── requirements.txt
└── README.md
```

---

## Roadmap MVP

### Phase 1 — Fondations (Jour 1)

- [ ] Créer `config.py` avec toutes les constantes (tokens, départements, chemins)
- [ ] Créer `database.py` : init SQLite, fonctions `deja_envoye()` et `enregistrer_envoi()`
- [ ] Tester la connexion à l'API INSEE avec un appel manuel simple

### Phase 2 — Données INSEE (Jour 2)

- [ ] Créer `insee.py` : fonction `recuperer_nouvelles_entreprises()`
- [ ] Implémenter le filtre par date de création (N derniers jours)
- [ ] Implémenter le filtre par département
- [ ] Normaliser la réponse en liste de dicts propres `{siret, nom, adresse, ...}`
- [ ] Logger les résultats et gérer les erreurs HTTP

### Phase 3 — Envoi Maileva (Jour 3)

- [ ] Créer un compte Maileva et obtenir les credentials OAuth2
- [ ] Créer `maileva.py` : fonction `envoyer_courrier(entreprise, pdf_path)`
- [ ] Implémenter les 3 étapes : création mailing → upload PDF → soumission
- [ ] Tester avec 1 envoi réel (mode test Maileva disponible)

### Phase 4 — Orchestration (Jour 4)

- [ ] Créer `main.py` : boucle principale avec contrôle du volume max par run
- [ ] Ajouter la pause entre appels API (rate limiting)
- [ ] Tester un run complet end-to-end
- [ ] Configurer le scheduler (cron ou Planificateur de tâches)

### Phase 5 — Robustesse (Jour 5, optionnel MVP)

- [ ] Retry automatique en cas d'erreur réseau (max 3 tentatives)
- [ ] Rapport email hebdomadaire (nb envoyés, erreurs) via `smtplib`
- [ ] Filtre par code NAF / secteur d'activité
- [ ] Mode dry-run (simuler sans envoyer) pour les tests

---

## Endpoints API

### INSEE SIRENE v3.11

**Base URL :** `https://api.insee.fr/entreprises/sirene/V3.11`

**Authentification :** OAuth2 Bearer Token
- Inscription gratuite sur : https://api.insee.fr
- Générer un token sur le portail développeur INSEE

**Endpoint principal :**

```
GET /siret
```

**Paramètres de requête :**

| Paramètre | Type | Description | Exemple |
|---|---|---|---|
| `q` | string | Requête Lucene de filtrage | voir ci-dessous |
| `nombre` | integer | Nombre de résultats (max 1000) | `50` |
| `debut` | integer | Offset pour la pagination | `0` |
| `champs` | string | Champs à retourner (optimise la réponse) | voir ci-dessous |

**Exemple de requête `q` :**

```
dateCreationEtablissement:[2026-03-01 TO *]
AND etatAdministratifEtablissement:A
AND (codePostalEtablissement:75* OR codePostalEtablissement:92*)
```

**Champs utiles à demander (`champs`) :**

```
siret,
denominationUniteLegale,
numeroVoieEtablissement,
typeVoieEtablissement,
libelleVoieEtablissement,
codePostalEtablissement,
libelleCommuneEtablissement,
dateCreationEtablissement,
activitePrincipaleEtablissement
```

**Structure de réponse :**

```json
{
  "header": { "total": 142, "debut": 0, "nombre": 50 },
  "etablissements": [
    {
      "siret": "12345678900012",
      "uniteLegale": {
        "denominationUniteLegale": "ACME SAS"
      },
      "adresseEtablissement": {
        "numeroVoieEtablissement": "10",
        "typeVoieEtablissement": "RUE",
        "libelleVoieEtablissement": "DE LA PAIX",
        "codePostalEtablissement": "75001",
        "libelleCommuneEtablissement": "PARIS"
      },
      "dateCreationEtablissement": "2026-03-10"
    }
  ]
}
```

**Codes d'erreur courants :**

| Code | Signification | Action |
|---|---|---|
| 401 | Token expiré ou invalide | Renouveler le token OAuth2 |
| 404 | Aucun résultat | Élargir les filtres de date ou département |
| 429 | Rate limit dépassé | Ajouter `time.sleep(1)` entre les appels |

---

### Maileva API v2 (La Poste)

**Base URL :** `https://api.maileva.com/mail/v2`

**Authentification :** OAuth2 Bearer Token
- Inscription sur : https://dev.maileva.com
- Créditer un compte prépayé pour les envois

**Flux en 3 appels successifs :**

---

**Étape 1 — Créer l'envoi**

```
POST /mailings
Content-Type: application/json
```

Body :

```json
{
  "name": "Prospection SIRET_12345",
  "postage_type": "ECONOMIC",
  "color_printing": false,
  "duplex_printing": false,
  "sender_address_line_1": "Votre Société SAS",
  "sender_address_line_2": "10 rue de la Paix",
  "sender_address_line_6": "75001 Paris",
  "recipient_address_line_1": "ACME SAS",
  "recipient_address_line_2": "10 RUE DE LA PAIX",
  "recipient_address_line_6": "75001 PARIS"
}
```

Réponse :

```json
{ "id": "mailing_abc123", "status": "DRAFT" }
```

> Conserver le `id` pour les étapes suivantes.

---

**Étape 2 — Uploader le PDF**

```
POST /mailings/{mailing_id}/documents
Content-Type: multipart/form-data
```

Body : fichier PDF en `multipart/form-data` avec la clé `document`.

Réponse : `201 Created`

---

**Étape 3 — Soumettre (déclenche l'impression et l'envoi)**

```
POST /mailings/{mailing_id}/submit
```

Réponse :

```json
{ "id": "mailing_abc123", "status": "SUBMITTED" }
```

> Une fois soumis, Maileva prend en charge l'impression et l'envoi physique. Délai estimé : J+1 à J+2 ouvré.

**Options `postage_type` :**

| Valeur | Description | Coût estimé |
|---|---|---|
| `ECONOMIC` | Lettre verte (J+2) | ~0,73 € affranchissement |
| `PRIORITAIRE` | Lettre rouge (J+1) | ~0,85 € affranchissement |
| `REGISTERED` | Recommandé avec AR | ~4,50 € |

**Coût total estimé par envoi (ECONOMIC, N&B, 1 page) :**

```
Impression Maileva :  ~0,30 €
Mise sous pli :       ~0,10 €
Affranchissement :    ~0,73 €
─────────────────────────────
Total :               ~1,13 € HT
```

> Tarifs dégressifs à partir de 500 envois/mois. Négociable à partir de 1 000 envois.

---

## Variables d'environnement

À définir avant de lancer le script, ou dans un fichier `.env` :

```bash
INSEE_TOKEN=votre_token_insee_ici
MAILEVA_TOKEN=votre_token_maileva_ici
```

Ne jamais committer ces valeurs dans Git. Ajouter `.env` au `.gitignore`.

---

## Schéma de la base SQLite

Table `envois` :

| Colonne | Type | Description |
|---|---|---|
| `siret` | TEXT (PK) | Identifiant unique de l'établissement |
| `nom` | TEXT | Dénomination légale |
| `adresse` | TEXT | Adresse complète normalisée |
| `date_creation` | TEXT | Date de création (format YYYY-MM-DD) |
| `date_envoi` | TEXT | Timestamp de l'envoi |
| `statut` | TEXT | `envoyé` ou `erreur` |

La clé primaire sur `siret` garantit qu'une même entreprise ne reçoit jamais deux courriers.

---

## Configuration (à centraliser dans `config.py`)

```python
CONFIG = {
    # Tokens API
    "insee_token":   os.getenv("INSEE_TOKEN"),
    "maileva_token": os.getenv("MAILEVA_TOKEN"),

    # Filtres de prospection
    "departements":          ["75", "92", "93", "94"],
    "jours_retroactifs":     7,
    "nb_max_envois_par_run": 50,

    # Expéditeur
    "expediteur_nom":     "Votre Société SAS",
    "expediteur_adresse": "10 rue de la Paix",
    "expediteur_cp":      "75001",
    "expediteur_ville":   "Paris",

    # Fichiers locaux
    "brochure_pdf": "brochure.pdf",
    "db_path":      "prospection.db",
    "log_path":     "prospection.log",
}
```

---

## Automatisation (sans serveur)

**Mac / Linux — cron :**

```bash
# Ouvrir l'éditeur cron
crontab -e

# Ajouter cette ligne : exécution chaque lundi à 8h00
0 8 * * 1 cd /chemin/vers/prospection && python3 main.py
```

**Windows — Planificateur de tâches :**

1. Ouvrir "Planificateur de tâches" (taskschd.msc)
2. Créer une tâche de base
3. Déclencheur : Hebdomadaire → Lundi → 08:00
4. Action : Démarrer un programme → `python.exe`
5. Arguments : `C:\chemin\vers\main.py`

---

## Conseils pour Cursor

- Générer les modules un par un dans cet ordre : `database.py` → `insee.py` → `maileva.py` → `main.py` → `config.py`
- Demander à Cursor de générer des **tests unitaires** pour chaque module (mock des appels HTTP avec `unittest.mock`)
- Utiliser le mode **Composer** de Cursor pour passer ce README en contexte au début de chaque session
- Prompt de départ suggéré pour Cursor :

```
En utilisant ce README comme spécification complète, génère le fichier
`database.py` avec les fonctions init_db(), deja_envoye() et enregistrer_envoi().
Utilise sqlite3 (built-in Python). Respecte le schéma de table défini dans le README.
```

---

## Liens utiles

- Documentation API INSEE SIRENE : https://api.insee.fr/catalogue/
- Portail développeur Maileva : https://dev.maileva.com/
- Filtres Lucene SIRENE (syntaxe `q`) : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/item-info.jag?name=Sirene&version=V3.11
- Codes NAF / secteurs d'activité : https://www.insee.fr/fr/information/2406147
