"""Fixed replay window and non-secret project settings."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
MEDIA = REPO / "media" / "india_railway_2026"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
INTRO, REPLAY, OUTRO = 3, 54, 3
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
CATEGORIES = SCHEDULE_CATEGORIES
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


BACKGROUND, LAND, OUTLINE = "#F7F5EF", "#E6ECE3", "#829787"
INK, MUTED = "#243A3D", "#60716E"
CITIES = [
    ("Srinagar", 74.80, 34.08, 14, -28), ("Delhi", 77.21, 28.61, 14, -28),
    ("Jaipur", 75.79, 26.91, -96, 4), ("Ahmedabad", 72.58, 23.02, -152, -28),
    ("Mumbai", 72.88, 19.08, -106, 4), ("Pune", 73.86, 18.52, 14, 8),
    ("Bhopal", 77.41, 23.26, 12, -30), ("Lucknow", 80.95, 26.85, 12, -30),
    ("Patna", 85.14, 25.61, -42, -35), ("Kolkata", 88.36, 22.57, 14, 4),
    ("Guwahati", 91.74, 26.14, -35, -38), ("Agartala", 91.29, 23.83, 14, 10),
    ("Bhubaneswar", 85.82, 20.30, 14, 8), ("Nagpur", 79.09, 21.15, 12, -28),
    ("Hyderabad", 78.49, 17.39, 14, -28), ("Bengaluru", 77.59, 12.97, -135, -16),
    ("Chennai", 80.27, 13.08, 14, 4), ("Thiruvananthapuram", 76.95, 8.52, -165, 14),
]
MAP_SCALE = 1000 / 944
