import json
import os
import sqlite3

DB_PATH = "bot.db"

USERS_FILE = "users.json"
USER_MODES_FILE = "user_modes.json"
REPLY_MAP_FILE = "reply_map.json"
PAYMENTS_FILE = "payments.json"
TEAMS_FILE = "teams.json"
COUNTERS_FILE = "counters.json"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if data is not None else default
    except Exception:
        return default


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


def migrate_users():
    users = load_json(USERS_FILE, {})
    if not isinstance(users, dict):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for user_id, data in users.items():
        if not str(user_id).isdigit():
            continue

        data = data if isinstance(data, dict) else {}
        username = data.get("username")
        first_name = data.get("first_name")
        joined_at = data.get("joined") or data.get("joined_at")

        cur.execute("""
            INSERT OR REPLACE INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
        """, (
            int(user_id),
            username,
            first_name,
            joined_at
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def migrate_user_modes():
    modes = load_json(USER_MODES_FILE, {})
    if not isinstance(modes, dict):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for sender_id, targets in modes.items():
        if not str(sender_id).isdigit():
            continue

        if isinstance(targets, list):
            targets_str = ",".join(str(x).strip() for x in targets if str(x).strip())
        else:
            targets_str = str(targets).strip()

        if not targets_str:
            continue

        cur.execute("""
            INSERT OR REPLACE INTO user_modes (sender_id, targets)
            VALUES (?, ?)
        """, (
            int(sender_id),
            targets_str
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def migrate_reply_map():
    reply_map = load_json(REPLY_MAP_FILE, {})
    if not isinstance(reply_map, dict):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for message_id, target_user_id in reply_map.items():
        if not str(message_id).isdigit():
            continue
        if not str(target_user_id).isdigit():
            continue

        cur.execute("""
            INSERT OR REPLACE INTO reply_map (message_id, target_user_id)
            VALUES (?, ?)
        """, (
            int(message_id),
            int(target_user_id)
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def migrate_teams():
    teams = load_json(TEAMS_FILE, {})
    if not isinstance(teams, dict):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for team_key, targets in teams.items():
        if not team_key:
            continue

        if isinstance(targets, list):
            targets_str = ",".join(str(x).strip() for x in targets if str(x).strip())
        else:
            targets_str = str(targets).strip()

        if not targets_str:
            continue

        cur.execute("""
            INSERT OR REPLACE INTO teams (team_key, targets, created_by, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            str(team_key),
            targets_str,
            None,
            None
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def migrate_payments():
    payments = load_json(PAYMENTS_FILE, [])
    if not isinstance(payments, list):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for p in payments:
        if not isinstance(p, dict):
            continue

        user_id = p.get("user_id", p.get("user"))
        amount = p.get("amount", 0)
        currency = p.get("currency", "XTR")
        payload = p.get("payload")
        paid_at = p.get("date", p.get("paid_at"))
        username = p.get("username")
        first_name = p.get("first_name")

        if not str(user_id).isdigit():
            continue

        try:
            amount = int(amount)
        except Exception:
            continue

        if not paid_at:
            paid_at = "unknown"

        cur.execute("""
            INSERT INTO payments (
                user_id, username, first_name, amount, currency, payload, paid_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            int(user_id),
            username,
            first_name,
            amount,
            currency,
            payload,
            paid_at
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def migrate_counters():
    counters = load_json(COUNTERS_FILE, {})
    if not isinstance(counters, dict):
        return 0

    conn = get_conn()
    cur = conn.cursor()
    count = 0

    for user_id, data in counters.items():
        if not str(user_id).isdigit():
            continue

        if isinstance(data, dict):
            received = data.get("received", data.get("received_count", 0))
        else:
            received = 0

        try:
            received = int(received)
        except Exception:
            received = 0

        cur.execute("""
            INSERT OR REPLACE INTO counters (user_id, received_count)
            VALUES (?, ?)
        """, (
            int(user_id),
            received
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def main():
    init_db()

    users_count = migrate_users()
    modes_count = migrate_user_modes()
    reply_count = migrate_reply_map()
    teams_count = migrate_teams()
    payments_count = migrate_payments()
    counters_count = migrate_counters()

    print("✅ Міграція завершена")
    print(f"Users: {users_count}")
    print(f"User modes: {modes_count}")
    print(f"Reply map: {reply_count}")
    print(f"Teams: {teams_count}")
    print(f"Payments: {payments_count}")
    print(f"Counters: {counters_count}")
    print(f"DB file: {DB_PATH}")


if __name__ == "__main__":
    main()