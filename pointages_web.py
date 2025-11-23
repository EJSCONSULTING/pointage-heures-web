import psycopg2
from datetime import datetime, date, time

import pandas as pd
import streamlit as st
from pathlib import Path

LOGO_PATH = "logo_ejs.png"


# ==========================
# Connexion PostgreSQL
# ==========================

def get_connection():
    try:
        return psycopg2.connect(
            host=st.secrets["DB_HOST"],
            port=st.secrets.get("DB_PORT", "5432"),
            dbname=st.secrets["DB_NAME"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"],
            sslmode="require",
        )
    except Exception as e:
        st.error("Erreur de connexion à la base de données.")
        st.exception(e)
        raise


# ==========================
# Fonctions base de données
# ==========================

def load_clients():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM clients WHERE active = true ORDER BY name;")
            rows = cur.fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=60)
def load_all_clients():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, active FROM clients ORDER BY name;")
            rows = cur.fetchall()

    data = []
    for cid, name, active in rows:
        data.append({"ID": cid, "Nom": name, "Actif": bool(active)})
    return pd.DataFrame(data)


def add_or_reactivate_client(name: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (name, active)
                VALUES (%s, true)
                ON CONFLICT (name)
                DO UPDATE SET active = true;
                """,
                (name,),
            )
        conn.commit()


def load_tasks():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, rate FROM tasks WHERE active = true ORDER BY name;")
            rows = cur.fetchall()
    return {name: float(rate) for name, rate in rows}


@st.cache_data(ttl=60)
def load_all_tasks():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, rate, active FROM tasks ORDER BY name;")
            rows = cur.fetchall()

    data = []
    for tid, name, rate, active in rows:
        data.append(
            {"ID": tid, "Tâche": name, "Tarif €/h": float(rate), "Actif": bool(active)}
        )
    return pd.DataFrame(data)


def upsert_task(name: str, rate: float):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (name, rate, active)
                VALUES (%s, %s, true)
                ON CONFLICT (name)
                DO UPDATE SET rate = EXCLUDED.rate, active = true;
                """,
                (name, rate),
            )
        conn.commit()


def ensure_default_tasks():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks;")
            count = cur.fetchone()[0]
            if count == 0:
                default_tasks = {
                    "Analyse": 75.0,
                    "Consultance": 90.0,
                    "Déplacement": 50.0,
                    "Administration": 60.0,
                }
                for name, rate in default_tasks.items():
                    cur.execute(
                        """
                        INSERT INTO tasks (name, rate, active)
                        VALUES (%s, %s, true)
                        ON CONFLICT (name) DO NOTHING;
                        """,
                        (name, rate),
                    )
        conn.commit()


# --------- Prestataires (multi-prestataire) ---------

def load_providers():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM providers WHERE active = true ORDER BY name;"
            )
            rows = cur.fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=60)
def load_all_providers():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, active FROM providers ORDER BY name;")
            rows = cur.fetchall()

    data = []
    for pid, name, active in rows:
        data.append({"ID": pid, "Prestataire": name, "Actif": bool(active)})
    return pd.DataFrame(data)


def add_or_reactivate_provider(name: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO providers (name, active)
                VALUES (%s, true)
                ON CONFLICT (name)
                DO UPDATE SET active = true;
                """,
                (name,),
            )
        conn.commit()


# --------- Prestations ---------

def insert_prestation(provider, client, task, description, start_dt, end_dt, rate):
    hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    total = round(hours * rate, 2)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prestations
                (provider, client, task, description,
                 start_at, end_at, hours, rate, total,
                 created_at, invoiced)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        now(), false)
                """,
                (
                    provider,
                    client,
                    task,
                    description,
                    start_dt,
                    end_dt,
                    hours,
                    rate,
                    total,
                ),
            )
        conn.commit()

    return hours, total


