#!/usr/bin/env python3
"""
SSQ Database layer - SQLite
Stores all historical draws, statistics, and predictions
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ssq.db')

def get_conn():
    """Get a database connection"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS draws (
            period TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            red1 INTEGER NOT NULL,
            red2 INTEGER NOT NULL,
            red3 INTEGER NOT NULL,
            red4 INTEGER NOT NULL,
            red5 INTEGER NOT NULL,
            red6 INTEGER NOT NULL,
            blue INTEGER NOT NULL,
            pool_amount REAL DEFAULT 0,
            first_prize_count INTEGER DEFAULT 0,
            first_prize_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            red1 INTEGER NOT NULL,
            red2 INTEGER NOT NULL,
            red3 INTEGER NOT NULL,
            red4 INTEGER NOT NULL,
            red5 INTEGER NOT NULL,
            red6 INTEGER NOT NULL,
            blue INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, algorithm)
        );

        CREATE TABLE IF NOT EXISTS prediction_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            red_hit INTEGER DEFAULT 0,
            blue_hit INTEGER DEFAULT 0,
            prize_level TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, algorithm)
        );

        CREATE TABLE IF NOT EXISTS algorithm_weights (
            algorithm TEXT PRIMARY KEY,
            weight REAL DEFAULT 1.0,
            total_predictions INTEGER DEFAULT 0,
            recent_hits INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_draws_date ON draws(date);
        CREATE INDEX IF NOT EXISTS idx_draws_period ON draws(period);
        CREATE INDEX IF NOT EXISTS idx_predictions_period ON predictions(period);
    ''')

    # Initialize default weights for algorithms
    algorithms = ['association_break', 'density_drift', 'interval_pattern', 'embedding_anomaly']
    for algo in algorithms:
        cursor.execute('''
            INSERT OR IGNORE INTO algorithm_weights (algorithm, weight)
            VALUES (?, 1.0)
        ''', (algo,))

    conn.commit()
    conn.close()

def get_draw_count():
    """Get total number of draws in database"""
    conn = get_conn()
    count = conn.execute('SELECT COUNT(*) FROM draws').fetchone()[0]
    conn.close()
    return count

def get_latest_draw():
    """Get the most recent draw"""
    conn = get_conn()
    row = conn.execute('SELECT * FROM draws ORDER BY period DESC LIMIT 1').fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_all_draws():
    """Get all draws ordered by period"""
    conn = get_conn()
    rows = conn.execute('SELECT * FROM draws ORDER BY period ASC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_draws(n=50):
    """Get the most recent N draws"""
    conn = get_conn()
    rows = conn.execute('SELECT * FROM draws ORDER BY period DESC LIMIT ?', (n,)).fetchall()
    conn.close()
    return [dict(r) for r in rows][::-1]  # Return in chronological order

def get_draws_by_period_range(start_period, end_period):
    """Get draws within a period range"""
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM draws WHERE period >= ? AND period <= ? ORDER BY period ASC',
        (start_period, end_period)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_draw(draw):
    """Insert a single draw record"""
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO draws 
            (period, date, red1, red2, red3, red4, red5, red6, blue, pool_amount, first_prize_count, first_prize_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(draw['period']),
            draw['date'],
            int(draw['red1']), int(draw['red2']), int(draw['red3']),
            int(draw['red4']), int(draw['red5']), int(draw['red6']),
            int(draw['blue']),
            draw.get('pool_amount', 0),
            draw.get('first_prize_count', 0),
            draw.get('first_prize_amount', 0)
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Insert error: {e}")
        return False
    finally:
        conn.close()

def insert_draws_batch(draws):
    """Insert multiple draws in a batch"""
    conn = get_conn()
    try:
        data = [(
            str(d['period']), d['date'],
            int(d['red1']), int(d['red2']), int(d['red3']),
            int(d['red4']), int(d['red5']), int(d['red6']),
            int(d['blue']),
            d.get('pool_amount', 0),
            d.get('first_prize_count', 0),
            d.get('first_prize_amount', 0)
        ) for d in draws]
        conn.executemany('''
            INSERT OR REPLACE INTO draws 
            (period, date, red1, red2, red3, red4, red5, red6, blue, pool_amount, first_prize_count, first_prize_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()
        return len(data)
    except Exception as e:
        conn.rollback()
        logger.error(f"批量插入失败，已回滚: {e}")
        return 0
    finally:
        conn.close()

def save_prediction(period, algorithm, numbers):
    """Save a prediction"""
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO predictions 
            (period, algorithm, red1, red2, red3, red4, red5, red6, blue)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (period, algorithm, numbers[0], numbers[1], numbers[2], numbers[3], numbers[4], numbers[5], numbers[6]))
        conn.commit()
    except Exception as e:
        logger.error(f"Save prediction error: {e}")
    finally:
        conn.close()

def save_prediction_result(period, algorithm, red_hit, blue_hit, prize_level=None):
    """Save prediction result after draw"""
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO prediction_results 
            (period, algorithm, red_hit, blue_hit, prize_level)
            VALUES (?, ?, ?, ?, ?)
        ''', (period, algorithm, red_hit, blue_hit, prize_level))
        conn.commit()
    except Exception as e:
        print(f"Save result error: {e}")
    finally:
        conn.close()

def get_algorithm_weights():
    """Get current algorithm weights"""
    conn = get_conn()
    rows = conn.execute('SELECT * FROM algorithm_weights').fetchall()
    conn.close()
    return {r['algorithm']: r['weight'] for r in rows}

def update_algorithm_weight(algorithm, success):
    """Update algorithm weight based on prediction success"""
    conn = get_conn()
    try:
        if success:
            conn.execute('''
                UPDATE algorithm_weights 
                SET weight = MIN(weight + 0.1, 3.0),
                    recent_hits = recent_hits + 1,
                    total_predictions = total_predictions + 1,
                    last_updated = CURRENT_TIMESTAMP
                WHERE algorithm = ?
            ''', (algorithm,))
        else:
            conn.execute('''
                UPDATE algorithm_weights 
                SET weight = MAX(weight - 0.05, 0.3),
                    total_predictions = total_predictions + 1,
                    last_updated = CURRENT_TIMESTAMP
                WHERE algorithm = ?
            ''', (algorithm,))
        conn.commit()
    except Exception as e:
        print(f"Update weight error: {e}")
    finally:
        conn.close()

def get_predictions_with_results(limit=20):
    """Get recent predictions with their results"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT p.*, pr.red_hit, pr.blue_hit, pr.prize_level
        FROM predictions p
        LEFT JOIN prediction_results pr ON p.period = pr.period AND p.algorithm = pr.algorithm
        ORDER BY p.id DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == '__main__':
    init_db()
    print(f"Database initialized at: {DB_PATH}")
    print(f"Current draws: {get_draw_count()}")
