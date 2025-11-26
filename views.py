import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import database as db
import plotly.express as px

# --- 1. ENCODAGE MANUEL ---
def ui_manual_entry():
    # On utilise un conteneur avec bordure pour délimiter la zone de saisie
    with st.container(border=True):
        st.subheader("📝 Nouvel encodage")
        
        clients = db.load_clients()
        tasks = db.load_tasks()
        providers = db.load_providers()

        col1, col2 = st.columns(2)

        with col1:
            # Choix du prestataire
            if providers:
                provider = st.selectbox("Prestataire", options=providers, key="prov_man")
            else:
                provider = st.text_input("Prestataire", key="prov_man_txt")
            
            client = st.selectbox("Client", options=[""] + clients, key="cli_man")
            
            # Logique dynamique pour le tarif
            task = st.selectbox("Tâche", options=[""] + list(tasks.keys()), key="task_man")
            
            if "last_task" not in st.session_state: st.session_state.last_task = ""
            if "rate_saisie" not in st.session_state: st.session_state.rate_saisie = 0.0

            if task and task != st.session_state.last_task:
                st.session_state.last_task = task
                st.session_state.rate_saisie = float(tasks.get(task, 0.0))

            rate = st.number_input("Tarif horaire (€/h)", min_value=0.0, step=5.0, key="rate_saisie")

        with col2:
            c_date1, c_time1 = st.columns(2)
            with c_date1: start_date = st.date_input("Date début", value=date.today(), key="man_start_d")
            with c_time1: start_time = st.time_input("Heure", value=time(9, 0), key="man_start_t")
            
            c_date2, c_time2 = st.columns(2)
            with c_date2: end_date = st.date_input("Date fin", value=date.today(), key="man_end_d")
            with c_time2: end_time = st.time_input("Heure", value=time(10, 0), key="man_end_t")
            
            description = st.text_area("Description / Notes", height=100, key="desc_man")

        # Bouton large et coloré (type 'primary')
        if st.button("💾 Enregistrer la prestation", type="primary", use_container_width=True):
            if not all([provider, client, task]):
                st.error("⚠️ Veuillez remplir le Prestataire, le Client et la Tâche.")
            else:
                start_dt = datetime.combine(start_date, start_time)
                end_dt = datetime.combine(end_date, end_time)
                
                if end_dt <= start_dt:
                    st.error("⚠️ La date de fin doit être après le début.")
                else:
                    h, t = db.insert_prestation(provider, client, task, description, start_dt, end_dt, rate)
                    st.success(f"✅ Prestation enregistrée : **{h} h** pour **{t} €**")
                    db.clear_prestations_cache()

# --- 2. TIMER ---
def ui_timer():
    clients = db.load_clients()
    tasks = db.load_tasks()
    providers = db.load_providers()

    if "timer_running" not in st.session_state: st.session_state.timer_running = False

    # Affichage différent selon l'état du timer
    if not st.session_state.timer_running:
        with st.container(border=True):
            st.subheader("⏱️ Lancer le chrono")
            c1, c2 = st.columns(2)
            with c1:
                prov = st.selectbox("Prestataire", options=providers, key="t_prov_sel") if providers else st.text_input("Prestataire", key="t_prov_txt")
                cli = st.selectbox("Client", options=[""] + clients, key="t_cli_sel")
            with c2:
                tsk = st.selectbox("Tâche", options=[""] + list(tasks.keys()), key="t_task_sel")
                desc = st.text_input("Description rapide", key="t_desc_in")
            
            st.write("") # Espace
            if st.button("▶️ Démarrer", type="primary", use_container_width=True):
                if all([prov, cli, tsk]):
                    st.session_state.update({
                        "timer_running": True, "timer_start": datetime.now(),
                        "t_prov": prov, "t_cli": cli, "t_task": tsk, "t_desc": desc
                    })
                    st.rerun()
                else:
                    st.error("Champs manquants")
    else:
        # ÉTAT EN COURS
        st.info(f"⏳ **Timer en cours** pour **{st.session_state.t_cli}** ({st.session_state.t_task})")
        
        col_metric1, col_metric2 = st.columns(2)
        start_time = st.session_state.timer_start
        elapsed = datetime.now() - start_time
        
        # On enlève les microsecondes pour l'affichage
        elapsed_clean = str(elapsed).split('.')[0] 
        
        col_metric1.metric("Heure de début", start_time.strftime("%H:%M"))
        col_metric2.metric("Temps écoulé", elapsed_clean)

        if st.button("⏹️ Arrêter et Enregistrer", type="primary", use_container_width=True):
            rate = float(tasks.get(st.session_state.t_task, 0.0))
            end_time = datetime.now()
            h, t = db.insert_prestation(
                st.session_state.t_prov, st.session_state.t_cli, st.session_state.t_task, 
                st.session_state.t_desc, st.session_state.timer_start, end_time, rate
            )
            st.balloons() # Petit effet sympa
            st.success(f"✅ Terminé : {h} h — {t} €")
            st.session_state.timer_running = False
            db.clear_prestations_cache()
            st.rerun()

