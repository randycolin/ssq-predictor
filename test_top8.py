#!/usr/bin/env python3
"""验证TOP8选最佳组合的稳定性"""
from database import get_all_draws, init_db
from scorecard import score_all
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

def top8_best(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    top8 = [r[0] for r in sr[:8]]
    
    best_combo = None
    best_score = -999
    
    for combo in combinations(top8, 6):
        c_sum = sum(combo)
        c_odd = sum(1 for n in combo if n % 2 == 1)
        c_span = max(combo) - min(combo)
        
        score = sum(r[1] for r in sr if r[0] in combo)
        dist = 0
        if 20 <= c_span <= 28: dist += 1
        if 2 <= c_odd <= 4: dist += 1
        if 85 <= c_sum <= 125: dist += 0.5
        
        if score + dist > best_score:
            best_score = score + dist
            best_combo = combo
    
    return sorted(best_combo) + [best_blue]

# 跑多次看波动
print("TOP8最佳组合 - 多次回测:")
print(f"{'期数':>6} {'avg_red':>8} {'3+%':>8} {'4+%':>8}")
print("-" * 35)

for periods in [20, 30, 50, 100, 150, 200]:
    test = draws[-periods:]
    train = draws[:-periods]
    hits = []
    blue_hits = []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50: continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        rs, bs = score_all(t)
        pred = top8_best(rs, bs, t)
        if not pred: continue
        h = len(set(pred[:6]) & ar)
        hits.append(h)
        blue_hits.append(1 if pred[6] == actual['blue'] else 0)
    
    n = len(hits)
    avg = np.mean(hits)
    r3 = sum(1 for h in hits if h>=3)/n*100
    r4 = sum(1 for h in hits if h>=4)/n*100
    blue = sum(blue_hits)/n*100
    print(f"{periods:>6} {avg:>8.3f} {r3:>8.1f}% {r4:>8.1f}%")
    print(f"  {'↑随机:':>6} {6*6/33:>8.3f} {11.5:>8.1f}% {1.1:>8.1f}%")
    print(f"  {'蓝球:':>6} {blue:>8.1f}% {'(随机6.2%)':>12}")
    print()

# 跟当前select_numbers对比
def current_select(rs, bs, t):
    from scorecard import select_numbers
    return select_numbers(rs, bs, t)

print("对照: 当前select_numbers:")
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
        pred = current_select(rs, bs, t)
        if not pred: continue
        hits.append(len(set(pred[:6]) & ar))
    n = len(hits)
    avg = np.mean(hits)
    r3 = sum(1 for h in hits if h>=3)/n*100
    print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%")
