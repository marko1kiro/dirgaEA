import re

B05T1_COUNTS = {"d": 9, "m": 18, "v": 33, "p": 17}
_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
_PATTERN = re.compile(
    rf"^schema=B05T1 h=(\d+) d=\[([^\[\]]+)\] m=\[([^\[\]]+)\] "
    rf"v=\[([^\[\]]+)\] p=\[([^\[\]]+)\] sig=(B05D2:[0-9A-F]+) end=1$"
)


def parse_b05t1_payload(payload):
    match = _PATTERN.fullmatch(payload)
    if not match:
        raise ValueError("invalid B05T1 schema")
    parsed = {"h": int(match.group(1)), "sig": match.group(6)}
    for index, (name, count) in enumerate(B05T1_COUNTS.items(), 2):
        values = match.group(index).split(",")
        if len(values) != count or any(not re.fullmatch(_NUMBER, value) for value in values):
            raise ValueError(f"invalid {name} fields")
        parsed[name] = values
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
    return parsed
