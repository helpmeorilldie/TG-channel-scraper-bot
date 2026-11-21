import os, time, sqlite3, asyncio
from threading import Thread
from datetime import datetime
from flask import Flask, send_from_directory
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile
from cryptography.fernet import InvalidToken
from telethon.errors import (SessionPasswordNeededError, PhoneCodeInvalidError,
                             PhoneCodeExpiredError, PhoneNumberInvalidError,
                             FloodWaitError, AuthKeyUnregisteredError)
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest

import db, jobs, tg, crypto, userdb
from config import BOT_TOKEN, ADMIN_IDS, PLANS, LABEL, PAID, DAYS, TZ, DEVICE, UPI_ID
from keyboards import (main_menu, back, plans_kb, cancel_kb, paid_kb, review_kb,
                       code_keypad, admin_menu)
from qr import card as upi_card, upi_link

# ---------------- keep-alive web server ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )

@app.route("/health")
def health():
    return "OK", 200

def run():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def keep_alive():
    server = Thread(target=run, daemon=True)
    server.start()

# ---------------- bot ----------------
router = Router()
PENDING: dict[int, tuple] = {}

def is_admin(uid: int) -> bool: return uid in ADMIN_IDS

async def notify_admins(bot: Bot, text: str, kb=None):
    for a in ADMIN_IDS:
        try: await bot.send_message(a, text, reply_markup=kb)
        except Exception: pass

async def show_home(m: Message, edit=False, clear=None):
    if clear: await clear.clear()
    logged = bool(await db.get_session(m.chat.id))
    txt = ("<b>Venice Scraper</b>\n\nLink your account, then export a member list "
           "(user id, username, name) from any channel you're in.")
    if edit: await m.edit_text(txt, reply_markup=main_menu(logged))
    else: await m.answer(txt, reply_markup=main_menu(logged))

class Login(StatesGroup):
    phone = State(); code = State(); password = State()

class Buy(StatesGroup):
    utr = State()

class Scrape(StatesGroup):
    target = State()

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await show_home(m, clear=state)

