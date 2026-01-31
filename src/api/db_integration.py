"""
Module d'integration de l'API avec la base de donnees existante
Utilise la structure BDD actuelle sans modification

Version: 2.1
Date: Janvier 2025
"""

import sqlite3
import logging
from typing import List, Dict
from datetime import datetime
import sys
import os

# Ajouter le chemin du projet
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.database import get_db_connection
from src.core import config

logger = logging.getLogger(__name__)

# ==================== HELPER ====================

def normalize_team_name(team_name: str) -> str:
    """
    Normalise le nom d'equipe en utilisant les alias du config
    
    Args:
        team_name: Nom de l'equipe depuis l'API
        
    Returns:
        Nom normalise pour la BDD
    """
    return config.TEAM_ALIASES.get(team_name, team_name)

def normalize_form_history(history: List[str]) -> str:
    """
    Convertit l'historique API (Won, Lost, Draw) en format BDD (V, D, N)
    Ex: ['Won', 'Draw', 'Lost'] -> "V,N,D"
    """
    mapping = {
        'Won': 'V',
        'Lost': 'D',
        'Draw': 'N'
    }
    # On prend les 5 derniers, on mappe, et on joint par une virgule (ou vide si pas de match)
    # L'utilisateur voulait "VVDVN" (sans virgule ?). 
    # Le code original faisait: ",".join(history[-5:]) -> "Won,Lost,Draw"
    # Si le format attendu est "VVDVN" (comme la forme actuelle en BDD ? Verifions)
    # La BDD actuelle utilise souvent "V,V,D,V,N" ou "VVDVN". 
    # Dans `intelligence.py` on voit `forme[-5:]` et `valeurs.get(c, 0)` sur chaque char. 
    # Donc intelligence.py s'attend a "V", "N", "D" iterables.
    # Si c'est comma-separated "V,N,D", `forme[-5:]` donnera ",N,D" ce qui est faux.
    # Mais le code original faisait ",".join()...
    # Attendez. 
    # `intelligence.py` ligne 70: `return sum(valeurs.get(c, 0) for c in (f[-5:] if f else ""))`
    # Si f est "V,V,D", f[-5:] est "V,V,D". 
    # `for c in ...` va iterer sur ',', 'V', ',' ... et `valeurs.get(',', 0)` donnera 0.
    # Donc ca marche "a peu pres" mais c'est sale.
    # L'utilisateur a demandé : "VVDVN" (exemple explicit sans virgule).
    # Je vais donc faire une chaine SANS virgule.
    
    normalized = [mapping.get(res, '?') for res in history[-5:]]
    return "".join(normalized)

# ==================== FONCTIONS D'INSERTION ====================

def insert_api_ranking(ranking_data: List[Dict]) -> int:
    """
    Insere le classement depuis l'API dans la table 'classement'
    
    Args:
        ranking_data: Liste des equipes avec leurs statistiques
        
    Returns:
        Nombre d'equipes inserees
    """
    if not ranking_data:
        logger.warning("Aucune donnee de classement a inserer")
        return 0
    
    # Determiner la journee actuelle (basee sur le nombre de matchs joues)
    # On prend le nombre de matchs de la premiere equipe
    journee = ranking_data[0].get("won", 0) + ranking_data[0].get("lost", 0) + ranking_data[0].get("draw", 0)
    
    count = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Nettoyage avant insertion (comme dans le scraper)
        cursor.execute("DELETE FROM classement")
        
        for team in ranking_data:
            team_name = normalize_team_name(team.get("name"))
            position = team.get("position")
            points = team.get("points")
            
            # Extraire la forme (5 derniers matchs) et normaliser
            # Validation des types : Won->V, Lost->D, Draw->N
            history = team.get("history", [])
            forme = normalize_form_history(history)
            
            # Verifier si l'equipe existe dans la table equipes
            cursor.execute("SELECT id FROM equipes WHERE nom = %s", (team_name,))
            result = cursor.fetchone()
            
            if result:
                equipe_id = result[0]
                
                # CALCUL DES BUTS (Pour/Contre) depuis la table resultats
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN equipe_dom_id = %s THEN score_dom ELSE score_ext END) as bp,
                        SUM(CASE WHEN equipe_dom_id = %s THEN score_ext ELSE score_dom END) as bc
                    FROM resultats 
                    WHERE (equipe_dom_id = %s OR equipe_ext_id = %s) AND score_dom IS NOT NULL
                """, (equipe_id, equipe_id, equipe_id, equipe_id))
                stats_buts = cursor.fetchone()
                buts_pour = stats_buts[0] if stats_buts and stats_buts[0] is not None else 0
                buts_contre = stats_buts[1] if stats_buts and stats_buts[1] is not None else 0
                
                # Inserer le classement avec les stats de buts
                cursor.execute("""
                    INSERT INTO classement (journee, equipe_id, position, points, forme, buts_pour, buts_contre)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (journee, equipe_id, position, points, forme, buts_pour, buts_contre))
                
                # --- NOUVEAU : Historique Global (Classement Global) ---
                # On insère aussi dans la table historique perpétuelle
                cursor.execute("""
                    INSERT INTO classement_global (journee, equipe_id, position, points, forme)
                    VALUES (%s, %s, %s, %s, %s)
                """, (journee, equipe_id, position, points, forme))
                
                count += 1
            else:
                logger.warning(f"Equipe '{team_name}' non trouvee dans la BDD")
    
    logger.info(f"{count} equipes inserees dans le classement (journee {journee}) avec stats buts")
    return count


