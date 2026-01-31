import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# URLs de base (extraites du README)
URL_RESULTATS = "https://bet261.mg/virtual/category/instant-league/8035/results"
URL_MATCHS = "https://bet261.mg/virtual/category/instant-league/8035/matches"
URL_CLASSEMENT = "https://bet261.mg/virtual/category/instant-league/8035/ranking"

# Configuration de la base de données
# Priotity: Env Var > Local SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
DB_NAME = "godmod_v2.db" # Fallback name for SQLite if needed logic persists somewhere, but we aim for Postgres

# Équipes de la English Virtual League (20)
EQUIPES = [
    "London Reds", "Manchester Blue", "Manchester Red", "Wolverhampton", "N. Forest",
    "Fulham", "West Ham", "Spurs", "London Blues", "Brighton",
    "Brentford", "Everton", "Aston Villa", "Leeds", "Sunderland",
    "Crystal Palace", "Liverpool", "Newcastle", "Burnley", "Bournemouth"
]

# Alias pour normaliser les noms d'équipes (Site -> DB)
TEAM_ALIASES = {
    "A. Villa": "Aston Villa",
    "C. Palace": "Crystal Palace",
    "Man Blue": "Manchester Blue",
    "Man Red": "Manchester Red",
}

# Paramètres de prédiction
JOURNEE_DEPART_PREDICTION = 2
MAX_PREDICTIONS_PAR_JOURNEE = 3
POINTS_VICTOIRE = 5
POINTS_DEFAITE = -8

# ============================================
# CONFIGURATION DU SYSTÈME INTELLIGENT
# ============================================

# Mode d'intelligence activé par défaut au démarrage
USE_INTELLIGENCE_AMELIOREE = True

# Sélection améliorée (Phase 3 complète)
USE_SELECTION_AMELIOREE = True

# État de ZEUS pendant l'entraînement automatique
# Si True, ZEUS n'émet pas de prédictions pour éviter les conflits
ZEUS_DEEP_SLEEP = False
