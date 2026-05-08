#!/usr/bin/env python3
"""精简版策略回测 - v2"""
from database import get_all_draws, init_db
from scorecard import score_all
import numpy as np
import random
from itertools import combinations

random.seed(42)
init_db()
draws = get_all_draws()

def eval_strategy(name, get_pred):
    print(f"--- {name} ---")
    for periods in [50, 100]:
        test = draws[-periods:]
        train = draws[:-periods]
        hits = []
        for i in range(1, len(test)):
            t = train + test[:i]
            if len(t) < 50: continue
            actual = test[i]
            ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
            rs, bs = score_all(t)
            pred = get_pred(rs, bs, t)
            if not pred: continue
            hits.append(len(set(pred[:6]) & ar))
        n = len(hits)
        avg = np.mean(hits) if hits else 0
        r3 = sum(1 for h in hits if h>=3)/n*100 if n else 0
        print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%  (随机: {6*6/33:.3f})")
    print()

# ====== 策略定义 ======

def strat_top6(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    return sorted([r[0] for r in sr[:6]]) + [sb[0][0]]

eval_strategy("前6高分", strat_top6)

# 策略2: 蓝球从TOP3中概率选
def strat_blue_prob(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    top3 = sb[:3]
    scores = [max(b[1], 0.01) for b in top3]
    total = sum(scores)
    probs = [s/total for s in scores]
    idx = np.random.choice(range(len(top3)), p=probs)
    return sorted([r[0] for r in sr[:6]]) + [top3[idx][0]]

eval_strategy("前6+蓝球TOP3概率", strat_blue_prob)

# 策略3: 从TOP10中选历史拟合最好的组合
def strat_hist_fit(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    top10 = [r[0] for r in sr[:10]]
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    
    last50 = t[-50:] if len(t) >= 50 else t
    hist_sums = [sum(sorted([d[f'red{i}'] for i in range(1,7)])) for d in last50]
    hist_odds = [sum(1 for i in range(1,7) if d[f'red{i}'] % 2 == 1) for d in last50]
    hist_spans = [sorted([d[f'red{i}'] for i in range(1,7)])[-1] - sorted([d[f'red{i}'] for i in range(1,7)])[0] for d in last50]
    
    avg_sum = np.mean(hist_sums)
    avg_odd = np.mean(hist_odds)
    avg_span = np.mean(hist_spans)
    
    best_combo = None
    best_fit = -999
    
    for combo in combinations(top10, 6):
        c_sum = sum(combo)
        c_odd = sum(1 for n in combo if n % 2 == 1)
        c_span = max(combo) - min(combo)
        fit = -abs(c_sum - avg_sum)/10 - abs(c_odd - avg_odd)*2 - abs(c_span - avg_span)/5
        if fit > best_fit:
            best_fit = fit
            best_combo = combo
    
    return sorted(best_combo) + [best_blue] if best_combo else strat_top6(rs, bs, t)

eval_strategy("TOP10历史拟合", strat_hist_fit)

# 策略4: 前8高分 + 2个补号（从后22个里选评分最高且不破坏分布的）
def strat_8plus2(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    
    top8 = [r[0] for r in sr[:8]]
    rest = [r[0] for r in sr[8:] if r[0] not in top8]
    
    # 从top8选6个：去掉2个最破坏分布的
    best_combo = None
    best_score = -999
    
    for combo in combinations(top8, 6):
        c_sum = sum(combo)
        c_odd = sum(1 for n in combo if n % 2 == 1)
        c_span = max(combo) - min(combo)
        
        # 评分 = 综合评分 + 分布分
        score = sum(r[1] for r in sr if r[0] in combo)
        dist = 0
        if 20 <= c_span <= 28: dist += 1
        if 2 <= c_odd <= 4: dist += 1
        if 85 <= c_sum <= 125: dist += 0.5
        
        total = score + dist
        if total > best_score:
            best_score = total
            best_combo = combo
    
    return sorted(best_combo) + [best_blue] if best_combo else strat_top6(rs, bs, t)

eval_strategy("TOP8选最佳组合", strat_8plus2)

# 策略5: 前6高分但做微调 - 如果前6有3个同区间，换一个
def strat_adjusted(rs, bs, t):
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    
    top10 = [r[0] for r in sr[:10]]
    base = list(sr[:6])
    base_nums = [r[0] for r in base]
    
    # 检查分布
    zones = [1 if n <= 11 else (2 if n <= 22 else 3) for n in base_nums]
    from collections import Counter
    zone_counts = Counter(zones)
    
    combo = list(base_nums)
    # 如果有区间有4个或以上，换掉评分最低的那个
    for z, count in zone_counts.items():
        if count >= 4:
            zone_nums = [n for i, n in enumerate(base_nums) if zones[i] == z]
            worst = min(zone_nums, key=lambda x: sum(r[1] for r in sr if r[0] == x))
            # 找其他区间的补号
            for r, s, d in sr[6:]:
                if r not in combo:
                    z2 = 1 if r <= 11 else (2 if r <= 22 else 3)
                    if z2 != z:
                        combo[combo.index(worst)] = r
                        break
    
    return sorted(combo) + [best_blue]

eval_strategy("前6高分+区间调整", strat_adjusted)

# 策略6: 多注合并（跑3个不同策略，合并评分最高分）
def strat_ensemble(rs, bs, t):
    """三注投票：每个号被选中的次数"""
    votes = {r: 0 for r in range(1, 34)}
    
    # 注1: 前6高分
    sr = sorted(rs, key=lambda x: x[1], reverse=True)
    for r, s, d in sr[:6]:
        votes[r[0]] += 3
    
    # 注2: TOP10历史拟合
    top10 = [r[0] for r in sr[:10]]
    last50 = t[-50:] if len(t) >= 50 else t
    avg_sum = np.mean([sum(sorted([d[f'red{i}'] for i in range(1,7)])) for d in last50])
    avg_odd = np.mean([sum(1 for i in range(1,7) if d[f'red{i}'] % 2 == 1) for d in last50])
    
    best_fit = -999
    best_combo2 = None
    for combo in combinations(top10, 6):
        fit = -abs(sum(combo)-avg_sum)/10 - abs(sum(1 for n in combo if n%2==1)-avg_odd)*2
        if fit > best_fit:
            best_fit = fit
            best_combo2 = combo
    for n in (best_combo2 or []):
        votes[n] += 2
    
    # 注3: 评分+分布均衡
    sorted_by_vote = sorted(votes.items(), key=lambda x: x[1], reverse=True)
    
    sb = sorted(bs, key=lambda x: x[1], reverse=True)
    best_blue = sb[0][0]
    return sorted([n for n, v in sorted_by_vote[:6]]) + [best_blue]

eval_strategy("三注投票融合", strat_ensemble)

print(f"随机期望: avg_red={6*6/33:.3f}  3+≈11.5%  蓝球=6.2%")