# --- 3. HISTORIQUE ---
def ui_historique():
    st.subheader("📚 Historique")

    # Zone de filtres repliable pour gagner de la place
    with st.expander("🔍 Filtres et Options", expanded=False):
        include_invoiced = st.checkbox("Voir aussi les archives (facturées)", value=False)
        invoiced_filter = None if include_invoiced else False

        c1, c2, c3 = st.columns(3)
        prov = c1.selectbox("Prestataire", ["(Tous)"] + db.load_providers())
        cli = c2.selectbox("Client", ["(Tous)"] + db.load_clients())
        tsk = c3.selectbox("Tâche", ["(Tous)"] + list(db.load_tasks().keys()))
        
        c4, c5 = st.columns(2)
        d_start = c4.date_input("Du", value=date.today())
        d_end = c5.date_input("Au", value=date.today())
        
        apply_filters = st.button("Appliquer les filtres")

    # Logique de chargement
    if apply_filters:
        df = db.load_prestations_filtered(provider=prov, client=cli, task=tsk, start_date=d_start, end_date=d_end, invoiced=invoiced_filter)
    else:
        df = db.load_prestations_filtered(invoiced=invoiced_filter)

    # Métriques globales au-dessus du tableau
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Nombre", f"{len(df)}")
        m2.metric("Heures", f"{df['Heures'].sum():.2f} h")
        m3.metric("Montant Total", f"{df['Total €'].sum():.2f} €")

        # Configuration des colonnes pour un affichage PRO (Devise, Date)
        st.dataframe(
            df, 
            use_container_width=True,
            column_config={
                "Total €": st.column_config.NumberColumn("Total", format="%.2f €"),
                "Tarif €/h": st.column_config.NumberColumn("Tarif", format="%.2f €"),
                "Début": st.column_config.DatetimeColumn("Début", format="DD/MM/YYYY HH:mm"),
                "Fin": st.column_config.DatetimeColumn("Fin", format="DD/MM/YYYY HH:mm"),
                "Description": st.column_config.TextColumn("Description", width="large"),
            },
            hide_index=True # On cache l'index numéroté moche
        )

        # Actions (Export / Suppression)
        col_act1, col_act2 = st.columns([1, 3])
        with col_act1:
            csv = df.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button("📥 Télécharger CSV", data=csv, file_name="export.csv", mime="text/csv")
        
        with col_act2:
            with st.popover("🗑️ Supprimer des lignes"):
                to_del = st.multiselect("Choisir les IDs à supprimer", df["ID"])
                if st.button("Confirmer suppression") and to_del:
                    db.delete_prestations(to_del)
                    db.clear_prestations_cache()
                    st.rerun()
    else:
        st.info("Aucune donnée ne correspond à votre recherche.")

