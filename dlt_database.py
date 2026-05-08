#!/usr/bin/env python3
"""
大乐透数据库扩展
追加到现有 ssq.db 中，新增大乐透专用表
"""
import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ssq.db')

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_dlt_tables():
    """初始化大乐透数据表"""
    conn = get_conn()
    cursor = conn.cursor()
    
    cursor.executescript('''
        -- 大乐透开奖数据
        -- 前区: 35选5 (front1-front5)
        -- 后区: 12选2 (back1, back2)
        CREATE TABLE IF NOT EXISTS dlt_draws (
            period TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            front1 INTEGER NOT NULL,
            front2 INTEGER NOT NULL,
            front3 INTEGER NOT NULL,
            front4 INTEGER NOT NULL,
            front5 INTEGER NOT NULL,
            back1 INTEGER NOT NULL,
            back2 INTEGER NOT NULL,
            pool_amount REAL DEFAULT 0,
            first_prize_count INTEGER DEFAULT 0,
            first_prize_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- 大乐透预测
        CREATE TABLE IF NOT EXISTS dlt_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            front1 INTEGER NOT NULL, front2 INTEGER NOT NULL,
            front3 INTEGER NOT NULL, front4 INTEGER NOT NULL,
            front5 INTEGER NOT NULL,
            back1 INTEGER NOT NULL, back2 INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, algorithm)
        );
        
        -- 大乐透预测结果
        CREATE TABLE IF NOT EXISTS dlt_prediction_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            front_hit INTEGER DEFAULT 0,
            back_hit INTEGER DEFAULT 0,
            prize_level TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, algorithm)
        );
        
        CREATE INDEX IF NOT EXISTS idx_dlt_draws_date ON dlt_draws(date);
        CREATE INDEX IF NOT EXISTS idx_dlt_draws_period ON dlt_draws(period);
        CREATE INDEX IF NOT EXISTS idx_dlt_predictions_period ON dlt_predictions(period);
    ''')
    
    conn.commit()
    conn.close()
    logger.info("大乐透数据库表创建完成")

def insert_dlt_draw(draw):
    """插入单条大乐透开奖"""
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO dlt_draws 
            (period, date, front1, front2, front3, front4, front5, back1, back2,
             pool_amount, first_prize_count, first_prize_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(draw['period']), draw['date'],
            int(draw['front1']), int(draw['front2']), int(draw['front3']),
            int(draw['front4']), int(draw['front5']),
            int(draw['back1']), int(draw['back2']),
            draw.get('pool_amount', 0),
            draw.get('first_prize_count', 0),
            draw.get('first_prize_amount', 0)
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Insert DLT error: {e}")
        return False
    finally:
        conn.close()

def insert_dlt_draws_batch(draws):
    """批量插入大乐透开奖"""
    conn = get_conn()
    try:
        data = [(
            str(d['period']), d['date'],
            int(d['front1']), int(d['front2']), int(d['front3']),
            int(d['front4']), int(d['front5']),
            int(d['back1']), int(d['back2']),
            d.get('pool_amount', 0),
            d.get('first_prize_count', 0),
            d.get('first_prize_amount', 0)
        ) for d in draws]
        conn.executemany('''
            INSERT OR REPLACE INTO dlt_draws 
            (period, date, front1, front2, front3, front4, front5, back1, back2,
             pool_amount, first_prize_count, first_prize_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()
        return len(data)
    except Exception as e:
        conn.rollback()
        logger.error(f"大乐透批量插入失败，已回滚: {e}")
        return 0
    finally:
        conn.close()

def get_dlt_draw_count():
    conn = get_conn()
    count = conn.execute('SELECT COUNT(*) FROM dlt_draws').fetchone()[0]
    conn.close()
    return count

def get_latest_dlt_draw():
    conn = get_conn()
    row = conn.execute('SELECT * FROM dlt_draws ORDER BY period DESC LIMIT 1').fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_dlt_draws():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM dlt_draws ORDER BY period ASC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_dlt_prediction(period, algorithm, front_numbers, back_numbers):
    """保存大乐透预测"""
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO dlt_predictions 
            (period, algorithm, front1, front2, front3, front4, front5, back1, back2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (period, algorithm,
              front_numbers[0], front_numbers[1], front_numbers[2],
              front_numbers[3], front_numbers[4],
              back_numbers[0], back_numbers[1]))
        conn.commit()
    except Exception as e:
        logger.error(f"Save DLT prediction error: {e}")
    finally:
        conn.close()

def save_dlt_prediction_result(period, algorithm, front_hit, back_hit, prize_level=None):
    conn = get_conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO dlt_prediction_results 
            (period, algorithm, front_hit, back_hit, prize_level)
            VALUES (?, ?, ?, ?, ?)
        ''', (period, algorithm, front_hit, back_hit, prize_level))
        conn.commit()
    except Exception as e:
        logger.error(f"Save DLT result error: {e}")
    finally:
        conn.close()

def get_dlt_predictions_with_results(limit=20):
    conn = get_conn()
    rows = conn.execute('''
        SELECT p.*, pr.front_hit, pr.back_hit, pr.prize_level
        FROM dlt_predictions p
        LEFT JOIN dlt_prediction_results pr ON p.period = pr.period AND p.algorithm = pr.algorithm
        ORDER BY p.id DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 验证 ============
if __name__ == '__main__':
    print("正在创建大乐透数据库表...")
    init_dlt_tables()
    
    # 验证
    conn = get_conn()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dlt_%'").fetchall()
    conn.close()
    print(f"\n✅ 已创建表: {[t['name'] for t in tables]}")
    
    # 验证字段完整性
    conn = get_conn()
    info = conn.execute("PRAGMA table_info(dlt_draws)").fetchall()
    conn.close()
    front_cols = [c['name'] for c in info if c['name'].startswith('front')]
    back_cols = [c['name'] for c in info if c['name'].startswith('back')]
    print(f"✅ 前区字段: {front_cols} ({len(front_cols)}个)")
    print(f"✅ 后区字段: {back_cols} ({len(back_cols)}个)")
    print(f"✅ 数据库路径: {DB_PATH}")
