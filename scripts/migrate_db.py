"""
Script de migration de la base de données GODMOD V2.
Corrige les incohérences de schéma pour les bases de données existantes.
"""
import sqlite3
import os
import sys

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import config

def migrate_database():
    """Migre la base de données vers le schéma correct."""
    print("=" * 50)
    print("🔄 MIGRATION DE LA BASE DE DONNÉES")
    print("=" * 50)
    
    if not os.path.exists(config.DB_NAME):
        print(f"❌ La base de données '{config.DB_NAME}' n'existe pas.")
        print("   La base sera créée automatiquement au prochain lancement.")
        return
    
    conn = sqlite3.connect(config.DB_NAME)
    cursor = conn.cursor()
    
    try:
        # 1. Migration de la table score_ia
        print("\n📊 Migration de la table score_ia...")
        
        # Vérifier quelles colonnes existent
        cursor.execute("PRAGMA table_info(score_ia)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Ajouter les colonnes manquantes
        if 'score' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE score_ia ADD COLUMN score DECIMAL(10,2) DEFAULT 100.00")
                print("   ✅ Colonne 'score' ajoutée")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de l'ajout de 'score': {e}")
        
        if 'predictions_total' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE score_ia ADD COLUMN predictions_total INTEGER DEFAULT 0")
                print("   ✅ Colonne 'predictions_total' ajoutée")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de l'ajout de 'predictions_total': {e}")
        
        if 'predictions_reussies' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE score_ia ADD COLUMN predictions_reussies INTEGER DEFAULT 0")
                print("   ✅ Colonne 'predictions_reussies' ajoutée")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de l'ajout de 'predictions_reussies': {e}")
        
        if 'pause_until' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE score_ia ADD COLUMN pause_until INTEGER DEFAULT 0")
                print("   ✅ Colonne 'pause_until' ajoutée")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de l'ajout de 'pause_until': {e}")
        
        if 'derniere_maj' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE score_ia ADD COLUMN derniere_maj TEXT")
                print("   ✅ Colonne 'derniere_maj' ajoutée")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de l'ajout de 'derniere_maj': {e}")
        
        # Migrer les données si score_total existe vers score
        if 'score_total' in existing_columns and 'score' in existing_columns:
            try:
                cursor.execute("UPDATE score_ia SET score = score_total WHERE score IS NULL OR score = 100.00")
                print("   ✅ Données migrées de 'score_total' vers 'score'")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de la migration des données: {e}")
        
        # Migrer date_maj vers derniere_maj
        if 'date_maj' in existing_columns and 'derniere_maj' in existing_columns:
            try:
                cursor.execute("UPDATE score_ia SET derniere_maj = date_maj WHERE derniere_maj IS NULL")
                print("   ✅ Données migrées de 'date_maj' vers 'derniere_maj'")
            except sqlite3.OperationalError as e:
                print(f"   ⚠️ Erreur lors de la migration des données: {e}")
        
        # 2. Migration de la table cotes
        print("\n💰 Migration de la table cotes...")
        cursor.execute("PRAGMA table_info(cotes)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Si la table utilise resultat_id, on doit la recréer
        if 'resultat_id' in existing_columns and 'journee' not in existing_columns:
            print("   ⚠️ La table cotes utilise l'ancien schéma (resultat_id).")
            print("   ⚠️ ATTENTION: Les données existantes seront perdues.")
            response = input("   Voulez-vous continuer? (o/n): ")
            if response.lower() != 'o':
                print("   ❌ Migration annulée.")
                conn.close()
                return
            
            # Sauvegarder les données si possible
            cursor.execute("SELECT COUNT(*) FROM cotes")
            count = cursor.fetchone()[0]
            print(f"   📦 {count} entrées seront supprimées.")
            
            # Supprimer et recréer la table
            cursor.execute("DROP TABLE IF EXISTS cotes")
            cursor.execute('''
                CREATE TABLE cotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            print("   ✅ Table cotes recréée avec le nouveau schéma")
        
        # 3. Migration de la table predictions
        print("\n🎯 Migration de la table predictions...")
        cursor.execute("PRAGMA table_info(predictions)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Si la table utilise resultat_id, on doit la recréer
        if 'resultat_id' in existing_columns and 'journee' not in existing_columns:
            print("   ⚠️ La table predictions utilise l'ancien schéma (resultat_id).")
            print("   ⚠️ ATTENTION: Les données existantes seront perdues.")
            response = input("   Voulez-vous continuer? (o/n): ")
            if response.lower() != 'o':
                print("   ❌ Migration annulée.")
                conn.close()
                return
            
            # Sauvegarder les données si possible
            cursor.execute("SELECT COUNT(*) FROM predictions")
            count = cursor.fetchone()[0]
            print(f"   📦 {count} entrées seront supprimées.")
            
            # Supprimer et recréer la table
            cursor.execute("DROP TABLE IF EXISTS predictions")
            cursor.execute('''
                CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            print("   ✅ Table predictions recréée avec le nouveau schéma")
        else:
            # Ajouter la colonne resultat si elle n'existe pas
            if 'resultat' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE predictions ADD COLUMN resultat TEXT")
                    print("   ✅ Colonne 'resultat' ajoutée")
                except sqlite3.OperationalError as e:
                    print(f"   ⚠️ Erreur lors de l'ajout de 'resultat': {e}")
        
        # 4. Vérifier que session_id n'existe pas dans resultats
        print("\n📋 Vérification de la table resultats...")
        cursor.execute("PRAGMA table_info(resultats)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        if 'session_id' in existing_columns:
            print("   ⚠️ La colonne 'session_id' existe mais n'est plus utilisée.")
            print("   ℹ️ Elle peut être supprimée manuellement si nécessaire.")
        
        conn.commit()
        print("\n" + "=" * 50)
        print("✅ MIGRATION TERMINÉE AVEC SUCCÈS")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ ERREUR lors de la migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()

