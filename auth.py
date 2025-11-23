import streamlit as st

def check_password():
    """Retourne True si l'authentification est réussie, sinon False."""
    app_pwd = st.secrets.get("APP_PASSWORD", None)
    if not app_pwd:
        return True

    if st.session_state.get("auth_ok", False):
        return True

    pwd = st.text_input("Mot de passe", type="password")
    if pwd == "":
        return False
    if pwd == app_pwd:
        st.session_state["auth_ok"] = True
        return True
    else:
        st.error("Mot de passe incorrect.")
        return False