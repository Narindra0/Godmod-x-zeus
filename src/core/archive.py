"""
Module d'archivage des sessions GODMOD V2.
Gère la détection des nouvelles sessions et l'export des données en CSV.
"""
import csv
import os
import shutil
import logging
from datetime import datetime
from . import config
from .database import get_db_connection

logger = logging.getLogger(__name__)

# Dossier d'archives
ARCHIVES_DIR = os.path.join(os.path.dirname(config.DB_NAME), "archives")

def detecter_nouvelle_session(nouvelle_journee: int) -> bool:
    """
    Détecte si une nouvelle session a commencé.
    
    Logique améliorée :
    - Si session_archived = 1 : Toute nouvelle journée = nouvelle session
    - Si Delta < 0 : Nouvelle session (Reset standard J38 -> J1)
    - Si 0 <= Delta < 10 : Même session
    - Si Delta >= 10 : Probable nouvelle session -> Vérification temporelle
    
    Args:
        nouvelle_journee: Numéro de la journée détectée sur le site
        
    Returns:
        True si nouvelle session détectée, False sinon
    """
    if nouvelle_journee <= 0:
        return False
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(journee) FROM resultats")
            derniere_j_db = cursor.fetchone()[0] or 0
            
            # PRIORITÉ 1 : Vérifier si la session a été archivée
            cursor.execute("SELECT session_archived, derniere_maj FROM score_ia WHERE id = 1")
            res = cursor.fetchone()
            session_archived = res[0] if res else 0
            derniere_maj_str = res[1] if res and len(res) > 1 else None
            
            # Si session déjà archivée et qu'on a des données, c'est une nouvelle session
            if session_archived == 1 and derniere_j_db > 0:
                print(f"🔄 Session archivée détectée. Nouvelle session commence à J{nouvelle_journee}.")
                return True
    except Exception as e:
        logger.error(f"Erreur lors de la détection de nouvelle session : {e}", exc_info=True)
        return False
    
    # Si pas de données en DB, pas de nouvelle session (c'est le début)
    if derniere_j_db == 0:
        return False

    delta_j = nouvelle_journee - derniere_j_db
    
    # Cas 1 : Reset standard (J38 -> J1) ou grand saut en arrière
    # On ajoute une marge de 10 journées aussi pour le saut en arrière
    if delta_j <= -10:
        print(f"🔄 Reset détecté (J{derniere_j_db} -> J{nouvelle_journee}). Nouvelle session.")
        return True
    
    # Cas 1.5 : Petit saut en arrière (ex: J14 -> J12) = Pas de reset, c'est juste des anciennes données
    if -10 < delta_j < 0:
        print(f"ℹ️ Ancienne journée détectée (J{nouvelle_journee} < J{derniere_j_db}). Pas de changement de session.")
        return False
        
    # Cas 2 : Même session (0 <= Delta < 10)
    if 0 <= delta_j < 10:
        return False
        
    # Cas 3 : Grand saut (Delta >= 10) -> Vérification temporelle
    if delta_j >= 10:
        # Si on n'a pas de date de MAJ, on assume que c'est une nouvelle session
        if not derniere_maj_str:
            print(f"⚠️ Grand saut journées (+{delta_j}) sans date MAJ. Nouvelle session présumée.")
            return True
            
        try:
            derniere_maj = datetime.strptime(derniere_maj_str, "%Y-%m-%d %H:%M:%S")
            diff_temps = (datetime.now() - derniere_maj).total_seconds()
            
            # Si plus de 1 heure (3600s) s'est écoulée, c'est crédible (utilisateurs demandent 1h)
            if diff_temps > 3600: 
                print(f"🕒 Grand saut journées (+{delta_j}) avec délai cohérent ({diff_temps/3600:.1f}h). Nouvelle session.")
                return True
            else:
                print(f"⏳ Grand saut journées (+{delta_j}) mais délai court ({diff_temps/60:.1f}min). Faux positif probable.")
                return False
        except Exception as e:
            # En cas d'erreur de parsing date, on est prudent
            logger.warning(f"Erreur lors du parsing de la date : {e}")
            return False
            
    return False


