#!/usr/bin/env python3
"""对比新权重下：select_numbers vs 前6高分"""
from database import get_all_draws, init_db
from scorecard import score_all, select_numbers
import numpy as np

init_db()
draws = get_all_draws()

for strategy_name, use_select in [("select_numbers", True), ("前6高分", False)]:
    print(f"=== {strategy_name} ===")
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
            
            if use_select:
                pred = select_numbers(rs, bs, t)
            else:
                sr = sorted(rs, key=lambda x: x[1], reverse=True)
                pred = [r[0] for r in sr[:6]]
                sb = sorted(bs, key=lambda x: x[1], reverse=True)
                pred.append(sb[0][0])
            
            if not pred: continue
            h = len(set(pred[:6]) & ar)
            hits.append(h)
        
        n = len(hits)
        avg = np.mean(hits) if hits else 0
        r3 = sum(1 for h in hits if h>=3)/n*100 if n else 0
        r4 = sum(1 for h in hits if h>=4)/n*100 if n else 0
        print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%  4+={r4:.1f}%  Δ{avg-6*6/33:+.3f}")
    print()

# 结论
print("=" * 40)
print(f"随机期望: avg_red={6*6/33:.3f}")
