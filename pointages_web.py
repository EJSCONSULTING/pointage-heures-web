import sqlite3
from datetime import datetime, date, time

import pandas as pd
import streamlit as st


DB_PATH = "prestations.db"


# ==========================
# Fonctions base de données
# ==========================

def get_connection():
    return sqlite3.connect(DB_PATH)


def load_clients():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM clients WHERE active = 1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_all_clients():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, active FROM clients ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    data = []
    for cid, name, active in rows:
        data.append(
            {"ID": cid, "Nom": name, "Actif": bool(active)}
        )
    return pd.DataFrame(data)


def add_or_reactivate_client(name: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM clients WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE clients SET active = 1 WHERE id = ?", (row[0],))
    else:
        cur.execute("INSERT INTO clients (name, active) VALUES (?, 1)", (name,))
    conn.commit()
    conn.close()


def load_tasks():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, rate FROM tasks WHERE active = 1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return {name: rate for name, rate in rows}


def load_all_tasks():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, rate, active FROM tasks ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    data = []
    for tid, name, rate, active in rows:
        data.append(
            {"ID": tid, "Tâche": name, "Tarif €/h": rate, "Actif": bool(active)}
        )
    return pd.DataFrame(data)


def upsert_task(name: str, rate: float):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tasks WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE tasks SET rate = ?, active = 1 WHERE id = ?",
            (rate, row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO tasks (name, rate, active) VALUES (?, ?, 1)",
            (name, rate),
        )
    conn.commit()
    conn.close()


def insert_prestation(provider, client, task, description, start_dt, end_dt, rate):
    hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    total = round(hours * rate, 2)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO prestations
        (provider, client, task, description, start, end, hours, rate, total, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provider,
            client,
            task,
            description,
            start_dt.isoformat(timespec="seconds"),
            end_dt.isoformat(timespec="seconds"),
            hours,
            rate,
            total,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()
    return hours, total


# ==========================
# Historique + filtres
# ==========================

def load_prestations_filtered(provider=None, client=None, task=None,
                              start_date=None, end_date=None):
    conn = get_connection()
    cur = conn.cursor()

    sql = """
        SELECT provider, client, task, description, start, end, hours, rate, total
        FROM prestations
    """
    conditions = []
    params = []

    if provider and provider != "(Tous)":
        conditions.append("provider = ?")
        params.append(provider)

    if client and client != "(Tous)":
        conditions.append("client = ?")
        params.append(client)

    if task and task != "(Tous)":
        conditions.append("task = ?")
        params.append(task)

    if start_date:
        start_dt = datetime.combine(start_date, time(0, 0, 0))
        conditions.append("start >= ?")
        params.append(start_dt.isoformat(timespec="seconds"))

    if end_date:
        end_dt = datetime.combine(end_date, time(23, 59, 59))
        conditions.append("start <= ?")
        params.append(end_dt.isoformat(timespec="seconds"))

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY start ASC"

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    data = []
    for provider_, client_, task_, desc, start_str, end_str, hours, rate, total in rows:
        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)
        except Exception:
            start_dt = start_str
            end_dt = end_str

        data.append({
            "Prestataire": provider_ or "",
            "Client": client_,
            "Tâche": task_,
            "Description": desc or "",
            "Début": start_dt,
            "Fin": end_dt,
            "Heures": hours,
            "Tarif €/h": rate,
            "Total €": total,
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
# Application Streamlit
# ==========================

def main():
    st.set_page_config(page_title="Pointage de temps", layout="wide")

    st.title("Application de pointage d'heures – Version Web")

    # Charger les listes pour les combos
    clients = load_clients()
    tasks = load_tasks()

    tab_saisie, tab_historique, tab_gestion = st.tabs(
        ["Saisir une prestation", "Historique et filtres", "Gestion clients / tâches"]
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
            task = st.selectbox("Tâche", options=[""] + list(tasks.keys()))

            default_rate = tasks.get(task, 0.0)
            rate = st.number_input("Tarif horaire (€ / h)", min_value=0.0, step=1.0, value=float(default_rate), key="rate_saisie")


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
                    st.experimental_rerun()

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
            new_task_rate = st.number_input("Tarif horaire (€ / h)", min_value=0.0, step=1.0, value=0.0, key="rate_task")


            if st.button("Ajouter / Mettre à jour la tâche"):
                if not new_task_name.strip():
                    st.error("Veuillez saisir un nom de tâche.")
                elif new_task_rate <= 0:
                    st.error("Le tarif doit être supérieur à 0.")
                else:
                    upsert_task(new_task_name.strip(), float(new_task_rate))
                    st.success(f"Tâche « {new_task_name.strip()} » enregistrée / mise à jour.")
                    st.experimental_rerun()

        with col_t2:
            df_tasks = load_all_tasks()
            if not df_tasks.empty:
                st.write("Liste des tâches")
                st.dataframe(df_tasks, use_container_width=True)
            else:
                st.info("Aucune tâche dans la base.")


if __name__ == "__main__":
    main()
