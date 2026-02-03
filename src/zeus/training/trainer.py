"""
Pipeline d'entraînement principal pour ZEUS.
"""

import os
from typing import Optional
from ..environment.betting_env import BettingEnv
from ..environment.betting_env import BettingEnv
from ..models.ppo_agent import create_ppo_agent, create_callbacks
from ..database.queries import get_available_seasons
from ...core.database import get_db_connection


def train_zeus_agent(
    db_path: str = "data/godmod.db",
    n_timesteps: int = 1_000_000,
    checkpoint_freq: int = 50_000,
    eval_freq: int = 10_000,
    learning_rate: float = 3e-4,
    version_ia: str = "v1.0",
    journee_debut_train: Optional[int] = None,
    journee_fin_train: Optional[int] = None,
    journee_debut_eval: Optional[int] = None,
    journee_fin_eval: Optional[int] = None
):
    """
    Entraîne l'agent ZEUS avec validation.
    
    Args:
        db_path: Chemin vers la base SQLite
        n_timesteps: Nombre total de timesteps d'entraînement
        checkpoint_freq: Fréquence de sauvegarde des checkpoints
        eval_freq: Fréquence d'évaluation
        learning_rate: Taux d'apprentissage
        version_ia: Version du modèle
        journee_debut_train: Première journée d'entraînement
        journee_fin_train: Dernière journée d'entraînement
        journee_debut_eval: Première journée d'évaluation
        journee_fin_eval: Dernière journée d'évaluation
        
    Returns:
        Modèle PPO entraîné
    """
    print("=" * 60)
    print("🏛️  ZEUS - Entraînement de l'agent RL")
    print("=" * 60)
    
    # Auto-détecter les saisons si non spécifié
    if journee_debut_train is None:
        with get_db_connection() as conn:
            seasons = get_available_seasons(conn)
        
        if len(seasons) < 2:
            raise ValueError(
                f"Pas assez de données. Trouvé {len(seasons)} saison(s), "
                "besoin d'au moins 2 pour train/eval."
            )
        
        # Utiliser toutes les saisons sauf la dernière pour le train
        journee_debut_train = seasons[0]
        journee_fin_train = seasons[-2] + 37  # Une saison = 38 journées
        
        # Dernière saison pour l'évaluation
        journee_debut_eval = seasons[-1]
        journee_fin_eval = journee_debut_eval + 37
        
        print(f"📊 Train: Journées {journee_debut_train} à {journee_fin_train}")
        print(f"📊 Eval:  Journées {journee_debut_eval} à {journee_fin_eval}")
    
    # Créer les environnements
    print("\n🔧 Création des environnements...")
    train_env = BettingEnv(
        db_path=db_path,
        capital_initial=20000,
        journee_debut=journee_debut_train,
        journee_fin=journee_fin_train,
        mode='train',
        version_ia=version_ia
    )
    
    eval_env = BettingEnv(
        db_path=db_path,
        capital_initial=20000,
        journee_debut=journee_debut_eval,
        journee_fin=journee_fin_eval,
        mode='eval',
        version_ia=version_ia
    )
    
    # Créer l'agent
    print("🧠 Création de l'agent PPO...")
    model = create_ppo_agent(
        train_env,
        learning_rate=learning_rate,
        tensorboard_log="./logs/zeus/",
        verbose=1
    )
    
    # Créer les callbacks
    print("📋 Configuration des callbacks...")
    callbacks = create_callbacks(
        eval_env=eval_env,
        checkpoint_freq=checkpoint_freq,
        eval_freq=eval_freq
    )
    
    # Entraîner
    print(f"\n🚀 Début de l'entraînement ({n_timesteps:,} timesteps)...")
    print("📊 Suivez la progression avec: tensorboard --logdir ./logs/zeus/")
    print("-" * 60)
    
    model.learn(
        total_timesteps=n_timesteps,
        callback=callbacks,
        progress_bar=True
    )
    
    # Sauvegarder le modèle final
    os.makedirs("./models/zeus/", exist_ok=True)
    final_model_path = f"./models/zeus/zeus_final_{version_ia}"
    model.save(final_model_path)
    
    print("\n" + "=" * 60)
    print(f"✅ Entraînement terminé!")
    print(f"📦 Modèle sauvegardé: {final_model_path}.zip")
    print(f"🏆 Meilleur modèle: ./models/zeus/best/best_model.zip")
    print("=" * 60)
    
    # Fermer les environnements
    train_env.close()
    eval_env.close()
    
    return model


if __name__ == "__main__":
    # Exemple d'utilisation
    train_zeus_agent(
        db_path="data/godmod.db",
        n_timesteps=100_000,  # 100k pour test rapide
        version_ia="v1.0_test"
    )
