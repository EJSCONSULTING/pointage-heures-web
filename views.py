import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import database as db  # On importe notre fichier database.py

def ui_manual_entry():
    clients = db.load_clients()
    tasks = db.load_tasks()
    providers = db.load_providers()

    st.subheader("Encodage manuel")
    col1, col2 = st.columns(2)

    with col1:
        provider = st.selectbox("Prestataire", options=providers, key="prov_man") if providers else st.text_input("Prestataire", key="prov_man_txt")
        client = st.selectbox("Client", options=[""] + clients, key="cli_man")
        task = st.selectbox("Tâche", options=[""] + list(tasks.keys()), key="task_man")

        if "last_task" not in st.session_state: st.session_state.last_task = ""
        if "rate_saisie" not in st.session_state: st.session_state.rate_saisie = 0.0

        if task and task != st.session_state.last_task:
            st.session_state.last_task = task
            st.session_state.rate_saisie = float(tasks.get(task, 0.0))

        rate = st.number_input("Tarif horaire (€ / h)", min_value=0.0, step=1.0, key="rate_saisie")

    with col2:
        start_date = st.date_input("Date début", value=date.today(), key="man_start_d")
        start_time = st.time_input("Heure début", value=time(9, 0), key="man_start_t")
        end_date = st.date_input("Date fin", value=date.today(), key="man_end_d")
        end_time = st.time_input("Heure fin", value=time(10, 0), key="man_end_t")

    description = st.text_area("Description", key="desc_man")

    if st.button("Enregistrer"):
        if not all([provider, client, task]):
            st.error("Champs manquants.")
        else:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)
            if end_dt <= start_dt:
                st.error("Erreur de date.")
            else:
                h, t = db.insert_prestation(provider, client, task, description, start_dt, end_dt, rate)
                st.success(f"Enregistré : {h} h – {t} €")
                db.clear_prestations_cache()

def ui_timer():
    clients = db.load_clients()
    tasks = db.load_tasks()
    providers = db.load_providers()

    st.subheader("Timer")
    if "timer_running" not in st.session_state: st.session_state.timer_running = False

    provider = st.selectbox("Prestataire", options=providers, key="timer_prov") if providers else st.text_input("Prestataire", key="timer_prov_txt")
    client = st.selectbox("Client", options=[""] + clients, key="timer_cli")
    task = st.selectbox("Tâche", options=[""] + list(tasks.keys()), key="timer_task")
    desc = st.text_area("Description", key="timer_desc")

    if not st.session_state.timer_running:
        if st.button("Démarrer"):
            if all([provider, client, task]):
                st.session_state.update({
                    "timer_running": True, "timer_start": datetime.now(),
                    "t_prov": provider, "t_cli": client, "t_task": task, "t_desc": desc
                })
                st.rerun()
            else: st.error("Remplissez tout.")
    else:
        elapsed = datetime.now() - st.session_state.timer_start
        st.info(f"En cours depuis : {elapsed}")
        if st.button("Arrêter et enregistrer"):
            rate = float(tasks.get(st.session_state.t_task, 0.0))
            h, t = db.insert_prestation(st.session_state.t_prov, st.session_state.t_cli, st.session_state.t_task, st.session_state.t_desc, st.session_state.timer_start, datetime.now(), rate)
            st.success(f"Terminé : {h} h - {t} €")
            st.session_state.timer_running = False
            db.clear_prestations_cache()

def ui_historique():
    st.subheader("Historique")
    inv = None if st.checkbox("Voir archivées") else False
    
    # Filtres
    c1, c2, c3 = st.columns(3)
    prov = c1.selectbox("Prestataire", ["(Tous)"] + db.load_providers())
    cli = c2.selectbox("Client", ["(Tous)"] + db.load_clients())
    tsk = c3.selectbox("Tâche", ["(Tous)"] + list(db.load_tasks().keys()))
    
    if st.button("Filtrer"):
        df = db.load_prestations_filtered(provider=prov, client=cli, task=tsk, invoiced=inv)
    else:
        df = db.load_prestations_filtered(invoiced=inv)

    st.dataframe(df, use_container_width=True)
    
    # Suppression
    to_del = st.multiselect("Supprimer (ID)", df["ID"].tolist())
    if st.button("Supprimer sélection") and to_del:
        db.delete_prestations(to_del)
        db.clear_prestations_cache()
        st.rerun()

def ui_dashboard():
    st.subheader("Dashboard")
    df = db.load_prestations_filtered()
    if df.empty:
        st.info("Rien à afficher")
        return
    c1, c2 = st.columns(2)
    c1.metric("Total Heures", f"{df['Heures'].sum():.2f}")
    c2.metric("Total Euros", f"{df['Total €'].sum():.2f}")
    st.bar_chart(df.groupby("Client")["Total €"].sum())

def ui_facturation():
    st.subheader("Facturation")
    # Logique simplifiée pour l'exemple
    clients = db.load_clients()
    cli = st.selectbox("Client à facturer", ["(Tous)"] + clients)
    df = db.load_prestations_filtered(client=cli if cli != "(Tous)" else None, invoiced=False)
    
    st.dataframe(df)
    sel = st.multiselect("IDs à facturer", df["ID"].tolist())
    ref = st.text_input("Réf facture")
    if st.button("Valider facturation") and sel:
        db.mark_prestations_invoiced(sel, ref)
        db.clear_prestations_cache()
        st.success("Facturé !")

def ui_gestion():
    st.subheader("Administration")
    c1, c2 = st.columns(2)
    with c1:
        new_c = st.text_input("Nouveau Client")
        if st.button("Ajouter Client") and new_c:
            db.add_or_reactivate_client(new_c)
            st.success("OK")
            db.load_clients.clear()
    with c2:
        st.dataframe(db.load_all_clients())