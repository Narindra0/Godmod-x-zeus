"""
Systeme de surveillance continue de l'API
Detecte automatiquement les nouvelles journees et declenche les collectes

Version: 2.1
Date: Janvier 2025
"""

import time
import random
import logging
import sys
import os
from typing import Optional, Dict
from datetime import datetime

# Ajouter le chemin du projet
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.api.api_client import get_recent_results, get_ranking, get_upcoming_matches
from src.api.results_filter import extract_results_minimal
from src.api.matches_filter import extract_matches_with_local_ids
from src.api.db_integration import insert_api_ranking, insert_api_results, insert_api_matches
from src.core.database import get_db_connection
from src.core.archive import archiver_session, reinitialiser_tables_session
from src.core.console import console, print_info, print_success, print_error, print_warning, print_step, create_panel, create_table
import threading
from src.zeus.training.self_improvement import trigger_zeus_improvement



logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

MONITOR_CONFIG = {
    "POLL_INTERVAL": 5,            # Verifier toutes les 5 secondes (Mise a jour "Live")
    "MAX_RETRIES": 3,              # Nombre de tentatives si erreur
    "RETRY_DELAY": 10,             # Delai entre tentatives (secondes)
    "LOG_ACTIVITY": True,          # Logger l'activite
}

# ==================== FONCTIONS HELPER ====================

