#!/usr/bin/env python3
"""精简版提升策略测试"""
from database import get_all_draws, init_db
from scorecard import score_all
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

def eval_strategy(name, get_pred):
    for periods in [100]:
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
            pred = get_pred(rs, bs, t)
            if not pred: continue
            h = len(set(pred[:6]) & ar)
            hits.append(h)
            blue_hits.append(1 if pred[6] == actual['blue'] else 0)
        n = len(hits)
        avg = np.mean(hits)
        r3 = sum(1 for h in hits if h>=3)/n*100
        r4 = sum(1 for h in hits if h>=4)/n*100
        blue = sum(blue_hits)/n*100
        print(f"  {name:>16}: {periods}期 avg={avg:.3f} 3+={r3:.1f}% 4+={r4:.1f}% blue={blue:.1f}% Δ{avg-6*6/33:+.3f}")

# 基准
def baseline(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    top8 = [r[0] for r in sr[:8]]
    best = None
    best_s = -999
    for combo in combinations(top8, 6):
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        sc = sum(r[1] for r in sr if r[0] in combo)
        d = (1 if 20<=c_span<=28 else 0) + (1 if 2<=c_odd<=4 else 0) + (0.5 if 85<=c_sum<=125 else 0)
        if sc+d > best_s:
            best_s = sc+d
            best = sorted(combo)
    return best + [sb[0][0]]

eval_strategy("当前(TOP8)", baseline)

# 策略1: 前6高分（最简单方案）
def top6(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    return sorted([r[0] for r in sr[:6]]) + [sb[0][0]]
eval_strategy("前6高分", top6)

# 策略2: 动态蓝球 — 近20期热门蓝球
def blue_hot(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    top8 = [r[0] for r in sr[:8]]
    best = None
    best_s = -999
    for combo in combinations(top8, 6):
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        sc = sum(r[1] for r in sr if r[0] in combo)
        d = (1 if 20<=c_span<=28 else 0) + (1 if 2<=c_odd<=4 else 0) + (0.5 if 85<=c_sum<=125 else 0)
        if sc+d > best_s:
            best_s = sc+d
            best = sorted(combo)
    
    # 蓝球: 近30期热号
    last30 = t[-30:] if len(t)>=30 else t
    bc = {}
    for d in last30:
        bc[d['blue']] = bc.get(d['blue'],0)+1
    best_blue = sorted(bc.items(), key=lambda x:x[1], reverse=True)[0][0]
    return best + [best_blue]
eval_strategy("动态蓝球热号", blue_hot)

# 策略3: 评分稍微加权随机 — 不固定取前8，从TOP15用概率采样
def prob_sample(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    
    import random
    random.seed(sum(draws[-1][f'red{i}'] for i in range(1,7)))  # 可复现
    
    top15 = [r[0] for r in sr[:15]]
    scores = [max(r[1], 0.01) for r in sr[:15]]
    total = sum(scores)
    probs = [s/total for s in scores]
    
    # TOP8里取4-5个，剩余从9-15里取
    best = None
    best_s = -999
    for _ in range(200):
        picked = set()
        # 从前8取4-5个
        n_from_top = random.choice([4,5])
        top_candidates = list(range(8))
        for idx in random.sample(top_candidates, n_from_top):
            picked.add(top15[idx])
        
        # 从9-15补到6个
        rest = [r for r in top15[8:] if r not in picked]
        while len(picked) < 6 and rest:
            idx = random.randint(0, len(rest)-1)
            picked.add(rest[idx])
            rest.pop(idx)
        
        if len(picked) < 6:
            continue
        
        combo = sorted(list(picked)[:6])
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        sc = sum(r[1] for r in sr if r[0] in combo)
        d = (1 if 20<=c_span<=28 else 0) + (1 if 2<=c_odd<=4 else 0) + (0.5 if 85<=c_sum<=125 else 0)
        if sc+d > best_s:
            best_s = sc+d
            best = combo
    return best + [sb[0][0]] if best else baseline(rs, bs, t)
eval_strategy("概率采样200次", prob_sample)

# 策略4: 6注覆盖（不对单注，但展示上限）
# 每注用不同方法，看看最佳单注能达到什么水平
def best_of_5(rs, bs, t):
    """跑5种不同选法取最好的"""
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    candidates = []
    
    # 1. TOP8最佳
    top8 = [r[0] for r in sr[:8]]
    best = None; best_s = -999
    for combo in combinations(top8, 6):
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        sc = sum(r[1] for r in sr if r[0] in combo)
        d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
        if sc+d > best_s: best_s, best = sc+d, sorted(combo)
    candidates.append(best + [sb[0][0]])
    
    # 2. 前6高分
    candidates.append(sorted([r[0] for r in sr[:6]]) + [sb[0][0]])
    
    # 3. 前6高分+不同蓝球
    last30 = t[-30:] if len(t)>=30 else t
    bc = {}
    for d in last30:
        bc[d['blue']] = bc.get(d['blue'],0)+1
    hot_blue = sorted(bc.items(), key=lambda x:x[1], reverse=True)[0][0]
    candidates.append(sorted([r[0] for r in sr[:6]]) + [hot_blue])
    
    # 4. 前8最佳 + 不同蓝球
    candidates.append(best + [hot_blue])
    
    # 返回第一个（单注预测不能多注）
    return candidates[0]

eval_strategy("5注最佳(上限)", best_of_5)

print(f"\n随机期望: avg_red={6*6/33:.3f}  blue={100/16:.1f}%")
