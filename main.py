import streamlit as st
from pathlib import Path

# Import des modules que nous venons de créer
import database as db
import auth
import views

LOGO_PATH = "logo_ejs.png"

def main():
    st.set_page_config(page_title="EJS – Pointage", page_icon=LOGO_PATH, layout="wide")

    # Header
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        if Path(LOGO_PATH).exists():
            st.image(LOGO_PATH, width=70)
    with col_title:
        st.title("EJS – Pointage des heures")

    # Sécurité
    if not auth.check_password():
        return

    # Initialisation DB
    if "defaults_done" not in st.session_state:
        db.ensure_default_tasks()
        st.session_state["defaults_done"] = True

    # Navigation
    mobile_mode = st.sidebar.checkbox("Mode mobile", value=False)

    if mobile_mode:
        page = st.sidebar.radio("Menu", ["Timer", "Saisie", "Factures", "Historique"])
        if page == "Timer": views.ui_timer()
        elif page == "Saisie": views.ui_manual_entry()
        elif page == "Factures": views.ui_facturation()
        elif page == "Historique": views.ui_historique()
    else:
        t1, t2, t3, t4, t5 = st.tabs(["Saisie", "Historique", "Dashboard", "Facturation", "Admin"])
        with t1:
            st1, st2 = st.tabs(["Manuel", "Timer"])
            with st1: views.ui_manual_entry()
            with st2: views.ui_timer()
        with t2: views.ui_historique()
        with t3: views.ui_dashboard()
        with t4: views.ui_facturation()
        with t5: views.ui_gestion()

if __name__ == "__main__":
    main()