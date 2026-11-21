import os, aiosqlite, time
from datetime import datetime, timedelta
from config import PLANS, TZ, DATA_DIR

PATH = os.path.join(DATA_DIR, "bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(
  tg_id INTEGER PRIMARY KEY, account_id INTEGER,
  session_enc BLOB, created_at INTEGER);
CREATE TABLE IF NOT EXISTS plans(
  tg_id INTEGER PRIMARY KEY, plan TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS usage(
  tg_id INTEGER NOT NULL, day TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tg_id, day));
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, plan TEXT, amount INTEGER,
  utr TEXT, status TEXT DEFAULT 'pending', created_at INTEGER, decided_at INTEGER);
"""

class DB:
    def __init__(self): self.con = None
    async def init(self):
        self.con = await aiosqlite.connect(PATH)
        self.con.row_factory = aiosqlite.Row
        await self.con.executescript(SCHEMA)
        await self.con.commit()
    async def one(self, q, a=()):
        cur = await self.con.execute(q, a); r = await cur.fetchone(); await cur.close(); return r
    async def all(self, q, a=()):
        cur = await self.con.execute(q, a); r = await cur.fetchall(); await cur.close(); return r
    async def run(self, q, a=()):
        cur = await self.con.execute(q, a); await self.con.commit()
        rid = cur.lastrowid; await cur.close(); return rid

db = DB()

def today() -> str: return datetime.now(TZ).date().isoformat()

def reset_at() -> str:
    n = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return n.strftime("%d %b, %H:%M IST")

async def get_plan(tg_id: int) -> str:
    r = await db.one("SELECT plan, expires_at FROM plans WHERE tg_id=?", (tg_id,))
    return r["plan"] if r and r["expires_at"] > time.time() else "free"

async def plan_expiry(tg_id: int):
    r = await db.one("SELECT expires_at FROM plans WHERE tg_id=?", (tg_id,))
    return r["expires_at"] if r else None

async def grant(tg_id: int, plan: str, days: int) -> int:
    base = max(int(time.time()), await plan_expiry(tg_id) or 0)
    exp = base + days * 86400
    await db.run("INSERT INTO plans(tg_id, plan, expires_at) VALUES(?,?,?) "
                 "ON CONFLICT(tg_id) DO UPDATE SET plan=excluded.plan, expires_at=excluded.expires_at",
                 (tg_id, plan, exp))
    return exp

async def revoke(tg_id: int):
    await db.run("DELETE FROM plans WHERE tg_id=?", (tg_id,))

async def used_today(tg_id: int) -> int:
    r = await db.one("SELECT used FROM usage WHERE tg_id=? AND day=?", (tg_id, today()))
    return r["used"] if r else 0

async def add_usage(tg_id: int, n: int):
    await db.run("INSERT INTO usage(tg_id, day, used) VALUES(?,?,?) "
                 "ON CONFLICT(tg_id, day) DO UPDATE SET used = used + ?",
                 (tg_id, today(), n, n))

async def remaining(tg_id: int):
    cap = PLANS[await get_plan(tg_id)]["daily"]
    return None if cap is None else max(0, cap - await used_today(tg_id))

async def save_session(tg_id: int, account_id: int, blob: bytes):
    await db.run("INSERT INTO accounts(tg_id, account_id, session_enc, created_at) VALUES(?,?,?,?) "
                 "ON CONFLICT(tg_id) DO UPDATE SET account_id=excluded.account_id, "
                 "session_enc=excluded.session_enc", (tg_id, account_id, blob, int(time.time())))

async def get_session(tg_id: int):
    return await db.one("SELECT account_id, session_enc FROM accounts WHERE tg_id=?", (tg_id,))

async def drop_session(tg_id: int):
    await db.run("DELETE FROM accounts WHERE tg_id=?", (tg_id,))

async def create_payment(tg_id: int, plan: str, amount: int) -> int:
    return await db.run("INSERT INTO payments(tg_id, plan, amount, created_at) VALUES(?,?,?,?)",
                        (tg_id, plan, amount, int(time.time())))

async def open_payment(tg_id: int):
    return await db.one("SELECT * FROM payments WHERE tg_id=? AND status='pending'", (tg_id,))

async def set_utr(pid: int, utr: str):
    await db.run("UPDATE payments SET utr=? WHERE id=?", (utr, pid))

async def get_payment(pid: int):
    return await db.one("SELECT * FROM payments WHERE id=?", (pid,))

async def decide(pid: int, status: str):
    await db.run("UPDATE payments SET status=?, decided_at=? WHERE id=?",
                 (status, int(time.time()), pid))
