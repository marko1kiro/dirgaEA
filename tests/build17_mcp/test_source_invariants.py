"""BUILD 17 MCP observability source invariants — EA status reporter + calendar writer.

Follows tests/build16/test_source_invariants.py convention: parse the
.mq5/.mqh text and assert exact code patterns. Observability ONLY;
no trading-logic changes.
"""

import os
import re

import pytest

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ontick_region(src):
    start = src.find("void OnTick()")
    assert start != -1, "OnTick() not found"
    end = src.find("void OnTimer()", start)
    assert end != -1, "OnTimer() not found"
    return src[start:end]


def ontimer_region(src):
    start = src.find("void OnTimer()")
    assert start != -1, "OnTimer() not found"
    end = src.find("void OnTradeTransaction(", start)
    assert end != -1, "OnTradeTransaction() not found"
    return src[start:end]


# --- 1: includes ---

def test_mcp_includes():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "#include <EA_StatusReporter.mqh>" in src
    assert "#include <EA_CalendarWriter.mqh>" in src


# --- 2: ReportEAStatus in OnTick with real state var + build sha ---

def test_mcp_report_status_in_ontick():
    src = read_source("AdaptiveSurvivalEA.mq5")
    region = ontick_region(src)
    assert 'ReportEAStatus("AdaptiveSurvivalEA",' in region
    m = re.search(r'ReportEAStatus\(\s*"AdaptiveSurvivalEA"\s*,(.*?)\)\s*;', region, re.DOTALL)
    assert m, "ReportEAStatus call not found in OnTick()"
    args = m.group(1)
    assert args.count(",") >= 4, "ReportEAStatus must pass magic, state, blocked, last_error, build"
    assert '"dd81814"' in args, "build SHA dd81814 must be passed"
    assert '"RUNNING"' not in args, "state must be a real variable, not a hardcoded RUNNING literal"


# --- 3: PollEACommand in OnTick ---

def test_mcp_poll_command_in_ontick():
    src = read_source("AdaptiveSurvivalEA.mq5")
    region = ontick_region(src)
    assert 'PollEACommand("AdaptiveSurvivalEA")' in region


# --- 4: four command handlers ---

@pytest.mark.parametrize("cmd", ["PAUSE", "RESUME", "FLATTEN_ALL", "RELOAD_INPUTS"])
def test_mcp_command_handlers(cmd):
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert '"%s"' % cmd in src, "handler for %s missing" % cmd


# --- 5: persistent pause flag blocks entries, positions still managed ---

def test_mcp_pause_flag_blocks_entries():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"bool\s+g_ea_paused\s*=", src), "persistent global bool g_ea_paused missing"
    region = ontick_region(src)
    manage_idx = region.find("ManageOpenPositions();")
    assert manage_idx != -1, "ManageOpenPositions() call missing in OnTick()"
    gate = re.search(r"if\s*\(\s*g_ea_paused\s*\)", region)
    assert gate, "pause flag must gate the entry path via an if check"
    gate_idx = gate.start()
    assert manage_idx < gate_idx, \
        "ManageOpenPositions() must run unconditionally BEFORE the pause check"
    for marker in ("PrepareMarketOrder", "ExecuteIntent", "AcquireOrderLock"):
        idx = region.find(marker)
        assert idx != -1, "%s missing in OnTick()" % marker
        assert gate_idx < idx, "pause gate must sit BEFORE %s" % marker


# --- 6: calendar write in OnTimer ---

def test_mcp_calendar_write_in_ontimer():
    src = read_source("AdaptiveSurvivalEA.mq5")
    region = ontimer_region(src)
    assert re.search(r"WriteCalendarFile\s*\(\s*7\s*,\s*2\s*\)", region), \
        "OnTimer() must call WriteCalendarFile(7, 2)"


# --- 7: guard — risk/input defaults unchanged, no new inputs ---

def test_mcp_risk_percent_default_unchanged():
    src = read_source("Config.mqh")
    assert re.search(r"input\s+double\s+RiskPercent\s*=\s*0\.50", src), \
        "RiskPercent input missing or default changed"


def test_mcp_no_new_inputs():
    ea = read_source("AdaptiveSurvivalEA.mq5")
    cfg = read_source("Config.mqh")
    ea_inputs = len(re.findall(r"(?m)^\s*input\s+", ea))
    cfg_inputs = len(re.findall(r"(?m)^\s*input\s+", cfg))
    assert ea_inputs == 0, "no input declarations allowed in AdaptiveSurvivalEA.mq5, found %d" % ea_inputs
    assert cfg_inputs == 39, "Config.mqh input count changed (baseline 39, got %d)" % cfg_inputs
