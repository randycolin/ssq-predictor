#!/usr/bin/env python3
"""对比AI因子 vs 老彩民因子的影响力"""
from database import get_all_draws, init_db
from scorecard import *
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

# ============ 定义不同的因子组合 ============

# 原方案（当前）
WEIGHTS_A = {
    '历史频率': 1.0, '近期热度': 1.5, '间隔百分位': 0.5,
    '关联断裂': 1.5, '重号': 1.5, '邻号': 0.5,
    '和值平衡': 0.5, '区间平衡': 0.5, '历史模式': 0.3
}

# AI增强（加大统计类）
WEIGHTS_B = {
    '历史频率': 2.0, '近期热度': 3.0, '间隔百分位': 1.0,
    '关联断裂': 2.0, '重号': 0.5, '邻号': 0.3,
    '和值平衡': 0.3, '区间平衡': 0.3, '历史模式': 0.3
}

# 老彩民增强（上面说的方案）
WEIGHTS_C = {
    '历史频率': 0.5, '近期热度': 1.0, '间隔百分位': 0.3,
    '关联断裂': 0.5, '重号': 3.0, '邻号': 2.0,
    '和值平衡': 2.0, '区间平衡': 1.5, '历史模式': 1.0
}

# 纯老彩民（去掉AI因子）
WEIGHTS_D = {
    '历史频率': 0.0, '近期热度': 0.0, '间隔百分位': 0.0,
    '关联断裂': 0.0, '重号': 3.0, '邻号': 2.0,
    '和值平衡': 2.0, '区间平衡': 1.5, '历史模式': 0.5
}

# 纯AI（去掉老彩民因子）
WEIGHTS_E = {
    '历史频率': 2.0, '近期热度': 3.0, '间隔百分位': 1.0,
    '关联断裂': 2.0, '重号': 0.0, '邻号': 0.0,
    '和值平衡': 0.0, '区间平衡': 0.0, '历史模式': 0.0
}

def backtest_with_weights(weights, label):
    """用指定权重回测"""
    test = draws[-100:]
    train = draws[:-100]
    hits = []
    blue_hits = []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50: continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        last = t[-1]
        lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
        lb = last['blue']
        
        # 用自定义权重评分
        red_scores = []
        for r in range(1, 34):
            score = 0
            for name, func, _ in RED_FACTORS:
                w = weights.get(name, 0)
                if w > 0:
                    raw = func(r, t, lr, lb)
                    score += raw * w
            red_scores.append((r, score, {}))
        
        blue_scores = []
        for b in range(1, 17):
            score = 0
            for name, func, _ in BLUE_FACTORS:
                w = weights.get(name, 0)
                if w > 0:
                    raw = func(b, t, lr, lb)
                    score += raw * w
            blue_scores.append((b, score))
        
        # TOP8选号
        sr = sorted(red_scores, key=lambda x: x[1], reverse=True)
        sb = sorted(blue_scores, key=lambda x: x[1], reverse=True)
        top8 = [r[0] for r in sr[:8]]
        best = None; best_s = -999
        for combo in combinations(top8, 6):
            c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
            sc = sum(r[1] for r in sr if r[0] in combo)
            d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
            if sc+d > best_s:
                best_s = sc+d
                best = sorted(combo)
        if not best:
            best = sorted([r[0] for r in sr[:6]])
        
        pred = best + [sb[0][0]]
        h = len(set(pred[:6]) & ar)
        hits.append(h)
        blue_hits.append(1 if pred[6] == actual['blue'] else 0)
    
    n = len(hits)
    avg = np.mean(hits)
    r3 = sum(1 for h in hits if h>=3)/n*100
    r4 = sum(1 for h in hits if h>=4)/n*100
    blue = sum(blue_hits)/n*100
    prize = sum(1 for h,b in zip(hits,blue_hits) if b or h>=3)/n*100
    
    print(f"{label:>16}:  avg={avg:.3f}  3+={r3:.1f}%  4+={r4:.1f}%  blue={blue:.1f}%  中奖={prize:.1f}%  Δ{avg-6*6/33:+.3f}")

print("各权重方案对比（100期回测）:")
print("-" * 70)
print(f"{'方案':>16}  {'avg':>8} {'3+%':>8} {'4+%':>8} {'蓝球%':>8} {'中奖%':>8} {'Δ随机':>8}")
print("-" * 70)

backtest_with_weights(WEIGHTS_A, "当前方案")
backtest_with_weights(WEIGHTS_B, "AI增强")
backtest_with_weights(WEIGHTS_C, "老彩民增强")
backtest_with_weights(WEIGHTS_D, "纯老彩民")
backtest_with_weights(WEIGHTS_E, "纯AI")

print("-" * 70)
print(f"{'随机期望':>16}:  {6*6/33:.3f}  11.5%   1.1%   6.2%   6.6%")
