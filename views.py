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

# --- 3. HISTORIQUE (Avec fonction ÉDITION) ---
def ui_historique():
    st.subheader("📚 Historique des prestations")
    
    # État de la session pour l'édition
    if "edit_mode" not in st.session_state: st.session_state.edit_mode = False
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    
    # Si on est en mode édition, on affiche le formulaire de modification
    if st.session_state.edit_mode and st.session_state.edit_id is not None:
        ui_edit_form(st.session_state.edit_id)
        return # Arrêter l'exécution pour ne pas afficher le tableau en dessous

    # --- Zone de filtres repliable ---
    with st.expander("🔍 Filtres et Options", expanded=False):
        # ... (Gardez la logique de filtres existante, qui est déjà dans votre code) ...
        include_invoiced = st.checkbox("Voir aussi les archives (facturées)", value=False)
        invoiced_filter = None if include_invoiced else False

        c1, c2, c3 = st.columns(3)
        prov = c1.selectbox("Prestataire", ["(Tous)"] + db.load_providers(), key="hist_prov")
        cli = c2.selectbox("Client", ["(Tous)"] + db.load_clients(), key="hist_cli")
        tsk = c3.selectbox("Tâche", ["(Tous)"] + list(db.load_tasks().keys()), key="hist_task")
        
        c4, c5 = st.columns(2)
        d_start = c4.date_input("Du", value=date.today(), key="hist_start")
        d_end = c5.date_input("Au", value=date.today(), key="hist_end")
        
        apply_filters = st.button("Appliquer les filtres")

    # Logique de chargement
    if apply_filters:
        df = db.load_prestations_filtered(provider=prov, client=cli, task=tsk, start_date=d_start, end_date=d_end, invoiced=invoiced_filter)
    else:
        df = db.load_prestations_filtered(invoiced=invoiced_filter)

    st.write(f"**{len(df)} prestation(s) trouvée(s).**")

    # --- Affichage des résultats ---
    if not df.empty:
        # Configuration des colonnes
        column_config = {
            "Total €": st.column_config.NumberColumn("Total", format="%.2f €"),
            "Tarif €/h": st.column_config.NumberColumn("Tarif", format="%.2f €"),
            "Début": st.column_config.DatetimeColumn("Début", format="DD/MM/YYYY HH:mm"),
            "Fin": st.column_config.DatetimeColumn("Fin", format="DD/MM/YYYY HH:mm"),
            "Description": st.column_config.TextColumn("Description", width="large"),
            # Ajout d'une colonne bouton pour l'édition
            "Action": st.column_config.ButtonColumn("Modifier", help="Modifier cette ligne", key="edit_btn_col"),
        }
        
        # Le st.dataframe appelle la session state quand on clique sur le bouton
        edited_df = st.dataframe(
            df, 
            use_container_width=True,
            column_config=column_config,
            hide_index=True,
            on_select="default"
        )
        
        # Logique pour le bouton "Modifier"
        if edited_df.selection["rows"]:
            # On prend l'ID de la ligne sélectionnée
            selected_row_index = edited_df.selection["rows"][0]
            selected_id = df.iloc[selected_row_index]["ID"]
            
            # On active le mode édition avec l'ID
            st.session_state.edit_id = selected_id
            st.session_state.edit_mode = True
            st.rerun()

        # ... (Gardez la zone d'export CSV et de suppression existante) ...
        st.markdown("---")
        
        # Totals et Export CSV
        col_export, col_total = st.columns([1, 2])
        total_global = df["Total €"].sum()
        
        with col_total:
            st.info(f"💰 **Total pour la sélection : {total_global:.2f} €**")
        with col_export:
            csv_data = df.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "📥 Télécharger CSV",
                data=csv_data,
                file_name="prestations_filtrees.csv",
                mime="text/csv",
            )
            
        st.markdown("---")
        
        # Suppression
        with st.popover("🗑️ Supprimer des lignes", use_container_width=True):
            # Création de libellés lisibles pour le multiselect
            labels_del = {}
            for _, row in df.iterrows():
                rid = row["ID"]
                labels_del[rid] = f"{row['Début']} – {row['Client']} – {row['Total €']:.2f} €"

            selected_for_delete = st.multiselect(
                "Sélectionnez les prestations à supprimer",
                options=df["ID"].tolist(),
                format_func=lambda x: labels_del.get(x, str(x)),
                key="del_ids"
            )

            if st.button("Confirmer la suppression", type="primary"):
                if not selected_for_delete:
                    st.error("Veuillez sélectionner au moins une ligne.")
                else:
                    db.delete_prestations(selected_for_delete)
                    db.clear_prestations_cache()
                    st.success(f"{len(selected_for_delete)} prestation(s) supprimée(s).")
                    st.rerun()

    else:
        st.warning("Aucune prestation trouvée avec ces critères.")
        
