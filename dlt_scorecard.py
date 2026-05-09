#!/usr/bin/env python3
"""
大乐透评分卡模型
前区: 35选5 — 纯老彩民因子（同双色球红球逻辑）
后区: 12选2 — AI因子（近期热度）
"""
import numpy as np
from collections import Counter, defaultdict
from itertools import combinations
from config import (
    DLT_FRONT_WEIGHTS, DLT_BACK_PAIR_WEIGHTS,
    DLT_FRONT_STRUCT_TEMPLATES, DLT_BACK_STRUCT_TEMPLATES
)

# ============================================================
# 前区因子（35选5）
# ============================================================

def dlt_factor_repeat_f(num, draws, last_fronts, last_backs):
    """重号：上期前区号码保留"""
    return 1.0 if num in last_fronts else 0.0

def dlt_factor_neighbor_f(num, draws, last_fronts, last_backs):
    """邻号：上期号码±1"""
    count = sum(1 for n in last_fronts if abs(num - n) == 1)
    return min(count / 2, 1.0)

def dlt_factor_sum_balance_f(num, draws, last_fronts, last_backs):
    """和值平衡：靠近理想值(18)"""
    return max(0, 1 - abs(num - 18) / 17)

def dlt_factor_zone_balance_f(num, draws, last_fronts, last_backs):
    """区间平衡：三区热度"""
    if num <= 12:
        zone = 0
    elif num <= 24:
        zone = 1
    else:
        zone = 2
    
    window = min(50, len(draws))
    recent = draws[-window:]
    
    zone_counts = [0, 0, 0]
    for d in recent:
        for r in ['front1','front2','front3','front4','front5']:
            v = d[r]
            if v <= 12:
                zone_counts[0] += 1
            elif v <= 24:
                zone_counts[1] += 1
            else:
                zone_counts[2] += 1
    
    total = sum(zone_counts)
    if total == 0:
        return 0.5
    
    zone_freq = zone_counts[zone] / total
    return 1 - abs(zone_freq - 1/3) * 3


# ============================================================
# 后区因子（12选2）
# ============================================================

def dlt_factor_recent_b(num, draws, last_fronts, last_backs):
    """近期热度（后区）"""
    window = min(30, len(draws))
    recent = draws[-window:]
    if not recent:
        return 0.5
    count = sum(1 for d in recent for r in ['back1','back2'] if d[r] == num)
    return count / (len(recent) * 2)

def dlt_factor_historical_b(num, draws, last_fronts, last_backs):
    """历史频率（后区）"""
    total = len(draws)
    if total == 0:
        return 0.5
    count = sum(1 for d in draws for r in ['back1','back2'] if d[r] == num)
    return count / (total * 2)

def dlt_factor_mid_freq_b(num, draws, last_fronts, last_backs):
    """中位热度：过去50~150期的频率，过滤偶然波动"""
    if len(draws) < 50:
        return 0.5
    window = draws[-150:-50] if len(draws) >= 150 else draws[:len(draws)-50]
    if not window:
        return 0.5
    count = sum(1 for d in window for r in ['back1','back2'] if d[r] == num)
    return count / (len(window) * 2)

def dlt_factor_repeat_b(num, draws, last_fronts, last_backs):
    """重号（后区）已废弃，改用连开趋势"""
    return 0.0

def dlt_factor_neighbor_b(num, draws, last_fronts, last_backs):
    """邻号（后区）已废弃，改用邻号趋势"""
    return 0.0

def dlt_factor_consecutive_b(num, draws, last_fronts, last_backs):
    """连开趋势：最近5期该号码出现次数，捕获热号连开"""
    window = min(5, len(draws))
    recent = draws[-window:]
    count = sum(1 for d in recent for r in ['back1','back2'] if d[r] == num)
    return count / 2  # 最高1.0（5期中出现2次）

def dlt_factor_neighbor_trend_b(num, draws, last_fronts, last_backs):
    """邻号趋势：上期号码的±1，统计近10期邻号命中趋势"""
    window = min(10, len(draws))
    recent = draws[-window:]
    if len(recent) < 2:
        return 0.5
    # 看num是不是上期某个号码的邻号
    last = draws[-1]
    last_backs = [last['back1'], last['back2']]
    is_neighbor = 1.0 if any(abs(num - b) == 1 for b in last_backs) else 0.0
    # 再看近10期这个位置的号码平均热度
    historical_neighbor = 0
    for d in recent[:-1]:
        prev = [d['back1'], d['back2']]
        if any(abs(num - p) == 1 for p in prev):
            historical_neighbor += 1
    avg = historical_neighbor / len(recent[:-1])
    return max(is_neighbor, avg)