def mark_prestations_invoiced(ids, invoice_ref: str | None):
    if not ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE prestations
                SET invoiced = true,
                    invoiced_at = now(),
                    invoice_ref = %s
                WHERE id = ANY(%s)
                """,
                (invoice_ref, list(ids)),
            )
        conn.commit()


def delete_prestations(ids):
    if not ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM prestations WHERE id = ANY(%s);",
                (list(ids),),
            )
        conn.commit()


# ==========================
# Historique + filtres
# ==========================

@st.cache_data(ttl=60)
def load_prestations_filtered(provider=None, client=None, task=None,
                              start_date=None, end_date=None,
                              invoiced: bool | None = None):
    conditions = []
    params = []

    if provider and provider != "(Tous)":
        conditions.append("provider = %s")
        params.append(provider)

    if client and client != "(Tous)":
        conditions.append("client = %s")
        params.append(client)

    if task and task != "(Tous)":
        conditions.append("task = %s")
        params.append(task)

    if start_date:
        start_dt = datetime.combine(start_date, time(0, 0, 0))
        conditions.append("start_at >= %s")
        params.append(start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time(23, 59, 59))
        conditions.append("start_at <= %s")
        params.append(end_dt)

    if invoiced is True:
        conditions.append("invoiced = true")
    elif invoiced is False:
        conditions.append("invoiced = false")

    sql = """
        SELECT id, provider, client, task, description,
               start_at, end_at, hours, rate, total,
               invoiced, invoice_ref, invoiced_at
        FROM prestations
    """

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY start_at ASC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    data = []
    for (pid, provider_, client_, task_, desc,
         start_dt, end_dt, hours, rate, total,
         invoiced_flag, invoice_ref, invoiced_at) in rows:
        data.append({
            "ID": pid,
            "Prestataire": provider_ or "",
            "Client": client_,
            "Tâche": task_,
            "Description": desc or "",
            "Début": start_dt,
            "Fin": end_dt,
            "Heures": float(hours),
            "Tarif €/h": float(rate),
            "Total €": float(total),
            "Facturée": bool(invoiced_flag),
            "Réf facture": invoice_ref or "",
            "Date facturation": invoiced_at,
        })

    if not data:
        return pd.DataFrame(
            columns=[
                "ID",
                "Prestataire",
                "Client",
                "Tâche",
                "Description",
                "Début",
                "Fin",
                "Heures",
                "Tarif €/h",
                "Total €",
                "Facturée",
                "Réf facture",
                "Date facturation",
            ]
        )

    return pd.DataFrame(data)


# ==========================
# Auth simple (mot de passe)
# ==========================

def check_password():
    app_pwd = st.secrets.get("APP_PASSWORD", None)
    if not app_pwd:
        return True

    # Si déjà authentifié dans cette session, on ne redemande plus le mot de passe
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

# ==========================
# UI helpers
# ==========================

def ui_manual_entry():
    clients = load_clients()
    tasks = load_tasks()
    providers = load_providers()

    st.subheader("Encodage manuel")

    col1, col2 = st.columns(2)

    with col1:
        if providers:
            provider = st.selectbox(
                "Prestataire",
                options=providers,
                key="provider_manual",
            )
        else:
            provider = st.text_input(
                "Prestataire (aucun prestataire configuré)",
                key="provider_manual_text",
            )

        client = st.selectbox("Client", options=[""] + clients, key="client_manual")

        task = st.selectbox(
            "Tâche",
            options=[""] + list(tasks.keys()),
            key="task_manual",
        )

        if "last_task" not in st.session_state:
            st.session_state.last_task = ""
        if "rate_saisie" not in st.session_state:
            st.session_state.rate_saisie = 0.0

        if task and task != st.session_state.last_task:
            st.session_state.last_task = task
            st.session_state.rate_saisie = float(tasks.get(task, 0.0))

        rate = st.number_input(
            "Tarif horaire (€ / h)",
            min_value=0.0,
            step=1.0,
            key="rate_saisie",
        )

    with col2:
        start_date = st.date_input("Date de début", value=date.today(), key="manual_start_date")
        start_time = st.time_input("Heure de début", value=time(9, 0), key="manual_start_time")
        end_date = st.date_input("Date de fin", value=date.today(), key="manual_end_date")
        end_time = st.time_input("Heure de fin", value=time(10, 0), key="manual_end_time")

    description = st.text_area("Description (facultatif)", key="desc_manual")

    if st.button("Enregistrer la prestation (manuel)", key="btn_manual_save"):
        if not provider:
            st.error("Veuillez indiquer le prestataire.")
        elif not client:
            st.error("Veuillez choisir un client.")
        elif not task:
            st.error("Veuillez choisir une tâche.")
        else:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)

            if end_dt <= start_dt:
                st.error("La date/heure de fin doit être postérieure au début.")
            else:
                hours, total = insert_prestation(
                    provider, client, task, description, start_dt, end_dt, rate
                )
                st.success(f"Prestation enregistrée : {hours:.2f} h – {total:.2f} €")
                st.cache_data.clear()


def ui_timer():
    clients = load_clients()
    tasks = load_tasks()
    providers = load_providers()

    st.subheader("Timer de prestation")

    if "timer_running" not in st.session_state:
        st.session_state.timer_running = False
    if "timer_start" not in st.session_state:
        st.session_state.timer_start = None

    if providers:
        provider_t = st.selectbox(
            "Prestataire",
            options=providers,
            key="timer_provider",
        )
    else:
        provider_t = st.text_input(
            "Prestataire (aucun prestataire configuré)",
            key="timer_provider_text",
        )

    client_t = st.selectbox(
        "Client",
        options=[""] + clients,
        key="timer_client",
    )

    task_t = st.selectbox(
        "Tâche",
        options=[""] + list(tasks.keys()),
        key="timer_task",
    )

    description_t = st.text_area(
        "Description (facultatif)",
        key="timer_desc",
    )

    if not st.session_state.timer_running:
        if st.button("Démarrer le timer", key="btn_timer_start"):
            if not provider_t:
                st.error("Veuillez indiquer le prestataire.")
            elif not client_t:
                st.error("Veuillez choisir un client.")
            elif not task_t:
                st.error("Veuillez choisir une tâche.")
            else:
                st.session_state.timer_running = True
                st.session_state.timer_start = datetime.now()
                st.session_state.timer_provider_val = provider_t
                st.session_state.timer_client_val = client_t
                st.session_state.timer_task_val = task_t
                st.session_state.timer_desc_val = description_t
                st.success(
                    f"Timer démarré à {st.session_state.timer_start.strftime('%Y-%m-%d %H:%M:%S')}"
                )
    else:
        st.write(
            f"Timer démarré à : {st.session_state.timer_start.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        elapsed = datetime.now() - st.session_state.timer_start
        seconds = int(elapsed.total_seconds())
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        st.write(f"Temps écoulé : {hours:02d} h {minutes:02d} min")

        if st.button("Arrêter le timer et enregistrer", key="btn_timer_stop"):
            start_dt = st.session_state.timer_start
            end_dt = datetime.now()
            provider = st.session_state.timer_provider_val
            client = st.session_state.timer_client_val
            task = st.session_state.timer_task_val
            description = st.session_state.timer_desc_val

            rate_auto = float(tasks.get(task, 0.0))
            hours_used, total = insert_prestation(
                provider, client, task, description, start_dt, end_dt, rate_auto
            )

            st.success(
                f"Prestation (timer) enregistrée : {hours_used:.2f} h – {total:.2f} €"
            )
            st.cache_data.clear()

            st.session_state.timer_running = False
            st.session_state.timer_start = None


def ui_historique():
    st.subheader("Historique des prestations et filtres")

    include_invoiced = st.checkbox(
        "Inclure les prestations déjà facturées (archivées)",
        value=False,
        key="include_invoiced_hist",
    )

    invoiced_filter = None if include_invoiced else False

    df_all = load_prestations_filtered(invoiced=invoiced_filter)

    providers_f = ["(Tous)"] + sorted(df_all["Prestataire"].dropna().unique().tolist())
    clients_f = ["(Tous)"] + sorted(df_all["Client"].dropna().unique().tolist())
    tasks_f = ["(Tous)"] + sorted(df_all["Tâche"].dropna().unique().tolist())

    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        f_provider = st.selectbox("Prestataire", options=providers_f, key="hist_provider")
    with col_f2:
        f_client = st.selectbox("Client", options=clients_f, key="hist_client")
    with col_f3:
        f_task = st.selectbox("Tâche", options=tasks_f, key="hist_task")

    col_f4, col_f5 = st.columns(2)
    with col_f4:
        f_start_date = st.date_input(
            "Date début (filtre)",
            value=date.today(),
            key="hist_start_date",
        )
    with col_f5:
        f_end_date = st.date_input(
            "Date fin (filtre)",
            value=date.today(),
            key="hist_end_date",
        )

    if st.button("Appliquer les filtres", key="btn_hist_filter"):
        df = load_prestations_filtered(
            provider=f_provider,
            client=f_client,
            task=f_task,
            start_date=f_start_date,
            end_date=f_end_date,
            invoiced=invoiced_filter,
        )
    else:
        df = df_all

    st.write(f"{len(df)} prestation(s) trouvée(s).")

    if not df.empty:
        st.dataframe(df, use_container_width=True)

        total_global = df["Total €"].sum()
        st.info(f"Total global : {total_global:.2f} €")

        st.write("Total par client")
        st.dataframe(
            df.groupby("Client")["Total €"].sum().reset_index(),
            use_container_width=True,
        )

        st.write("Total par prestataire")
        st.dataframe(
            df.groupby("Prestataire")["Total €"].sum().reset_index(),
            use_container_width=True,
        )

        csv_data = df.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "Télécharger les résultats filtrés (CSV)",
            data=csv_data,
            file_name="prestations_filtrees.csv",
            mime="text/csv",
            key="btn_hist_export",
        )

        st.markdown("---")
        st.subheader("Supprimer des prestations")

        labels_del = {}
        for _, row in df.iterrows():
            rid = row["ID"]
            labels_del[rid] = (
                f"{row['Début']} – {row['Client']} – "
                f"{row['Tâche']} – {row['Heures']:.2f} h – {row['Total €']:.2f} €"
            )

        selected_for_delete = st.multiselect(
            "Sélectionnez les prestations à supprimer",
            options=df["ID"].tolist(),
            format_func=lambda x: labels_del.get(x, str(x)),
            key="delete_prestations_ids",
        )

        if st.button("Supprimer les prestations sélectionnées", key="btn_delete_prestations"):
            if not selected_for_delete:
                st.error("Veuillez sélectionner au moins une prestation à supprimer.")
            else:
                delete_prestations(selected_for_delete)
                st.success(f"{len(selected_for_delete)} prestation(s) supprimée(s).")
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("Aucune prestation trouvée avec ces filtres.")


def ui_dashboard():
    st.subheader("Tableau de bord")

    df_dash = load_prestations_filtered(invoiced=None)

    if df_dash.empty:
        st.info("Aucune prestation dans la base pour le moment.")
        return

    total_heures = df_dash["Heures"].sum()
    total_euros = df_dash["Total €"].sum()
    non_fact = df_dash[df_dash["Facturée"] == False]
    total_non_fact = non_fact["Total €"].sum()

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    with col_kpi1:
        st.metric("Heures totales (toutes)", f"{total_heures:.2f} h")
    with col_kpi2:
        st.metric("Montant total (toutes)", f"{total_euros:.2f} €")
    with col_kpi3:
        st.metric("En attente de facturation", f"{total_non_fact:.2f} €")

    st.markdown("---")

    df_dash = df_dash.copy()
    df_dash["Mois"] = df_dash["Début"].dt.to_period("M").dt.to_timestamp()

    st.write("Total par client (€)")
    df_client = df_dash.groupby("Client")["Total €"].sum().sort_values(ascending=False)
    if not df_client.empty:
        st.bar_chart(df_client)

    st.write("Total par tâche (€)")
    df_task = df_dash.groupby("Tâche")["Total €"].sum().sort_values(ascending=False)
    if not df_task.empty:
        st.bar_chart(df_task)

    st.write("Total par mois (€)")
    df_month = df_dash.groupby("Mois")["Total €"].sum().sort_index()
    if not df_month.empty:
        st.line_chart(df_month)


def ui_facturation():
    clients = load_clients()

    st.subheader("Préparation de facturation / Archivage")

    col_fc1, col_fc2 = st.columns(2)

    with col_fc1:
        cli_fact = st.selectbox(
            "Client à facturer",
            options=["(Tous)"] + clients,
            key="fact_client",
        )
    with col_fc2:
        prest_fact = st.text_input(
            "Prestataire (facultatif, filtre)",
            key="fact_provider",
        )

    col_fd1, col_fd2 = st.columns(2)
    with col_fd1:
        d_start = st.date_input(
            "Période - date de début",
            value=date.today().replace(day=1),
            key="fact_start",
        )
    with col_fd2:
        d_end = st.date_input(
            "Période - date de fin",
            value=date.today(),
            key="fact_end",
        )

    df_to_invoice = load_prestations_filtered(
        provider=prest_fact or None,
        client=cli_fact if cli_fact != "(Tous)" else None,
        start_date=d_start,
        end_date=d_end,
        invoiced=False,
    )

    if df_to_invoice.empty:
        st.info("Aucune prestation à facturer pour ces critères.")
    else:
        st.write(f"{len(df_to_invoice)} prestation(s) non facturée(s) trouvée(s).")

        labels = {}
        for _, row in df_to_invoice.iterrows():
            rid = row["ID"]
            labels[rid] = (
                f"{row['Début'].date()} – {row['Client']} – "
                f"{row['Tâche']} – {row['Heures']:.2f} h – {row['Total €']:.2f} €"
            )

        selected_ids = st.multiselect(
            "Sélectionnez les prestations à facturer",
            options=df_to_invoice["ID"].tolist(),
            format_func=lambda x: labels.get(x, str(x)),
            key="fact_ids",
        )

        st.write("Détail des prestations à facturer (non facturées) :")
        st.dataframe(df_to_invoice, use_container_width=True)

        total_sel = df_to_invoice[df_to_invoice["ID"].isin(selected_ids)]["Total €"].sum()
        st.info(f"Total de la sélection : {total_sel:.2f} €")

        invoice_ref = st.text_input(
            "Référence de facture (facultatif, ex : 2025-001)",
            key="fact_ref",
        )

        if st.button("Marquer comme facturées / archivées", key="btn_fact_archive"):
            if not selected_ids:
                st.error("Veuillez sélectionner au moins une prestation.")
            else:
                mark_prestations_invoiced(selected_ids, invoice_ref.strip() or None)
                st.success(
                    f"{len(selected_ids)} prestation(s) marquée(s) comme facturées."
                )
                st.cache_data.clear()


def ui_gestion():
    st.subheader("Gestion des clients")

    col_c1, col_c2 = st.columns([1, 2])

    with col_c1:
        new_client = st.text_input("Nouveau client (ou à réactiver)", key="new_client")
        if st.button("Ajouter / Réactiver le client", key="btn_add_client"):
            if not new_client.strip():
                st.error("Veuillez saisir un nom de client.")
            else:
                add_or_reactivate_client(new_client.strip())
                st.success(f"Client « {new_client.strip()} » enregistré / réactivé.")
                st.cache_data.clear()

    with col_c2:
        df_clients = load_all_clients()
        if not df_clients.empty:
            st.write("Liste des clients")
            st.dataframe(df_clients, use_container_width=True)
        else:
            st.info("Aucun client dans la base.")

    st.markdown("---")
    st.subheader("Gestion des tâches")

    col_t1, col_t2 = st.columns([1, 2])

    with col_t1:
        new_task_name = st.text_input("Nom de la tâche", key="new_task_name")
        new_task_rate = st.number_input(
            "Tarif horaire (€ / h)",
            min_value=0.0,
            step=1.0,
            value=0.0,
            key="rate_task",
        )

        if st.button("Ajouter / Mettre à jour la tâche", key="btn_add_task"):
            if not new_task_name.strip():
                st.error("Veuillez saisir un nom de tâche.")
            elif new_task_rate <= 0:
                st.error("Le tarif doit être supérieur à 0.")
            else:
                upsert_task(new_task_name.strip(), float(new_task_rate))
                st.success(f"Tâche « {new_task_name.strip()} » enregistrée / mise à jour.")
                st.cache_data.clear()

    with col_t2:
        df_tasks = load_all_tasks()
        if not df_tasks.empty:
            st.write("Liste des tâches")
            st.dataframe(df_tasks, use_container_width=True)
        else:
            st.info("Aucune tâche dans la base.")

    st.markdown("---")
    st.subheader("Gestion des prestataires")

    col_p1, col_p2 = st.columns([1, 2])

    with col_p1:
        new_provider = st.text_input("Nouveau prestataire (ou à réactiver)", key="new_provider")
        if st.button("Ajouter / Réactiver le prestataire", key="btn_add_provider"):
            if not new_provider.strip():
                st.error("Veuillez saisir un nom de prestataire.")
            else:
                add_or_reactivate_provider(new_provider.strip())
                st.success(
                    f"Prestataire « {new_provider.strip()} » enregistré / réactivé."
                )
                st.cache_data.clear()

    with col_p2:
        df_providers = load_all_providers()
        if not df_providers.empty:
            st.write("Liste des prestataires")
            st.dataframe(df_providers, use_container_width=True)
        else:
            st.info("Aucun prestataire dans la base.")


# ==========================
# Application Streamlit
# ==========================

def main():
    st.set_page_config(
        page_title="EJS – Pointage des heures",
        page_icon=LOGO_PATH,
        layout="wide",
    )

    col_logo, col_title = st.columns([1, 4])

    with col_logo:
        if Path(LOGO_PATH).exists():
            st.image(LOGO_PATH, use_column_width=False, width=70)

    with col_title:
        st.markdown(
            """
            <div style="padding-top:10px;">
              <h1 style="margin-bottom:0;">EJS – Pointage des heures</h1>
              <p style="margin-top:4px; color:#666; font-size:18px;">
                Suivi des prestations, facturation et tableau de bord
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not check_password():
        return

    if "defaults_done" not in st.session_state:
        ensure_default_tasks()
        st.session_state["defaults_done"] = True

    mobile_mode = st.sidebar.checkbox("Mode mobile (vue simplifiée)", value=False)

    if mobile_mode:
        st.write("Mode mobile activé – interface simplifiée pour téléphone.")
        page = st.sidebar.radio(
            "Navigation",
            ["Timer", "Saisie rapide", "Facturation", "Historique"],
            key="mobile_nav",
        )

        if page == "Timer":
            ui_timer()
        elif page == "Saisie rapide":
            ui_manual_entry()
        elif page == "Facturation":
            ui_facturation()
        elif page == "Historique":
            ui_historique()
    else:
        tab_saisie, tab_historique, tab_dashboard, tab_facturation, tab_gestion = st.tabs(
            [
                "Saisir une prestation",
                "Historique et filtres",
                "Tableau de bord",
                "Facturation / Archivage",
                "Gestion clients / tâches / prestataires",
            ]
        )

        with tab_saisie:
            sub_tab_manual, sub_tab_timer = st.tabs(["Encodage manuel", "Timer"])
            with sub_tab_manual:
                ui_manual_entry()
            with sub_tab_timer:
                st.info("Mode timer : démarrez et arrêtez le chronomètre pour enregistrer une prestation.")
                ui_timer()

        with tab_historique:
            ui_historique()

        with tab_dashboard:
            ui_dashboard()

        with tab_facturation:
            ui_facturation()

        with tab_gestion:
            ui_gestion()


if __name__ == "__main__":
    main()
















