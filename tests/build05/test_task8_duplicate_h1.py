import pathlib
import re

BASE = pathlib.Path(r"C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA")
MQ5_PATH = BASE / "AdaptiveSurvivalEA.mq5"
MQH_PATH = BASE / "MarketBrain.mqh"

def _read(p):
    return p.read_text(encoding="utf-8", errors="ignore")

def find_fn_body(text, name):
    m = re.search(r'\b' + re.escape(name) + r'\s*\([^)]*\)\s*\{', text)
    if not m: return ""
    start = m.end()-1
    depth=0
    for i in range(start, len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0: return text[start:i+1]
    return ""

class TestDuplicateH1Guard:
    def test_duplicate_h1_guard_exists(self):
        source = _read(MQ5_PATH)
        assert "b05_last_accepted_h1" in source, "b05_last_accepted_h1 not found"

    def test_guard_skips_duplicate(self):
        source = _read(MQ5_PATH)
        assert "b05_last_accepted_h1" in source and ("time <=" in source or "time<=" in source), "Guard condition not found"

class TestFormingBarDiscipline:
    def test_no_bar0_access_in_canonical(self):
        source = _read(MQH_PATH)
        body = find_fn_body(source, "ProcessBuild05ClosedHistoryPrefix")
        assert "rates[0]" not in body, "rates[0] found — forming bar access"
        # Additional checks for indicator buffers
        assert "atr[0]" not in body or "atr[count" in body, "atr[0] found — forming bar access"
        assert "emaFast[0]" not in body, "emaFast[0] found — forming bar access"