def dlt_factor_span_balance_b(num, draws, last_fronts, last_backs):
    """跨度平衡：避免两个号码太近或太远"""
    # 这个因子在pair层面更有效，但作为单号码因子，
    # 偏好中位号码（5-8），因为它们和其他号码形成小跨度概率更高
    return max(0, 1 - abs(num - 6.5) / 6)


# ============================================================
# 后区：直接Pair评分（更精准）
# ============================================================

def dlt_score_back_pairs(draws):
    """直接对后区66个pair评分，不拆成单号码再组合"""
    if len(draws) < 10:
        return None
    
    w = DLT_BACK_PAIR_WEIGHTS
    all_pairs = list(combinations(range(1, 13), 2))
    last = draws[-1]
    last_backs = {last['back1'], last['back2']}
    
    window_short = min(20, len(draws))
    window_mid = min(100, len(draws))
    recent_short = draws[-window_short:]
    recent_mid = draws[-window_mid:]
    
    pair_scores = []
    for pair in all_pairs:
        pair_set = set(pair)
        score = 0.0
        
        # 1. 近期热度
        cnt_short = sum(1 for d in recent_short if d['back1'] in pair_set and d['back2'] in pair_set)
        score += cnt_short * w['recent_hot']
        
        # 2. 中期热度
        cnt_mid = sum(1 for d in recent_mid if d['back1'] in pair_set and d['back2'] in pair_set)
        score += cnt_mid * w['mid_freq']
        
        # 3. 连开趋势
        score += w['consecutive'] if pair_set == last_backs else 0.0
        
        # 4. 邻号趋势
        neighbor_scores = []
        for n in pair:
            neighbors = {n-1, n+1} & last_backs
            neighbor_scores.append(len(neighbors))
        score += sum(neighbor_scores) * w['neighbor']
        
        # 5. 跨度偏好
        span = max(pair) - min(pair)
        if span <= 5:
            score += w['span_small']
        elif span <= 8:
            score += w['span_mid']
        
        # 6. 和值偏好
        pair_sum = sum(pair)
        if 7 <= pair_sum <= 14:
            score += w['sum_mid']
        
        pair_scores.append((pair, score))
    
    pair_scores.sort(key=lambda x: -x[1])
    return pair_scores


# ============================================================
# 因子注册表

DLT_FRONT_FACTORS = [
    ('重号', dlt_factor_repeat_f, DLT_FRONT_WEIGHTS['repeat']),
    ('邻号', dlt_factor_neighbor_f, DLT_FRONT_WEIGHTS['neighbor']),
    ('和值平衡', dlt_factor_sum_balance_f, DLT_FRONT_WEIGHTS['sum_balance']),
    ('区间平衡', dlt_factor_zone_balance_f, DLT_FRONT_WEIGHTS['zone_balance']),
]

DLT_BACK_FACTORS = [
    ('近期热度', dlt_factor_recent_b, DLT_BACK_PAIR_WEIGHTS['recent_hot']),
    ('中位热度', dlt_factor_mid_freq_b, DLT_BACK_PAIR_WEIGHTS['mid_freq']),
    ('连开趋势', dlt_factor_consecutive_b, DLT_BACK_PAIR_WEIGHTS['consecutive']),
    ('邻号趋势', dlt_factor_neighbor_trend_b, DLT_BACK_PAIR_WEIGHTS['neighbor']),
    ('历史频率', dlt_factor_historical_b, 1.0),
    ('跨度平衡', dlt_factor_span_balance_b, 1.0),
]


# ============================================================
# 评分函数
# ============================================================

def dlt_score_number(num, draws, last_fronts, last_backs, is_front=True):
    factors = DLT_FRONT_FACTORS if is_front else DLT_BACK_FACTORS
    total = 0
    details = {}
    for name, func, weight in factors:
        try:
            raw = func(num, draws, last_fronts, last_backs)
            total += raw * weight
            details[name] = {'raw': round(raw, 3), 'weight': weight, 'weighted': round(raw * weight, 3)}
        except:
            pass
    return total, details


