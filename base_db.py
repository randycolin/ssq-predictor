#!/usr/bin/env python3
"""
数据库公共基类 — 消除 SSQ / DLT 数据库层的重复代码

两个彩种共享同一数据库文件 (data/ssq.db)，使用不同的表名前缀。
SSQ: draws, predictions, prediction_results
DLT: dlt_draws, dlt_predictions, dlt_prediction_results

⚠️ 所有存取都走 get_conn()，共用连接池。
"""
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ssq.db')


def get_conn():
    """获取数据库连接（共用）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class BaseLotteryDB:
    """彩票数据库公共CRUD基类

    子类只需定义：
      - table_prefix: 'dlt_' 或 ''（空=双色球）
      - draw_columns: 开奖表的字段列表
      - draw_placeholders: INSERT的?占位符
    """

    def __init__(self, table_prefix: str):
        self.p = table_prefix  # 表名前缀，如 'dlt_' 或 ''
        self.draw_table = f"{self.p}draws"
        self.pred_table = f"{self.p}predictions"
        self.result_table = f"{self.p}prediction_results"

    # ===================== 开奖数据 =====================

    def get_draw_count(self) -> int:
        conn = get_conn()
        count = conn.execute(f"SELECT COUNT(*) FROM {self.draw_table}").fetchone()[0]
        conn.close()
        return count

    def get_latest_draw(self):
        conn = get_conn()
        row = conn.execute(f"SELECT * FROM {self.draw_table} ORDER BY period DESC LIMIT 1").fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_draws(self):
        conn = get_conn()
        rows = conn.execute(f"SELECT * FROM {self.draw_table} ORDER BY period ASC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recent_draws(self, n=50):
        conn = get_conn()
        rows = conn.execute(f"SELECT * FROM {self.draw_table} ORDER BY period DESC LIMIT ?", (n,)).fetchall()
        conn.close()
        return [dict(r) for r in rows][::-1]

    def insert_draw(self, draw: dict) -> bool:
        conn = get_conn()
        try:
            self._insert_one(conn, self.draw_table, draw)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Insert {self.draw_table} error: {e}")
            return False
        finally:
            conn.close()

    def insert_draws_batch(self, draws: list) -> int:
        conn = get_conn()
        try:
            data = [self._draw_to_tuple(d) for d in draws]
            cols = ", ".join(self.draw_columns)
            placeholders = ", ".join("?" for _ in self.draw_columns)
            conn.executemany(
                f"INSERT OR REPLACE INTO {self.draw_table} ({cols}) VALUES ({placeholders})",
                data
            )
            conn.commit()
            return len(data)
        except Exception as e:
            conn.rollback()
            logger.error(f"批量插入{self.draw_table}失败，已回滚: {e}")
            return 0
        finally:
            conn.close()

    # ===================== 预测 =====================

    def save_prediction(self, period: str, algorithm: str, numbers: list):
        """numbers: [n1, n2, n3, ...] 与表列数匹配"""
        conn = get_conn()
        try:
            self._insert_one(conn, self.pred_table, {
                'period': period, 'algorithm': algorithm,
                **{self.pred_cols[i]: numbers[i] for i in range(len(numbers))}
            })
            conn.commit()
        except Exception as e:
            logger.error(f"Save {self.pred_table} error: {e}")
        finally:
            conn.close()

    def save_prediction_result(self, period: str, algorithm: str,
                               hit_col1: int, hit_col2: int, prize_level=None):
        conn = get_conn()
        try:
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.result_table} 
                (period, algorithm, {self.hit_col1_name}, {self.hit_col2_name}, prize_level)
                VALUES (?, ?, ?, ?, ?)
            """, (period, algorithm, hit_col1, hit_col2, prize_level))
            conn.commit()
        except Exception as e:
            logger.error(f"Save {self.result_table} result error: {e}")
        finally:
            conn.close()

    def get_predictions_with_results(self, limit=20):
        conn = get_conn()
        rows = conn.execute(f"""
            SELECT p.*, pr.{self.hit_col1_name}, pr.{self.hit_col2_name}, pr.prize_level
            FROM {self.pred_table} p
            LEFT JOIN {self.result_table} pr 
              ON p.period = pr.period AND p.algorithm = pr.algorithm
            ORDER BY p.id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ===================== 内部工具 =====================

    def _insert_one(self, conn, table: str, data: dict):
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
            tuple(data.values())
        )

    def _draw_to_tuple(self, d: dict):
        """将draw dict转为INSERT元组，自动推断类型，不存在的字段填0或空"""
        def _val(c):
            v = d.get(c, 0)
            if c in ('first_prize_count',) or (c.startswith(('red', 'blue', 'front', 'back')) and c != 'pool_amount'):
                return int(v)
            elif c in ('pool_amount', 'first_prize_amount'):
                return float(v)
            return str(v)
        return tuple(_val(c) for c in self.draw_columns)


class SSQDB(BaseLotteryDB):
    """双色球数据库操作"""

    def __init__(self):
        super().__init__('')
        self.draw_columns = ['period', 'date', 'red1', 'red2', 'red3', 'red4', 'red5', 'red6',
                             'blue', 'pool_amount', 'first_prize_count', 'first_prize_amount']
        self.pred_cols = ['red1', 'red2', 'red3', 'red4', 'red5', 'red6', 'blue']
        self.hit_col1_name = 'red_hit'
        self.hit_col2_name = 'blue_hit'
        self.init_sql = """
            CREATE TABLE IF NOT EXISTS draws (
                period TEXT PRIMARY KEY, date TEXT NOT NULL,
                red1 INTEGER NOT NULL, red2 INTEGER NOT NULL,
                red3 INTEGER NOT NULL, red4 INTEGER NOT NULL,
                red5 INTEGER NOT NULL, red6 INTEGER NOT NULL,
                blue INTEGER NOT NULL,
                pool_amount REAL DEFAULT 0,
                first_prize_count INTEGER DEFAULT 0,
                first_prize_amount REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL, algorithm TEXT NOT NULL,
                red1 INTEGER NOT NULL, red2 INTEGER NOT NULL,
                red3 INTEGER NOT NULL, red4 INTEGER NOT NULL,
                red5 INTEGER NOT NULL, red6 INTEGER NOT NULL,
                blue INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(period, algorithm)
            );
            CREATE TABLE IF NOT EXISTS prediction_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL, algorithm TEXT NOT NULL,
                red_hit INTEGER DEFAULT 0, blue_hit INTEGER DEFAULT 0,
                prize_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(period, algorithm)
            );
            CREATE INDEX IF NOT EXISTS idx_draws_date ON draws(date);
            CREATE INDEX IF NOT EXISTS idx_draws_period ON draws(period);
            CREATE INDEX IF NOT EXISTS idx_predictions_period ON predictions(period);
        """

    def init_tables(self):
        conn = get_conn()
        conn.executescript(self.init_sql)
        conn.commit()
        conn.close()


class DLTDB(BaseLotteryDB):
    """大乐透数据库操作"""

    def __init__(self):
        super().__init__('dlt_')
        self.draw_columns = ['period', 'date', 'front1', 'front2', 'front3', 'front4', 'front5',
                             'back1', 'back2', 'pool_amount', 'first_prize_count', 'first_prize_amount']
        self.pred_cols = ['front1', 'front2', 'front3', 'front4', 'front5', 'back1', 'back2']
        self.hit_col1_name = 'front_hit'
        self.hit_col2_name = 'back_hit'
        self.init_sql = """
            CREATE TABLE IF NOT EXISTS dlt_draws (
                period TEXT PRIMARY KEY, date TEXT NOT NULL,
                front1 INTEGER NOT NULL, front2 INTEGER NOT NULL,
                front3 INTEGER NOT NULL, front4 INTEGER NOT NULL,
                front5 INTEGER NOT NULL,
                back1 INTEGER NOT NULL, back2 INTEGER NOT NULL,
                pool_amount REAL DEFAULT 0,
                first_prize_count INTEGER DEFAULT 0,
                first_prize_amount REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS dlt_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL, algorithm TEXT NOT NULL,
                front1 INTEGER NOT NULL, front2 INTEGER NOT NULL,
                front3 INTEGER NOT NULL, front4 INTEGER NOT NULL,
                front5 INTEGER NOT NULL,
                back1 INTEGER NOT NULL, back2 INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(period, algorithm)
            );
            CREATE TABLE IF NOT EXISTS dlt_prediction_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL, algorithm TEXT NOT NULL,
                front_hit INTEGER DEFAULT 0, back_hit INTEGER DEFAULT 0,
                prize_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(period, algorithm)
            );
            CREATE INDEX IF NOT EXISTS idx_dlt_draws_date ON dlt_draws(date);
            CREATE INDEX IF NOT EXISTS idx_dlt_draws_period ON dlt_draws(period);
            CREATE INDEX IF NOT EXISTS idx_dlt_predictions_period ON dlt_predictions(period);
        """

    def init_tables(self):
        conn = get_conn()
        conn.executescript(self.init_sql)
        conn.commit()
        conn.close()
