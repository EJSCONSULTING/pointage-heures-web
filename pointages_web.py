import os
from datetime import datetime, date, time

import pandas as pd
import psycopg2
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
        # Debug lisible si ça casse encore
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
                (provider, client, task, description, start_at, end_at, hours, rate, total, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
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


# ==========================
# Historique + filtres
# ==========================

def load_prestations_filtered(provider=None, client=None, task=None,
                              start_date=None, end_date=None):
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

    sql = """
        SELECT provider, client, task, description, start_at, end_at, hours, rate, total
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
    for provider_, client_, task_, desc, start_dt, end_dt, hours, rate, total in rows:
        data.append({
            "Prestataire": provider_ or "",
            "Client": client_,
            "Tâche": task_,
            "Description": desc or "",
            "Début": start_dt,
            "Fin": end_dt,
            "Heures": float(hours),
            "Tarif €/h": float(rate),
            "Total €": float(total),
        })

    if not data:
        return pd.DataFrame(
            columns=[
                "Prestataire",
                "Client",
                "Tâche",
                "Description",
                "Début",
                "Fin",
                "Heures",
                "Tarif €/h",
                "Total €",
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

    # S'assurer que quelques tâches par défaut existent
    ensure_default_tasks()

    clients = load_clients()
    tasks = load_tasks()

    tab_saisie, tab_historique, tab_gestion = st.tabs(
        ["Saisir une prestation", "Historique et filtres", "Gestion clients / tâches"]
    )

    # ==========================
    # Onglet SAISIE PRESTATION
    # ==========================

    elif menu == "Saisir une prestation":

    st.subheader("Encoder une prestation")

    col1, col2 = st.columns(2)

    with col1:
        provider = st.text_input("Prestataire")

        clients = load_clients()
        tasks = load_tasks()

        client = st.selectbox("Client", options=[""] + clients)

        task = st.selectbox("Tâche", options=[""] + list(tasks.keys()))

        rate = st.number_input("Tarif horaire (€ / h)", min_value=0.0, step=1.0, value=0.0)

    # ==========================
    # Onglet HISTORIQUE + FILTRES
    # ==========================

    with tab_historique:
        st.subheader("Historique des prestations et filtres")

        df_all = load_prestations_filtered()

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
            f_start_date = st.date_input("Date début (filtre)", value=None, key="filter_start")
        with col_f5:
            f_end_date = st.date_input("Date fin (filtre)", value=None, key="filter_end")

        if st.button("Appliquer les filtres"):
            df = load_prestations_filtered(
                provider=f_provider,
                client=f_client,
                task=f_task,
                start_date=f_start_date if isinstance(f_start_date, date) else None,
                end_date=f_end_date if isinstance(f_end_date, date) else None,
            )
        else:
            df = df_all

        st.write(f"{len(df)} prestation(s) trouvée(s).")

        if not df.empty:
            st.dataframe(df, use_container_width=True)

            total_global = df["Total €"].sum()
            st.info(f"Total global : {total_global:.2f} €")

            st.write("Total par client")
            st.dataframe(df.groupby("Client")["Total €"].sum().reset_index(), use_container_width=True)

            st.write("Total par prestataire")
            st.dataframe(df.groupby("Prestataire")["Total €"].sum().reset_index(), use_container_width=True)

            # Export CSV des résultats filtrés
            csv_data = df.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Télécharger les résultats filtrés (CSV)",
                data=csv_data,
                file_name="prestations_filtrees.csv",
                mime="text/csv",
            )
        else:
            st.warning("Aucune prestation trouvée avec ces filtres.")

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
                    st.rerun()

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
                    st.rerun()

        with col_t2:
            df_tasks = load_all_tasks()
            if not df_tasks.empty:
                st.write("Liste des tâches")
                st.dataframe(df_tasks, use_container_width=True)
            else:
                st.info("Aucune tâche dans la base.")


if __name__ == "__main__":
    main()



