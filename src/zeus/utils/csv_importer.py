import csv
import os
import sqlite3
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[3]))

from src.core import config
from src.core.database import get_db_connection

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CSV_IMPORTER")

ARCHIVES_DIR = os.path.join(os.path.dirname(config.DB_NAME), "archives")

def get_team_id_map(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, nom FROM equipes")
    return {row[1]: row[0] for row in cursor.fetchall()}

def parse_csv_file(filepath):
    """
    Parses a GODMOD archive CSV and extracts Global Matches and Global Ranking.
    """
    matches = []
    ranking = []
    current_section = None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                
                line = row[0].strip()
                
                if line == "=== MATCHES GLOBAL (Historique) ===":
                    current_section = "MATCHES"
                    next(reader) # skip header
                    continue
                elif line == "=== CLASSEMENT GLOBAL (Historique) ===":
                    current_section = "RANKING"
                    next(reader) # skip header
                    continue
                elif line.startswith("==="):
                    current_section = None
                    continue
                
                if current_section == "MATCHES":
                    # Journee,Equipe_Dom,Equipe_Ext,Cote_1,Cote_X,Cote_2,Status,Score_Dom,Score_Ext
                    matches.append(row)
                elif current_section == "RANKING":
                    # Journee,Equipe,Position,Points,Forme
                    ranking.append(row)
                    
    except Exception as e:
        logger.error(f"Error parsing {filepath}: {e}")
        
    return matches, ranking

def import_session(filepath, session_index, team_map, conn):
    """
    Imports historical data with journee offset to keep linear history.
    """
    matches, ranking = parse_csv_file(filepath)
    if not matches and not ranking:
        logger.warning(f"No data found in {filepath}")
        return
    
    cursor = conn.cursor()
    
    # 38 days per season
    offset = (session_index - 1) * 38
    
    logger.info(f"Importing {filepath} (Session {session_index}, Offset +{offset})")
    
    # 1. Matches
    m_count = 0
    for m in matches:
        try:
            # Journee,Equipe_Dom,Equipe_Ext,Cote_1,Cote_X,Cote_2,Status,Score_Dom,Score_Ext
            j = int(m[0]) + offset
            dom_id = team_map.get(m[1])
            ext_id = team_map.get(m[2])
            
            if not dom_id or not ext_id:
                continue
                
            c1 = float(m[3]) if m[3] else None
            cx = float(m[4]) if m[4] else None
            c2 = float(m[5]) if m[5] else None
            status = m[6]
            sd = int(m[7]) if m[7] else None
            se = int(m[8]) if m[8] else None
            
            # Check for existing
            cursor.execute("""
                SELECT id FROM matches_global 
                WHERE journee = ? AND equipe_dom_id = ? AND equipe_ext_id = ?
            """, (j, dom_id, ext_id))
            
            if cursor.fetchone():
                continue
                
            cursor.execute("""
                INSERT INTO matches_global (journee, equipe_dom_id, equipe_ext_id, cote_1, cote_x, cote_2, status, score_dom, score_ext)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (j, dom_id, ext_id, c1, cx, c2, status, sd, se))
            m_count += 1
        except Exception as e:
            logger.debug(f"Skip match row: {e}")
            
    # 2. Ranking
    r_count = 0
    for r in ranking:
        try:
            # Journee,Equipe,Position,Points,Forme
            j = int(r[0]) + offset
            e_id = team_map.get(r[1])
            
            if not e_id:
                continue
                
            pos = int(r[2]) if r[2] else None
            pts = int(r[3]) if r[3] else 0
            forme = r[4]
            
            # Check for existing
            cursor.execute("""
                SELECT id FROM classement_global 
                WHERE journee = ? AND equipe_id = ?
            """, (j, e_id))
            
            if cursor.fetchone():
                continue
                
            cursor.execute("""
                INSERT INTO classement_global (journee, equipe_id, position, points, forme)
                VALUES (?, ?, ?, ?, ?)
            """, (j, e_id, pos, pts, forme))
            r_count += 1
        except Exception as e:
            logger.debug(f"Skip ranking row: {e}")
            
    conn.commit()
    logger.info(f"Done: {m_count} matches, {r_count} rankings imported.")

def main():
    logger.info("Starting CSV Historical Import...")
    
    if not os.path.exists(ARCHIVES_DIR):
        logger.error(f"Archives directory not found: {ARCHIVES_DIR}")
        return
    
    # List files: archives_session_X.csv
    files = [f for f in os.listdir(ARCHIVES_DIR) if f.startswith("archives_session_") and f.endswith(".csv")]
    
    if not files:
        logger.info("No archive files found.")
        return
        
    # Sort files by session index
    files.sort(key=lambda x: int(x.replace("archives_session_", "").replace(".csv", "")))
    
    with get_db_connection() as conn:
        team_map = get_team_id_map(conn)
        
        for f in files:
            path = os.path.join(ARCHIVES_DIR, f)
            session_idx = int(f.replace("archives_session_", "").replace(".csv", ""))
            import_session(path, session_idx, team_map, conn)
            
    logger.info("Historical Import Complete!")

if __name__ == "__main__":
    main()
