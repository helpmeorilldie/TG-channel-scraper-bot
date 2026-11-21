from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import LABEL, PLANS, PAID

def btn(text, data=None, style=None, **kw):
    kw["text"] = text
    if data: kw["callback_data"] = data
    if style:
        try: return InlineKeyboardButton(style=style, **kw)
        except TypeError: return InlineKeyboardButton(**kw)
    return InlineKeyboardButton(**kw)

def main_menu(logged_in: bool):
    rows = []
    if logged_in:
        rows.append([btn("📤 Scrape members", "m:scrape", style="primary")])
        rows.append([btn("📊 Usage", "m:usage", style="primary"),
                     btn("📁 My channels", "m:channels", style="primary")])
        rows.append([btn("💎 Premium", "m:premium", style="success")])
        rows.append([btn("🚪 Logout", "m:logout", style="danger")])
    else:
        rows.append([btn("🔐 Login", "m:login", style="success")])
        rows.append([btn("💎 Premium", "m:premium", style="success"),
                     btn("❓ Help", "m:help", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back(data="m:home"):
    return InlineKeyboardMarkup(inline_keyboard=[[btn("◀️ Back", data, style="primary")]])

def plans_kb():
    rows = [[btn(f"{LABEL[p]} — ₹{PLANS[p]['price']}", f"buy:{p}",
                 style="danger" if p == "premium_max" else "success")] for p in PAID]
    rows.append([btn("◀️ Back", "m:home", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[btn("✖️ Cancel", "m:home", style="danger")]])

def paid_kb(pid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        btn("✅ I've paid", f"paid:{pid}", style="success"),
        btn("✖️ Cancel", "m:home", style="danger")]])

def review_kb(pid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        btn("✅ Approve", f"ap:{pid}", style="success"),
        btn("❌ Reject", f"rj:{pid}", style="danger")]])

def code_keypad(entered: str):
    d = lambda x: btn(x, f"c:{x}", style="primary")
    rows = [[d("1"), d("2"), d("3")], [d("4"), d("5"), d("6")], [d("7"), d("8"), d("9")]]
    tail = [btn("⌫", "c:del", style="danger"), d("0")]
    if len(entered) >= 5: tail.append(btn("✅", "c:ok", style="success"))
    rows.append(tail)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🧾 Review queue", "a:pending", style="primary")],
        [btn("📈 Stats", "a:stats", style="primary")],
        [btn("◀️ Back", "m:home", style="primary")]])
