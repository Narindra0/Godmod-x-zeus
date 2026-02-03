"""
Script utilitaire pour uploader manuellement le modèle ZEUS sur Hugging Face Hub.
Utile pour le premier upload ou après un entraînement local.
"""

import os
import sys
from src.core import config
from src.core.storage import upload_model_to_hf

def main():
    model_path = "./models/zeus/best/best_model.zip"
    
    print("🚀 Préparation de l'upload vers Hugging Face Hub...")
    print(f"📦 Repo cible : {config.HF_REPO_ID}")
    
    if not os.path.exists(model_path):
        print(f"❌ Erreur : Le fichier {model_path} est introuvable.")
        print("Assurez-vous d'avoir entraîné ZEUS localement ou d'avoir placé le fichier .zip au bon endroit.")
        return

    # Vérification du token
    if not config.HF_TOKEN:
        print("❌ Erreur : HF_TOKEN manquant dans votre fichier .env")
        return

    success = upload_model_to_hf(model_path)
    
    if success:
        print("\n✅ Félicitations ! Votre modèle est maintenant en sécurité sur Hugging Face.")
        print("Votre application Streamlit pourra le télécharger automatiquement au prochain démarrage.")
    else:
        print("\n❌ L'upload a échoué. Vérifiez vos permissions de Token (il doit être en mode 'WRITE').")

if __name__ == "__main__":
    main()
