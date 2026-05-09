#!/usr/bin/env python3
"""
SSQ Database layer - SQLite (thin wrapper around base_db)

旧版API保持兼容，内部委托给 base_db.SSQDB。
"""
from base_db import SSQDB, get_conn as _get_conn_base

_db = SSQDB()

# ===== 兼容旧API =====
get_conn = _get_conn_base
DB_PATH = _db.draw_table  # 仅用于 __name__ == '__main__' 检查

def init_db():
    _db.init_tables()

def get_draw_count():
    return _db.get_draw_count()

def get_latest_draw():
    return _db.get_latest_draw()

def get_all_draws():
    return _db.get_all_draws()

def get_recent_draws(n=50):
    return _db.get_recent_draws(n)

def insert_draw(draw):
    return _db.insert_draw(draw)

def insert_draws_batch(draws):
    return _db.insert_draws_batch(draws)

def save_prediction(period, algorithm, numbers):
    return _db.save_prediction(period, algorithm, numbers)

def save_prediction_result(period, algorithm, red_hit, blue_hit, prize_level=None):
    return _db.save_prediction_result(period, algorithm, red_hit, blue_hit, prize_level)

def get_predictions_with_results(limit=20):
    return _db.get_predictions_with_results(limit)