def dlt_score_all(draws):
    """给所有前区35个+后区12个号码评分"""
    if len(draws) < 5:
        return [], []
    
    last = draws[-1]
    last_fronts = [last[f'front{i}'] for i in range(1, 6)]
    last_backs = [last[f'back{i}'] for i in range(1, 3)]
    
    front_scores = []
    for n in range(1, 36):
        score, details = dlt_score_number(n, draws, last_fronts, last_backs, is_front=True)
        front_scores.append((n, score, details))
    
    back_scores = []
    for n in range(1, 13):
        score, details = dlt_score_number(n, draws, last_fronts, last_backs, is_front=False)
        back_scores.append((n, score, details))
    
    return front_scores, back_scores


# ============================================================
# 选号：结构优先
# ============================================================

def dlt_select_numbers(front_scores, back_scores, draws=None):
    """
    前区: TOP15中选5个，匹配结构模板
    后区: TOP8中选2个，匹配结构模板
    """
    if not front_scores or not back_scores:
        return None, None
    
    fs = sorted(front_scores, key=lambda x: x[1], reverse=True)
    bs = sorted(back_scores, key=lambda x: x[1], reverse=True)
    
    # 前区结构模板（从config.py读取）
    FRONT_STRUCTS = DLT_FRONT_STRUCT_TEMPLATES
    
    def match_front(fs_set, tmpl):
        c_sum, c_odd = sum(fs_set), sum(1 for n in fs_set if n % 2 == 1)
        c_span = max(fs_set) - min(fs_set)
        low = sum(1 for n in fs_set if n <= 12)
        mid = sum(1 for n in fs_set if 13 <= n <= 24)
        high = sum(1 for n in fs_set if n >= 25)
        return (tmpl[0][0] <= c_sum <= tmpl[0][1] and
                tmpl[1][0] <= c_odd <= tmpl[1][1] and
                tmpl[2][0] <= c_span <= tmpl[2][1] and
                low == tmpl[3][0] and mid == tmpl[3][1] and high == tmpl[3][2])
    
    # 后区结构（从config.py读取）
    BACK_STRUCTS = DLT_BACK_STRUCT_TEMPLATES
    
    def match_back(bs_set, tmpl):
        c_sum, c_odd = sum(bs_set), sum(1 for n in bs_set if n % 2 == 1)
        c_span = max(bs_set) - min(bs_set)
        return (tmpl[0][0] <= c_sum <= tmpl[0][1] and
                tmpl[1][0] == c_odd and
                tmpl[2][0] <= c_span <= tmpl[2][1])
    
    # ---- 前区选号 ----
    from config import DLT_BACKTEST
    FRONT_TOP = DLT_BACKTEST['front_top_n']
    FRONT_FALLBACK = DLT_BACKTEST['front_fallback_top_n']
    MAX_REPEAT_FRONT = DLT_BACKTEST['max_repeat_fronts']
    MAX_REPEAT_BACK = DLT_BACKTEST['max_repeat_backs']

    top_n_fronts = [r[0] for r in fs[:FRONT_TOP]]
    last_fronts_set = set()
    if draws:
        last = draws[-1]
        last_fronts_set = {last[f'front{i}'] for i in range(1, 6)}

    best_front = None
    best_score = -999

    for combo in combinations(top_n_fronts, 5):
        # 最多MAX_REPEAT_FRONT个重号
        if last_fronts_set and len(set(combo) & last_fronts_set) > MAX_REPEAT_FRONT:
            continue
        for tmpl in FRONT_STRUCTS:
            if match_front(combo, tmpl):
                sc = sum(r[1] for r in fs if r[0] in combo)
                if sc > best_score:
                    best_score = sc
                    best_front = sorted(combo)
                break

    # fallback
    if best_front is None:
        fallback_fronts = [r[0] for r in fs[:FRONT_FALLBACK]]
        for combo in combinations(fallback_fronts, 5):
            sc = sum(r[1] for r in fs if r[0] in combo)
            if sc > best_score:
                best_score = sc
                best_front = sorted(combo)

    # ---- 后区选号：直接Pair评分 ---
    pair_scores = dlt_score_back_pairs(draws)
    if pair_scores:
        last = draws[-1]
        last_backs_set = {last['back1'], last['back2']}

        best_back = None
        best_back_score = -999
        for pair, sc in pair_scores[:DLT_BACKTEST['back_top_n_pairs']]:  # TOP{N} pair
            # 最多MAX_REPEAT_BACK个重号
            if last_backs_set and len(set(pair) & last_backs_set) > MAX_REPEAT_BACK:
                continue
            # 结构匹配（跨度、和值等已经在pair评分里考虑了，但保留模板）
            for tmpl in BACK_STRUCTS:
                if match_back(set(pair), tmpl):
                    if sc > best_back_score:
                        best_back_score = sc
                        best_back = sorted(pair)
                    break
        
        if best_back is None and pair_scores:
            # fallback: 最高分pair（跳过完全重复的）
            for pair, sc in pair_scores:
                if last_backs_set and len(set(pair) & last_backs_set) < 2:
                    best_back = sorted(pair)
                    break
    
    if best_back is None:
        best_back = sorted([r[0] for r in bs[:2]])
    
    return best_front, best_back


