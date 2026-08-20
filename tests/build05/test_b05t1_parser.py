import pathlib
import re

import pytest

from b05t1_parser import B05T1_COUNTS, B05T1_Q4_POSITIONS, parse_brain_updates, parse_b05t1_payload, q4_decode, q4_encode

BASE = pathlib.Path(__file__).resolve().parents[2]
DIAG = BASE / "DiagnosticCollector.mqh"


def full_payload(h=1720000000):
    groups = {
        "d": [2, 1235, 1, 1000, 2000, 3000, 4000, 5000, 6000],
        "m": [2, 2000, -1000, 100, 5000, 1, 0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 201000, 192000, 9000],
        "v": [1, 7500, 3, 9000, 1, 1] + list(range(1000, 28000, 1000)),
        "p": [2, 3, 1, 2, 2, 4, 2000, 1, 1, 5, 2, 1, 3, 9000, 1, 4, 2],
    }
    encoded = " ".join(f"{name}=[{','.join(map(str, values))}]" for name, values in groups.items())
    return f"schema=B05T1 h={h} {encoded} sig=B05D2:ABCDEF0123456789 end=1"


@pytest.mark.parametrize(("value", "encoded"), [
    (0, 0), (0.3624, 3624), (-0.052, -520), (1.2345, 12345),
    (0.00005, 1), (-0.00005, -1), (1.23445, 12345), (-1.23445, -12345),
])
def test_q4_known_vectors_half_away_from_zero(value, encoded):
    assert q4_encode(value) == encoded


@pytest.mark.parametrize("value", [0, 0.3624, -0.052, 1.23454, -1.23454, 200.12344])
def test_q4_semantic_round_trip(value):
    assert abs(q4_decode(q4_encode(value)) - value) <= 0.00005


def test_accepts_exact_typed_schema_counts_and_order():
    parsed = parse_b05t1_payload(full_payload())
    assert parsed["h"] == 1720000000
    assert {name: len(parsed[name]) for name in B05T1_COUNTS} == B05T1_COUNTS
    assert parsed["d"][:3] == [2, 0.1235, 1]
    assert parsed["p"][6] == 0.2
    assert parsed["p"][13] == 0.9
    for name, values in parsed.items():
        if name not in B05T1_COUNTS:
            continue
        for position, value in enumerate(values):
            assert isinstance(value, float) if position in B05T1_Q4_POSITIONS[name] else isinstance(value, int)


@pytest.mark.parametrize("token", ["123.4", "1e4", "-2E3"])
def test_rejects_decimal_or_scientific_raw_q4_tokens(token):
    with pytest.raises(ValueError):
        parse_b05t1_payload(full_payload().replace("1235", token, 1))


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


def test_source_uses_q4_only_for_runtime_and_keeps_b05d2_at_15_digits():
    source = DIAG.read_text(encoding="utf-8")
    runtime = source[source.index("string Build05RuntimeDecimal"):source.index("// B05T1 positions:")]
    assert "MathRound(value*10000.0)" in runtime
    assert "DoubleToString(value, 4)" not in runtime
    assert "DoubleToString(value,15)" in source
    assert '"schema=B05T1 h=%I64d d=[%s] m=[%s] v=[%s] p=[%s] sig=%s end=1"' in source


def test_representative_payload_has_integer_tokens_and_fits_mt5_line():
    groups = re.findall(r"[dmvp]=\[([^]]+)\]", full_payload())
    assert all(re.fullmatch(r"-?\d+", token) for group in groups for token in group.split(","))
    assert len(full_payload()) < 454
