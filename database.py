import psycopg2
import pandas as pd
import streamlit as st
from datetime import datetime, time

# --- Connexion ---
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

# --- Clients ---
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
                INSERT INTO clients (name, active) VALUES (%s, true)
                ON CONFLICT (name) DO UPDATE SET active = true;
                """,
                (name,),
            )
        conn.commit()

# --- Tâches ---
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
        data.append({"ID": tid, "Tâche": name, "Tarif €/h": float(rate), "Actif": bool(active)})
    return pd.DataFrame(data)

def upsert_task(name: str, rate: float):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (name, rate, active) VALUES (%s, %s, true)
                ON CONFLICT (name) DO UPDATE SET rate = EXCLUDED.rate, active = true;
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
                default_tasks = {"Analyse": 75.0, "Consultance": 90.0, "Déplacement": 50.0, "Administration": 60.0}
                for name, rate in default_tasks.items():
                    cur.execute(
                        "INSERT INTO tasks (name, rate, active) VALUES (%s, %s, true) ON CONFLICT (name) DO NOTHING;",
                        (name, rate),
                    )
        conn.commit()

# --- Prestataires ---
@st.cache_data(ttl=60)
def load_providers():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM providers WHERE active = true ORDER BY name;")
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
                "INSERT INTO providers (name, active) VALUES (%s, true) ON CONFLICT (name) DO UPDATE SET active = true;",
                (name,),
            )
        conn.commit()

# --- Prestations ---
def insert_prestation(provider, client, task, description, start_dt, end_dt, rate):
    hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    total = round(hours * rate, 2)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prestations (provider, client, task, description, start_at, end_at, hours, rate, total, created_at, invoiced)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), false)
                """,
                (provider, client, task, description, start_dt, end_dt, hours, rate, total),
            )
        conn.commit()
    return hours, total

def mark_prestations_invoiced(ids, invoice_ref):
    if not ids: return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE prestations SET invoiced = true, invoiced_at = now(), invoice_ref = %s WHERE id = ANY(%s)",
                (invoice_ref, list(ids)),
            )
        conn.commit()

def delete_prestations(ids):
    if not ids: return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prestations WHERE id = ANY(%s);", (list(ids),))
        conn.commit()

@st.cache_data(ttl=60)
def load_prestations_filtered(provider=None, client=None, task=None, start_date=None, end_date=None, invoiced=None):
    conditions, params = [], []
    
    if provider and provider != "(Tous)":
        conditions.append("provider = %s"); params.append(provider)
    if client and client != "(Tous)":
        conditions.append("client = %s"); params.append(client)
    if task and task != "(Tous)":
        conditions.append("task = %s"); params.append(task)
    if start_date:
        conditions.append("start_at >= %s"); params.append(datetime.combine(start_date, time(0, 0, 0)))
    if end_date:
        conditions.append("start_at <= %s"); params.append(datetime.combine(end_date, time(23, 59, 59)))
    if invoiced is True: conditions.append("invoiced = true")
    elif invoiced is False: conditions.append("invoiced = false")

    sql = "SELECT id, provider, client, task, description, start_at, end_at, hours, rate, total, invoiced, invoice_ref, invoiced_at FROM prestations"
    if conditions: sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY start_at ASC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    data = []
    for r in rows:
        data.append({
            "ID": r[0], "Prestataire": r[1] or "", "Client": r[2], "Tâche": r[3], "Description": r[4] or "",
            "Début": r[5], "Fin": r[6], "Heures": float(r[7]), "Tarif €/h": float(r[8]), "Total €": float(r[9]),
            "Facturée": bool(r[10]), "Réf facture": r[11] or "", "Date facturation": r[12],
        })
    
    if not data:
        return pd.DataFrame(columns=["ID", "Prestataire", "Client", "Tâche", "Description", "Début", "Fin", "Heures", "Tarif €/h", "Total €", "Facturée", "Réf facture", "Date facturation"])
    return pd.DataFrame(data)

def clear_prestations_cache():
    try: load_prestations_filtered.clear()
    except: pass