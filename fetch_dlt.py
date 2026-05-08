#!/usr/bin/env python3
"""
大乐透数据爬虫
从 aicai.com（爱彩）抓取历史开奖数据
"""
import requests
import re
import time
import json
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)
from dlt_database import init_dlt_tables, insert_dlt_draws_batch, get_dlt_draw_count

def fetch_dlt_latest_home():
    """从首页接口获取最新一期数据"""
    url = "https://www.aicai.com/lottery/dlt/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        # 解析开奖号码
        # 示例: 25050期 05 10 17 25 29 + 03 08
        patterns = [
            r'(\d{5})期.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?[+＋].*?(\d{2}).*?(\d{2})',
            r'期号.*?(\d{5}).*?前区.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?后区.*?(\d{2}).*?(\d{2})',
        ]
        for p in patterns:
            m = re.search(p, r.text, re.DOTALL)
            if m:
                return {
                    'period': m.group(1),
                    'front': [int(m.group(i)) for i in range(2, 7)],
                    'back': [int(m.group(i)) for i in range(7, 9)]
                }
        return None
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def fetch_dlt_history(start_period=25001, end_period=25060):
    """爬取历史区间数据"""
    base_url = "https://www.aicai.com/lottery/dlt/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    all_draws = []
    failed = 0
    
    for period in range(start_period, end_period + 1):
        period_str = str(period)
        url = f"{base_url}{period_str}.html"
        
        try:
            r = requests.get(url, headers=headers, timeout=8)
            r.encoding = 'utf-8'
            
            if r.status_code != 200:
                failed += 1
                if failed > 5:
                    print(f"连续{5}期失败，停止")
                    break
                continue
            
            # 解析开奖号码
            patterns = [
                r'前区.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?后区.*?(\d{2}).*?(\d{2})',
                r'(\d{2})\s+(\d{2})\s+(\d{2})\s+(\d{2})\s+(\d{2})\s*[+＋]\s*(\d{2})\s+(\d{2})',
                r'class="ball_red".*?>(\d+)<.*?>(\d+)<.*?>(\d+)<.*?>(\d+)<.*?>(\d+)<.*?class="ball_blue".*?>(\d+)<.*?>(\d+)<',
                r'kjhm.*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?(\d{2}).*?[+＋].*?(\d{2}).*?(\d{2})',
            ]
            
            found = False
            for p in patterns:
                m = re.search(p, r.text, re.DOTALL | re.IGNORECASE)
                if m:
                    nums = [int(m.group(i)) for i in range(1, 8)]
                    if all(1 <= n <= 35 for n in nums[:5]) and all(1 <= n <= 12 for n in nums[5:]):
                        all_draws.append({
                            'period': period_str,
                            'date': str(date.today()),
                            'front1': nums[0], 'front2': nums[1], 'front3': nums[2],
                            'front4': nums[3], 'front5': nums[4],
                            'back1': nums[5], 'back2': nums[6],
                        })
                        found = True
                        break
            
            if found:
                failed = 0
                if len(all_draws) % 10 == 0:
                    print(f"  已抓取 {len(all_draws)} 期...")
            else:
                failed += 1
            
            time.sleep(0.3)
            
        except Exception as e:
            failed += 1
            if failed > 5:
                break
    
    return all_draws