# --- NOUVELLE FONCTION : FORMULAIRE D'ÉDITION ---
def ui_edit_form(prestation_id):
    st.subheader(f"✏️ Modification de la prestation ID: {prestation_id}")
    
    # Chargement de la ligne à éditer (on réutilise load_prestations_filtered pour ne pas surcharger database.py)
    df_single = db.load_prestations_filtered(provider=None, start_date=None, end_date=None, invoiced=None)
    
    try:
        data = df_single[df_single["ID"] == prestation_id].iloc[0]
    except IndexError:
        st.error("Prestation non trouvée.")
        st.session_state.edit_mode = False
        st.session_state.edit_id = None
        return

    clients = db.load_clients()
    tasks = db.load_tasks()
    providers = db.load_providers()
    task_rates = db.load_tasks()
    
    # --- Formulaire d'édition ---
    with st.form("edit_prestation_form", border=True):
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            e_provider = st.selectbox("Prestataire", options=providers, index=providers.index(data["Prestataire"]) if data["Prestataire"] in providers else 0, key="e_prov")
            e_client = st.selectbox("Client", options=clients, index=clients.index(data["Client"]), key="e_cli")
        
        with col2:
            e_task = st.selectbox("Tâche", options=list(tasks.keys()), index=list(tasks.keys()).index(data["Tâche"]), key="e_task")
            # Le tarif est soit celui par défaut de la tâche, soit celui enregistré s'il était customisé
            default_rate = task_rates.get(data["Tâche"], 0.0)
            initial_rate = data["Tarif €/h"]
            e_rate = st.number_input("Tarif horaire (€ / h)", min_value=0.0, step=1.0, value=initial_rate, key="e_rate")

        with col3:
            # Récupération des composants date/time
            start_dt = data["Début"]
            end_dt = data["Fin"]
            
            e_start_date = st.date_input("Date début", value=start_dt.date(), key="e_start_d")
            e_start_time = st.time_input("Heure début", value=start_dt.time(), key="e_start_t")
            e_end_date = st.date_input("Date fin", value=end_dt.date(), key="e_end_d")
            e_end_time = st.time_input("Heure fin", value=end_dt.time(), key="e_end_t")
            
        e_description = st.text_area("Description complète", value=data["Description"], key="e_desc")

        col_b1, col_b2 = st.columns(2)
        
        if col_b1.form_submit_button("💾 Enregistrer les modifications", type="primary"):
            new_start_dt = datetime.combine(e_start_date, e_start_time)
            new_end_dt = datetime.combine(e_end_date, e_end_time)
            
            if new_end_dt <= new_start_dt:
                st.error("⚠️ La date de fin doit être après le début.")
            else:
                h, t = db.update_prestation(
                    prestation_id, e_provider, e_client, e_task, e_description, 
                    new_start_dt, new_end_dt, e_rate
                )
                st.success(f"✅ Prestation mise à jour : {h} h — {t} €")
                db.clear_prestations_cache()
                # Sortir du mode édition
                st.session_state.edit_mode = False
                st.session_state.edit_id = None
                st.rerun()

        if col_b2.form_submit_button("Annuler et revenir à l'historique"):
            # Sortir du mode édition sans sauvegarder
            st.session_state.edit_mode = False
            st.session_state.edit_id = None
            st.rerun()
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


