import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from . import config

# Configuration du logging
logger = logging.getLogger(__name__)

@contextmanager
def get_db_connection():
    """
    Context manager pour les connexions DB (PostgreSQL).
    """
    try:
        if config.DATABASE_URL:
            conn = psycopg2.connect(config.DATABASE_URL)
        else:
            # Fallback to local sqlite is removed as per plan to migrate to Postgres
            # But for safety, we might want to warn or error if no URL.
            # Assuming strictly Postgres for now as per "Change to Postgres" request.
            raise ValueError("DATABASE_URL not set. Please configure your .env file.")
            
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur DB, rollback effectué: {e}", exc_info=True)
            raise
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Erreur de connexion DB: {e}", exc_info=True)
        raise e

def initialiser_db():
    """Initialise la base de données avec une structure PostgreSQL."""
    # Note: Dans un environnement de prod comme Aiven, on utiliserait idéalement des migrations (Alembic).
    # Ici on fait un 'CREATE TABLE IF NOT EXISTS' pour rester simple.
    
    if not config.DATABASE_URL:
        logger.error("DATABASE_URL manquant pour initialiser_db")
        return

    try:
        with psycopg2.connect(config.DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                
                # 1. Table des équipes
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS equipes (
                        id SERIAL PRIMARY KEY,
                        nom TEXT UNIQUE NOT NULL
                    )
                ''')

                # 2. Table des résultats
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS resultats (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        equipe_dom_id INTEGER NOT NULL,
                        equipe_ext_id INTEGER NOT NULL,
                        score_dom INTEGER,
                        score_ext INTEGER,
                        FOREIGN KEY (equipe_dom_id) REFERENCES equipes(id),
                        FOREIGN KEY (equipe_ext_id) REFERENCES equipes(id),
                        UNIQUE(journee, equipe_dom_id, equipe_ext_id)
                    )
                ''')

                # 3. Table des cotes
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cotes (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        equipe_dom_id INTEGER NOT NULL,
                        equipe_ext_id INTEGER NOT NULL,
                        cote_1 DECIMAL(5,2),
                        cote_x DECIMAL(5,2),
                        cote_2 DECIMAL(5,2),
                        FOREIGN KEY (equipe_dom_id) REFERENCES equipes(id),
                        FOREIGN KEY (equipe_ext_id) REFERENCES equipes(id),
                        UNIQUE(journee, equipe_dom_id, equipe_ext_id)
                    )
                ''')

                # 4. Table du classement
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS classement (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        equipe_id INTEGER NOT NULL,
                        position INTEGER,
                        points INTEGER NOT NULL,
                        forme TEXT,
                        buts_pour DECIMAL(4,2) DEFAULT 0,
                        buts_contre DECIMAL(4,2) DEFAULT 0,
                        FOREIGN KEY (equipe_id) REFERENCES equipes(id),
                        UNIQUE(journee, equipe_id)
                    )
                ''')

                # 5. Table des prédictions
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS predictions (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        equipe_dom_id INTEGER NOT NULL,
                        equipe_ext_id INTEGER NOT NULL,
                        prediction TEXT NOT NULL,
                        resultat TEXT,
                        fiabilite DECIMAL(5,2),
                        succes INTEGER,
                        points_gagnes INTEGER,
                        FOREIGN KEY (equipe_dom_id) REFERENCES equipes(id),
                        FOREIGN KEY (equipe_ext_id) REFERENCES equipes(id)
                    )
                ''')

                # 6. Table des scores IA
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS score_ia (
                        id SERIAL PRIMARY KEY,
                        score DECIMAL(10,2) DEFAULT 100.00,
                        predictions_total INTEGER DEFAULT 0,
                        predictions_reussies INTEGER DEFAULT 0,
                        pause_until INTEGER DEFAULT 0,
                        session_archived INTEGER DEFAULT 0,
                        derniere_maj TIMESTAMP
                    )
                ''')

                # 7. Table Classement Global
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS classement_global (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        position INTEGER,
                        equipe_id INTEGER NOT NULL,
                        points INTEGER NOT NULL,
                        forme TEXT,
                        FOREIGN KEY (equipe_id) REFERENCES equipes(id)
                    )
                ''')

                # 8. Table Matches Global
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS matches_global (
                        id SERIAL PRIMARY KEY,
                        journee INTEGER NOT NULL,
                        equipe_dom_id INTEGER NOT NULL,
                        equipe_ext_id INTEGER NOT NULL,
                        cote_1 DECIMAL(5,2),
                        cote_x DECIMAL(5,2),
                        cote_2 DECIMAL(5,2),
                        status TEXT,
                        score_dom INTEGER,
                        score_ext INTEGER,
                        FOREIGN KEY (equipe_dom_id) REFERENCES equipes(id),
                        FOREIGN KEY (equipe_ext_id) REFERENCES equipes(id)
                    )
                ''')

                # 9. Table Sessions ZEUS
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id SERIAL PRIMARY KEY,
                        timestamp_debut TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        timestamp_fin TIMESTAMP,
                        capital_initial INTEGER DEFAULT 20000,
                        capital_final INTEGER,
                        nombre_journees INTEGER DEFAULT 38,
                        version_ia TEXT,
                        profit_total INTEGER,
                        type_session TEXT CHECK(type_session IN ('TRAINING', 'EVALUATION', 'PRODUCTION')),
                        score_zeus INTEGER DEFAULT 0
                    )
                ''')

                # 10. Table Historique Paris ZEUS
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS historique_paris (
                        id_pari SERIAL PRIMARY KEY,
                        session_id INTEGER NOT NULL,
                        match_id INTEGER NOT NULL,
                        journee INTEGER NOT NULL,
                        type_pari TEXT CHECK(type_pari IN ('1', 'N', '2', 'Aucun')),
                        mise_ar INTEGER,
                        pourcentage_bankroll REAL,
                        cote_jouee REAL,
                        resultat INTEGER,
                        profit_net INTEGER,
                        bankroll_apres INTEGER NOT NULL,
                        timestamp_pari TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        probabilite_implicite REAL,
                        action_id INTEGER,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                        FOREIGN KEY (match_id) REFERENCES matches_global(id)
                    )
                ''')

                # --- Initialisation des données ---
                
                # 1. Équipes
                # Postgres "ON CONFLICT" syntax instead of "INSERT OR IGNORE"
                for equipe in config.EQUIPES:
                    cursor.execute('INSERT INTO equipes (nom) VALUES (%s) ON CONFLICT (nom) DO NOTHING', (equipe,))
                
                # 2. Score IA
                cursor.execute("SELECT COUNT(*) FROM score_ia")
                if cursor.fetchone()[0] == 0:
                    cursor.execute('INSERT INTO score_ia (score, predictions_total, predictions_reussies, pause_until, session_archived, derniere_maj) VALUES (100, 0, 0, 0, 0, NOW())')

                # 3. Index
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_resultats_journee ON resultats(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_resultats_equipes ON resultats(equipe_dom_id, equipe_ext_id)",
                    "CREATE INDEX IF NOT EXISTS idx_predictions_journee ON predictions(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_predictions_succes ON predictions(succes)",
                    "CREATE INDEX IF NOT EXISTS idx_cotes_journee ON cotes(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_classement_equipe ON classement(equipe_id)",
                    "CREATE INDEX IF NOT EXISTS idx_classement_journee ON classement(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_classement_global_journee ON classement_global(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_matches_global_journee ON matches_global(journee)",
                    "CREATE INDEX IF NOT EXISTS idx_matches_global_equipes ON matches_global(equipe_dom_id, equipe_ext_id)",
                    "CREATE INDEX IF NOT EXISTS idx_sessions_type ON sessions(type_session)",
                    "CREATE INDEX IF NOT EXISTS idx_historique_paris_session ON historique_paris(session_id)",
                    "CREATE INDEX IF NOT EXISTS idx_historique_paris_match ON historique_paris(match_id)",
                    "CREATE INDEX IF NOT EXISTS idx_historique_paris_journee ON historique_paris(journee)"
                ]
                
                for index_sql in indexes:
                    cursor.execute(index_sql)
            
            conn.commit()
            print("Base de donnees PostgreSQL initialisee avec succes.")

    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
        print(f"Erreur initialisation DB: {e}")

if __name__ == "__main__":
    initialiser_db()