def fetch_dlt_from_apis():
    """
    用多个API接口抓取大乐透历史数据
    来源1: 彩宝贝
    来源2: 500彩票
    """
    all_draws = []
    seen_periods = set()
    
    sources = [
        # 彩宝贝 API
        {
            'url': 'https://www.cai88.com/api/lottery/history',
            'params': {'code': 'dlt', 'pageSize': 200, 'pageNo': 1},
            'parser': None
        },
    ]
    
    # 500彩票 - 历史页面
    url_500 = "https://datachart.500.com/dlt/history/newinc/history.php"
    try:
        r = requests.get(url_500, params={
            'start': '07001',
            'end': '25060',
        }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.encoding = 'utf-8'
        
        # 500彩票表格格式: 期号, 开奖日期, 前区5个, 后区2个
        # <tr class="t_tr1"><td>25050</td><td>...</td>
        rows = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>(\d{5})</td>.*?<td[^>]*>(\d{4}-\d{2}-\d{2})</td>.*?'
            r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?'
            r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>.*?'
            r'<td[^>]*>(\d{2})</td>.*?<td[^>]*>(\d{2})</td>',
            r.text, re.DOTALL
        )
        
        for row in rows:
            period = row[0]
            if period in seen_periods:
                continue
            seen_periods.add(period)
            all_draws.append({
                'period': period,
                'date': row[1],
                'front1': int(row[2]), 'front2': int(row[3]), 'front3': int(row[4]),
                'front4': int(row[5]), 'front5': int(row[6]),
                'back1': int(row[7]), 'back2': int(row[8]),
            })
        
        print(f"  500彩票: 抓取 {len(rows)} 期")
        
    except Exception as e:
        print(f"  500彩票失败: {e}")
    
    # 试一试json接口
    try:
        r = requests.get(
            "https://web.liyuyun.cn/api/dlt/list",
            params={'page': 1, 'size': 100},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            for item in data.get('data', data.get('list', [])):
                period = str(item.get('period', item.get('issue', '')))
                if period in seen_periods:
                    continue
                seen_periods.add(period)
                nums = item.get('numbers', item.get('result', ''))
                if isinstance(nums, str):
                    parts = re.findall(r'\d+', nums)
                    if len(parts) >= 7:
                        all_draws.append({
                            'period': period,
                            'date': item.get('date', str(date.today())),
                            'front1': int(parts[0]), 'front2': int(parts[1]),
                            'front3': int(parts[2]), 'front4': int(parts[3]),
                            'front5': int(parts[4]),
                            'back1': int(parts[5]), 'back2': int(parts[6]),
                        })
    except Exception as e:
        logger.warning(f"大乐透源1解析行失败: {e}")
    
    # 按期号排序去重
    all_draws.sort(key=lambda x: x['period'])
    
    # 去重（保留先出现的）
    seen = set()
    unique = []
    for d in all_draws:
        if d['period'] not in seen:
            seen.add(d['period'])
            unique.append(d)
    
    return unique


def fetch_all_dlt_history():
    """主入口：抓取全部大乐透历史数据"""
    print("=" * 50)
    print("大乐透历史数据抓取")
    print("=" * 50)
    
    # 先初始化表
    init_dlt_tables()
    
    # 从500彩票抓取
    print("\n📡 正在从500彩票抓取...")
    draws = fetch_dlt_from_apis()
    
    if not draws:
        print("❌ 全部来源抓取失败")
        return 0
    
    print(f"\n📊 共抓取 {len(draws)} 期")
    
    # 验证数据有效性
    valid = 0
    invalid = 0
    for d in draws:
        fronts = [d['front1'], d['front2'], d['front3'], d['front4'], d['front5']]
        backs = [d['back1'], d['back2']]
        if (all(1 <= n <= 35 for n in fronts) and
            len(set(fronts)) == 5 and
            all(1 <= n <= 12 for n in backs) and
            len(set(backs)) == 2):
            valid += 1
        else:
            invalid += 1
    
    print(f"✅ 有效数据: {valid} 期")
    print(f"❌ 无效数据: {invalid} 期（已跳过）")
    
    # 批量入库
    valid_draws = [d for d in draws if 
        all(1 <= d[f'front{i}'] <= 35 for i in range(1,6)) and
        len({d[f'front{i}'] for i in range(1,6)}) == 5 and
        all(1 <= d[f'back{i}'] <= 12 for i in range(1,3)) and
        len({d[f'back{i}'] for i in range(1,3)}) == 2
    ]
    
    if valid_draws:
        count = insert_dlt_draws_batch(valid_draws)
        print(f"\n💾 已入库 {count} 期")
    
    total = get_dlt_draw_count()
    print(f"📊 数据库总计: {total} 期")
    
    return total


def fetch_dlt_latest():
    """抓取最新一期并更新数据库"""
    from dlt_database import get_all_dlt_draws
    
    print("📡 正在抓取最新大乐透开奖...")
    
    draws = fetch_dlt_from_apis()
    if not draws:
        return False
    
    existing = get_all_dlt_draws()
    existing_periods = {d['period'] for d in existing}
    
    new_draws = [d for d in draws if d['period'] not in existing_periods]
    
    if new_draws:
        insert_dlt_draws_batch(new_draws)
        print(f"✅ 新增 {len(new_draws)} 期")
        return True
    else:
        print("✅ 数据已是最新")
        return False


if __name__ == '__main__':
    fetch_all_dlt_history()
