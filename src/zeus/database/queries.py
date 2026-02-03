"""
Requêtes SQL sécurisées pour ZEUS avec isolation temporelle.
"""

from typing import Dict, List, Optional, Tuple, Any
import pandas as pd


def get_classement_snapshot(journee_actuelle: int, conn: Any) -> pd.DataFrame:
    """
    Récupère le classement des équipes AVANT le match day actuel.
    CRITIQUE: Évite le data leakage en utilisant journee < journee_actuelle.
    
    Args:
        journee_actuelle: Numéro de journée actuelle
        conn: Connexion SQLite
        
    Returns:
        DataFrame avec colonnes: equipe_id, position, points, forme
    """
    query = """
        SELECT 
            cg.equipe_id,
            cg.position,
            cg.points,
            cg.forme,
            e.nom as equipe_nom
        FROM classement_global cg
        JOIN equipes e ON cg.equipe_id = e.id
        WHERE cg.journee = (
            SELECT MAX(journee) 
            FROM classement_global 
            WHERE journee < %s
        )
        ORDER BY cg.position
    """
    return pd.read_sql(query, conn, params=(journee_actuelle,))


def get_match_data(match_id: int, conn: Any) -> Optional[Dict]:
    """
    Récupère les données d'un match spécifique.
    
    Args:
        match_id: ID du match dans matches_global
        conn: Connexion SQLite
        
    Returns:
        Dictionnaire avec les données du match ou None si non trouvé
    """
    query = """
        SELECT 
            mg.id,
            mg.journee,
            mg.equipe_dom_id,
            mg.equipe_ext_id,
            e_dom.nom as equipe_dom_nom,
            e_ext.nom as equipe_ext_nom,
            mg.cote_1,
            mg.cote_x,
            mg.cote_2,
            mg.score_dom,
            mg.score_ext,
            mg.status
        FROM matches_global mg
        JOIN equipes e_dom ON mg.equipe_dom_id = e_dom.id
        JOIN equipes e_ext ON mg.equipe_ext_id = e_ext.id
        WHERE mg.id = %s
    """
    cursor = conn.cursor()
    cursor.execute(query, (match_id,))
    row = cursor.fetchone()
    
    if row is None:
        return None
        
    return {
        'id': row[0],
        'journee': row[1],
        'equipe_dom_id': row[2],
        'equipe_ext_id': row[3],
        'equipe_dom_nom': row[4],
        'equipe_ext_nom': row[5],
        'cote_1': row[6],
        'cote_x': row[7],
        'cote_2': row[8],
        'score_dom': row[9],
        'score_ext': row[10],
        'status': row[11]
    }


def get_matches_for_journee(journee: int, conn: Any) -> List[Dict]:
    """
    Récupère tous les matchs d'une journée spécifique.
    
    Args:
        journee: Numéro de journée
        conn: Connexion SQLite
        
    Returns:
        Liste de dictionnaires de matchs
    """
    query = """
        SELECT 
            mg.id,
            mg.journee,
            mg.equipe_dom_id,
            mg.equipe_ext_id,
            e_dom.nom as equipe_dom_nom,
            e_ext.nom as equipe_ext_nom,
            mg.cote_1,
            mg.cote_x,
            mg.cote_2,
            mg.score_dom,
            mg.score_ext,
            mg.status
        FROM matches_global mg
        JOIN equipes e_dom ON mg.equipe_dom_id = e_dom.id
        JOIN equipes e_ext ON mg.equipe_ext_id = e_ext.id
        WHERE mg.journee = %s
        ORDER BY mg.id
    """
    cursor = conn.cursor()
    cursor.execute(query, (journee,))
    rows = cursor.fetchall()
    
    matches = []
    for row in rows:
        matches.append({
            'id': row[0],
            'journee': row[1],
            'equipe_dom_id': row[2],
            'equipe_ext_id': row[3],
            'equipe_dom_nom': row[4],
            'equipe_ext_nom': row[5],
            'cote_1': row[6],
            'cote_x': row[7],
            'cote_2': row[8],
            'score_dom': row[9],
            'score_ext': row[10],
            'status': row[11]
        })
    
    return matches


