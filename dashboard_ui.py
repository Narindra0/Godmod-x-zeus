import streamlit as st
import pandas as pd
import os
import time
import threading
import logging
from datetime import datetime
from src.core import config
from src.core import database
from src.analysis import intelligence
from src.api.api_monitor import start_monitoring
from src.core.console import console, print_step, print_success, print_error, print_info, print_warning, create_panel, create_table

# Configuration de la page
st.set_page_config(
    page_title="GODMOD V2 - Intelligence Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

logger = logging.getLogger(__name__)

# --- BACKGROUND WORKER (MONITORING) ---
def callback_predictions_ia(journee: int):
    """
    Callback appele automatiquement quand une nouvelle journee est detectee.
    Execute apres la collecte complete des donnees.
    """
    try:
        # 1. Mise a jour du scoring IA
        intelligence.mettre_a_jour_scoring()
        
        # 2. Determiner la prochaine journee
        journee_prediction = journee + 1
        
        if journee_prediction < config.JOURNEE_DEPART_PREDICTION:
            return
        
        # 3. Generation des predictions
        if config.USE_SELECTION_AMELIOREE:
            intelligence.selectionner_meilleurs_matchs_ameliore(journee_prediction)
        else:
            intelligence.selectionner_meilleurs_matchs(journee_prediction)
        
        # 4. Generation des predictions ZEUS
        intelligence.obtenir_predictions_zeus_journee(journee_prediction)
        
        logger.info(f"Analyses terminees pour J{journee_prediction}")
            
    except Exception as e:
        logger.error(f"Erreur dans callback IA : {e}", exc_info=True)

@st.cache_resource
def run_background_worker():
    """
    Lance le monitoring API en arrière-plan (une seule fois par session serveur).
    """
    def worker():
        logger.info("Démarrage du worker de monitoring...")
        # Initialiser DB au démarrage du thread si besoin change
        try:
            database.initialiser_db()
        except Exception as e:
            logger.error(f"Erreur init DB dans worker: {e}")

        # Lancer la boucle infinie
        start_monitoring(
            callback_on_new_journee=callback_predictions_ia,
            verbose=True
        )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread

# Démarrer le worker immédiatement
run_background_worker()


# --- STYLE PREMIUM ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
    
    .main { background-color: #0d1117; }
    
    .stMetric {
        background: linear-gradient(145deg, #161b22, #0d1117);
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #30363d;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    
    .big-font {
        font-family: 'Orbitron', sans-serif;
        font-size: 24px !important;
        font-weight: bold;
        color: #58a6ff;
    }
    
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    
    .status-active {
        color: #238636;
        font-weight: bold;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 0.5; }
        50% { opacity: 1; }
        100% { opacity: 0.5; }
    }
</style>
""", unsafe_allow_html=True)

# --- LOGIQUE DE DONNÉES ---
def safe_read_sql(query, conn):
    """
    Exécute une requête SQL brute et retourne un DataFrame pandas.
    Évite le warning 'pandas only supports SQLAlchemy' avec des connexions brutes.
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()
                return pd.DataFrame(data, columns=columns)
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Erreur SQL pandas : {e} - Query: {query}")
        return pd.DataFrame()

@st.cache_data(ttl=5)
def load_all_data():
    with database.get_db_connection() as conn:
        # Performance
        df_perf = safe_read_sql("SELECT SUM(points_gagnes) as score, COUNT(*) as total FROM predictions WHERE succes IS NOT NULL", conn)
        df_wins = safe_read_sql("SELECT COUNT(*) as wins FROM predictions WHERE succes = 1", conn)
        
        # Score IA global
        df_score_ia = safe_read_sql("SELECT score, predictions_total, predictions_reussies, pause_until FROM score_ia LIMIT 1", conn)
        
        # Prédictions
        df_preds = safe_read_sql("""
            SELECT p.journee as "J", e1.nom as "Domicile", e2.nom as "Exterieur", p.prediction as "Prono", p.resultat as "Reel", p.succes
            FROM predictions p
            JOIN equipes e1 ON p.equipe_dom_id = e1.id
            JOIN equipes e2 ON p.equipe_ext_id = e2.id
            ORDER BY p.id DESC LIMIT 15
        """, conn)
        
        # Résultats réels
        df_results = safe_read_sql("""
            SELECT r.journee as "J", e1.nom as "Domicile", CAST(r.score_dom AS VARCHAR) || ' - ' || CAST(r.score_ext AS VARCHAR) as "Score", e2.nom as "Exterieur"
            FROM resultats r
            JOIN equipes e1 ON r.equipe_dom_id = e1.id
            JOIN equipes e2 ON r.equipe_ext_id = e2.id
            ORDER BY r.journee DESC, r.id DESC
        """, conn)
        
        # Classement
        df_ranking = safe_read_sql("""
            SELECT e.nom as "Equipe", c.points as "Pts", c.forme as "Forme"
            FROM classement c
            JOIN equipes e ON c.equipe_id = e.id
            ORDER BY c.points DESC
        """, conn)
        
        # Trend
        df_trend = safe_read_sql("SELECT id, points_gagnes FROM predictions WHERE succes IS NOT NULL ORDER BY id", conn)
        
        return df_perf, df_wins, df_preds, df_results, df_ranking, df_trend, df_score_ia

# --- INTERFACE ---
st.title("⚡ GODMOD V2 | Intelligence Center")
st.markdown(f"*Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')}*")

if not config.DATABASE_URL and not os.path.exists(config.DB_NAME):
    st.error("⚠️ DATABASE_URL non configuré et BDD locale introuvable.")
else:
    try:
        # Chargement
        df_perf, df_wins, df_preds, df_results, df_ranking, df_trend, df_score_ia = load_all_data()

        score_ia = df_score_ia['score'].iloc[0] if not df_score_ia.empty else 100
        ia_total = df_score_ia['predictions_total'].iloc[0] if not df_score_ia.empty else 0
        ia_wins = df_score_ia['predictions_reussies'].iloc[0] if not df_score_ia.empty else 0
        pause_until = df_score_ia['pause_until'].iloc[0] if not df_score_ia.empty and 'pause_until' in df_score_ia.columns else 0

        score = df_perf['score'].iloc[0] if not df_perf.empty else 0
        wins = df_wins['wins'].iloc[0] if not df_wins.empty else 0
        total_history = df_perf['total'].iloc[0] if not df_perf.empty else 0
        win_rate = (wins / total_history * 100) if total_history > 0 else 0

        # Détermination de la journée actuelle
        current_journee = df_results['J'].max() if not df_results.empty else 0
        current_journee += 1

        # VÉRIFICATION PAUSE
        if pause_until >= current_journee:
            st.error(f"🛑 Renforcement du programme : attendre la journée {pause_until + 1} avant le prochain pronostic fiable.")

        # Metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: st.metric("🤖 Score IA", f"{score_ia} pts")
        with m2: st.metric("Score Global", f"{score} pts")
        with m3: st.metric("Taux de Réussite", f"{win_rate:.1f}%")
        with m4: st.metric("Total Prédictions", f"{ia_wins}/{ia_total}")
        with m5: st.metric("Victoires", wins)

        st.markdown("---")

        col_left, col_right = st.columns([2, 1])

        with col_left:
            tab_preds, tab_results = st.tabs(["🎯 Prédictions", "📜 Derniers Résultats"])
            
            with tab_preds:
                st.subheader("Dernières Prédictions")
                if not df_preds.empty:
                    st.dataframe(df_preds, use_container_width=True, hide_index=True)
                else:
                    st.info("En attente de prédictions...")

            with tab_results:
                st.subheader("Résultats Officiels")
                if not df_results.empty:
                    # Liste des journées disponibles (de la plus récente à la plus ancienne)
                    journees = sorted(df_results['J'].unique().tolist(), reverse=True)
                    journee_selectionnee = st.selectbox(
                        "📅 Sélectionner la journée", 
                        journees, 
                        index=0,
                        key="journee_selector"
                    )
                    # Filtrer les résultats pour la journée sélectionnée
                    df_filtered = df_results[df_results['J'] == journee_selectionnee]
                    st.dataframe(df_filtered, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucun résultat enregistré.")

        with col_right:
            st.subheader("📊 Top Classement")
            if not df_ranking.empty:
                st.dataframe(df_ranking.head(10), use_container_width=True, hide_index=True)
            else:
                st.info("Classement indisponible")
            
            st.subheader("📈 Courbe de Profit")
            if not df_trend.empty:
                df_trend['Cumulative'] = df_trend['points_gagnes'].cumsum()
                st.line_chart(df_trend.set_index('id')['Cumulative'], height=200)

    except Exception as e:
        st.error(f"Erreur lors du chargement des données: {e}")
        logger.error(f"Erreur chargement dashboard: {e}", exc_info=True)

# --- SIDEBAR ---
st.sidebar.title("🛠️ Paramètres")
st.sidebar.markdown(f"**Statut :** <span class='status-active'>LIVE MONITORING</span>", unsafe_allow_html=True)

# Section Intelligence & Sélection Unifiée
st.sidebar.markdown("---")
st.sidebar.subheader("🧠 Intelligence & Sélection")

# Récupérer l'état actuel
current_intelligence_state = config.USE_INTELLIGENCE_AMELIOREE

# Toggle unique pour tout activer/désactiver
new_intelligence_state = st.sidebar.toggle(
    "Intelligence Complète",
    value=current_intelligence_state,
    help="Active simultanément le Mode Multi-Facteurs et la Phase 3 (Sélection Améliorée)"
)

# Si l'état a changé
if new_intelligence_state != current_intelligence_state:
    from src.core import utils
    # Mise à jour globale des deux flags
    if utils.update_global_intelligence_flags(new_intelligence_state):
        # Recharger les modules
        import importlib
        import sys
        if 'src.core.config' in sys.modules:
            importlib.reload(sys.modules['src.core.config'])
            # Recharger intelligence si chargé
            if 'src.analysis.intelligence' in sys.modules:
                importlib.reload(sys.modules['src.analysis.intelligence'])
        
        # Feedback utilisateur
        if new_intelligence_state:
            st.sidebar.success("✅ Mode Intelligence Complète activé !")
        else:
            st.sidebar.info("ℹ️ Retour au Mode Standard")
        
        # Rafraîchir
        time.sleep(0.5)
        st.rerun()
    else:
        st.sidebar.error("❌ Erreur de mise à jour configuration")

# Affichage du statut
if current_intelligence_state:
    st.sidebar.markdown(
        """
        <div style='background-color: rgba(35, 134, 54, 0.2); padding: 10px; border-radius: 5px; border-left: 3px solid #238636;'>
            <span style='color: #238636; font-weight: bold;'>🟢 SYSTÈME ACTIF</span>
        </div>
        """, 
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        """
        <div style='background-color: rgba(248, 81, 73, 0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #f85149;'>
            <span style='color: #f85149; font-weight: bold;'>🔴 MODE SIMPLE</span>
        </div>
        """, 
        unsafe_allow_html=True
    )

st.sidebar.markdown("---")
refresh = st.sidebar.slider("Rafraîchissement (sec)", 2, 30, 5)

# Auto-refresh actif par défaut
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
if auto_refresh:
    time.sleep(refresh)
    st.rerun()
