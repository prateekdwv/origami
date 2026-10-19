"""Fixed replay window and non-secret project settings."""
from datetime import datetime, timedelta
from pathlib import Path
import re
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

# The legacy observation/demo palette above stays separate from the timetable
# taxonomy. Named families take priority, then source service type, then names.
SCHEDULE_CATEGORIES = {
    "express": ("Mail / Express", "#0072B2"),
    "superfast": ("Superfast", "#A83D83"),
    "regional": ("Passenger / Regional", "#6842A6"),
    "local": ("Suburban / Local", "#008B8B"),
    "vande": ("Vande Bharat", "#E87818"),
    "rajdhani": ("Rajdhani", "#BF3043"),
    "shatabdi": ("Shatabdi / Jan Shatabdi", "#27466B"),
    "unknown": ("Unknown service type", "#6B7280"),
}
SCHEDULE_PALETTE_BASIS = (
    "Representative livery-inspired colours for Vande Bharat, Rajdhani, Shatabdi "
    "and conventional Mail/Express; other colours distinguish service groups. "
    "Not observed rake colours or an official category-wide paint standard."
)


def classify_scheduled(name, kind=""):
    """Display hierarchy, not a claim that train families and speed classes coincide.

    Never infer Superfast from journey speed, train number, or a named brand.
    Special/holiday operation is independent of the underlying service class.
    """
    name = re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()
    kind = re.sub(r"[^A-Z0-9]+", " ", kind.upper()).strip()
    combined = name+" "+kind
    def has(pattern):
        return re.search(r"\b(?:"+pattern+r")\b", combined) is not None
    if has("FREIGHT|CARGO|GOODS|PARCEL"):
        return None
    if kind == "VANDE BHARAT METRO" or has(r"NAMO BHARAT RAPID RAIL"):
        return "regional"
    for category, aliases, pattern in (
        ("vande", {"VANDE BHARAT", "VANDE BHARAT SLEEPER"}, r"VANDE\s*BHARAT"),
        ("rajdhani", {"RAJ", "RAJDHANI"}, "RAJDHANI"),
        ("shatabdi", {"SHTB", "JSHTB", "SHATABDI", "JAN SHATABDI"}, r"(?:JAN\s*)?SHATABDI"),
    ):
        if kind in aliases or has(pattern):
            return category
    for category, aliases in (
        ("local", {"SUBURBAN", "LOCAL", "EMU", "MMTS", "KLKT", "HYD", "DEL"}),
        ("regional", {"PASS", "PASSENGER", "MEMU", "DEMU", "DMU"}),
        ("superfast", {"SF", "SUPERFAST", "SUPER FAST"}),
        ("express", {"MAIL EXPRESS", "MAIL", "EXPRESS", "EXP"}),
    ):
        if kind in aliases:
            return category
    for category, pattern in (
        ("local", "SUBURBAN|LOCAL|MMTS|EMU"),
        ("regional", "PASSENGER|PASS|PGR|PSGR|MEMU|DEMU|DMU"),
        ("superfast", r"SUPER\s*FAST|SF"),
        ("express", r"MAIL|EXPRESS|EXP|DURONTO|TEJAS|GARIB\s*RATH|HUMSAFAR|AMRIT\s*BHARAT"),
    ):
        if has(pattern):
            return category
    return "unknown"


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
