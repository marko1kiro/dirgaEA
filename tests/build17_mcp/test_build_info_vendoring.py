"""BUILD 17 MCP reviewer fixes — auto build SHA + vendored .mqh includes.

Follows the source-invariant convention: parse repo text and assert exact
patterns. Goal is build reproducibility only — no trading-logic changes.
"""

import os
import re

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


# --- 1a: BuildInfo include + BUILD_SHA as build argument, no hardcoded 7-hex ---

def test_mq5_includes_buildinfo():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "#include <BuildInfo.mqh>" in src


def test_mq5_report_status_uses_build_sha():
    src = read_source("AdaptiveSurvivalEA.mq5")
    region = ontick_region(src)
    m = re.search(r'ReportEAStatus\(\s*"AdaptiveSurvivalEA"\s*,(.*?)\)\s*;', region, re.DOTALL)
    assert m, "ReportEAStatus call not found in OnTick()"
    args = m.group(1)
    assert "BUILD_SHA" in args, "ReportEAStatus must pass BUILD_SHA as the build argument"
    assert '"dd81814"' not in args, "hardcoded build SHA dd81814 must be removed"


def test_mq5_no_hardcoded_build_sha_literal():
    src = read_source("AdaptiveSurvivalEA.mq5")
    region = ontick_region(src)
    m = re.search(r'ReportEAStatus\(\s*"AdaptiveSurvivalEA"\s*,(.*?)\)\s*;', region, re.DOTALL)
    assert m, "ReportEAStatus call not found in OnTick()"
    args = m.group(1)
    hex_literal = re.search(r'"[0-9a-f]{7}"', args)
    assert hex_literal is None, \
        "no 7-char hex literal may be used as the build argument, found %s" % hex_literal.group(0)


# --- 1b: BuildInfo.mqh generated include exists ---

def test_buildinfo_mqh_has_build_sha_macro():
    src = read_source(os.path.join("mql5", "include", "BuildInfo.mqh"))
    assert re.search(r"#define\s+BUILD_SHA\s+\"[0-9a-f]{7}\"", src), \
        "BuildInfo.mqh must define BUILD_SHA as a 7-char hex string literal"


# --- 1c: vendored .mqh includes exist in repo ---

def test_vendored_status_reporter_exists():
    path = os.path.join(SOURCE_DIR, "mql5", "include", "EA_StatusReporter.mqh")
    assert os.path.isfile(path), "mql5/include/EA_StatusReporter.mqh must exist"
    assert os.path.getsize(path) > 0


def test_vendored_calendar_writer_exists():
    path = os.path.join(SOURCE_DIR, "mql5", "include", "EA_CalendarWriter.mqh")
    assert os.path.isfile(path), "mql5/include/EA_CalendarWriter.mqh must exist"
    assert os.path.getsize(path) > 0


# --- 1d: .gitignore excludes the generated BuildInfo.mqh ---

def test_gitignore_excludes_buildinfo():
    src = read_source(".gitignore")
    assert "mql5/include/BuildInfo.mqh" in src, \
        ".gitignore must ignore the generated mql5/include/BuildInfo.mqh"
