from src.core.database import get_db_connection

def check_counts():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            res = c.execute("SELECT COUNT(*) FROM resultats WHERE score_dom IS NOT NULL").fetchone()[0]
            print(f"Matchs joués en DB: {res}")
            
            cotes = c.execute("SELECT COUNT(*) FROM cotes").fetchone()[0]
            print(f"Cotes en DB: {cotes}")
            
            class_rows = c.execute("SELECT COUNT(*) FROM classement").fetchone()[0]
            print(f"Lignes Classement en DB: {class_rows}")
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    check_counts()