def get_max_journee_in_db() -> int:
    """
    Recupere la derniere journee presente en base de donnees
    
    Returns:
        Numero de la derniere journee (0 si vide)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(journee) FROM resultats")
            result = cursor.fetchone()[0]
            return result if result else 0
    except Exception as e:
        logger.error(f"Erreur lors de la recuperation de la journee max : {e}")
        return 0


def get_max_journee_from_api() -> Optional[int]:
    """
    Recupere la derniere journee disponible sur l'API via les resultats
    
    Returns:
        Numero de la derniere journee ou None si erreur
    """
    try:
        # Recuperer les 2 dernieres journees pour etre sur
        results_raw = get_recent_results(skip=0, take=2)
        results_filtered = extract_results_minimal(results_raw)
        
        if results_filtered:
            # Trouver la journee max
            max_journee = max(r["roundNumber"] for r in results_filtered)
            return max_journee
        
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la recuperation journee API : {e}")
        return None


def get_journee_from_cotes() -> Optional[int]:
    """
    Recupere la premiere journee disponible dans les cotes (pour detecter nouvelle saison)
    
    Returns:
        Numero de la journee dans les cotes ou None si erreur
    """
    try:
        matches_raw = get_upcoming_matches()
        matches_filtered = extract_matches_with_local_ids(matches_raw, limit=1)
        
        if matches_filtered and len(matches_filtered) > 0:
            # La premiere journee dans les cotes
            first_journee = matches_filtered[0].get("roundNumber")
            if first_journee:
                return first_journee
        
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la recuperation journee depuis cotes : {e}")
        return None


def collect_full_data(journee: int) -> bool:
    """
    Collecte complete des donnees pour une nouvelle journee detectee
    
    Args:
        journee: Numero de la journee detectee
        
    Returns:
        True si succes, False sinon
    """
    logger.info(f"[COLLECTE] Demarrage collecte complete pour journee {journee}")
    console.print()
    console.rule(f"[bold green]NOUVELLE JOURNEE DETECTEE : J{journee}[/]")
    console.print()
    
    success = True
    
    # 1. Recuperer les resultats
    print_step("Recuperation des resultats")
    try:
        results_raw = get_recent_results(skip=0, take=4)
        results_filtered = extract_results_minimal(results_raw)
        
        if results_filtered:
            count, validated = insert_api_results(results_filtered)
            print_success(f"{count} resultats inseres (+{validated} valides)")
            logger.info(f"[COLLECTE] Resultats : {count} inseres, {validated} valides")
        else:
            print_warning("Aucun resultat recupere")
            success = False
    except Exception as e:
        print_error(f"Erreur resultats : {e}")
        logger.error(f"[COLLECTE] Erreur resultats : {e}")
        success = False
    
    # Pause aleatoire pour eviter les rafales (Stealth mais rapide)
    time.sleep(random.uniform(0.5, 1.5))

    # 2. Recuperer le classement
    print_step("Recuperation du classement")
    try:
        ranking_data = get_ranking()
        
        if ranking_data:
            count = insert_api_ranking(ranking_data)
            print_success(f"{count} equipes inserees")
            logger.info(f"[COLLECTE] Classement insere : {count} equipes")
        else:
            print_warning("Aucune equipe recuperee")
            success = False
    except Exception as e:
        print_error(f"Erreur classement : {e}")
        logger.error(f"[COLLECTE] Erreur classement : {e}")
        success = False
    
    # Pause aleatoire pour eviter les rafales (Stealth mais rapide)
    time.sleep(random.uniform(0.5, 1.5))

    # 3. Recuperer les cotes pour J+1
    journee_cotes = journee + 1
    print_step(f"Recuperation des cotes pour J{journee_cotes}")
    try:
        matches_raw = get_upcoming_matches()
        matches_filtered = extract_matches_with_local_ids(matches_raw, limit=2)
        
        if matches_filtered:
            count = insert_api_matches(matches_filtered)
            print_success(f"{count} matchs avec cotes inseres")
            logger.info(f"[COLLECTE] Cotes inserees : {count} matchs")
        else:
            print_warning("Aucune cote recuperee")
    except Exception as e:
        print_error(f"Erreur cotes : {e}")
        logger.error(f"[COLLECTE] Erreur cotes : {e}")
        # Les cotes ne sont pas critiques, on ne met pas success=False
    
    console.print()
    if success:
        console.rule("[bold green]COLLECTE TERMINEE AVEC SUCCES[/]")
    else:
        console.rule("[bold yellow]COLLECTE TERMINEE AVEC AVERTISSEMENTS[/]")
    console.print()
    
    return success


# ==================== BOUCLE DE SURVEILLANCE ====================

def start_monitoring(callback_on_new_journee=None, verbose=True):
    """
    Demarre la surveillance continue de l'API
    
    Args:
        callback_on_new_journee: Fonction optionnelle a appeler apres collecte
        verbose: Afficher les messages de surveillance
        
    Example:
        def my_callback(journee):
            print(f"Nouvelle journee {journee} traitee !")
            # Lancer predictions IA, etc.
        
        start_monitoring(callback_on_new_journee=my_callback)
    """
    logger.info("[MONITOR] Demarrage de la surveillance API")
    console.print()
    console.print(create_panel(
        "Mode: Detection automatique nouvelles journees\n" +
        f"Intervalle: {MONITOR_CONFIG['POLL_INTERVAL']}s",
        title="SURVEILLANCE API ACTIVEE",
        style="green"
    ))
    
    last_journee_db = get_max_journee_in_db()
    logger.info(f"[MONITOR] Journee initiale en BDD : J{last_journee_db}")
    print_info(f"Journee actuelle en BDD : J{last_journee_db}")
    print_info("Surveillance en cours... (CTRL+C pour arreter)")
    console.print()
    
    consecutive_errors = 0
    
    try:
        while True:
            try:
                # Verifier l'API
                api_journee = get_max_journee_from_api()
                
                # Si les resultats sont vides (fin de saison), verifier les cotes pour J1
                journee_cotes = None
                if api_journee is None:
                    journee_cotes = get_journee_from_cotes()
                    logger.info(f"[MONITOR] Resultats vides, verification cotes -> J{journee_cotes}")
                
                if api_journee is None and journee_cotes is None:
                    consecutive_errors += 1
                    
                    # Backoff exponentiel : 10s, 20s, 40s, 80s... max 5min (300s)
                    wait_time = min(MONITOR_CONFIG['RETRY_DELAY'] * (2 ** (consecutive_errors - 1)), 300)
                    
                    logger.warning(f"[MONITOR] Impossible de recuperer journee API (Erreur {consecutive_errors}). Nouvelle tentative dans {wait_time}s")
                    print_warning(f"Erreur connexion API ({consecutive_errors}). Attente {wait_time}s...")
                    
                    # On ne break plus jamais la boucle, on attend juste plus longtemps
                    time.sleep(wait_time)
                    continue

                
                # Reset compteur erreurs si succes
                consecutive_errors = 0
                
                # --- LOGIQUE DE TRANSITION DE SAISON ---
                
                # 1. Fin de Saison (J37 -> J38)
                # Si on est a J37 et que l'API annonce J38, on ignore J38 pour preparer la transition
                if last_journee_db == 37 and api_journee == 38:
                    if verbose and MONITOR_CONFIG["LOG_ACTIVITY"]:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        console.print(f"[{timestamp}] [INFO] Fin de saison (J38) detectee. En attente de J1...", end='\r')
                    time.sleep(MONITOR_CONFIG['POLL_INTERVAL'])
                    continue

                # 2. Nouvelle Saison (Detection J1 via cotes)
                # Si on etait en fin de saison (>=37) OU si la BDD est vide et qu'on voit J1 dans les cotes -> RESET
                if journee_cotes == 1 and (last_journee_db >= 37 or last_journee_db == 0):
                    logger.info(f"[MONITOR] Nouvelle saison detectee via cotes : J1 (Ancienne: J{last_journee_db})")
                    console.print()
                    console.rule("[bold magenta]NOUVELLE SAISON DETECTEE (J1) ![/]")
                    print_info(f"Transition J{last_journee_db} -> J1")
                    print_info("Detection via les cotes (resultats vides)")
                    
                    # A. Archiver
                    print_step("Archivage de la saison terminee")
                    fichier = archiver_session()
                    if fichier:
                        print_success(f"Archive creee : {fichier}")
                    
                    # B. Reinitialiser
                    print_step("Reinitialisation de la base de donnees")
                    reinitialiser_tables_session()
                    last_journee_db = 0
                    print_success("Tables reinitialisees")
                    
                    # D. Lancer reentrainement ZEUS en arriere-plan
                    print_info("Lancement du cycle d'amélioration ZEUS en arrière-plan...")
                    threading.Thread(target=trigger_zeus_improvement, daemon=True).start()
                    
                    # C. Collecter J1 (cotes seulement, resultats vides)
                    print_step("Collecte des cotes pour J1 (resultats non disponibles)")
                    try:
                        matches_raw = get_upcoming_matches()
                        matches_filtered = extract_matches_with_local_ids(matches_raw, limit=2)
                        
                        if matches_filtered:
                            count = insert_api_matches(matches_filtered)
                            print_success(f"{count} matchs avec cotes inseres pour J1")
                            logger.info(f"[COLLECTE] Cotes J1 inserees : {count} matchs")
                            last_journee_db = 1
                            
                            # Callback IA (optionnel pour J1)
                            if callback_on_new_journee:
                                callback_on_new_journee(1)
                        else:
                            print_warning("Aucune cote recuperee pour J1")
                    except Exception as e:
                        print_error(f"Erreur cotes J1 : {e}")
                        logger.error(f"[COLLECTE] Erreur cotes J1 : {e}")
                    
                    continue

                # --- LOGIQUE STANDARD ---
                
                # Comparer avec BDD (seulement si l'API a retourne une journee)
                if api_journee is not None and api_journee > last_journee_db:
                    # NOUVELLE JOURNEE DETECTEE !
                    logger.info(f"[MONITOR] Nouvelle journee detectee : J{api_journee} (BDD: J{last_journee_db})")
                    console.print()
                    console.rule(f"[bold green]ALERTE : Nouvelle journee detectee ![/]")
                    print_info(f"BDD : J{last_journee_db} -> API : J{api_journee}")
                    
                    # Collecte complete
                    success = collect_full_data(api_journee)
                    
                    if success:
                        # Mettre a jour notre reference
                        last_journee_db = api_journee
                        logger.info(f"[MONITOR] Reference mise a jour : J{last_journee_db}")
                        
                        # Appeler le callback si fourni
                        if callback_on_new_journee:
                            try:
                                logger.info(f"[MONITOR] Appel callback utilisateur pour J{api_journee}")
                                callback_on_new_journee(api_journee)
                            except Exception as e:
                                logger.error(f"[MONITOR] Erreur dans callback utilisateur : {e}")
                                print_error(f"Erreur dans callback : {e}")
                    else:
                        logger.warning(f"[MONITOR] Collecte incomplete pour J{api_journee}, nouvelle tentative au prochain cycle")
                        print_warning(f"Collecte incomplete, nouvelle tentative dans {MONITOR_CONFIG['POLL_INTERVAL']}s")
                
                elif verbose and MONITOR_CONFIG["LOG_ACTIVITY"]:
                    # Message de surveillance
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    console.print(f"[{timestamp}] [dim]Surveillance... (BDD: J{last_journee_db}, API: J{api_journee})[/]", end='\r')
                
                # Attendre avant prochain check (Jitter: +/- 40% de l'intervalle -> 3s a 7s)
                base_interval = MONITOR_CONFIG['POLL_INTERVAL']
                jitter = base_interval * 0.4
                sleep_time = random.uniform(base_interval - jitter, base_interval + jitter)
                
                if verbose:
                     # Petit hack visuel pour le timer
                     pass 
                     
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                raise  # Propager pour sortir proprement
            except Exception as e:
                logger.error(f"[MONITOR] Erreur dans boucle surveillance : {e}", exc_info=True)
                print_error(f"Erreur surveillance : {e}")
                consecutive_errors += 1
                
                if consecutive_errors >= MONITOR_CONFIG['MAX_RETRIES']:
                    logger.error("[MONITOR] Trop d'erreurs, arret surveillance")
                    break
                
                time.sleep(MONITOR_CONFIG['RETRY_DELAY'])
    
    except KeyboardInterrupt:
        console.print()
        console.rule("[bold red]STOP[/]")
        print_warning("Arret surveillance (utilisateur)")
        logger.info("[MONITOR] Arret surveillance par utilisateur")
    
    finally:
        logger.info(f"[MONITOR] Fin surveillance - Derniere journee: J{last_journee_db}")


# ==================== TEST ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Callback de test
    def callback_test(journee):
        print(f"\n[CALLBACK] Nouvelle journee {journee} traitee !")
        print(f"[CALLBACK] Vous pouvez maintenant lancer les predictions IA...")
    
    # Demarrer la surveillance
    start_monitoring(callback_on_new_journee=callback_test, verbose=True)
