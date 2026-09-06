"""
One-click migration script: Local robur_fit.db -> Turso Cloud Database
Usage:
    python migrate_to_turso.py
Requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .streamlit/secrets.toml or environment variables.
"""
import sqlite3
import os
import toml
import libsql_client

def migrate():
    # 1. Load credentials
    turso_url = os.environ.get("TURSO_DATABASE_URL", "")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    if os.path.exists(".streamlit/secrets.toml"):
        try:
            sec = toml.load(".streamlit/secrets.toml")
            turso_url = sec.get("TURSO_DATABASE_URL", turso_url)
            turso_token = sec.get("TURSO_AUTH_TOKEN", turso_token)
        except Exception:
            pass

    if not turso_url or not turso_token:
        print("❌ Error: TURSO_DATABASE_URL or TURSO_AUTH_TOKEN missing.")
        print("Please add them to .streamlit/secrets.toml or set as environment variables.")
        return

    clean_url = turso_url.strip()
    if clean_url.startswith("libsql://"):
        clean_url = "https://" + clean_url[len("libsql://"):]

    print(f"Connecting to Turso: {clean_url}...")
    try:
        remote_client = libsql_client.create_client_sync(url=clean_url, auth_token=turso_token.strip())
    except Exception as e:
        print(f"❌ Failed to connect to Turso: {e}")
        return

    if not os.path.exists("robur_fit.db"):
        print("No local robur_fit.db found to migrate.")
        return

    local_conn = sqlite3.connect("robur_fit.db")
    local_cursor = local_conn.cursor()

    tables = [r[0] for r in local_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    print(f"Found tables to migrate: {tables}")

    for table in tables:
        create_sql = local_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()[0]
        remote_client.execute(create_sql)
        print(f"  ✅ Table ready: {table}")

        rows = local_cursor.execute(f"SELECT * FROM {table}").fetchall()
        if rows:
            col_count = len(rows[0])
            placeholders = ",".join(["?"] * col_count)
            for row in rows:
                remote_client.execute(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", list(row))
            print(f"     Uploaded {len(rows)} rows to {table}")

    local_conn.close()
    remote_client.close()
    print("\n🎉 Migration complete! Your cloud database is now fully populated and ready.")

if __name__ == "__main__":
    migrate()
