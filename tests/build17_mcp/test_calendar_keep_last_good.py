"""Keep-last-good guard for EA_CalendarWriter — empty fetch must not clobber good file."""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_writer():
    path = os.path.join(SOURCE_DIR, "mql5", "include", "EA_CalendarWriter.mqh")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_empty_fetch_skips_file_write():
    src = read_writer()
    m = re.search(r"event_count\s*==\s*0", src)
    assert m, "missing empty-fetch guard (event_count == 0)"
    tail = src[m.start():]
    assert re.search(r"\breturn\b", tail), "empty-fetch branch must return to skip FileOpen FILE_WRITE"
    ret_idx = re.search(r"\breturn\b", tail).start()
    write_idx = tail.find("FILE_WRITE")
    assert write_idx == -1 or ret_idx < write_idx, \
        "empty-fetch return must sit BEFORE the FileOpen FILE_WRITE path"


def test_single_keep_last_good_warning():
    src = read_writer()
    assert src.count("CALENDAR_EMPTY_KEEP_LAST_GOOD") == 1, \
        "expected exactly ONE CALENDAR_EMPTY_KEEP_LAST_GOOD warning log call"


def test_old_file_good_checks_existence_and_events():
    src = read_writer()
    assert ("FileIsExist" in src or "FileFindFirst" in src), \
        "must check existing Calendar\\events.json file existence"
    assert ("FileSize" in src or "FileReadString" in src or "StringFind" in src), \
        "must check old file has events (size/content check)"
