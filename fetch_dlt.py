#!/usr/bin/env python3
"""
大乐透数据爬虫 — 多源fallback架构

源1: 500彩票网 (datachart.500.com) — 主源，全量历史表格
源2: 网易彩票 (caipiao.163.com) — 备用源
源3: 彩宝贝 (aicai.com) — 逐页爬取（最后手段）

fallback逻辑: 源1成功就返回 → 源2 → 源3
"""
import requests
import re
import time
import json
import logging
import sys
import os
from datetime import datetime, date

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlt_database import init_dlt_tables, insert_dlt_draws_batch, get_dlt_draw_count, get_all_dlt_draws

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://datachart.500.com/',
}

# ============================================================
# 源1: 500彩票网 — 全量历史表格（大乐透专用）
# ============================================================

def fetch_500_history():
    """从500彩票网抓取大乐透全部历史数据"""
    url = "https://datachart.500.com/dlt/history/newinc/history.php"
    try:
        r = requests.get(url, params={
            'start': '07001', 'end': '99999',
        }, headers=HEADERS, timeout=30)
        r.encoding = 'gb2312'
        html = r.text
        draws = _parse_500_dlt_html(html)
        logger.info(f"500彩票大乐透: 抓取 {len(draws)} 期")
        return draws
    except Exception as e:
        logger.warning(f"500彩票大乐透抓取失败: {e}")
        return None


def fetch_500_latest():
    """从500彩票网抓取大乐透最近几期"""
    url = "https://datachart.500.com/dlt/history/newinc/history.php"
    try:
        r = requests.get(url, params={
            'start': '00000', 'end': '99999',
        }, headers=HEADERS, timeout=30)
        r.encoding = 'gb2312'
        html = r.text
        draws = _parse_500_dlt_html(html)
        logger.info(f"500彩票大乐透最新: 抓取 {len(draws)} 期")
        return draws
    except Exception as e:
        logger.warning(f"500彩票大乐透更新失败: {e}")
        return None


def _parse_500_dlt_html(html):
    """解析500彩票网的大乐透HTML表格

    表格列: 期号, 日期, 前区5个, 后区2个, 销量, 奖池, ...
    """
    draws = []
    rows = re.findall(
        r'<tr[^>]*t_tr1[^>]*>.*?<td[^>]*>(\d{5})</td>.*?<td[^>]*>(\d{4}-\d{2}-\d{2})</td>.*?'
        r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?'
        r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?'
        r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>',
        html, re.DOTALL
    )
    for row in rows:
        period = row[0]
        date_str = row[1]
        fronts = [int(row[i]) for i in range(2, 7)]
        backs = [int(row[i]) for i in range(7, 9)]
        draw = {
            'period': period, 'date': date_str,
            'front1': fronts[0], 'front2': fronts[1], 'front3': fronts[2],
            'front4': fronts[3], 'front5': fronts[4],
            'back1': backs[0], 'back2': backs[1],
            'pool_amount': 0, 'first_prize_count': 0, 'first_prize_amount': 0,
        }
        # 验证
        if (all(1 <= n <= 35 for n in fronts) and len(set(fronts)) == 5 and
            all(1 <= n <= 12 for n in backs) and len(set(backs)) == 2):
            draws.append(draw)
    return draws


# ============================================================
# 源2: 网易彩票 (caipiao.163.com)
# ============================================================

def fetch_163_dlt_history():
    """从网易彩票抓取大乐透全部历史数据"""
    draws = []
    page = 1
    while True:
        draws_page = _fetch_163_dlt_page(page)
        if not draws_page:
            break
        draws.extend(draws_page)
        page += 1
        if page > 300:
            break
        time.sleep(0.3)
    logger.info(f"网易大乐透: 抓取 {len(draws)} 期")
    return draws


def fetch_163_dlt_latest():
    """从网易彩票抓取最新大乐透"""
    return _fetch_163_dlt_page(1)


def _fetch_163_dlt_page(page=1):
    try:
        url = "https://caipiao.163.com/award/dlt/"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'

        draws = []
        rows = re.findall(
            r'<tr[^>]*data-period[=]?"(\d+)"[^>]*>(.*?)</tr>',
            r.text, re.DOTALL
        )
        for period_str, row_html in rows:
            balls = re.findall(r'<span class="(?:red|blue)">(\d+)</span>', row_html)
            if len(balls) < 7:
                continue
            fronts = [int(b) for b in balls[:5]]
            backs = [int(b) for b in balls[5:7]]
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', row_html)
            date_str = date_match.group(1) if date_match else ''
            draw = {
                'period': str(period_str), 'date': date_str,
                'front1': fronts[0], 'front2': fronts[1], 'front3': fronts[2],
                'front4': fronts[3], 'front5': fronts[4],
                'back1': backs[0], 'back2': backs[1],
                'pool_amount': 0, 'first_prize_count': 0, 'first_prize_amount': 0,
            }
            if (all(1 <= n <= 35 for n in fronts) and len(set(fronts)) == 5 and
                all(1 <= n <= 12 for n in backs) and len(set(backs)) == 2):
                draws.append(draw)
        return draws
    except Exception as e:
        logger.warning(f"网易大乐透第{page}页抓取失败: {e}")
        return []


