"""
Outils d'augmentation de données pour renforcer la robustesse de ZEUS.
Simule la volatilité du marché et différentes conditions de capital.
"""

import numpy as np
from typing import List, Dict
import copy


def generer_variantes_cotes(matches: List[Dict], variance: float = 0.05) -> List[List[Dict]]:
    """
    Génère des variantes des matchs en perturbant légèrement les cotes.
    Simule une fluctuation de ±5%.
    """
    variants = []
    
    # Variante 1: Cotes originales
    variants.append(copy.deepcopy(matches))
    
    # Variante 2: Augmentation légère des cotes
    v2 = copy.deepcopy(matches)
    for m in v2:
        m['cote_1'] *= (1 + variance)
        m['cote_x'] *= (1 + variance)
        m['cote_2'] *= (1 + variance)
    variants.append(v2)
    
    # Variante 3: Diminution légère des cotes
    v3 = copy.deepcopy(matches)
    for m in v3:
        m['cote_1'] *= (1 - variance)
        m['cote_x'] *= (1 - variance)
        m['cote_2'] *= (1 - variance)
    variants.append(v3)
    
    return variants


def generer_scenarios_capital(capitaux: List[int] = [10000, 15000, 20000, 25000, 30000]) -> List[int]:
    """
    Génère différents scénarios de capital de départ pour l'entraînement/évaluation.
    """
    return capitaux


def perturber_observation(obs: np.ndarray, noise_level: float = 0.01) -> np.ndarray:
    """
    Ajoute un bruit gaussien léger sur l'observation pour forcer l'IA à être robuste.
    """
    noise = np.random.normal(0, noise_level, obs.shape)
    perturbed_obs = obs + noise
    return np.clip(perturbed_obs, 0.0, 1.0)