@router.callback_query(F.data == "m:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await show_home(cb.message, edit=True, clear=state); await cb.answer()

@router.callback_query(F.data == "m:help")
async def cb_help(cb: CallbackQuery):
    await cb.message.edit_text(
        "<b>How it works</b>\n\n"
        "1. Login with your phone — the code arrives in your Telegram app from "
        "<b>Telegram</b>, not from this bot.\n"
        "2. Send a channel link.\n"
        "3. Receive a CSV of user id, username, name.\n\n"
        "Full lists need admin rights in the channel. Hidden-member channels only "
        "give partial lists.\n\n"
        "Free: 200 members/day at 6 per 10 s. Paid tiers are faster and higher.",
        reply_markup=back()); await cb.answer()

@router.callback_query(F.data == "m:usage")
async def cb_usage(cb: CallbackQuery):
    uid = cb.from_user.id
    plan = await db.get_plan(uid)
    cap = PLANS[plan]["daily"]
    used = await db.used_today(uid)
    txt = (f"Plan: <b>{LABEL[plan]}</b>\nUsed today: {used} / {cap or '∞'}\n"
           f"Pace: {round(10 / PLANS[plan]['delay'])} members per 10 s")
    if cap: txt += f"\nResets: {db.reset_at()}"
    exp = await db.plan_expiry(uid)
    if exp and exp > time.time():
        txt += f"\nExpires: {datetime.fromtimestamp(exp, TZ):%d %b %Y}"
    await cb.message.edit_text(txt, reply_markup=back()); await cb.answer()

# ---------------- login ----------------
@router.callback_query(F.data == "m:login")
async def cb_login(cb: CallbackQuery, state: FSMContext):
    if await db.get_session(cb.from_user.id):
        return await cb.answer("Already linked.", show_alert=True)
    await state.set_state(Login.phone)
    await cb.message.edit_text(
        "Send your number in international format, e.g. <code>+9198xxxxxxxx</code>.\n\n"
        "The login code appears in your Telegram app from <b>Telegram</b>.",
        reply_markup=cancel_kb()); await cb.answer()

@router.message(Login.phone, F.text)
async def on_phone(m: Message, state: FSMContext):
    phone = m.text.strip().replace(" ", "")
    if not phone.startswith("+") or not phone[1:].isdigit():
        return await m.answer("Include the + and country code.", reply_markup=cancel_kb())
    c = tg.client()
    await c.connect()
    try:
        await c.send_code_request(phone)
    except FloodWaitError as e:
        await c.disconnect(); return await m.answer(f"Throttled, retry in {e.seconds}s.")
    except PhoneNumberInvalidError:
        await c.disconnect(); return await m.answer("Number rejected.")
    PENDING[m.from_user.id] = (c, phone)
    await state.set_state(Login.code)
    await state.update_data(code="")
    await m.answer("Tap the digits of your code:", reply_markup=code_keypad(""))

@router.callback_query(Login.code, F.data.startswith("c:"))
async def on_key(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    code = d.get("code", "")
    act = cb.data[2:]

    if act == "del":
        code = code[:-1]
    elif act == "ok":
        if len(code) < 5: return await cb.answer("Need 5 digits.", show_alert=True)
        c, phone = PENDING[cb.from_user.id]
        try:
            await c.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            await state.set_state(Login.password)
            return await cb.message.edit_text("Two-step verification is on. Type your password:",
                                              reply_markup=cancel_kb())
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await state.update_data(code="")
            return await cb.message.edit_text("Wrong or expired. Try again:",
                                              reply_markup=code_keypad(""))
        return await finish(cb, state, c)
    elif len(code) < 6:
        code += act

    await state.update_data(code=code)
    shown = " ".join(code) or "—"
    await cb.message.edit_text(f"Code: <code>{shown}</code>", reply_markup=code_keypad(code))
    await cb.answer()

@router.message(Login.password, F.text)
async def on_password(m: Message, state: FSMContext):
    c, _ = PENDING[m.from_user.id]
    try:
        await c.sign_in(password=m.text.strip())
    except Exception as e:
        return await m.answer(f"Rejected ({type(e).__name__}). Try again.")
    finally:
        await m.delete()
    await finish(m, state, c)

async def finish(m, state, c):
    uid = m.from_user.id
    me = await c.get_me()
    await db.save_session(uid, me.id, crypto.enc(c.session.save()))
    await c.disconnect()
    PENDING.pop(uid, None)
    await state.clear()
    await m.answer(f"✅ Linked as <b>{me.first_name or me.id}</b>.", reply_markup=main_menu(True))

# ---------------- scrape ----------------
@router.callback_query(F.data == "m:scrape")
async def cb_scrape(cb: CallbackQuery, state: FSMContext):
    if not await db.get_session(cb.from_user.id):
        return await cb.answer("Login first.", show_alert=True)
    await state.set_state(Scrape.target)
    await cb.message.edit_text("Send the channel link or @username:", reply_markup=cancel_kb())
    await cb.answer()

@router.message(Command("scrape"))
async def cmd_scrape(m: Message, state: FSMContext):
    a = m.text.split(maxsplit=1)
    if len(a) < 2: return await m.answer("Usage: <code>/scrape &lt;link&gt;</code>")
    await run_scrape(m, a[1].strip(), state)

@router.message(Scrape.target, F.text)
async def on_target(m: Message, state: FSMContext):
    await run_scrape(m, m.text.strip(), state)

async def run_scrape(m: Message, target: str, state: FSMContext):
    uid = m.from_user.id
    if not await db.get_session(uid):
        return await m.answer("Login first.", reply_markup=main_menu(False))
    if jobs.busy(uid): return await m.answer("One scrape at a time.")
    if await db.remaining(uid) == 0:
        return await m.answer(f"Daily limit reached. Resets {db.reset_at()}.", reply_markup=main_menu(True))
    await state.clear()

    msg = await m.answer("Starting…")
    last = [0.0]

    async def progress(done, total, left):
        if time.time() - last[0] < 8: return
        last[0] = time.time()
        try:
            await msg.edit_text(f"{done}/{total}" + (f" · {left} left today" if left is not None else ""))
        except Exception: pass

    async with jobs.lock(uid):
        sess = await db.get_session(uid)
        try:
            c = tg.client(crypto.dec(sess["session_enc"]))
        except InvalidToken:
            await db.drop_session(uid)
            return await m.answer("Stored session is unreadable. /login again.")
        await c.connect()
        try:
            path, note = await tg.scrape(c, target, uid, progress)
            if path:
                await m.answer_document(FSInputFile(path), caption=note); os.remove(path)
            else:
                await m.answer(note)
            await msg.delete()
        except AuthKeyUnregisteredError:
            await db.drop_session(uid)
            await m.answer("Session revoked from your phone. /login again.")
        except Exception as e:
            await m.answer(f"Failed: {type(e).__name__}")
        finally:
            await c.disconnect()

# ---------------- premium + manual review ----------------
@router.callback_query(F.data == "m:premium")
async def cb_premium(cb: CallbackQuery):
    plan = await db.get_plan(cb.from_user.id)
    await cb.message.edit_text(
        f"Current plan: <b>{LABEL[plan]}</b>\n\n"
        "Pay by UPI, tap <b>I've paid</b>, send the UTR. An admin activates your plan manually.",
        reply_markup=plans_kb()); await cb.answer()

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if await db.open_payment(uid):
        return await cb.answer("You already have a pending payment.", show_alert=True)
    plan = cb.data[4:]
    amount = PLANS[plan]["price"]
    pid = await db.create_payment(uid, plan, amount)
    path = upi_card(plan, amount, str(pid))
    await cb.message.answer_photo(
        FSInputFile(path),
        caption=(f"<b>{LABEL[plan]} — ₹{amount}</b>\n"
                 f"UPI: <code>{UPI_ID}</code>\n"
                 f"Tap to pay: <code>{upi_link(amount, f'{plan} {pid}')}</code>\n\n"
                 f"After paying, press <b>I've paid</b> and send the UTR."),
        reply_markup=paid_kb(pid))
    os.remove(path)
    await state.set_state(Buy.utr)
    await state.update_data(pid=pid)
    await cb.answer()

@router.callback_query(F.data.startswith("paid:"))
async def cb_paid(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data[5:])
    pay = await db.get_payment(pid)
    if not pay or pay["status"] != "pending":
        return await cb.answer("Not pending.", show_alert=True)
    await state.set_state(Buy.utr)
    await state.update_data(pid=pid)
    await cb.message.answer("Send the UTR / reference number from your UPI app.")
    await cb.answer()

@router.message(Buy.utr, F.text)
async def on_utr(m: Message, state: FSMContext):
    d = await state.get_data()
    utr = m.text.strip().upper()
    if not (10 <= len(utr) <= 22 and utr.replace("-", "").isalnum()):
        return await m.answer("That doesn't look like a UTR. 10–22 letters/digits.")
    await db.set_utr(d["pid"], utr)
    await state.clear()

    pay = await db.get_payment(d["pid"])
    await m.answer(f"⏳ Payment #{d['pid']} submitted for review.", reply_markup=main_menu(True))
    await notify_admins(
        m.bot,
        f"🧾 <b>Review needed</b> · #{d['pid']}\n"
        f"{LABEL[pay['plan']]} · ₹{pay['amount']}\n"
        f"User <code>{pay['tg_id']}</code>\nUTR <code>{utr}</code>",
        review_kb(d["pid"]))

@router.callback_query(F.data.startswith("ap:"))
async def cb_approve(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Admins only.", show_alert=True)
    pid = int(cb.data[3:])
    pay = await db.get_payment(pid)
    if not pay or pay["status"] != "pending": return await cb.answer("Not pending.")
    exp = await db.grant(pay["tg_id"], pay["plan"], DAYS)
    await db.decide(pid, "approved")
    until = datetime.fromtimestamp(exp, TZ).strftime("%d %b %Y")
    await cb.message.edit_text(f"✅ #{pid} approved — {LABEL[pay['plan']]} until {until}.")
    await cb.answer()
    try:
        await cb.bot.send_message(pay["tg_id"],
            f"✅ Payment confirmed. <b>{LABEL[pay['plan']]}</b> active until {until}.")
    except Exception: pass

@router.callback_query(F.data.startswith("rj:"))
async def cb_reject(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Admins only.", show_alert=True)
    pid = int(cb.data[3:])
    pay = await db.get_payment(pid)
    if not pay or pay["status"] != "pending": return await cb.answer("Not pending.")
    await db.decide(pid, "rejected")
    await cb.message.edit_text(f"❌ #{pid} rejected.")
    await cb.answer()
    try:
        await cb.bot.send_message(pay["tg_id"],
            f"❌ Payment #{pid} rejected. Recheck the UTR and submit again.")
    except Exception: pass

# ---------------- admin ----------------
@router.message(Command("admin"))
async def cmd_admin(m: Message):
    if not is_admin(m.from_user.id): return
    await m.answer("Admin panel:", reply_markup=admin_menu())

@router.callback_query(F.data == "a:pending")
async def a_pending(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Admins only.", show_alert=True)
    rows = await db.all("SELECT * FROM payments WHERE status='pending' ORDER BY id")
    if not rows: return await cb.answer("Queue empty.", show_alert=True)
    for p in rows[:15]:
        await cb.message.answer(
            f"#{p['id']} · {LABEL[p['plan']]} ₹{p['amount']}\n"
            f"User <code>{p['tg_id']}</code>\nUTR <code>{p['utr'] or '—'}</code>",
            reply_markup=review_kb(p["id"]))
    await cb.answer()

@router.callback_query(F.data == "a:stats")
async def a_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Admins only.", show_alert=True)
    acc = await db.one("SELECT COUNT(*) c FROM accounts")
    pay = await db.one("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM payments WHERE status='approved'")
    pend = await db.one("SELECT COUNT(*) c FROM payments WHERE status='pending'")
    await cb.message.answer(
        f"Linked accounts: {acc['c']}\nApproved: {pay['c']} · ₹{pay['s']}\nPending: {pend['c']}")
    await cb.answer()

@router.message(Command("grant"))
async def cmd_grant(m: Message):
    if not is_admin(m.from_user.id): return
    try:
        _, uid, plan, days = m.text.split()
        assert plan in PAID
        exp = await db.grant(int(uid), plan, int(days))
    except Exception:
        return await m.answer("Usage: <code>/grant &lt;uid&gt; &lt;plan&gt; &lt;days&gt;</code>")
    await m.answer(f"Granted {LABEL[plan]} until {datetime.fromtimestamp(exp, TZ):%d %b %Y}.")

@router.message(Command("revoke"))
async def cmd_revoke(m: Message):
    if not is_admin(m.from_user.id): return
    try: uid = int(m.text.split()[1])
    except Exception: return await m.answer("Usage: <code>/revoke &lt;uid&gt;</code>")
    await db.revoke(uid)
    await m.answer("Revoked.")

# ---------------- misc ----------------
@router.callback_query(F.data == "m:channels")
async def cb_channels(cb: CallbackQuery):
    try:
        con = sqlite3.connect(userdb.path(cb.from_user.id))
        rows = con.execute("SELECT title, total, cursor, finished FROM channels").fetchall()
        con.close()
    except sqlite3.OperationalError:
        rows = []
    if not rows: return await cb.answer("Nothing scraped yet.", show_alert=True)
    txt = "\n".join(f"· {t} — {c}/{tot}{' ✅' if f else ''}" for t, tot, c, f in rows[:20])
    await cb.message.edit_text(f"<b>Your channels</b>\n{txt}", reply_markup=back())
    await cb.answer()

@router.callback_query(F.data == "m:logout")
async def cb_logout(cb: CallbackQuery):
    uid = cb.from_user.id
    s = await db.get_session(uid)
    if not s: return await cb.answer("Not linked.")
    try:
        c = tg.client(crypto.dec(s["session_enc"]))
    except InvalidToken:
        await db.drop_session(uid)
        return await cb.message.edit_text("Unreadable session, dropped.", reply_markup=main_menu(False))
    await c.connect()
    try:
        for a in (await c(GetAuthorizationsRequest())).authorizations:
            if a.device_model == DEVICE:
                await c(ResetAuthorizationRequest(a.hash))
    except AuthKeyUnregisteredError:
        pass
    finally:
        await c.disconnect()
    await db.drop_session(uid)
    await cb.message.edit_text("Session revoked and account unlinked.", reply_markup=main_menu(False))
    await cb.answer()

# ---------------- entry point ----------------
async def main():
    await db.db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
