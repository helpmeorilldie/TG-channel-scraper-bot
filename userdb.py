import sqlite3, os
from config import DATA_DIR

DIR = os.path.join(DATA_DIR, "data")

def path(tg_id: int) -> str:
    os.makedirs(DIR, exist_ok=True)
    return os.path.join(DIR, f"{tg_id}.db")

def open_userdb(tg_id: int) -> sqlite3.Connection:
    con = sqlite3.connect(path(tg_id))
    con.executescript("""
    CREATE TABLE IF NOT EXISTS members(
      peer TEXT NOT NULL, user_id INTEGER NOT NULL,
      username TEXT, name TEXT, scraped_at INTEGER,
      PRIMARY KEY(peer, user_id));
    CREATE TABLE IF NOT EXISTS channels(
      peer TEXT PRIMARY KEY, title TEXT, total INTEGER,
      cursor INTEGER DEFAULT 0, finished INTEGER DEFAULT 0, started_at INTEGER);
    """)
    return con