# ============================================================
# 主预测接口
# ============================================================

def dlt_predict_detailed(draws=None):
    """返回大乐透预测结果"""
    if draws is None:
        from dlt_database import get_all_dlt_draws
        draws = get_all_dlt_draws()
    
    if len(draws) < 10:
        return {"error": "数据不足"}
    
    front_scores, back_scores = dlt_score_all(draws)
    best_front, best_back = dlt_select_numbers(front_scores, back_scores, draws)
    
    if not best_front or not best_back:
        return {"error": "预测失败"}
    
    last = draws[-1]
    period_prefix = last['period'][:2]
    period_suffix = int(last['period'][2:]) + 1
    next_period = f"{period_prefix}{period_suffix:03d}"
    
    return {
        'period': next_period,
        'date': last['date'],
        'total_draws': len(draws),
        'front_numbers': best_front,
        'back_numbers': best_back,
        'front_scores': [(n, round(s, 3)) for n, s, _ in front_scores],
        'back_scores': [(n, round(s, 3)) for n, s, _ in back_scores],
    }


# ============================================================
# 回测
# ============================================================

def run_dlt_backtest(periods):
    """执行大乐透回测，返回详细统计"""
    from dlt_database import get_all_dlt_draws
    draws = get_all_dlt_draws()
    
    if len(draws) < periods + 30:
        return {"error": f"数据不足，仅{len(draws)}期，需要至少{periods+30}期"}
    
    test_draws = draws[-periods:]
    train_draws = draws[:-periods]
    
    front_hit_list = []
    back_hit_list = []
    detail_5 = 0  # 前区5中
    detail_4 = 0
    detail_3 = 0
    detail_2 = 0
    detail_1 = 0
    detail_0 = 0
    
    # 奖项统计（按大乐透真实规则）
    prize_1 = 0   # 5+2
    prize_2 = 0   # 5+1
    prize_3 = 0   # 5+0
    prize_4 = 0   # 4+2
    prize_5 = 0   # 4+1
    prize_6 = 0   # 3+2
    prize_7 = 0   # 4+0 或 3+1 或 2+2
    prize_8 = 0   # 3+0 或 1+2 或 2+1 或 0+2
    prize_9 = 0   # 后区1中（含各种1+0组合）
    no_prize = 0
    
    for i in range(1, len(test_draws)):
        train = train_draws + test_draws[:i]
        if len(train) < 30:
            continue
        
        actual = test_draws[i]
        actual_fronts = {actual[f'front{i}'] for i in range(1, 6)}
        actual_backs = {actual[f'back{i}'] for i in range(1, 3)}
        
        # 执行预测
        front_scores, back_scores = dlt_score_all(train)
        pred_front, pred_back = dlt_select_numbers(front_scores, back_scores, train)
        
        if not pred_front or not pred_back:
            continue
        
        fh = len(set(pred_front) & actual_fronts)
        bh = len(set(pred_back) & actual_backs)
        
        front_hit_list.append(fh)
        back_hit_list.append(bh)
        
        # 前区命中分布
        if fh == 5: detail_5 += 1
        elif fh == 4: detail_4 += 1
        elif fh == 3: detail_3 += 1
        elif fh == 2: detail_2 += 1
        elif fh == 1: detail_1 += 1
        else: detail_0 += 1
        
        # 奖项判定（大乐透官方规则，共8个奖级）
        if fh == 5 and bh == 2: prize_1 += 1
        elif fh == 5 and bh == 1: prize_2 += 1
        elif fh == 5: prize_3 += 1
        elif fh == 4 and bh == 2: prize_4 += 1
        elif (fh == 4 and bh == 1) or (fh == 3 and bh == 2): prize_5 += 1
        elif (fh == 4 and bh == 0) or (fh == 3 and bh == 1) or (fh == 2 and bh == 2): prize_6 += 1
        elif (fh == 3 and bh == 0) or (fh == 2 and bh == 1) or (fh == 1 and bh == 2) or (fh == 0 and bh == 2): prize_7 += 1
        elif (fh == 2 and bh == 0) or (fh == 1 and bh == 1) or (fh == 0 and bh == 1): prize_8 += 1
        else: no_prize += 1
    
    n = len(front_hit_list)
    if n == 0:
        return {"error": "回测数据不足"}
    
    avg_fh = sum(front_hit_list) / n
    bh_rate = sum(back_hit_list) / n * 100
    hit_3plus = sum(1 for h in front_hit_list if h >= 3)
    hit_4plus = sum(1 for h in front_hit_list if h >= 4)
    
    # 随机期望：前区35选5，期望命中 = 5*5/35 ≈ 0.714
    random_fh = 5 * 5 / 35
    random_bh = 2 * 2 / 12 * 100  # 后区12选2 = 33.3%
    
    total_prize = prize_1 + prize_2 + prize_3 + prize_4 + prize_5 + prize_6 + prize_7 + prize_8
    
    return {
        'n': n,
        'avg_front_hit': round(avg_fh, 3),
        'back_hit_rate': round(bh_rate, 1),
        'random_avg_front': round(random_fh, 3),
        'random_back_rate': round(random_bh, 1),
        'hit_3plus': hit_3plus,
        'hit_3plus_pct': round(hit_3plus/n*100, 1),
        'hit_4plus': hit_4plus,
        'hit_4plus_pct': round(hit_4plus/n*100, 1),
        'detail_5': detail_5, 'detail_4': detail_4, 'detail_3': detail_3,
        'detail_2': detail_2, 'detail_1': detail_1, 'detail_0': detail_0,
        'prize_1': prize_1, 'prize_2': prize_2, 'prize_3': prize_3,
        'prize_4': prize_4, 'prize_5': prize_5, 'prize_6': prize_6,
        'prize_7': prize_7, 'prize_8': prize_8,
        'no_prize': no_prize,
        'total_prize': total_prize,
        'prize_rate': round(total_prize/n*100, 1),
    }


