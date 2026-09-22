"""Symbol-spec sync retry on EA init — bounded wait instead of instant INIT_FAILED.

Follows tests/build16 + tests/build17_mcp convention: parse the .mq5/.mqh
text and assert exact code patterns. Init hardening ONLY; no trading-logic
changes.
"""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_env_region(src):
    start = src.find("SYMBOL_SYNC_TIMEOUT_SEC")
    assert start != -1, "SYMBOL_SYNC constants not found"
    end = src.find("void LogBrokerEnvironment(", start)
    assert end != -1, "LogBrokerEnvironment() not found"
    return src[start:end]


# --- (a) named upper-bound constants on the symbol-spec validation path ---

def test_symbol_sync_timeout_constant():
    src = read_source("BrokerEnvironment.mqh")
    assert re.search(r"SYMBOL_SYNC_TIMEOUT_SEC\s*=\s*60\b", src), \
        "named constant SYMBOL_SYNC_TIMEOUT_SEC = 60 missing"


def test_symbol_sync_poll_constant():
    src = read_source("BrokerEnvironment.mqh")
    assert re.search(r"SYMBOL_SYNC_POLL_MS\s*=\s*1000\b", src), \
        "named constant SYMBOL_SYNC_POLL_MS = 1000 missing"


def test_retry_loop_uses_named_bounds():
    src = read_source("BrokerEnvironment.mqh")
    region = load_env_region(src)
    assert "SYMBOL_SYNC_TIMEOUT_SEC" in region, \
        "retry bound must reference SYMBOL_SYNC_TIMEOUT_SEC"
    assert "SYMBOL_SYNC_POLL_MS" in region, \
        "retry poll must reference SYMBOL_SYNC_POLL_MS"
    assert re.search(r"Sleep\s*\(\s*SYMBOL_SYNC_POLL_MS\s*\)", region), \
        "retry loop must Sleep(SYMBOL_SYNC_POLL_MS)"


def test_retry_waits_with_periodic_warning():
    src = read_source("BrokerEnvironment.mqh")
    region = load_env_region(src)
    assert "LogWarning" in region, \
        "retry loop must log periodic LogWarning while waiting"


def test_fast_path_checks_before_sleep():
    src = read_source("BrokerEnvironment.mqh")
    region = load_env_region(src)
    sleep_idx = region.find("Sleep")
    assert sleep_idx != -1, "retry Sleep not found"
    first_check = region.find("IsSymbolSpecValid(environment)")
    if first_check == -1:
        first_check = region.find("ReadSymbolSpec(environment")
    assert first_check != -1, "symbol-spec validity check not found"
    assert first_check < sleep_idx, \
        "first validity check must precede any Sleep (fast path, zero added delay)"


# --- (b) no unbounded retry ---

def test_no_unbounded_while_in_broker_environment():
    src = read_source("BrokerEnvironment.mqh")
    assert not re.search(r"while\s*\(\s*true\s*\)", src), \
        "unbounded while(true) forbidden in BrokerEnvironment.mqh"


def test_no_unbounded_while_added_to_ea():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert not re.search(r"while\s*\(\s*true\s*\)", src), \
        "unbounded while(true) forbidden in AdaptiveSurvivalEA.mq5"


# --- (c) fail-closed: timeout/invalid still returns false -> INIT_FAILED ---

def test_symbol_invalid_logged_exactly_once():
    src = read_source("BrokerEnvironment.mqh")
    assert src.count("Critical symbol specification is invalid") == 1, \
        "ENVIRONMENT_INVALID for symbol spec must fire exactly once (final failure only)"


def test_retry_exhausted_returns_false():
    src = read_source("BrokerEnvironment.mqh")
    region = load_env_region(src)
    invalid_idx = region.find("Critical symbol specification is invalid")
    assert invalid_idx != -1, "final ENVIRONMENT_INVALID log missing"
    tail = region[invalid_idx:]
    assert re.search(r"return\s+false\s*;", tail), \
        "retry-exhausted branch must return false"


def test_oninit_still_fails_closed():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"if\s*\(\s*!LoadBrokerEnvironment", src), \
        "OnInit must keep its single if(!LoadBrokerEnvironment(...)) gate"
    gate_idx = src.find("LoadBrokerEnvironment(broker_environment)")
    assert gate_idx != -1
    tail = src[gate_idx:gate_idx + 200]
    assert re.search(r"return\s+INIT_FAILED\s*;", tail), \
        "OnInit must still return INIT_FAILED when LoadBrokerEnvironment fails"
