#!/usr/bin/env python3
"""
双色球历史数据抓取器
从500彩票网抓取2003年至今的全部开奖数据
"""

import requests
import time
import re
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db, get_draw_count, get_latest_draw, insert_draws_batch

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://datachart.500.com/',
}

def fetch_all_history():
    """
    抓取所有历史数据
    500彩票网双色球历史数据接口
    """
    url = 'https://datachart.500.com/ssq/history/newinc/history.php'
    
    print("正在抓取全部历史数据（分批）...")
    draws = []
    
    # 500.com limit is about 150 per page. We'll page through
    # Period format: 03001 ~ current
    # Strategy: fetch in chunks of 150 periods
    current_end = 99999
    
    try:
        params = {
            'start': '03001',
            'end': str(current_end),
            'limit': 5000,
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
        resp.encoding = 'gb2312'
        html = resp.text
        
        # Debug
        print(f"Response size: {len(html)} bytes")
        print(f"Has t_tr1: {'t_tr1' in html}")
        
        # Parse the HTML table
        draws = parse_500_html(html)
        if draws:
            print(f"抓取到 {len(draws)} 期数据")
            count = insert_draws_batch(draws)
            print(f"成功导入 {count} 期")
            return draws
        else:
            print("解析失败，未提取到数据")
            return []
            
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

def fetch_latest():
    """
    只抓取最新一期（用于日常更新）
    """
    url = 'https://datachart.500.com/ssq/history/newinc/history.php'
    params = {
        'start': '00000',
        'end': '99999',
        'limit': 5,
    }
    
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        resp.encoding = 'gb2312'
        html = resp.text
        draws = parse_500_html(html)
        if draws:
            latest_db = get_latest_draw()
            latest_period = latest_db['period'] if latest_db else '00000'
            
            new_draws = [d for d in draws if str(d['period']) > str(latest_period)]
            if new_draws:
                count = insert_draws_batch(new_draws)
                print(f"新增 {count} 期数据")
                return new_draws
            else:
                print("已是最新数据")
                return []
        return []
    except Exception as e:
        print(f"更新失败: {e}")
        return []

def parse_500_html(html):
    """解析500彩票网的双色球历史数据HTML
    
    HTML行格式:
    <tr class="t_tr1"><!--<td>2</td>--><td>期号</td><td class="t_cfont2">红1</td>...<td class="t_cfont2">红6</td><td class="t_cfont4">蓝</td>...<td>日期</td></tr>
    """
    import re
    
    draws = []
    
    # Find all data rows
    # Use [^>]* to match class="t_tr1" or other attribute formats
    pattern = r'<tr[^>]*t_tr1[^>]*>.*?</tr>'
    rows = re.findall(pattern, html, re.DOTALL)
    
    for row in rows:
        try:
            # Extract all td values
            tds = re.findall(r'<td[^>]*>([^<]*)</td>', row)
            
            # Format: [hidden, period, red1, red2, red3, red4, red5, red6, blue, happy_sunday, pool, first_count, first_amount, second_count, second_amount, total_bet, date]
            # First TD is a hidden index column
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
                'period': period,
                'date': date_str,
                'red1': reds[0], 'red2': reds[1], 'red3': reds[2],
                'red4': reds[3], 'red5': reds[4], 'red6': reds[5],
                'blue': blue,
                'pool_amount': pool_amount,
                'first_prize_count': first_count,
                'first_prize_amount': first_amount,
            }
            
            # Validate
            if (all(1 <= r <= 33 for r in reds) and 
                1 <= blue <= 16 and
                len(set(reds)) == 6):
                draws.append(draw)
                
        except (ValueError, IndexError) as e:
            continue
    
    return draws

if __name__ == '__main__':
    init_db()
    
    current_count = get_draw_count()
    print(f"当前数据库已有: {current_count} 期")
    
    if current_count == 0:
        print("首次初始化，抓取全部历史数据...")
        draws = fetch_all_history()
    else:
        print("检查最新数据...")
        draws = fetch_latest()
    
    new_count = get_draw_count()
    print(f"操作完成，数据库现有: {new_count} 期数据")
