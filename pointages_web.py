import sqlite3
from datetime import datetime, date, time

import pandas as pd
import streamlit as st


DB_PATH = "prestations.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def load_clients():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM clients WHERE active = 1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_tasks():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, rate FROM tasks WHERE active = 1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return {name: rate for name, rate in rows}


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
# FONCTION CORRIGÉE (IMPORTANT)
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

    # Retourne un DataFrame même s’il est vide
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
# APPLICATION STREAMLIT
# ==========================

def main():
    st.set_page_config(page_title="Pointage de temps", layout="wide")

    st.title("Application de pointage d'heures – Version Web")

    clients = load_clients()
    tasks = load_tasks()

    tab_saisie, tab_historique = st.tabs(["Saisir une prestation", "Historique et filtres"])

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

            rate = st.number_input(
                "Tarif horaire (€ / h)", min_value=0.0, step=1.0, value=float(default_rate)
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
            f_start_date = st.date_input("Date début (filtre)", value=None)
        with col_f5:
            f_end_date = st.date_input("Date fin (filtre)", value=None)

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

        st.write(f"{len(df)} prestations trouvées.")

        if not df.empty:
            st.dataframe(df, use_container_width=True)

            total_global = df["Total €"].sum()
            st.info(f"Total global : {total_global:.2f} €")

            st.write("Total par client")
            st.dataframe(df.groupby("Client")["Total €"].sum().reset_index())

            st.write("Total par prestataire")
            st.dataframe(df.groupby("Prestataire")["Total €"].sum().reset_index())
        else:
            st.warning("Aucune prestation trouvée.")


if __name__ == "__main__":
    main()
