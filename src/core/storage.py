"""
Module de gestion du stockage distant (Hugging Face Hub).
Permet de synchroniser les modèles ZEUS (.zip) entre le local et le cloud.
"""

import os
import logging
from huggingface_hub import hf_hub_download, HfApi
from . import config

logger = logging.getLogger(__name__)

def download_model_from_hf(local_dir="./models/zeus/best", filename="best_model.zip"):
    """
    Télécharge le modèle depuis Hugging Face Hub.
    """
    if not config.HF_REPO_ID or "/" not in config.HF_REPO_ID:
        logger.warning("HF_REPO_ID non configuré ou invalide. Téléchargement ignoré.")
        return False

    try:
        os.makedirs(local_dir, exist_ok=True)
        local_path = hf_hub_download(
            repo_id=config.HF_REPO_ID,
            filename=filename,
            local_dir=local_dir,
            token=config.HF_TOKEN
        )
        logger.info(f"✅ Modèle téléchargé avec succès depuis HF : {local_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur lors du téléchargement depuis HF : {e}")
        return False

def upload_model_to_hf(local_path, filename="best_model.zip"):
    """
    Upload le modèle vers Hugging Face Hub.
    Nécessite un HF_TOKEN avec droit d'écriture.
    """
    if not config.HF_TOKEN:
        logger.error("HF_TOKEN manquant. Impossible d'uploader le modèle.")
        return False

    if not config.HF_REPO_ID or "/" not in config.HF_REPO_ID:
        logger.error("HF_REPO_ID non configuré ou invalide.")
        return False

    try:
        api = HfApi()
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=filename,
            repo_id=config.HF_REPO_ID,
            token=config.HF_TOKEN
        )
        logger.info(f"✅ Modèle '{filename}' uploadé avec succès sur HF ({config.HF_REPO_ID})")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'upload sur HF : {e}")
        return False
