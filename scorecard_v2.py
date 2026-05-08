#!/usr/bin/env python3
"""
评分卡模型 - 双色球号码评分系统
=========================================
每个号码的得分 = Σ(因子_i × 权重_i)

核心逻辑：
1. 用9个因子对33个红球逐一评分
2. 从TOP8高分中枚举C(8,6)=28种组合，选评分+分布最优的
3. 蓝球单独用5个因子评分，取最高分
=========================================
"""

import numpy as np
from collections import Counter, defaultdict
from itertools import combinations

# ============================================================
# 因子1: 历史频率 — 全周期出现次数/总期数
# ============================================================
def factor_historical_frequency(num, draws, last_reds, last_blue):
    total = len(draws)
    if total == 0:
        return 0.5
    if isinstance(num, int) and 1 <= num <= 33:
        count = sum(1 for d in draws for r in ['red1','red2','red3','red4','red5','red6'] if d[r] == num)
        return count / total
    elif isinstance(num, int) and 1 <= num <= 16:
        count = sum(1 for d in draws if d['blue'] == num)
        return count / total
    return 0.5

# ============================================================
# 因子2: 近期热度 — 近30期出现频率
# ============================================================
def factor_recent_frequency(num, draws, last_reds, last_blue):
    window = min(30, len(draws))
    recent = draws[-window:]
    total = len(recent) * 6 if isinstance(num, int) and 1 <= num <= 33 else len(recent)
    if total == 0:
        return 0.5
    if isinstance(num, int) and 1 <= num <= 33:
        count = sum(1 for d in recent for r in ['red1','red2','red3','red4','red5','red6'] if d[r] == num)
    else:
        count = sum(1 for d in recent if d['blue'] == num)
    return count / total

# ============================================================
# 因子3: 间隔百分位 — 当前间隔在历史中的位置
# 间隔越久分数越高（赌回归）
# ⚠️ 单因子表现差，已降权
# ============================================================
def factor_interval_percentile(num, draws, last_reds, last_blue):
    if len(draws) < 30:
        return 0.5
    
    intervals = []
    last_seen = -1
    
    for idx, d in enumerate(draws):
        if isinstance(num, int) and 1 <= num <= 33:
            for r in ['red1','red2','red3','red4','red5','red6']:
                if d[r] == num:
                    if last_seen >= 0:
                        intervals.append(idx - last_seen)
                    last_seen = idx
                    break
        else:
            if d['blue'] == num:
                if last_seen >= 0:
                    intervals.append(idx - last_seen)
                last_seen = idx
    
    current_interval = len(draws) - 1 - last_seen if last_seen >= 0 else len(draws)
    
    if not intervals:
        return min(current_interval / 50, 1.0)
    
    avg_interval = np.mean(intervals)
    if avg_interval <= 0:
        return 0.5
    
    ratio = current_interval / avg_interval
    score = 1 - 0.5 ** ratio  # ratio=1→0.5, ratio=2→0.75, ratio=3→0.875
    return min(score, 1.0)

# ============================================================
# 因子4: 关联断裂 — 高频组合近期断裂程度
# ============================================================
def factor_correlation_break(num, draws, last_reds, last_blue,
                              old_sets=None, recent_sets=None):
    if len(draws) < 100 or not (isinstance(num, int) and 1 <= num <= 33):
        return 0.5
    
    if old_sets is None or recent_sets is None:
        window = 100
        older = draws[:-window]
        recent = draws[-window:]
        old_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in older]
        recent_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in recent]
    
    old_partners = Counter()
    for s in old_sets:
        if num in s:
            for p in s:
                if p != num:
                    old_partners[p] += 1
    
    recent_partners = Counter()
    for s in recent_sets:
        if num in s:
            for p in s:
                if p != num:
                    recent_partners[p] += 1
    
    break_score = 0
    for partner, old_count in old_partners.most_common(10):
        old_freq = old_count / len(old_sets)
        recent_freq = recent_partners.get(partner, 0) / len(recent_sets)
        if old_freq > 0.03 and recent_freq < old_freq * 0.5:
            break_score += (old_freq - recent_freq)
    
    return min(break_score * 10, 1.0)