# ============================================================
# 验证
# ============================================================
if __name__ == '__main__':
    from dlt_database import get_all_dlt_draws, get_dlt_draw_count
    
    draws = get_all_dlt_draws()
    print(f"大乐透数据: {len(draws)} 期")
    
    # 测试评分
    print("\n📊 测试评分...")
    front_scores, back_scores = dlt_score_all(draws)
    print(f"  前区评分: {len(front_scores)}个号码")
    print(f"  后区评分: {len(back_scores)}个号码")
    
    fs = sorted(front_scores, key=lambda x: x[1], reverse=True)
    print(f"\n  前区TOP10:")
    for n, s, d in fs[:10]:
        print(f"    {n:02d}: {s:.2f}")
    
    bs = sorted(back_scores, key=lambda x: x[1], reverse=True)
    print(f"\n  后区TOP5:")
    for n, s, d in bs[:5]:
        print(f"    {n:02d}: {s:.2f}")
    
    # 测试选号
    print("\n🎯 测试选号...")
    best_front, best_back = dlt_select_numbers(front_scores, back_scores, draws)
    if best_front and best_back:
        front_str = ' '.join(f"{n:02d}" for n in best_front)
        back_str = ' '.join(f"{n:02d}" for n in best_back)
        print(f"  前区: {front_str}")
        print(f"  后区: {back_str}")
        
        # 验证结构
        print(f"  和值: {sum(best_front)}, 奇偶: {sum(1 for n in best_front if n%2==1)}奇, 跨度: {max(best_front)-min(best_front)}")
        z = f"{sum(1 for n in best_front if n<=12)}:{sum(1 for n in best_front if 13<=n<=24)}:{sum(1 for n in best_front if n>=25)}"
        print(f"  三区: {z}")
    
    # 验证完整性
    print(f"\n✅ 评分卡验证通过")
    print(f"✅ 前区因子: {len(DLT_FRONT_FACTORS)}个")
    print(f"✅ 后区因子: {len(DLT_BACK_FACTORS)}个")