# --- 4. DASHBOARD ---
def ui_dashboard():
    st.subheader("📊 Tableau de bord")
    df = db.load_prestations_filtered(invoiced=None) # On charge tout
    
    if df.empty:
        st.warning("Pas assez de données pour afficher le dashboard.")
        return

    # Gros chiffres clés
    col1, col2, col3 = st.columns(3)
    col1.metric("Chiffre d'Affaires", f"{df['Total €'].sum():.2f} €", delta="Global")
    col2.metric("Heures Totales", f"{df['Heures'].sum():.2f} h")
    col3.metric("Prestations", len(df))

    st.markdown("---")
    
    # Graphiques
    c_chart1, c_chart2 = st.columns(2)
    
    with c_chart1:
        st.write("**Par Client (€)**")
        st.bar_chart(df.groupby("Client")["Total €"].sum(), color="#4CAF50") # Vert
        
    with c_chart2:
        st.write("**Par Tâche (€)**")
        st.bar_chart(df.groupby("Tâche")["Total €"].sum(), color="#2196F3") # Bleu

# --- 5. FACTURATION ---
def ui_facturation():
    st.subheader("💶 Facturation")
    clients = db.load_clients()
    
    col_sel, col_act = st.columns([2, 1])
    with col_sel:
        cli = st.selectbox("Client à facturer", ["(Choisir)"] + clients)
    
    if cli != "(Choisir)":
        df = db.load_prestations_filtered(client=cli, invoiced=False)
        if df.empty:
            st.success("Rien à facturer pour ce client ! 🎉")
        else:
            st.dataframe(
                df, 
                use_container_width=True,
                column_config={"Total €": st.column_config.NumberColumn(format="%.2f €")},
                hide_index=True
            )
            
            with st.container(border=True):
                st.write(f"**Total à facturer : {df['Total €'].sum():.2f} €**")
                sel_ids = st.multiselect("Sélectionner manuellement (si partiel)", df["ID"].tolist(), default=df["ID"].tolist())
                ref_facture = st.text_input("Numéro de facture (ex: 2025-01)")
                
                if st.button("✅ Marquer comme FACTURÉ", type="primary"):
                    if ref_facture and sel_ids:
                        db.mark_prestations_invoiced(sel_ids, ref_facture)
                        db.clear_prestations_cache()
                        st.balloons()
                        st.success("Prestations archivées avec succès !")
                        st.rerun()
                    else:
                        st.error("Indiquez une référence de facture.")

# --- 6. GESTION (ADMIN) ---
def ui_gestion():
    st.subheader("⚙️ Administration")
    
    tab1, tab2, tab3 = st.tabs(["👥 Clients", "🛠️ Tâches", "👷 Prestataires"])
    
    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write("Ajouter un client")
            with st.form("add_cli"):
                new_c = st.text_input("Nom")
                if st.form_submit_button("Ajouter"):
                    if new_c:
                        db.add_or_reactivate_client(new_c)
                        st.success("Ajouté")
                        db.load_clients.clear()
                        db.load_all_clients.clear()
                        st.rerun()
        with c2:
            st.dataframe(db.load_all_clients(), use_container_width=True, hide_index=True)

    with tab2:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write("Ajouter/Modifier Tâche")
            with st.form("add_task"):
                n_t = st.text_input("Nom")
                r_t = st.number_input("Taux horaire", min_value=0.0)
                if st.form_submit_button("Sauvegarder"):
                    if n_t and r_t > 0:
                        db.upsert_task(n_t, r_t)
                        st.success("Sauvegardé")
                        db.load_tasks.clear()
                        db.load_all_tasks.clear()
                        st.rerun()
        with c2:
            st.dataframe(db.load_all_tasks(), use_container_width=True, hide_index=True)
            
    with tab3:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write("Ajouter Prestataire")
            with st.form("add_prov"):
                n_p = st.text_input("Nom")
                if st.form_submit_button("Ajouter"):
                    if n_p:
                        db.add_or_reactivate_provider(n_p)
                        st.success("Ajouté")
                        db.load_providers.clear()
                        db.load_all_providers.clear()
                        st.rerun()
        with c2:
            st.dataframe(db.load_all_providers(), use_container_width=True, hide_index=True)

