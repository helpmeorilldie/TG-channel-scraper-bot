import asyncio, csv, time
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch, UserEmpty
from telethon.errors import FloodWaitError
from config import TG_API_ID, TG_API_HASH, PLANS, DEVICE
from db import remaining, add_usage, get_plan
from userdb import open_userdb

def client(session: str = "") -> TelegramClient:
    return TelegramClient(StringSession(session), TG_API_ID, TG_API_HASH,
                          device_model=DEVICE, system_version="1.0", app_version="1.0")

async def scrape(c, target: str, uid: int, progress):
    con = open_userdb(uid)
    plan = await get_plan(uid)
    delay = PLANS[plan]["delay"]
    left = await remaining(uid)
    if left == 0:
        con.close(); return None, "Daily limit reached."

    full = await c(GetFullChannelRequest(target))
    peer = str(target)
    total = full.full_chat.participants_count
    con.execute("INSERT OR IGNORE INTO channels(peer, title, total, started_at) VALUES(?,?,?,?)",
                (peer, full.chats[0].title, total, int(time.time())))
    con.commit()
    cursor = con.execute("SELECT cursor FROM channels WHERE peer=?", (peer,)).fetchone()[0]

    added = 0
    while cursor < total:
        if left is not None and left <= 0: break
        limit = 200 if left is None else min(200, left)
        try:
            part = await c(GetParticipantsRequest(
                channel=target, filter=ChannelParticipantsSearch(""),
                offset=cursor, limit=limit, hash=0))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5); continue
        if not part.users:
            con.execute("UPDATE channels SET finished=1 WHERE peer=?", (peer,))
            con.commit(); break

        rows = [(peer, u.id, getattr(u, "username", "") or "",
                 " ".join(filter(None, [getattr(u, "first_name", "") or "",
                                        getattr(u, "last_name", "") or ""]))
                 or ("(deleted)" if isinstance(u, UserEmpty) else ""), int(time.time()))
                for u in part.users]
        before = con.total_changes
        con.executemany("INSERT OR IGNORE INTO members(peer, user_id, username, name, scraped_at) "
                        "VALUES(?,?,?,?,?)", rows)
        new = con.total_changes - before
        con.execute("UPDATE channels SET cursor=? WHERE peer=?", (cursor + len(part.users), peer))
        con.commit()

        n = len(part.users)
        cursor += n
        added += new
        if left is not None: left -= n
        await add_usage(uid, n)
        if progress: await progress(cursor, total, left)
        await asyncio.sleep(delay * n)

    out = con.execute("SELECT user_id, username, name FROM members WHERE peer=? ORDER BY user_id",
                      (peer,)).fetchall()
    con.close()
    path = f"/tmp/{uid}_{int(time.time())}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["user_id", "username", "name"]); w.writerows(out)
    tail = " · quota hit" if left is not None and left <= 0 else ""
    return path, f"{added} new · {len(out)} stored{tail}"
