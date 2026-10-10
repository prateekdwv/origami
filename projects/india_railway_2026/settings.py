"""Fixed replay window and non-secret project settings."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DATA = ROOT / "data"
MEDIA = REPO / "media" / "india_railway_2026"
IST = ZoneInfo("Asia/Kolkata")
DAY = "2026-10-10"
START = datetime(2026, 10, 10, tzinfo=IST)
END = START + timedelta(days=1)
COMPLETION = END + timedelta(minutes=30)
WIDTH, HEIGHT, FPS = 1080, 1920, 30
INTRO, REPLAY, OUTRO = 3, 54, 3
CATEGORIES = {
    "vande": ("Vande Bharat", "#B77909"),
    "rajdhani": ("Rajdhani", "#C34F46"),
    "shatabdi": ("Shatabdi family", "#7856AD"),
    "regional": ("Regional / Intercity", "#207EAC"),
    "local": ("Suburban / Local", "#218268"),
    "express": ("Other passenger express", "#485CB0"),
}


def timestamp(value):
    """Only dated, timezone-aware observations; never infer a date from HH:MM."""
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(IST) if result.tzinfo else None
    except ValueError:
        return None


def classify(name, kind=""):
    text = (name + " " + kind).upper()
    if any(word in text for word in ("FREIGHT", "CARGO", "GOODS", "PARCEL")):
        return None
    for category, words in (
        ("vande", ("VANDE",)), ("rajdhani", ("RAJDHANI",)),
        ("shatabdi", ("SHATABDI", "JAN SHATABDI")),
        ("local", ("LOCAL", "SUBURBAN", "MMTS")),
        ("regional", ("INTERCITY", "INTER CITY", "PASSENGER", "MEMU", "DEMU")),
        ("express", ("EXPRESS", " EXP", "SUPERFAST", "DURONTO", "TEJAS", "GARIB RATH")),
    ):
        if any(word in text for word in words):
            return category
    return None
