#!/usr/bin/env python3
"""测试加入结构评分+反大众优化"""
from database import get_all_draws, init_db
from scorecard import score_all
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

# ============ 优化版select_numbers ============
def select_numbers_v2(red_scores, blue_scores, draws=None):
    """TOP8 + 结构评分 + 反大众"""
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
        
        # 评分分 = 因子总分
        score_sum = sum(r[1] for r in reds_sorted if r[0] in combo)
        
        # 分布分
        span_score = 1.0 if 20 <= c_span <= 28 else (0.5 if c_span >= 15 else 0)
        odd_score = 1.0 if 2 <= c_odd <= 4 else 0
        sum_score = 0.5 if 85 <= c_sum <= 125 else 0
        
        # 连号评分：1组连号常见，加分；3组以上扣分
        gaps = [combo[i+1] - combo[i] for i in range(5)]
        consecutive = sum(1 for g in gaps if g == 1)
        if consecutive == 1:
            cons_score = 0.5
        elif consecutive >= 3:
            cons_score = -1.5
        else:
            cons_score = 0
        
        # 反大众：全是生日号(≤31)扣分
        birthday_count = sum(1 for n in combo if n <= 31)
        anti_crowd = -1.0 if birthday_count == 6 else 0
        
        total = score_sum + span_score + odd_score + sum_score + cons_score + anti_crowd
        
        if total > best_total:
            best_total = total
            best_reds = sorted(combo)
    
    best_blue = blues_sorted[0][0]
    return best_reds + [best_blue]


# 当前版本（对照）
def select_numbers_v1(red_scores, blue_scores, draws=None):
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    top8 = [r[0] for r in reds_sorted[:8]]
    best_reds = None
    best_total = -999
    for combo in combinations(top8, 6):
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        score_sum = sum(r[1] for r in reds_sorted if r[0] in combo)
        span_score = 1.0 if 20 <= c_span <= 28 else (0.5 if c_span >= 15 else 0)
        odd_score = 1.0 if 2 <= c_odd <= 4 else 0
        sum_score = 0.5 if 85 <= c_sum <= 125 else 0
        if score_sum + span_score + odd_score + sum_score > best_total:
            best_total = score_sum + span_score + odd_score + sum_score
            best_reds = sorted(combo)
    return best_reds + [blues_sorted[0][0]]


# ============ 回测 ============
def backtest(selector, label):
    print(f"--- {label} ---")
    for periods in [50, 100, 200]:
        test = draws[-periods:]
        train = draws[:-periods]
        hits = []
        blue_hits = []
        hit_dist = {6:0,5:0,4:0,3:0,2:0,1:0,0:0}
        
        for i in range(1, len(test)):
            t = train + test[:i]
            if len(t) < 50: continue
            actual = test[i]
            ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
            rs, bs = score_all(t)
            pred = selector(rs, bs, t)
            if not pred: continue
            h = len(set(pred[:6]) & ar)
            hits.append(h)
            blue_hits.append(1 if pred[6] == actual['blue'] else 0)
            hit_dist[h] = hit_dist.get(h, 0) + 1
        
        n = len(hits)
        avg = np.mean(hits)
        r3 = sum(1 for h in hits if h>=3)/n*100
        r4 = sum(1 for h in hits if h>=4)/n*100
        blue = sum(blue_hits)/n*100
        prize = sum(1 for h,b in zip(hits,blue_hits) if b or h>=3)/n*100
        
        print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%  4+={r4:.1f}%  blue={blue:.1f}%  中奖={prize:.1f}%  Δ{avg-6*6/33:+.3f}")
        
        # 打印命中分布
        dist_str = ", ".join(f"{k}红:{v}" for k,v in sorted(hit_dist.items()))
        print(f"    分布: {dist_str}")
    print()

backtest(select_numbers_v1, "当前TOP8")
backtest(select_numbers_v2, "优化版(结构+反大众)")

print(f"随机期望: avg_red={6*6/33:.3f}  blue={100/16:.1f}%  中奖~6.6%")