def insert_api_results(results_data: List[Dict]) -> int:
    """
    Insere les resultats depuis l'API dans la table 'resultats'
    
    Args:
        results_data: Liste des journees avec leurs matchs
        
    Returns:
        Nombre de matchs inseres
    """
    if not results_data:
        logger.warning("Aucun resultat a inserer")
        return 0
    
    count = 0
    validated_count = 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for round_data in results_data:
            journee = round_data.get("roundNumber")
            
            for match in round_data.get("matches", []):
                home_team = normalize_team_name(match.get("homeTeam"))
                away_team = normalize_team_name(match.get("awayTeam"))
                score = match.get("score", "")
                
                # Parser le score (format "2:1")
                if score and ":" in score:
                    parts = score.split(":")
                    score_dom = int(parts[0])
                    score_ext = int(parts[1])
                else:
                    score_dom = None
                    score_ext = None
                
                # Recuperer les IDs des equipes
                cursor.execute("SELECT id FROM equipes WHERE nom = %s", (home_team,))
                home_result = cursor.fetchone()
                cursor.execute("SELECT id FROM equipes WHERE nom = %s", (away_team,))
                away_result = cursor.fetchone()
                
                if home_result and away_result:
                    home_id = home_result[0]
                    away_id = away_result[0]
                    
                    # --- SMART CHECK : Verifier coherence avant UPDATE ---
                    cursor.execute("""
                        SELECT score_dom, score_ext FROM resultats 
                        WHERE journee = %s AND equipe_dom_id = %s AND equipe_ext_id = %s
                    """, (journee, home_id, away_id))
                    existing = cursor.fetchone()
                    
                    # Si le match existe et que le score est IDENTIQUE, on considere valide et on passe
                    # Cela evite les ecritures inutiles pour l'historique (J-1, J-2...)
                    if existing and existing[0] == score_dom and existing[1] == score_ext:
                        validated_count += 1
                        continue
                        
                    # Sinon (Nouveau score ou nouveau match) -> INSERT / UPDATE
                    
                    # Inserer ou mettre a jour le resultat
                    cursor.execute("""
                        INSERT INTO resultats (journee, equipe_dom_id, equipe_ext_id, score_dom, score_ext)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT(journee, equipe_dom_id, equipe_ext_id) DO UPDATE SET
                            score_dom = excluded.score_dom,
                            score_ext = excluded.score_ext
                    """, (journee, home_id, away_id, score_dom, score_ext))
                    
                    # --- NOUVEAU : Historique Global (Matches Global) ---
                    # Mise à jour du match terminé (Update si existe, Insert sinon)
                    
                    # 1. Tenter un UPDATE d'abord
                    cursor.execute("""
                        UPDATE matches_global 
                        SET score_dom = %s, score_ext = %s, status = 'TERMINE'
                        WHERE journee = %s AND equipe_dom_id = %s AND equipe_ext_id = %s
                    """, (score_dom, score_ext, journee, home_id, away_id))
                    
                    if cursor.rowcount == 0:
                        # Si pas trouvé (cas rare où on insère des résultats sans avoir scanné les cotes avant), on insère
                        cursor.execute("""
                            INSERT INTO matches_global (journee, equipe_dom_id, equipe_ext_id, score_dom, score_ext, status)
                            VALUES (%s, %s, %s, %s, %s, 'TERMINE')
                        """, (journee, home_id, away_id, score_dom, score_ext))
                    
                    count += 1
                else:
                    logger.warning(f"Equipes non trouvees: {home_team} vs {away_team}")
    
    logger.info(f"{count} resultats inseres/mis-a-jour, {validated_count} valides (sans changement)")
    return count, validated_count


