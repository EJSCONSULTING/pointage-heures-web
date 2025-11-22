import psycopg2
from datetime import datetime, date, time

import pandas as pd
import streamlit as st


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

@st.cache_data(ttl=60)
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


@st.cache_data(ttl=60)
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
    """Insère quelques tâches par défaut si la table est vide."""
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
    """Marque une liste de prestations comme facturées / archivées."""
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


def update_prestation_basic(p_id, provider, client, task, description, rate, total):
    """Met à jour les infos principales d'une prestation (sans changer les heures/dates)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE prestations
                SET provider = %s,
                    client = %s,
                    task = %s,
                    description = %s,
                    rate = %s,
                    total = %s
                WHERE id = %s
                """,
                (provider, client, task, description, rate, total, p_id),
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
        # Pas de mot de passe configuré => accès libre
        return True

    pwd = st.text_input("Mot de passe", type="password")
    if pwd == "":
        return False
    if pwd == app_pwd:
        return True
    else:
        st.error("Mot de passe incorrect.")
        return False


# ==========================
# Application Streamlit
# ==========================

def main():
    st.set_page_config(page_title="Pointage de temps", layout="wide")

    st.title("Application de pointage d'heures – Version Web (PostgreSQL)")

    if not check_password():
        return

    # Ne remplir les tâches par défaut qu'une seule fois par session
    if "defaults_done" not in st.session_state:
        ensure_default_tasks()
        st.session_state["defaults_done"] = True

    clients = load_clients()
    tasks = load_tasks()

    tab_saisie, tab_historique, tab_facturation, tab_gestion = st.tabs(
        [
            "Saisir une prestation",
            "Historique et filtres",
            "Facturation / Archivage",
            "Gestion clients / tâches",
        ]
    )

    # ==========================
    # Onglet SAISIE PRESTATION
    # ==========================

    with tab_saisie:
        st.subheader("Nouvelle prestation manuelle")

        col1, col2 = st.columns(2)

        with col1:
            provider = st.text_input("Prestataire")

            client = st.selectbox("Client", options=[""] + clients)

            task = st.selectbox(
                "Tâche",
                options=[""] + list(tasks.keys()),
                key="task_select",
            )

            # Initialisation du state
            if "last_task" not in st.session_state:
                st.session_state.last_task = ""
            if "rate_saisie" not in st.session_state:
                st.session_state.rate_saisie = 0.0

            # Si la tâche change, mettre à jour le tarif automatiquement
            if task and task != st.session_state.last_task:
                st.session_state.last_task = task
                st.session_state.rate_saisie = float(tasks.get(task, 0.0))

            # Le champ tarif qui s'adapte automatiquement
            rate = st.number_input(
                "Tarif horaire (€ / h)",
                min_value=0.0,
                step=1.0,
                key="rate_saisie",
            )

        with col2:
            start_date = st.date_input("Date de début", value=date.today())
            start_time = st.time_input("Heure de début", value=time(9, 0))
            end_date = st.date_input("Date de fin", value=date.today())
            end_time = st.time_input("Heure de fin", value=time(10, 0))

        description = st.text_area("Description (facultatif)")

        if st.button("Enregistrer la prestation"):
            if not provider:
                st.error("Veuillez indiquer le nom du prestataire.")
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

    # ==========================
    # Onglet HISTORIQUE + FILTRES
    # ==========================

    with tab_historique:
        st.subheader("Historique des prestations et filtres")

        # Par défaut, on n'affiche que les non facturées
        include_invoiced = st.checkbox(
            "Inclure les prestations déjà facturées (archivées)",
            value=False,
        )

        invoiced_filter = None if include_invoiced else False

        df_all = load_prestations_filtered(invoiced=invoiced_filter)

        providers = ["(Tous)"] + sorted(df_all["Prestataire"].dropna().unique().tolist())
        clients_f = ["(Tous)"] + sorted(df_all["Client"].dropna().unique().tolist())
        tasks_f = ["(Tous)"] + sorted(df_all["Tâche"].dropna().unique().tolist())

        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
            f_provider = st.selectbox("Prestataire", options=providers)
        with col_f2:
            f_client = st.selectbox("Client", options=clients_f)
        with col_f3:
            f_task = st.selectbox("Tâche", options=tasks_f)

        col_f4, col_f5 = st.columns(2)
        with col_f4:
            f_start_date = st.date_input(
                "Date début (filtre)",
                value=date.today(),
                key="filter_start",
            )
        with col_f5:
            f_end_date = st.date_input(
                "Date fin (filtre)",
                value=date.today(),
                key="filter_end",
            )

        if st.button("Appliquer les filtres"):
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

                    st.markdown("---")
            st.subheader("Modifier une prestation")

            # Choix de la prestation à modifier
            labels_edit = {}
            for _, row in df.iterrows():
                rid = row["ID"]
                labels_edit[rid] = (
                    f"{row['Début']} – {row['Client']} – "
                    f"{row['Tâche']} – {row['Heures']:.2f} h – {row['Total €']:.2f} €"
                )

            edit_id = st.selectbox(
                "Sélectionnez la prestation à modifier",
                options=df["ID"].tolist(),
                format_func=lambda x: labels_edit.get(x, str(x)),
                key="edit_prestation_id",
            )

            # Ligne de la prestation sélectionnée
            row_edit = df[df["ID"] == edit_id].iloc[0]

            col_e1, col_e2 = st.columns(2)

            with col_e1:
                provider_edit = st.text_input(
                    "Prestataire",
                    value=row_edit["Prestataire"],
                    key="edit_provider",
                )

                # On part de la liste des clients actifs
                clients_all = load_clients()
                # On s'assure que le client de la prestation est présent dans la liste
                if row_edit["Client"] not in clients_all:
                    clients_all = clients_all + [row_edit["Client"]]

                # Calcul de l'index du client actuel
                try:
                    idx_client = clients_all.index(row_edit["Client"])
                except ValueError:
                    idx_client = 0

                client_edit = st.selectbox(
                    "Client",
                    options=clients_all,
                    index=idx_client if clients_all else 0,
                    key="edit_client",
                )

                # Même logique pour les tâches
                tasks_all = load_tasks()  # dict nom -> rate
                task_names = list(tasks_all.keys())
                if row_edit["Tâche"] not in task_names:
                    task_names.append(row_edit["Tâche"])

                try:
                    idx_task = task_names.index(row_edit["Tâche"])
                except ValueError:
                    idx_task = 0

                task_edit = st.selectbox(
                    "Tâche",
                    options=task_names,
                    index=idx_task if task_names else 0,
                    key="edit_task",
                )

            with col_e2:
                description_edit = st.text_area(
                    "Description",
                    value=row_edit["Description"],
                    key="edit_description",
                )

                rate_edit = st.number_input(
                    "Tarif horaire (€ / h)",
                    min_value=0.0,
                    step=1.0,
                    value=float(row_edit["Tarif €/h"]),
                    key="edit_rate",
                )

            if st.button("Enregistrer les modifications", key="btn_edit_save"):
                hours = float(row_edit["Heures"])
                new_total = round(hours * float(rate_edit), 2)

                update_prestation_basic(
                    p_id=edit_id,
                    provider=provider_edit,
                    client=client_edit,
                    task=task_edit,
                    description=description_edit,
                    rate=float(rate_edit),
                    total=new_total,
                )

                st.success("Prestation mise à jour avec succès.")
                st.cache_data.clear()


    # ==========================
    # Onglet FACTURATION / ARCHIVAGE
    # ==========================

    with tab_facturation:
        st.subheader("Préparation de facturation / Archivage")

        # On ne travaille ici QUE sur les prestations non facturées
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

            if st.button("Marquer comme facturées / archivées"):
                if not selected_ids:
                    st.error("Veuillez sélectionner au moins une prestation.")
                else:
                    mark_prestations_invoiced(selected_ids, invoice_ref.strip() or None)
                    st.success(
                        f"{len(selected_ids)} prestation(s) marquée(s) comme facturées."
                    )
                    st.cache_data.clear()


    # ==========================
    # Onglet GESTION CLIENTS / TÂCHES
    # ==========================

    with tab_gestion:
        st.subheader("Gestion des clients")

        col_c1, col_c2 = st.columns([1, 2])

        with col_c1:
            new_client = st.text_input("Nouveau client (ou à réactiver)")
            if st.button("Ajouter / Réactiver le client"):
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
            new_task_name = st.text_input("Nom de la tâche")
            new_task_rate = st.number_input(
                "Tarif horaire (€ / h)",
                min_value=0.0,
                step=1.0,
                value=0.0,
                key="rate_task",
            )

            if st.button("Ajouter / Mettre à jour la tâche"):
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


if __name__ == "__main__":
    main()











