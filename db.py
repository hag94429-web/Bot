import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = "bot.db"
UKRAINE_TZ = ZoneInfo("Europe/Kyiv")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_modes (
            sender_id INTEGER PRIMARY KEY,
            targets TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reply_map (
            message_id INTEGER PRIMARY KEY,
            target_user_id INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_key TEXT PRIMARY KEY,
            targets TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            payload TEXT,
            paid_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            user_id INTEGER PRIMARY KEY,
            received_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

def serialize_targets(targets: list[str]) -> str:
    return ",".join(str(x) for x in targets)

def deserialize_targets(raw: str) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]

def ensure_user(user_id: int, username: str | None = None, first_name: str | None = None):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        username,
        first_name,
        datetime.now(UKRAINE_TZ).strftime("%Y-%m-%d %H:%M:%S")
    ))

    cur.execute("""
        UPDATE users
        SET username = ?, first_name = ?
        WHERE user_id = ?
    """, (username, first_name, user_id))

    cur.execute("""
        INSERT OR IGNORE INTO counters (user_id, received_count)
        VALUES (?, 0)
    """, (user_id,))

    conn.commit()
    conn.close()

def get_users_count() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    row = cur.fetchone()
    conn.close()
    return int(row["cnt"])

def get_all_user_ids() -> list[int]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [int(row["user_id"]) for row in rows]

def delete_users(user_ids: list[int]) -> int:
    if not user_ids:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    removed = 0

    for uid in user_ids:
        cur.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        removed += cur.rowcount

    conn.commit()
    conn.close()
    return removed

def set_user_mode(sender_id: int, targets: list[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO user_modes (sender_id, targets)
        VALUES (?, ?)
    """, (sender_id, serialize_targets(targets)))
    conn.commit()
    conn.close()

def get_user_mode(sender_id: int) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT targets FROM user_modes WHERE sender_id = ?", (sender_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return []
    return deserialize_targets(row["targets"])

def delete_user_mode(sender_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_modes WHERE sender_id = ?", (sender_id,))
    conn.commit()
    conn.close()

def set_reply_target(message_id: int, target_user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO reply_map (message_id, target_user_id)
        VALUES (?, ?)
    """, (message_id, target_user_id))
    conn.commit()
    conn.close()

def get_reply_target(message_id: int) -> int | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT target_user_id FROM reply_map WHERE message_id = ?", (message_id,))
    row = cur.fetchone()
    conn.close()

    return int(row["target_user_id"]) if row else None

def create_team(team_key: str, targets: list[str], created_by: int | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO teams (team_key, targets, created_by, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        team_key,
        serialize_targets(targets),
        created_by,
        datetime.now(UKRAINE_TZ).strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def team_exists(team_key: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM teams WHERE team_key = ?", (team_key,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def get_team_targets(team_key: str) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT targets FROM teams WHERE team_key = ?", (team_key,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return []
    return deserialize_targets(row["targets"])

def get_all_teams():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT team_key, targets, created_by, created_at
        FROM teams
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_teams_count() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM teams")
    row = cur.fetchone()
    conn.close()
    return int(row["cnt"])

def add_payment(
    user_id: int,
    username: str | None,
    first_name: str | None,
    amount: int,
    currency: str,
    payload: str | None
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (
            user_id, username, first_name, amount, currency, payload, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        first_name,
        amount,
        currency,
        payload,
        datetime.now(UKRAINE_TZ).strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def get_last_payments(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, first_name, amount, currency, payload, paid_at
        FROM payments
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_total_stars() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments")
    row = cur.fetchone()
    conn.close()
    return int(row["total"]) if row else 0

def increment_received_count(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO counters (user_id, received_count)
        VALUES (?, 0)
    """, (user_id,))

    cur.execute("""
        UPDATE counters
        SET received_count = received_count + 1
        WHERE user_id = ?
    """, (user_id,))

    cur.execute("SELECT received_count FROM counters WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    conn.commit()
    conn.close()
    return int(row["received_count"])

def get_received_count(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT received_count FROM counters WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row["received_count"]) if row else 0