# ============================================================
# 因子5: 重号 — 上期号码保留
# ============================================================
def factor_repeat(num, draws, last_reds, last_blue):
    if isinstance(num, int) and 1 <= num <= 33:
        return 1.0 if num in last_reds else 0.0
    else:
        return 1.0 if num == last_blue else 0.0

# ============================================================
# 因子6: 邻号 — 上期号码±1
# ============================================================
def factor_neighbor(num, draws, last_reds, last_blue):
    if isinstance(num, int) and 1 <= num <= 33:
        count = sum(1 for r in last_reds if abs(num - r) == 1)
        return min(count / 2, 1.0)
    else:
        return 1.0 if abs(num - last_blue) == 1 else 0.0

# ============================================================
# 因子7: 和值平衡 — 靠近均值17加分
# ============================================================
def factor_sum_balance(num, draws, last_reds, last_blue):
    if isinstance(num, int) and 1 <= num <= 33:
        return max(0, 1 - abs(num - 17) / 16)
    return 0.5

# ============================================================
# 因子8: 区间平衡 — 看号码所在区间的整体热度
# ============================================================
def factor_zone_balance(num, draws, last_reds, last_blue):
    if not isinstance(num, int) or not (1 <= num <= 33):
        return 0.5
    
    if num <= 11:
        zone = 0
    elif num <= 22:
        zone = 1
    else:
        zone = 2
    
    window = min(50, len(draws))
    recent = draws[-window:]
    
    zone_counts = [0, 0, 0]
    for d in recent:
        for r in ['red1','red2','red3','red4','red5','red6']:
            v = d[r]
            if v <= 11:
                zone_counts[0] += 1
            elif v <= 22:
                zone_counts[1] += 1
            else:
                zone_counts[2] += 1
    
    total = sum(zone_counts)
    if total == 0:
        return 0.5
    
    zone_freq = zone_counts[zone] / total
    return 1 - abs(zone_freq - 1/3) * 3

# ============================================================
# 因子9: 历史模式 — 传统构造（较弱占位）
# ============================================================
def factor_historical_pattern(num, draws, last_reds, last_blue):
    return 0.5  # 占位，实际在选号阶段处理

# ============================================================
# 因子注册表（名称, 函数, 权重）
# 权重通过回测优化调整
# ============================================================

RED_FACTORS = [
    ('历史频率', factor_historical_frequency, 1.0),
    ('近期热度', factor_recent_frequency, 1.5),
    ('间隔百分位', factor_interval_percentile, 0.5),
    ('关联断裂', factor_correlation_break, 1.5),
    ('重号', factor_repeat, 1.5),
    ('邻号', factor_neighbor, 0.5),
    ('和值平衡', factor_sum_balance, 0.5),
    ('区间平衡', factor_zone_balance, 0.5),
    ('历史模式', factor_historical_pattern, 0.3),
]

BLUE_FACTORS = [
    ('历史频率', factor_historical_frequency, 1.0),
    ('近期热度', factor_recent_frequency, 1.5),
    ('间隔百分位', factor_interval_percentile, 0.3),
    ('重号', factor_repeat, 1.5),
    ('邻号', factor_neighbor, 1.0),
]


# ============================================================
# 核心评分函数
# ============================================================

def score_number(num, draws, last_reds, last_blue, is_red=True):
    """对一个号码计算综合评分 = Σ(因子_i × 权重_i)"""
    factors = RED_FACTORS if is_red else BLUE_FACTORS
    total_score = 0
    details = {}
    
    for name, func, weight in factors:
        try:
            raw_score = func(num, draws, last_reds, last_blue)
            weighted = raw_score * weight
            total_score += weighted
            details[name] = {'raw': round(raw_score, 3), 'weight': weight, 'weighted': round(weighted, 3)}
        except Exception as e:
            details[name] = {'raw': 0, 'weight': weight, 'weighted': 0, 'error': str(e)}
    
    return total_score, details