# ============================================================
# 源3: 彩宝贝 (aicai.com) — 逐页爬（最后手段）
# ============================================================

def fetch_aicai_latest():
    """从aicai首页接口获取最新一期"""
    try:
        r = requests.get("https://www.aicai.com/lottery/dlt/",
                         headers=HEADERS, timeout=10)
        r.encoding = 'utf-8'
        patterns = [
            r'(\d{5})期.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?[+＋].*?(\d{2}).*?(\d{2})',
            r'期号.*?(\d{5}).*?前区.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?后区.*?(\d{2}).*?(\d{2})',
        ]
        for p in patterns:
            m = re.search(p, r.text, re.DOTALL)
            if m:
                fronts = [int(m.group(i)) for i in range(2, 7)]
                backs = [int(m.group(i)) for i in range(7, 9)]
                return [{
                    'period': m.group(1), 'date': str(date.today()),
                    'front1': fronts[0], 'front2': fronts[1], 'front3': fronts[2],
                    'front4': fronts[3], 'front5': fronts[4],
                    'back1': backs[0], 'back2': backs[1],
                    'pool_amount': 0, 'first_prize_count': 0, 'first_prize_amount': 0,
                }]
        return None
    except Exception as e:
        logger.warning(f"aicai抓取失败: {e}")
        return None


# ============================================================
# 统一入口（带fallback链）
# ============================================================

_HISTORY_SOURCES = [
    ('500彩票', fetch_500_history),
    ('网易彩票', fetch_163_dlt_history),
]

_LATEST_SOURCES = [
    ('500彩票', fetch_500_latest),
    ('网易彩票', fetch_163_dlt_latest),
    ('彩宝贝', fetch_aicai_latest),
]


def fetch_all_dlt_history():
    """主入口：抓取全部大乐透历史数据（带fallback）"""
    init_dlt_tables()

    print("=" * 50)
    print("大乐透历史数据抓取")
    print("=" * 50)

    for name, fetch_fn in _HISTORY_SOURCES:
        print(f"\n📡 正在从 [{name}] 抓取...")
        draws = fetch_fn()
        if draws and len(draws) > 50:
            print(f"✅ [{name}] 成功: {len(draws)} 期")

            # 验证
            valid = [d for d in draws if
                     all(1 <= d[f'front{i}'] <= 35 for i in range(1, 6)) and
                     len({d[f'front{i}'] for i in range(1, 6)}) == 5 and
                     all(1 <= d[f'back{i}'] <= 12 for i in range(1, 3)) and
                     len({d[f'back{i}'] for i in range(1, 3)}) == 2]

            if valid:
                count = insert_dlt_draws_batch(valid)
                print(f"💾 入库 {count}/{len(valid)} 期（已过滤无效数据）")
                total = get_dlt_draw_count()
                print(f"📊 数据库总计: {total} 期")
                return total
        else:
            print(f"⚠️ [{name}] 数据不足 ({len(draws) if draws else 0}期)，尝试备用源...")

    print("❌ 所有源均抓取失败")
    return 0


def fetch_dlt_latest():
    """抓取最新一期（带fallback），返回新增的数据列表"""
    print("📡 正在抓取最新大乐透开奖...")

    for name, fetch_fn in _LATEST_SOURCES:
        print(f"  尝试 [{name}]...")
        draws = fetch_fn()
        if not draws:
            print(f"  ⚠️ [{name}] 失败")
            continue

        existing = get_all_dlt_draws()
        existing_periods = {d['period'] for d in existing}

        new_draws = [d for d in draws if d['period'] not in existing_periods]
        if new_draws:
            insert_dlt_draws_batch(new_draws)
            print(f"✅ [{name}] 新增 {len(new_draws)} 期")
            return new_draws
        else:
            print(f"✅ [{name}] 数据已是最新")
            return []

    print("❌ 所有源均更新失败")
    return []


if __name__ == '__main__':
    fetch_all_dlt_history()
