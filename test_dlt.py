#!/usr/bin/env python3
"""大乐透评分卡回测"""
from dlt_database import get_all_dlt_draws
from dlt_scorecard import dlt_score_all, dlt_select_numbers
import numpy as np
from itertools import combinations

draws = get_all_dlt_draws()
print(f"总计 {len(draws)} 期\n")

def backtest(periods=100):
    test = draws[-periods:]
    train = draws[:-periods]
    front_hits = []
    back_hits = []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50: continue
        
        actual = test[i]
        actual_fronts = {actual[f'front{j}'] for j in range(1, 6)}
        actual_backs = {actual[f'back{j}'] for j in range(1, 3)}
        
        fs, bs = dlt_score_all(t)
        best_f, best_b = dlt_select_numbers(fs, bs, t)
        
        if not best_f or not best_b:
            continue
        
        fh = len(set(best_f) & actual_fronts)
        bh = len(set(best_b) & actual_backs)
        front_hits.append(fh)
        back_hits.append(bh)
    
    n = len(front_hits)
    avg_f = np.mean(front_hits)
    avg_b = np.mean(back_hits)
    
    f3 = sum(1 for h in front_hits if h >= 3)/n*100
    f4 = sum(1 for h in front_hits if h >= 4)/n*100
    b2 = sum(1 for h in back_hits if h >= 2)/n*100
    b1 = sum(1 for h in back_hits if h >= 1)/n*100
    
    # 随机期望：前区35选5，平均命中5*5/35=0.714；后区12选2，平均命中2*2/12=0.333
    rand_f = 5 * 5 / 35
    rand_b = 2 * 2 / 12
    
    print(f"--- 大乐透回测（最近{periods}期）---")
    print(f"前区平均命中: {avg_f:.3f} (随机期望: {rand_f:.3f}) Δ{avg_f-rand_f:+.3f}")
    print(f"后区平均命中: {avg_b:.3f} (随机期望: {rand_b:.3f}) Δ{avg_b-rand_b:+.3f}")
    print(f"前区3+命中率: {f3:.1f}%")
    print(f"前区4+命中率: {f4:.1f}%")
    print(f"后区2+命中率(全中): {b2:.1f}%")
    print(f"后区1+命中率: {b1:.1f}%")

for p in [50, 100]:
    backtest(p)
    print()
