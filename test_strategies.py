#!/usr/bin/env python3
"""
尝试多种选号策略，找最优方案
"""
from database import get_all_draws, init_db
from scorecard import score_all, score_number, RED_FACTORS
import numpy as np
import random
from copy import deepcopy

init_db()
draws = get_all_draws()

def evaluate_strategy(strategy_name, selector_func):
    """回测一种选号策略"""
    results = []
    for periods in [50, 100, 200]:
        test = draws[-periods:]
        train = draws[:-periods]
        hits = []
        
        for i in range(1, len(test)):
            t = train + test[:i]
            if len(t) < 50: continue
            actual = test[i]
            ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
            rs, bs = score_all(t)
            pred = selector_func(rs, bs, t)
            if not pred: continue
            h = len(set(pred[:6]) & ar)
            hits.append(h)
        
        n = len(hits)
        avg = np.mean(hits) if hits else 0
        r3 = sum(1 for h in hits if h>=3)/n*100 if n else 0
        r4 = sum(1 for h in hits if h>=4)/n*100 if n else 0
        results.append((periods, avg, r3, r4))
    return results

# ============ 各种选号策略 ============

# 策略1: 前6高分（基准）
def select_top6(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    pred = [r[0] for r in sr[:6]]
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    return sorted(pred) + [sb[0][0]]

# 策略2: TOP10中按历史分布采样（加权随机）
def select_weighted_random(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    top10 = sr[:10]
    
    # 加权随机：评分越高概率越大
    scores = [max(r[1], 0) for r in top10]
    total = sum(scores)
    probs = [s/total for s in scores]
    
    # 采样6个不重复
    indices = list(range(len(top10)))
    chosen = set()
    while len(chosen) < 6 and len(indices) >= 6:
        idx = np.random.choice(indices, p=probs)
        chosen.add(top10[idx][0])
        # 动态调整采样集
        remaining = [i for i in indices if top10[i][0] not in chosen]
        if len(remaining) < 6 - len(chosen):
            break
        indices = remaining
        if len(remaining) > 0:
            remaining_scores = [max(top10[i][1], 0) for i in remaining]
            t2 = sum(remaining_scores)
            probs = [s/t2 for s in remaining_scores] if t2 > 0 else [1/len(remaining)]*len(remaining)
    
    # 补全
    while len(chosen) < 6:
        for r, s, d in sr:
            if r not in chosen:
                chosen.add(r)
                if len(chosen) >= 6:
                    break
    
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    return sorted(list(chosen)[:6]) + [sb[0][0]]

# 策略3: TOP15中选最优组合（蒙特卡洛采样）
def select_monte_carlo(rs, bs, t, samples=5000):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    top15 = [r[0] for r in sr[:15]]
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    
    # 评分字典
    score_dict = {r: s for r, s, d in sr[:15]}
    
    # 蒙特卡洛采样：随机选6个，评估组合质量
    best_combo = None
    best_quality = -999
    
    for _ in range(samples):
        combo = sorted(random.sample(top15, 6))
        
        # 质量分 = 平均评分 * 0.7 + 分布分 * 0.3
        avg_score = np.mean([score_dict.get(n, 0) for n in combo])
        
        span = combo[-1] - combo[0]
        span_score = 1.0 if 18 <= span <= 28 else (0.5 if span >= 12 else 0)
        
        odd_count = sum(1 for n in combo if n % 2 == 1)
        odd_score = 1.0 - abs(odd_count - 3) / 3
        
        gap1 = sum(1 for i in range(5) if combo[i+1] - combo[i] == 1)
        gap_score = 1.0 if gap1 <= 2 else (0.5 if gap1 <= 3 else 0)
        
        quality = avg_score * 0.5 + span_score * 0.2 + odd_score * 0.15 + gap_score * 0.15
        if quality > best_quality:
            best_quality = quality
            best_combo = combo
    
    return best_combo + [best_blue] if best_combo else select_top6(rs, bs, t)

# 策略4: 前6高分，但蓝球改成概率选（不总是最高分）
def select_top6_with_blue_probs(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    pred = [r[0] for r in sr[:6]]
    
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    bs_scores = [max(b[1], 0) for b in sb[:5]]
    total = sum(bs_scores)
    if total > 0:
        probs = [s/total for s in bs_scores]
        blue_idx = np.random.choice(range(min(5, len(sb))), p=probs)
    else:
        blue_idx = 0
    
    return sorted(pred) + [sb[blue_idx][0]]

# 策略5: 综合性最强 — TOP15蒙特卡洛 + 历史分布拟合
def select_historical_fit(rs, bs, t):
    """选出的号码组合要跟历史分布最像"""
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    top15 = [r[0] for r in sr[:15]]
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    
    # 历史统计：和值、奇偶、区间分布
    last_100 = t[-100:] if len(t) >= 100 else t
    hist_sums = []
    hist_odds = []
    hist_spans = []
    hist_gap1 = []
    for d in last_100:
        reds = sorted([d[f'red{i}'] for i in range(1,7)])
        hist_sums.append(sum(reds))
        hist_odds.append(sum(1 for n in reds if n % 2 == 1))
        hist_spans.append(reds[-1] - reds[0])
        hist_gap1.append(sum(1 for i in range(5) if reds[i+1]-reds[i]==1))
    
    avg_sum = np.mean(hist_sums) if hist_sums else 102
    avg_odd = np.mean(hist_odds) if hist_odds else 3
    avg_span = np.mean(hist_spans) if hist_spans else 25
    avg_gap1 = np.mean(hist_gap1) if hist_gap1 else 1.5
    
    score_dict = {r: s for r, s, d in sr[:15]}
    
    best_combo = None
    best_fit = -999
    
    for _ in range(200):
        combo = sorted(random.sample(top15, 6))
        
        c_sum = sum(combo)
        c_odd = sum(1 for n in combo if n % 2 == 1)
        c_span = combo[-1] - combo[0]
        c_gap1 = sum(1 for i in range(5) if combo[i+1]-combo[i]==1)
        
        # 拟合度：越接近历史平均越好
        sum_fit = -abs(c_sum - avg_sum) / avg_sum * 100
        odd_fit = -abs(c_odd - avg_odd)
        span_fit = -abs(c_span - avg_span) / avg_span * 100
        gap_fit = -abs(c_gap1 - avg_gap1)
        
        # 评分分
        avg_score = np.mean([score_dict.get(n, 0) for n in combo])
        
        total_fit = avg_score * 3 + sum_fit + odd_fit * 2 + span_fit + gap_fit * 2
        if total_fit > best_fit:
            best_fit = total_fit
            best_combo = combo
    
    return best_combo + [best_blue] if best_combo else select_top6(rs, bs, t)


# ============ 跑回测 ============
strategies = [
    ("前6高分（基准）", select_top6),
    ("TOP10加权随机", select_weighted_random),
    ("TOP15蒙特卡洛", select_monte_carlo),
    ("TOP6+蓝球概率", select_top6_with_blue_probs),
    ("历史分布拟合", select_historical_fit),
]

print(f"{'策略':>20} {'50期':>18} {'100期':>18} {'200期':>18}")
print(f"{'':>20} {'avg_r3%':>8} {'avg_r4%':>8} {'avg_r3%':>8} {'avg_r4%':>8} {'avg_r3%':>8} {'avg_r4%':>8}")
print("-" * 80)

for name, func in strategies:
    res = evaluate_strategy(name, func)
    vals = []
    for periods, avg, r3, r4 in res:
        vals.extend([avg, r3, r4])
    print(f"{name:>16}  {vals[0]:6.3f} {vals[1]:6.1f}% {vals[2]:6.1f}%  {vals[3]:6.3f} {vals[4]:6.1f}% {vals[5]:6.1f}%  {vals[6]:6.3f} {vals[7]:6.1f}% {vals[8]:6.1f}%")

print(f"\n随机期望: avg_red={6*6/33:.3f}  3+≈11.5%  蓝球=6.2%")
