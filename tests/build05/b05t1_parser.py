import re
from decimal import Decimal, ROUND_HALF_UP

B05T1_COUNTS = {"d": 9, "m": 18, "v": 33, "p": 17}
B05T1_Q4_POSITIONS = {
    "d": frozenset(range(1, 9)) - {2},
    "m": frozenset(range(1, 18)) - {5, 6},
    "v": frozenset(range(1, 33)) - {2, 4, 5},
    "p": frozenset({6, 13}),
}
_INTEGER = re.compile(r"-?\d+")
_PATTERN = re.compile(
    r"^schema=B05T1 h=(\d+) d=\[([^\[\]]+)\] m=\[([^\[\]]+)\] "
    r"v=\[([^\[\]]+)\] p=\[([^\[\]]+)\] sig=(B05D2:[0-9A-F]+) end=1$"
)


def q4_encode(value):
    return int((Decimal(str(value)) * 10000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def q4_decode(value):
    return int(value) / 10000.0


def parse_b05t1_payload(payload):
    match = _PATTERN.fullmatch(payload)
    if not match:
        raise ValueError("invalid B05T1 schema")
    parsed = {"h": int(match.group(1)), "sig": match.group(6)}
    for index, (name, count) in enumerate(B05T1_COUNTS.items(), 2):
        values = match.group(index).split(",")
        if len(values) != count or any(not _INTEGER.fullmatch(value) for value in values):
            raise ValueError(f"invalid {name} fields")
        parsed[name] = [q4_decode(value) if position in B05T1_Q4_POSITIONS[name] else int(value)
                        for position, value in enumerate(values)]
    return parsed


def parse_brain_updates(lines):
    parsed = []
    seen = set()
    for line in lines:
        marker = "[BRAIN_UPDATE] "
        if marker not in line:
            continue
        item = parse_b05t1_payload(line.split(marker, 1)[1].strip())
        if item["h"] in seen:
            raise ValueError(f"duplicate h={item['h']}")
        seen.add(item["h"])
        parsed.append(item)
    if not parsed:
        raise ValueError("no BRAIN_UPDATE lines")
    return parsed