def score_all(draws):
    """给所有33红+16蓝评分，返回(红球得分列表, 蓝球得分列表)"""
    if len(draws) < 10:
        return [], []
    
    last = draws[-1]
    last_reds = [last['red1'], last['red2'], last['red3'],
                 last['red4'], last['red5'], last['red6']]
    last_blue = last['blue']
    
    # 预计算关联断裂数据
    window = 100
    older = draws[:-window] if len(draws) > window else draws
    recent = draws[-window:] if len(draws) > window else draws
    corr_old_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in older]
    corr_recent_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in recent]
    
    red_scores = []
    for r in range(1, 34):
        score, details = score_number(r, draws, last_reds, last_blue, is_red=True)
        # 用预计算的关联断裂覆盖
        cb = factor_correlation_break(r, draws, last_reds, last_blue, corr_old_sets, corr_recent_sets)
        if '关联断裂' in details:
            old_cb_weighted = details['关联断裂'].get('weighted', 0)
            new_cb_weighted = cb * 1.0
            score = score - old_cb_weighted + new_cb_weighted
            details['关联断裂'] = {'raw': round(cb, 3), 'weight': 1.0, 'weighted': round(new_cb_weighted, 3)}
        red_scores.append((r, score, details))
    
    blue_scores = []
    for b in range(1, 17):
        score, details = score_number(b, draws, last_reds, last_blue, is_red=False)
        blue_scores.append((b, score, details))
    
    return red_scores, blue_scores


# ============================================================
# 选号：TOP8高分中选最佳组合
# ============================================================

def select_numbers(red_scores, blue_scores, draws=None):
    """
    从评分中选出最优的6红+1蓝
    策略：TOP8高分中枚举C(8,6)=28种组合，选评分+分布最优的
    """
    if not red_scores or not blue_scores:
        return None
    
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    
    top8 = [r[0] for r in reds_sorted[:8]]
    
    best_reds = None
    best_total = -999
    
    for combo in combinations(top8, 6):
        c_sum = sum(combo)
        c_odd = sum(1 for n in combo if n % 2 == 1)
        c_span = max(combo) - min(combo)
        
        # 评分分 = 9个因子总分
        score_sum = sum(r[1] for r in reds_sorted if r[0] in combo)
        
        # 分布分：跨度20-28加分，奇偶2-4加分，和值85-125加分
        span_score = 1.0 if 20 <= c_span <= 28 else (0.5 if c_span >= 15 else 0)
        odd_score = 1.0 if 2 <= c_odd <= 4 else 0
        sum_score = 0.5 if 85 <= c_sum <= 125 else 0
        
        total = score_sum + span_score + odd_score + sum_score
        
        if total > best_total:
            best_total = total
            best_reds = sorted(combo)
    
    best_blue = blues_sorted[0][0]
    
    return best_reds + [best_blue]


# ============================================================
# 使用示例（需要数据库）
# ============================================================
if __name__ == '__main__':
    print("评分卡模型 v2.0")
    print("=" * 40)
    print("9个红球因子（含权重）：")
    for name, _, w in RED_FACTORS:
        print(f"  {name} × {w}")
    print()
    print("5个蓝球因子：")
    for name, _, w in BLUE_FACTORS:
        print(f"  {name} × {w}")
    print()
    print("选号策略：TOP8 → C(8,6) → 评分+分布优化")
    print()
    
    # 如果需要完整运行，取消下面的注释
    # from database import init_db, get_all_draws
    # init_db()
    # draws = get_all_draws()
    # red_scores, blue_scores = score_all(draws)
    # nums = select_numbers(red_scores, blue_scores, draws)
    # print(f"推荐号码: {nums[:6]} + {nums[6]}")
