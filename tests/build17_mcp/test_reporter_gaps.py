"""Reporter gaps — last_error, news blocked_reasons, ERROR state.

Source-invariant tests for AdaptiveSurvivalEA.mq5 only. No trading-logic change.
RED-first: each test targets an unwired reporter gap.
"""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_ea():
    path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ontick_region(src):
    start = src.find("void OnTick()")
    assert start != -1, "OnTick() not found"
    end = src.find("void OnTimer()", start)
    assert end != -1, "OnTimer() not found"
    return src[start:end]


def report_call_args(region):
    m = re.search(r'ReportEAStatus\(\s*"AdaptiveSurvivalEA"\s*,(.*?)\)\s*;', region, re.DOTALL)
    assert m, "ReportEAStatus call not found in OnTick()"
    return m.group(1)


# --- Item 1: real last_error ---

def test_reporter_last_error_is_global_variable():
    src = read_ea()
    args = report_call_args(ontick_region(src))
    assert ',"",' not in args.replace(" ", ""), \
        "last_error arg must not be hardcoded empty literal"
    assert re.search(r",\s*g_\w*[Ee]rror\w*\s*,\s*BUILD_SHA", args), \
        "last_error slot (before BUILD_SHA) must reference a global error string"


def test_last_error_global_assigned_at_failure_sites():
    src = read_ea()
    assert re.search(r"string\s+g_last\w*[Ee]rror\w*\s*(\s*=\s*\"\"\s*)?;", src), \
        "global last-error string missing in EA main"
    assert re.search(r"string\s+g_last\w*[Ee]rror\w*\s*=\s*\"\"\s*;", src), \
        "last-error global must default to empty string (MQL5 NULL renders as (null))"
    assigns = re.findall(r"g_last\w*[Ee]rror\w*\s*=", src)
    assert len(assigns) >= 2, \
        "global error string must be assigned at >=2 EA-main failure sites, found %d" % len(assigns)


# --- Item 2: news stash in blocked_reasons ---

def test_news_stash_global_written_at_entry_site():
    src = read_ea()
    assert re.search(r"ENUM_NEWS_STATE\s+g_last\w*[Nn]ews\w*\s*(=\s*NEWS_UNKNOWN\s*)?;", src), \
        "news-stash global (ENUM_NEWS_STATE) missing in EA main"
    assert re.search(r"ENUM_NEWS_STATE\s+g_last\w*[Nn]ews\w*\s*=\s*NEWS_UNKNOWN\s*;", src), \
        "news stash must default to NEWS_UNKNOWN (fail-closed)"
    eval_idx = src.find("EvaluateNews(")
    assert eval_idx != -1, "EvaluateNews call site missing"
    m = re.search(r"g_last\w*[Nn]ews\w*\s*=", src[eval_idx:eval_idx + 3000])
    assert m, "news stash must be written near the entry-evaluation site (after EvaluateNews)"


def test_blocked_reasons_builder_reads_news_stash():
    src = read_ea()
    start = src.find("string EAComputeBlockedReasons()")
    assert start != -1, "EAComputeBlockedReasons() not found"
    body = src[start:start + 3000]
    assert re.search(r"g_last\w*[Nn]ews\w*", body), \
        "blocked-reasons builder must read the news stash global"
    assert "EvaluateNews(" not in body, \
        "reporter must NOT re-call EvaluateNews (cache/gating choke point)"
    assert "NEWS_UNKNOWN" in body or "NEWS_BLACKOUT" in body or "NEWS_" in body, \
        "builder must emit a NEWS_* reason from the stash"


# --- Item 3: ERROR state with entry + exit ---

def test_error_state_in_state_helper():
    src = read_ea()
    region = ontick_region(src)
    assert '"ERROR"' in region, "ERROR literal must appear as a state value in OnTick state computation"


def test_error_flag_has_entry_and_exit():
    src = read_ea()
    assert re.search(r"bool\s+g_ea\w*[Ee]rror\w*\s*=", src), \
        "latched error flag global missing in EA main"
    sets = re.findall(r"g_ea\w*[Ee]rror\w*\s*=\s*true", src)
    clears = re.findall(r"g_ea\w*[Ee]rror\w*\s*=\s*false", src)
    assert len(sets) >= 1, "error flag needs >=1 setter (entry condition)"
    assert len(clears) >= 1, "error flag needs >=1 clearer (exit condition)"
