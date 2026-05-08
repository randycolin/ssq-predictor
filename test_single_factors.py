#!/usr/bin/env python3
"""单因子回测：挨个看哪些因子有用"""
from database import get_all_draws, init_db
import numpy as np

def test_single_factor(draws, factor_func, factor_name, weight=1.0, is_red=True):
    test = draws[-100:]
    train = draws[:-100]
    hits = []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50:
            continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        last = t[-1]
        lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
        lb = last['blue']
        
        scores = []
        for r in range(1, 34):
            raw = factor_func(r, t, lr, lb)
            scores.append((r, raw * weight))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        pred = sorted([s[0] for s in scores[:6]])
        hit = len(set(pred) & ar)
        hits.append(hit)
    
    return np.mean(hits), sum(1 for h in hits if h>=3)/len(hits)*100

init_db()
draws = get_all_draws()
print(f"总期数: {len(draws)}")
print()

from scorecard import (
    factor_historical_frequency, factor_recent_frequency,
    factor_interval_percentile, factor_correlation_break,
    factor_repeat, factor_neighbor
)

factors = [
    ("历史频率", factor_historical_frequency, 1.0),
    ("近期热度", factor_recent_frequency, 1.0),
    ("间隔百分位", factor_interval_percentile, 1.0),
    ("关联断裂", factor_correlation_break, 1.0),
    ("重号", factor_repeat, 1.0),
    ("邻号", factor_neighbor, 1.0),
]

print("单因子回测(最近100期):")
print(f"{'因子':>8}  {'avg_red':>8}  {'3+%':>8}")
print("-" * 30)
random_avg = 6*6/33
random_3p = 11.5
print(f"{'随机':>8}  {random_avg:>8.3f}  {random_3p:>8.1f}%")
print()

for name, func, w in factors:
    avg, r3 = test_single_factor(draws, func, name, w)
    diff = avg - random_avg
    mark = "📈" if diff > 0.03 else "📉" if diff < -0.03 else "➡️"
    print(f"{mark} {name:>6}:  {avg:>8.3f}  {r3:>8.1f}%  (Δ{diff:+.3f})")

# 最佳组合搜索：去掉表现差的因子
print()
print("--- 最佳组合尝试 ---")
print("(去掉重号 & 降低间隔权重)")
test = draws[-100:]
train = draws[:-100]
hits = []

for i in range(1, len(test)):
    t = train + test[:i]
    if len(t) < 50:
        continue
    actual = test[i]
    ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
    last = t[-1]
    lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
    lb = last['blue']
    
    scores = []
    for r in range(1, 34):
        # 均衡权重组合
        score = 0
        score += factor_historical_frequency(r, t, lr, lb) * 1.0
        score += factor_recent_frequency(r, t, lr, lb) * 1.0
        score += factor_interval_percentile(r, t, lr, lb) * 0.5  # 降权
        score += factor_correlation_break(r, t, lr, lb) * 1.0
        score += factor_neighbor(r, t, lr, lb) * 0.5
        scores.append((r, score))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    pred = sorted([s[0] for s in scores[:6]])
    hit = len(set(pred) & ar)
    hits.append(hit)

avg_best = np.mean(hits) if hits else 0
r3_best = sum(1 for h in hits if h>=3)/len(hits)*100 if hits else 0
print(f"组合(均衡): avg_red={avg_best:.3f}  3+={r3_best:.1f}%  (Δ{avg_best-random_avg:+.3f})")
print(f"随机期望:    avg_red={random_avg:.3f}  3+={random_3p:.1f}%")
