import re

CODE39_PATTERNS = {
    "0": "nnnwwnwnn",
    "1": "wnnwnnnnw",
    "2": "nnwwnnnnw",
    "3": "wnwwnnnnn",
    "4": "nnnwwnnnw",
    "5": "wnnwwnnnn",
    "6": "nnwwwnnnn",
    "7": "nnnwnnwnw",
    "8": "wnnwnnwnn",
    "9": "nnwwnnwnn",
    "A": "wnnnnwnnw",
    "B": "nnwnnwnnw",
    "C": "wnwnnwnnn",
    "D": "nnnnwwnnw",
    "E": "wnnnwwnnn",
    "F": "nnwnwwnnn",
    "G": "nnnnnwwnw",
    "H": "wnnnnwwnn",
    "I": "nnwnnwwnn",
    "J": "nnnnwwwnn",
    "K": "wnnnnnnww",
    "L": "nnwnnnnww",
    "M": "wnwnnnnwn",
    "N": "nnnnwnnww",
    "O": "wnnnwnnwn",
    "P": "nnwnwnnwn",
    "Q": "nnnnnnwww",
    "R": "wnnnnnwwn",
    "S": "nnwnnnwwn",
    "T": "nnnnwnwwn",
    "U": "wwnnnnnnw",
    "V": "nwwnnnnnw",
    "W": "wwwnnnnnn",
    "X": "nwnnwnnnw",
    "Y": "wwnnwnnnn",
    "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw",
    ".": "wwnnnnwnn",
    " ": "nwwnnnwnn",
    "$": "nwnwnwnnn",
    "/": "nwnwnnnwn",
    "+": "nwnnnwnwn",
    "%": "nnnwnwnwn",
    "*": "nwnnwnwnn",
}

CODE39_ALLOWED = re.compile(r"[^A-Z0-9.\- $/+%]")


def normalize_code39(value: object) -> str:
    code = str(value or "").upper().strip()
    code = CODE39_ALLOWED.sub("-", code)
    code = re.sub(r"-{2,}", "-", code).strip("-")
    return code or "UNSET"


def code39_segments(value: object) -> list[dict]:
    encoded = f"*{normalize_code39(value)}*"
    segments = []
    for char_index, char in enumerate(encoded):
        pattern = CODE39_PATTERNS[char]
        for i, width in enumerate(pattern):
            segments.append(
                {
                    "bar": i % 2 == 0,
                    "wide": width == "w",
                }
            )
        if char_index < len(encoded) - 1:
            segments.append({"bar": False, "wide": False})
    return segments


def label_payload(kind: str, title: str, code: object, subtitle: str = "", meta: str = "") -> dict:
    normalized = normalize_code39(code)
    return {
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "meta": meta,
        "code": normalized,
        "segments": code39_segments(normalized),
    }


def repeated_labels(labels: list[dict], copies: int) -> list[dict]:
    copies = max(1, min(int(copies or 1), 100))
    repeated = []
    for label in labels:
        repeated.extend(label for _ in range(copies))
    return repeated
