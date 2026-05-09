#!/usr/bin/env python3
"""
大乐透数据库扩展 — 兼容旧API（thin wrapper around base_db）
"""
from base_db import DLTDB, get_conn as _get_conn_base

_db = DLTDB()

# ===== 兼容旧API =====
get_conn = _get_conn_base
DB_PATH = _db.draw_table

def init_dlt_tables():
    _db.init_tables()

def insert_dlt_draw(draw):
    return _db.insert_draw(draw)

def insert_dlt_draws_batch(draws):
    return _db.insert_draws_batch(draws)

def get_dlt_draw_count():
    return _db.get_draw_count()

def get_latest_dlt_draw():
    return _db.get_latest_draw()

def get_all_dlt_draws():
    return _db.get_all_draws()

def save_dlt_prediction(period, algorithm, front_numbers, back_numbers):
    numbers = list(front_numbers) + list(back_numbers)
    return _db.save_prediction(period, algorithm, numbers)

def save_dlt_prediction_result(period, algorithm, front_hit, back_hit, prize_level=None):
    return _db.save_prediction_result(period, algorithm, front_hit, back_hit, prize_level)

def get_dlt_predictions_with_results(limit=20):
    return _db.get_predictions_with_results(limit)
