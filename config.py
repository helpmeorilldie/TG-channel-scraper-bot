import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.environ["BOT_TOKEN"]
TG_API_ID   = int(os.environ["TG_API_ID"])
TG_API_HASH = os.environ["TG_API_HASH"]
ADMIN_IDS   = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x}

DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

UPI_ID = os.environ.get("UPI_ID", "AhmadAmmar@fam"
UPI_NAME = "Venice Scraper"
TZ       = ZoneInfo("Asia/Kolkata")
DEVICE   = "VeniceScraper"

PLANS = {
    "free":         {"price": 0,  "daily": 200,  "delay": 10 / 6},
    "premium":      {"price": 39, "daily": 800,  "delay": 0.5},
    "premium_plus": {"price": 69, "daily": 1800, "delay": 0.4},
    "premium_max":  {"price": 99, "daily": None, "delay": 0.12},
}
LABEL = {"free": "Free", "premium": "Premium",
         "premium_plus": "Premium Plus", "premium_max": "Premium Max"}
PAID = ("premium", "premium_plus", "premium_max")
DAYS = 30