def create_session(
    capital_initial: int,
    type_session: str,
    version_ia: str,
    conn: Any
) -> int:
    """
    Crée une nouvelle session ZEUS.
    
    Args:
        capital_initial: Capital de départ (généralement 20000)
        type_session: 'TRAINING', 'EVALUATION', ou 'PRODUCTION'
        version_ia: Version du modèle IA
        conn: Connexion SQLite
        
    Returns:
        ID de la session créée
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (
            capital_initial,
            type_session,
            version_ia,
            score_zeus
        ) VALUES (%s, %s, %s, 0)
    """, (capital_initial, type_session, version_ia))
    conn.commit()
    return cursor.lastrowid


def enregistrer_pari(
    session_id: int,
    match_id: int,
    journee: int,
    type_pari: str,
    mise_ar: int,
    pourcentage_bankroll: float,
    cote_jouee: Optional[float],
    resultat: Optional[int],
    profit_net: Optional[int],
    bankroll_apres: int,
    probabilite_implicite: Optional[float],
    action_id: int,
    conn: Any
) -> int:
    """
    Enregistre un pari dans l'historique.
    
    Args:
        session_id: ID de la session
        match_id: ID du match
        journee: Numéro de journée
        type_pari: '1', 'N', '2', ou 'Aucun'
        mise_ar: Montant misé
        pourcentage_bankroll: Pourcentage du capital
        cote_jouee: Cote jouée (None si abstention)
        resultat: 1 (gagné), 0 (perdu), None (abstention)
        profit_net: Profit/perte net
        bankroll_apres: Capital après le pari
        probabilite_implicite: Probabilité calculée de l'issue
        action_id: ID de l'action discrète (0-12)
        conn: Connexion SQLite
        
    Returns:
        ID du pari enregistré
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historique_paris (
            session_id,
            match_id,
            journee,
            type_pari,
            mise_ar,
            pourcentage_bankroll,
            cote_jouee,
            resultat,
            profit_net,
            bankroll_apres,
            probabilite_implicite,
            action_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        session_id, match_id, journee, type_pari, mise_ar,
        pourcentage_bankroll, cote_jouee, resultat, profit_net,
        bankroll_apres, probabilite_implicite, action_id
    ))
    conn.commit()
    return cursor.lastrowid


def finaliser_session(
    session_id: int,
    capital_final: int,
    profit_total: int,
    score_zeus: int,
    conn: Any
):
    """
    Finalise une session avec les résultats finaux.
    
    Args:
        session_id: ID de la session
        capital_final: Capital final
        profit_total: Profit total (peut être négatif)
        score_zeus: Score final ZEUS (+1/-1 cumulatif)
        conn: Connexion SQLite
    """
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions
        SET timestamp_fin = CURRENT_TIMESTAMP,
            capital_final = %s,
            profit_total = %s,
            score_zeus = %s
        WHERE session_id = %s
    """, (capital_final, profit_total, score_zeus, session_id))
    conn.commit()


def get_available_seasons(conn: Any) -> List[int]:
    """
    Récupère la liste des saisons disponibles (groupes de 38 journées).
    
    Returns:
        Liste des numéros de journées début de saison
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT journee 
        FROM matches_global 
        WHERE status = 'TERMINE'
        ORDER BY journee
    """)
    all_journees = [row[0] for row in cursor.fetchall()]
    
    # Grouper par saisons de 38 journées
    seasons = []
    if all_journees:
        for j in all_journees:
            if (j - 1) % 38 == 0:
                seasons.append(j)
    
    return seasons


def get_last_training_metadata(conn: Any) -> Dict:
    """
    Récupère les métadonnées de la dernière session d'entraînement réussie.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT version_ia, MAX(journee) as max_j, session_id
        FROM sessions
        WHERE type_session = 'TRAINING' AND timestamp_fin IS NOT NULL
        ORDER BY session_id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        return {'version': row[0], 'max_journee': row[1] if row[1] else 0, 'id': row[2]}
    return {'version': 'v0', 'max_journee': 0, 'id': None}


def get_completed_journees_count(conn: Any) -> int:
    """
    Retourne la dernière journée complétée.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(journee) FROM matches_global WHERE status = 'TERMINE'")
    row = cursor.fetchone()
    return row[0] if row[0] else 0


def check_new_season_available(conn: Any) -> bool:
    """
    Vérifie si une nouvelle saison complète (38 j) est disponible depuis le dernier entraînement.
    """
    last_meta = get_last_training_metadata(conn)
    current_max = get_completed_journees_count(conn)
    
    # Si on a au moins 38 journées de plus que le dernier entraînement
    return (current_max - last_meta['max_journee']) >= 38