def archiver_session() -> str:
    """
    Archive toutes les données de la session actuelle dans un fichier CSV.
    Crée un backup de sécurité avant l'archivage.
    
    Returns:
        Chemin du fichier CSV créé
    """
    # ÉTAPE 1 : Backup de sécurité automatique
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(config.DB_NAME), "data", "backup")
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_filename = f"backup_godmod_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    try:
        shutil.copy2(config.DB_NAME, backup_path)
        logger.info(f"📦 Backup créé : {backup_path}")
        print(f"📦 Backup de sécurité créé : {backup_path}")
    except Exception as e:
        logger.error(f"Erreur lors du backup : {e}", exc_info=True)
        print(f"⚠️ Échec du backup (on continue quand même) : {e}")
    
    # ÉTAPE 2 : Créer le dossier archives si nécessaire
    os.makedirs(ARCHIVES_DIR, exist_ok=True)
    
    # Détermination du prochain ID de session
    existing_files = [f for f in os.listdir(ARCHIVES_DIR) if f.startswith("archives_session_") and f.endswith(".csv")]
    max_id = 0
    for f in existing_files:
        try:
            # Extraction du numéro X de archives_session_X.csv
            part = f.replace("archives_session_", "").replace(".csv", "")
            num = int(part)
            if num > max_id:
                max_id = num
        except ValueError:
            pass
            
    next_id = max_id + 1
    filename = f"archives_session_{next_id}.csv"
    filepath = os.path.join(ARCHIVES_DIR, filename)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # --- Section: Résultats ---
                writer.writerow(["=== RESULTATS ==="])
                writer.writerow(["Journee", "Equipe_Dom", "Equipe_Ext", "Score_Dom", "Score_Ext"])
                
                cursor.execute("""
                    SELECT r.journee, e1.nom, e2.nom, r.score_dom, r.score_ext
                    FROM resultats r
                    JOIN equipes e1 ON r.equipe_dom_id = e1.id
                    JOIN equipes e2 ON r.equipe_ext_id = e2.id
                    ORDER BY r.journee, r.id
                """)
                for row in cursor.fetchall():
                    writer.writerow(row)
                
                writer.writerow([])  # Ligne vide
                
                # --- Section: Prédictions ---
                writer.writerow(["=== PREDICTIONS ==="])
                writer.writerow(["Journee", "Equipe_Dom", "Equipe_Ext", "Prediction", "Resultat", "Succes", "Points"])
                
                cursor.execute("""
                    SELECT p.journee, e1.nom, e2.nom, p.prediction, p.resultat, p.succes, p.points_gagnes
                    FROM predictions p
                    JOIN equipes e1 ON p.equipe_dom_id = e1.id
                    JOIN equipes e2 ON p.equipe_ext_id = e2.id
                    ORDER BY p.journee, p.id
                """)
                for row in cursor.fetchall():
                    writer.writerow(row)
                
                writer.writerow([])  # Ligne vide
                
                # --- Section: Score IA ---
                writer.writerow(["=== SCORE IA ==="])
                writer.writerow(["Score_Final", "Predictions_Total", "Predictions_Reussies"])
                
                cursor.execute("SELECT score, predictions_total, predictions_reussies FROM score_ia WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    writer.writerow(row)
                
                writer.writerow([])  # Ligne vide
                
                # --- Section: Classement Final ---
                writer.writerow(["=== CLASSEMENT FINAL ==="])
                writer.writerow(["Equipe", "Points", "Forme"])
                
                cursor.execute("""
                    SELECT e.nom, c.points, c.forme
                    FROM classement c
                    JOIN equipes e ON c.equipe_id = e.id
                    ORDER BY c.points DESC
                """)
                for row in cursor.fetchall():
                    writer.writerow(row)
                
                writer.writerow([])  # Ligne vide

                # --- Section: Matches Global (Historique avec cotes) ---
                writer.writerow(["=== MATCHES GLOBAL (Historique) ==="])
                writer.writerow(["Journee", "Equipe_Dom", "Equipe_Ext", "Cote_1", "Cote_X", "Cote_2", "Status", "Score_Dom", "Score_Ext"])
                
                cursor.execute("""
                    SELECT m.journee, e1.nom, e2.nom, m.cote_1, m.cote_x, m.cote_2, m.status, m.score_dom, m.score_ext
                    FROM matches_global m
                    JOIN equipes e1 ON m.equipe_dom_id = e1.id
                    JOIN equipes e2 ON m.equipe_ext_id = e2.id
                    ORDER BY m.journee
                """)
                for row in cursor.fetchall():
                    writer.writerow(row)
                    
                writer.writerow([])
                
                # --- Section: Classement Global (Historique par journee) ---
                writer.writerow(["=== CLASSEMENT GLOBAL (Historique) ==="])
                writer.writerow(["Journee", "Equipe", "Position", "Points", "Forme"])
                
                cursor.execute("""
                    SELECT cg.journee, e.nom, cg.position, cg.points, cg.forme
                    FROM classement_global cg
                    JOIN equipes e ON cg.equipe_id = e.id
                    ORDER BY cg.journee, cg.position
                """)
                for row in cursor.fetchall():
                    writer.writerow(row)
            
            # ÉTAPE 3 : Marquer la session comme archivée
            cursor.execute("UPDATE score_ia SET session_archived = 1 WHERE id = 1")
            conn.commit()
        
        # Vérification finale
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f"📁 Archive créée avec succès : {filepath}")
            return filepath
        else:
            print(f"❌ Erreur : Le fichier d'archive {filepath} est vide ou non créé.")
            return None
            
    except Exception as e:
        logger.error(f"❌ CRITICAL ERREUR lors de l'archivage : {e}", exc_info=True)
        print(f"❌ CRITICAL ERREUR lors de l'archivage : {e}")
        return None


def reinitialiser_tables_session():
    """
    Réinitialise les tables de données pour une nouvelle session.
    Garde la table 'equipes' intacte et conserve le score IA.
    Réinitialise pause_until et session_archived pour la nouvelle session.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Suppression des données (pas des tables)
            cursor.execute("DELETE FROM resultats")
            cursor.execute("DELETE FROM predictions")
            cursor.execute("DELETE FROM cotes")
            cursor.execute("DELETE FROM classement")
            
            # Réinitialisation pour nouvelle session (score IA conservé)
            cursor.execute("""
                UPDATE score_ia 
                SET predictions_total = 0, 
                    predictions_reussies = 0, 
                    pause_until = 0,
                    session_archived = 0,
                    derniere_maj = NULL
                WHERE id = 1
            """)
    except Exception as e:
        logger.error(f"Erreur lors de la réinitialisation des tables : {e}", exc_info=True)
        print(f"❌ Erreur lors de la réinitialisation : {e}")
        return
    
    print("🔄 Tables réinitialisées pour la nouvelle session. Score IA conservé.")


if __name__ == "__main__":
    # Test manuel
    print("Test du module d'archivage...")
    print(f"Dossier archives : {ARCHIVES_DIR}")
