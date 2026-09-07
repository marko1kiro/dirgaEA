import pytest
from tests.build14.reference_session_news import (
    evaluate_session_state, evaluate_news_state, SESSION_STATE, NEWS_STATE
)


def test_rollover_session_block():
    # 23:50 (server time) -> Rollover window (23:45 - 00:15)
    state = evaluate_session_state(hour=23, minute=50)
    assert state == SESSION_STATE.SESSION_ROLLOVER


def test_core_session():
    # 14:30 (server time) -> Core Session (08:00 - 21:00)
    state = evaluate_session_state(hour=14, minute=30)
    assert state == SESSION_STATE.SESSION_CORE


def test_news_lock_window():
    # News event at T=1700001800 (30 mins ahead). Current time T=1700000000 -> 30 mins before -> NEWS_LOCK
    news_events = [1700001800]
    news_state = evaluate_news_state(current_time=1700000000, high_impact_events=news_events)
    assert news_state == NEWS_STATE.NEWS_LOCK
