import pathlib

import pytest

from b05t1_parser import B05T1_COUNTS, parse_brain_updates, parse_b05t1_payload


def full_payload(h=1720000000):
    groups = {
        "d": [2, "0.12345678", 1, "0.1", "0.2", "0.3", "0.4", "0.5", "0.6"],
        "m": [2, "0.2", "-0.1", "0.01", "0.5", 1, 0, "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "20.1", "19.2", "0.9"],
        "v": [1, "0.75", 3, "0.9", 1, 1] + [f"0.{index}" for index in range(1, 10)] + [f"1.{index}" for index in range(1, 10)] + [f"2.{index}" for index in range(1, 10)],
        "p": [2, 3, 1, 2, 2, 4, "0.2", 1, 1, 5, 2, 1, 3, "0.9", 1, 4, 2],
    }
    encoded = " ".join(f"{name}=[{','.join(map(str, values))}]" for name, values in groups.items())
    return f"schema=B05T1 h={h} {encoded} sig=B05D2:ABCDEF0123456789 end=1"


def test_accepts_exact_schema_counts_and_order():
    parsed = parse_b05t1_payload(full_payload())
    assert parsed["h"] == 1720000000
    assert {name: len(parsed[name]) for name in B05T1_COUNTS} == B05T1_COUNTS


@pytest.mark.parametrize("group", ["d", "m", "v", "p"])
def test_rejects_missing_group(group):
    payload = full_payload()
    start = payload.index(f" {group}=[")
    end = payload.index("]", start) + 1
    with pytest.raises(ValueError):
        parse_b05t1_payload(payload[:start] + payload[end:])


@pytest.mark.parametrize("tail", [" sig=B05D2:ABCDEF0123456789", " end=1"])
def test_rejects_missing_required_tail(tail):
    with pytest.raises(ValueError):
        parse_b05t1_payload(full_payload().replace(tail, ""))


@pytest.mark.parametrize("mutation", [
    lambda value: value.replace("d=[", "d=", 1),
    lambda value: value.replace("] m=", " m=", 1),
    lambda value: value[:-1],
    lambda value: value + " junk",
    lambda value: value.replace(" d=[", " m=[", 1),
])
def test_rejects_malformed_truncated_or_reordered_payload(mutation):
    with pytest.raises(ValueError):
        parse_b05t1_payload(mutation(full_payload()))


def test_extracts_journal_payload_and_rejects_duplicate_h():
    line = "2026.08.21 12:00:00.000 AdaptiveSurvivalEA [BRAIN_UPDATE] " + full_payload()
    assert parse_brain_updates([line])[0]["h"] == 1720000000
    with pytest.raises(ValueError, match="duplicate h"):
        parse_brain_updates([line, line])


def test_rejects_log_without_brain_updates():
    with pytest.raises(ValueError, match="no BRAIN_UPDATE lines"):
        parse_brain_updates(["tester started"])


def test_representative_payload_fits_mt5_line():
    assert len(full_payload()) < 1024
