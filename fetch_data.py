#!/usr/bin/env python3
"""
双色球历史数据抓取器 — 多源fallback架构

源1: 500彩票网 (datachart.500.com) — 主源，全量数据
源2: 网易彩票 (caipiao.163.com) — 备用源

fallback逻辑: 源1失败 → 自动切源2 → 还失败则返回错误
"""
import requests
import re
import time
import logging
import sys
import os
from datetime import datetime, date

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db, get_draw_count, get_latest_draw, insert_draws_batch

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://datachart.500.com/',
}

# ============================================================
# 源1: 500彩票网
# ============================================================

def fetch_500_history():
    """从500彩票网抓取全部历史数据"""
    url = 'https://datachart.500.com/ssq/history/newinc/history.php'
    try:
        params = {'start': '03001', 'end': '99999', 'limit': 5000}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
        resp.encoding = 'gb2312'
        html = resp.text
        draws = _parse_500_html(html)
        logger.info(f"500彩票: 抓取 {len(draws)} 期")
        return draws
    except Exception as e:
        logger.warning(f"500彩票抓取失败: {e}")
        return None


def fetch_500_latest():
    """从500彩票网抓取最近几期"""
    url = 'https://datachart.500.com/ssq/history/newinc/history.php'
    try:
        params = {'start': '00000', 'end': '99999', 'limit': 5}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        resp.encoding = 'gb2312'
        html = resp.text
        draws = _parse_500_html(html)
        logger.info(f"500彩票最新: 抓取 {len(draws)} 期")
        return draws
    except Exception as e:
        logger.warning(f"500彩票更新失败: {e}")
        return None


def _parse_500_html(html):
    """解析500彩票网的双色球HTML表格"""
    draws = []
    # 匹配 <tr class="t_tr1">...</tr>
    pattern = r'<tr[^>]*t_tr1[^>]*>.*?</tr>'
    rows = re.findall(pattern, html, re.DOTALL)

    for row in rows:
        try:
            tds = re.findall(r'<td[^>]*>([^<]*)</td>', row)
            if len(tds) < 17:
                continue
            period = tds[1].strip()
            reds = [int(tds[i].strip()) for i in range(2, 8)]
            blue = int(tds[8].strip())
            pool_str = tds[10].strip().replace(',', '')
            pool_amount = float(pool_str) if pool_str and pool_str != '&nbsp;' else 0
            first_count_str = tds[11].strip()
            first_count = int(first_count_str) if first_count_str and first_count_str != '&nbsp;' else 0
            first_amount_str = tds[12].strip().replace(',', '')
            first_amount = float(first_amount_str) if first_amount_str and first_amount_str != '&nbsp;' else 0
            date_str = tds[16].strip()
            draw = {
                'period': period, 'date': date_str,
                'red1': reds[0], 'red2': reds[1], 'red3': reds[2],
                'red4': reds[3], 'red5': reds[4], 'red6': reds[5],
                'blue': blue, 'pool_amount': pool_amount,
                'first_prize_count': first_count, 'first_prize_amount': first_amount,
            }
            if all(1 <= r <= 33 for r in reds) and 1 <= blue <= 16 and len(set(reds)) == 6:
                draws.append(draw)
        except (ValueError, IndexError) as e:
            logger.warning(f"解析500彩票行失败: {e}")
            continue
    return draws


# ============================================================
# 源2: 网易彩票 (caipiao.163.com)
# ============================================================

def fetch_163_history():
    """从网易彩票抓取全部历史数据"""
    draws = []
    page = 1
    while True:
        draws_page = _fetch_163_page(page)
        if not draws_page:
            break
        draws.extend(draws_page)
        page += 1
        if page > 300:  # 安全限制
            break
        time.sleep(0.3)
    logger.info(f"网易彩票: 抓取 {len(draws)} 期")
    return draws


def fetch_163_latest():
    """从网易彩票抓取最新一期"""
    return _fetch_163_page(1)


def _fetch_163_page(page=1):
    """抓取网易彩票某页数据"""
    try:
        url = "https://caipiao.163.com/award/ssq/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = 'utf-8'

        # 网易格式: <tr data-period="25001"><td class="num">...<span class="red">01</span><span class="red">05</span>...</td></tr>
        # 先找所有期号行
        draws = []
        rows = re.findall(
            r'<tr[^>]*data-period[=]?"(\d+)"[^>]*>(.*?)</tr>',
            r.text, re.DOTALL
        )
        for period_str, row_html in rows:
            # 找所有球号
            balls = re.findall(r'<span class="(?:red|blue)">(\d+)</span>', row_html)
            if len(balls) < 7:
                continue
            reds = [int(b) for b in balls[:6]]
            blue = int(balls[6])
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', row_html)
            date_str = date_match.group(1) if date_match else ''
            draw = {
                'period': str(period_str), 'date': date_str,
                'red1': reds[0], 'red2': reds[1], 'red3': reds[2],
                'red4': reds[3], 'red5': reds[4], 'red6': reds[5],
                'blue': blue, 'pool_amount': 0,
                'first_prize_count': 0, 'first_prize_amount': 0,
            }
            if all(1 <= r <= 33 for r in reds) and 1 <= blue <= 16 and len(set(reds)) == 6:
                draws.append(draw)

        return draws
    except Exception as e:
        logger.warning(f"网易彩票第{page}页抓取失败: {e}")
        return []


# ============================================================
# 统一入口（带fallback链）
# ============================================================

SOURCES = [
    ('500彩票', fetch_500_history, fetch_500_latest),
    ('网易彩票', fetch_163_history, fetch_163_latest),
]


def fetch_all_history():
    """抓取所有历史数据（带fallback）"""
    for name, fetch_fn, _ in SOURCES:
        print(f"📡 正在从 [{name}] 抓取全部历史数据...")
        draws = fetch_fn()
        if draws and len(draws) > 100:
            print(f"✅ [{name}] 抓取成功: {len(draws)} 期")
            count = insert_draws_batch(draws)
            print(f"💾 入库 {count} 期")
            return draws
        else:
            print(f"⚠️ [{name}] 失败或数据不足 ({len(draws) if draws else 0}期)，尝试备用源...")

    print("❌ 所有源均抓取失败")
    return []


def fetch_latest():
    """抓取最新一期（带fallback）"""
    for name, _, fetch_fn in SOURCES:
        print(f"📡 正在从 [{name}] 抓取最新数据...")
        draws = fetch_fn()
        if draws:
            # 过滤新数据
            latest_db = get_latest_draw()
            latest_period = latest_db['period'] if latest_db else '00000'
            new_draws = [d for d in draws if str(d['period']) > str(latest_period)]
            if new_draws:
                count = insert_draws_batch(new_draws)
                print(f"✅ [{name}] 新增 {count} 期")
                return new_draws
            else:
                print(f"✅ 数据已是最新")
                return []
        else:
            print(f"⚠️ [{name}] 失败，尝试备用源...")

    print("❌ 所有源均更新失败")
    return []


if __name__ == '__main__':
    init_db()
    current_count = get_draw_count()
    print(f"当前数据库已有: {current_count} 期")
    if current_count == 0:
        draws = fetch_all_history()
    else:
        draws = fetch_latest()
    new_count = get_draw_count()
    print(f"操作完成，数据库现有: {new_count} 期数据")
