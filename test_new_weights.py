#!/usr/bin/env python3
"""验证新权重下的回测效果"""
from database import get_all_draws, init_db
from scorecard import score_all, select_numbers
import numpy as np

init_db()
draws = get_all_draws()

for periods in [50, 100, 200]:
    test = draws[-periods:]
    train = draws[:-periods]
    hits = []
    blue_hits = []
    hit_dist = {6:0,5:0,4:0,3:0,2:0,1:0,0:0}
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50:
            continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        rs, bs = score_all(t)
        pred = select_numbers(rs, bs, t)
        if not pred:
            continue
        h = len(set(pred[:6]) & ar)
        bh = 1 if pred[6] == actual['blue'] else 0
        hits.append(h)
        blue_hits.append(bh)
        hit_dist[h] = hit_dist.get(h, 0) + 1
    
    n = len(hits)
    avg = np.mean(hits) if hits else 0
    r3 = sum(1 for h in hits if h>=3)/n*100 if n else 0
    r4 = sum(1 for h in hits if h>=4)/n*100 if n else 0
    blue = sum(blue_hits)/n*100 if n else 0
    prize = (sum(1 for h in hits if h>=3) + sum(blue_hits))/n*100 if n else 0
    
    print(f"--- 最近{periods}期 ---")
    print(f"平均红球: {avg:.3f} (随机: {6*6/33:.3f})  Δ{avg-6*6/33:+.3f}")
    print(f"3+红: {r3:.1f}%  4+红: {r4:.1f}%  蓝球: {blue:.1f}%  中奖率: {prize:.1f}%")
    print(f"命中分布: {dict(sorted(hit_dist.items()))}")
    print()