def insert_api_matches(matches_data: List[Dict]) -> int:
    """
    Insere les matchs a venir depuis l'API dans les tables 'resultats' et 'cotes'
    
    Args:
        matches_data: Liste des journees avec leurs matchs et cotes
        
    Returns:
        Nombre de matchs inseres
    """
    if not matches_data:
        logger.warning("Aucun match a venir a inserer")
        return 0
    
    count = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for round_data in matches_data:
            journee = round_data.get("roundNumber")
            
            for match in round_data.get("matches", []):
                home_team = normalize_team_name(match.get("homeTeam"))
                away_team = normalize_team_name(match.get("awayTeam"))
                odds = match.get("odds", [])
                
                # Extraire les cotes 1X2
                cote_1 = next((o["odds"] for o in odds if o["type"] == "1"), None)
                cote_x = next((o["odds"] for o in odds if o["type"] == "X"), None)
                cote_2 = next((o["odds"] for o in odds if o["type"] == "2"), None)
                
                # Recuperer les IDs des equipes
                cursor.execute("SELECT id FROM equipes WHERE nom = %s", (home_team,))
                home_result = cursor.fetchone()
                cursor.execute("SELECT id FROM equipes WHERE nom = %s", (away_team,))
                away_result = cursor.fetchone()
                
                if home_result and away_result:
                    home_id = home_result[0]
                    away_id = away_result[0]
                    
                    # 1. Inserer le match dans 'resultats' (scores NULL car pas encore joue)
                    cursor.execute("""
                        INSERT INTO resultats (journee, equipe_dom_id, equipe_ext_id, score_dom, score_ext)
                        VALUES (%s, %s, %s, NULL, NULL)
                        ON CONFLICT(journee, equipe_dom_id, equipe_ext_id) DO NOTHING
                    """, (journee, home_id, away_id))
                    
                    # 2. Inserer les cotes dans 'cotes'
                    cursor.execute("""
                        INSERT INTO cotes (journee, equipe_dom_id, equipe_ext_id, cote_1, cote_x, cote_2)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT(journee, equipe_dom_id, equipe_ext_id) DO UPDATE SET
                            cote_1 = excluded.cote_1,
                            cote_x = excluded.cote_x,
                            cote_2 = excluded.cote_2
                    """, (journee, home_id, away_id, cote_1, cote_x, cote_2))
                    
                    # --- NOUVEAU : Historique Global (Matches Global) ---
                    # Insertion des indicateurs de marché
                    # On vérifie si existe déjà pour ne pas dupliquer bêtement (pas de contrainte unique stricte demandée mais logique)
                    cursor.execute("""
                        SELECT id FROM matches_global 
                        WHERE journee = %s AND equipe_dom_id = %s AND equipe_ext_id = %s
                    """, (journee, home_id, away_id))
                    exists = cursor.fetchone()
                    
                    if exists:
                        # Update des cotes si ça a bougé (Closing line evolution)
                        cursor.execute("""
                            UPDATE matches_global 
                            SET cote_1 = %s, cote_x = %s, cote_2 = %s
                            WHERE id = %s
                        """, (cote_1, cote_x, cote_2, exists[0]))
                    else:
                        cursor.execute("""
                            INSERT INTO matches_global (journee, equipe_dom_id, equipe_ext_id, cote_1, cote_x, cote_2, status)
                            VALUES (%s, %s, %s, %s, %s, %s, 'A_VENIR')
                        """, (journee, home_id, away_id, cote_1, cote_x, cote_2))
                    
                    count += 1
                else:
                    logger.warning(f"Equipes non trouvees: {home_team} vs {away_team}")
    
    logger.info(f"{count} matchs a venir inseres avec leurs cotes")
    return count


# ==================== FONCTION DE NETTOYAGE ====================

def clean_old_odds(journee_min: int):
    """
    Supprime les cotes des journees passees pour eviter l'accumulation
    
    Args:
        journee_min: Conserver uniquement les cotes >= a cette journee
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cotes WHERE journee < %s", (journee_min,))
        deleted = cursor.rowcount
        logger.info(f"{deleted} cotes anciennes supprimees (journee < {journee_min})")


# ==================== TEST ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("[TEST] Module API Database Integration")
    print("=" * 60)
    
    # Import des filtres
    from api_client import get_ranking, get_recent_results, get_upcoming_matches
    from results_filter import extract_results_minimal
    from matches_filter import extract_matches_with_local_ids
    
    # Test 1: Insertion du classement
    print("\n[TEST 1] Insertion du classement...")
    ranking = get_ranking()
    if ranking:
        count = insert_api_ranking(ranking)
        print(f"[OK] {count} equipes inserees dans le classement")
    
    # Test 2: Insertion des resultats
    print("\n[TEST 2] Insertion des resultats...")
    results_raw = get_recent_results(take=3)
    results_filtered = extract_results_minimal(results_raw)
    if results_filtered:
        count, validated = insert_api_results(results_filtered)
        print(f"[OK] {count} resultats inseres, {validated} valides")
    
    # Test 3: Insertion des matchs a venir
    print("\n[TEST 3] Insertion des matchs a venir...")
    matches_raw = get_upcoming_matches()
    matches_filtered = extract_matches_with_local_ids(matches_raw, limit=2)
    if matches_filtered:
        count = insert_api_matches(matches_filtered)
        print(f"[OK] {count} matchs a venir inseres")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Tests d'integration termines")
    print("Verifiez la base de donnees avec un outil SQLite")
