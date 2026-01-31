"""
Orchestrateur de la boucle d'auto-amélioration (Self-Improvement) de ZEUS.
Gère le trigger, l'entraînement global, et la promotion du modèle.
"""

import time
import sqlite3
import os
import logging
from .trainer import train_zeus_agent
from ..database.queries import check_new_season_available, get_last_training_metadata
from ..models.comparison import evaluer_robustesse, doit_promouvoir, deployer_modele
from ..environment.betting_env import BettingEnv
from ...core import config
from stable_baselines3 import PPO

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ZEUS_SELF_IMPROVEMENT")


def enter_deep_sleep():
    """Active le mode sommeil profond pour ZEUS."""
    logger.info("💤 ZEUS Entre en Sommeil Profond...")
    config.ZEUS_DEEP_SLEEP = True


def exit_deep_sleep():
    """Désactive le mode sommeil profond."""
    logger.info("🌅 ZEUS se réveille.")
    config.ZEUS_DEEP_SLEEP = False


def trigger_zeus_improvement(db_path: str = "data/godmod.db"):
    """
    Exécute un cycle complet d'amélioration ZEUS.
    Peut être appelé manuellement ou via un trigger.
    """
    try:
        conn = sqlite3.connect(db_path)
        
        if check_new_season_available(conn):
            logger.info("🔔 Nouvelle saison détectée ! Lancement du cycle d'amélioration...")
            
            # 1. Sommeil Profond
            enter_deep_sleep()
            
            # 2. Récupérer métadonnées actuelles
            last_meta = get_last_training_metadata(conn)
            old_model_path = "./models/zeus/best/best_model.zip"
            
            # 3. Entraînement Global intensif
            # On utilise une version incrémentée
            try:
                version_num = float(last_meta['version'].replace('ZEUS_v', ''))
                new_version = f"ZEUS_v{version_num + 0.1:.1f}"
            except:
                new_version = "ZEUS_v1.0"
            
            logger.info(f"🏋️ Entraînement de la version {new_version} sur tout l'historique...")
            new_model = train_zeus_agent(
                db_path=db_path,
                n_timesteps=500_000, # Entraînement intensif
                version_ia=new_version
            )
            
            # 4. Évaluation et Comparaison
            logger.info("📊 Comparaison des performances...")
            
            # Env d'évaluation (dernière saison)
            eval_env = BettingEnv(db_path=db_path, mode='eval')
            
            # Métriques nouveau modèle
            new_metrics = evaluer_robustesse(new_model, eval_env)
            
            # Métriques ancien modèle (si existant)
            old_metrics = {
                'avg_roi': -100, 'std_roi': 100, 'survival_rate': 0
            }
            
            if os.path.exists(old_model_path):
                old_model = PPO.load(old_model_path)
                old_metrics = evaluer_robustesse(old_model, eval_env)
            
            # 5. Promotion
            if doit_promouvoir(new_metrics, old_metrics):
                logger.info(f"🏆 Promotion de la version {new_version} !")
                deployer_modele(f"./models/zeus/zeus_final_{new_version}.zip")
            else:
                logger.info("❌ Le nouveau modèle n'a pas surpassé l'ancien. Maintien du modèle actuel.")
            
            # 6. Réveil
            exit_deep_sleep()
        else:
            logger.info("ℹ️ Pas assez de nouvelles données pour un réentraînement (besoin d'une saison complète).")
            
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du cycle d'amélioration : {e}")
        exit_deep_sleep() # Sécurité


def run_self_improvement_loop(db_path: str = "data/godmod.db"):
    """
    Boucle principale de monitoring pour l'auto-amélioration.
    """
    logger.info("🔭 Démarrage du moniteur d'auto-amélioration ZEUS (Polling horaire)...")
    
    while True:
        trigger_zeus_improvement(db_path)
        # Vérification toutes les heures
        time.sleep(3600)


if __name__ == "__main__":
    run_self_improvement_loop()
