"""
Module de validation des données pour GODMOD V2.
Vérifie la cohérence et l'intégrité des données scrapées.
"""
import logging
from .database import get_db_connection

logger = logging.getLogger(__name__)

def valider_donnees_journee(journee):
    """
    Vérifie qu'une journée a exactement 10 matchs.
    
    Args:
        journee: Numéro de la journée à valider
    
    Returns:
        True si valide (10 matchs), False sinon
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM resultats WHERE journee = ?", (journee,))
            nb_matchs = cursor.fetchone()[0]
            
            if nb_matchs != 10:
                logger.warning(f"⚠️ Journée {journee} : {nb_matchs}/10 matchs détectés")
                return False
            
            logger.info(f"✅ Journée {journee} : validation OK (10 matchs)")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la validation J{journee}: {e}", exc_info=True)
        return False


def valider_scores(journee):
    """
    Vérifie que les scores d'une journée sont valides (≥ 0).
    
    Args:
        journee: Numéro de la journée à valider
    
    Returns:
        True si tous les scores sont valides, False sinon
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM resultats 
                WHERE journee = ? 
                AND (score_dom < 0 OR score_ext < 0)
            """, (journee,))
            nb_invalides = cursor.fetchone()[0]
            
            if nb_invalides > 0:
                logger.error(f"❌ Journée {journee} : {nb_invalides} scores invalides (< 0)")
                return False
            
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la validation des scores J{journee}: {e}", exc_info=True)
        return False


def valider_cotes(journee):
    """
    Vérifie que les cotes sont cohérentes (entre 1.01 et 100).
    
    Args:
        journee: Numéro de la journée à valider
    
    Returns:
        True si toutes les cotes sont valides, False sinon
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM cotes 
                WHERE journee = ? 
                AND (cote_1 < 1.01 OR cote_1 > 100 
                     OR cote_x < 1.01 OR cote_x > 100 
                     OR cote_2 < 1.01 OR cote_2 > 100)
            """, (journee,))
            nb_invalides = cursor.fetchone()[0]
            
            if nb_invalides > 0:
                logger.warning(f"⚠️ Journée {journee} : {nb_invalides} cotes hors limites")
                return False
            
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la validation des cotes J{journee}: {e}", exc_info=True)
        return False
