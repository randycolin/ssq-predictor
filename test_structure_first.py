#!/usr/bin/env python3
"""测试结构优先的选号策略"""
from database import get_all_draws, init_db
from scorecard import score_all, score_number, RED_FACTORS
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

# ================================================================
# 结构优先选号
# 先定结构，再从符合结构的组合中挑评分高的
# ================================================================

# 高概率结构模板（来自3447期真实数据）
STRUCTURE_TEMPLATES = [
    # (和值范围, 奇偶范围, 跨度范围, 连号范围, 三区模板)
    # 2:2:2 是最常见的
    ((90, 110), (2, 4), (20, 28), (0, 2), (2, 2, 2)),
    ((90, 110), (2, 4), (20, 28), (0, 1), (3, 2, 1)),
    ((90, 110), (2, 4), (20, 28), (0, 1), (2, 3, 1)),
    ((90, 110), (2, 4), (20, 28), (0, 1), (1, 3, 2)),
    ((90, 110), (2, 4), (20, 28), (0, 1), (1, 2, 3)),
    ((80, 90), (3, 5), (20, 28), (0, 2), (2, 2, 2)),
    ((110, 120), (1, 3), (22, 30), (0, 2), (2, 2, 2)),
    # 和值偏移但结构合理的
    ((80, 100), (3, 5), (18, 26), (0, 2), (3, 1, 2)),
    ((100, 120), (2, 4), (22, 30), (0, 2), (1, 3, 2)),
    ((95, 115), (2, 4), (24, 30), (0, 1), (2, 1, 3)),
]


def check_structure(reds, template):
    """检查一组号码是否符合结构模板"""
    sum_lo, sum_hi = template[0]
    odd_lo, odd_hi = template[1]
    span_lo, span_hi = template[2]
    cons_lo, cons_hi = template[3]
    z1, z2, z3 = template[4]
    
    c_sum = sum(reds)
    if not (sum_lo <= c_sum <= sum_hi):
        return False
    
    c_odd = sum(1 for n in reds if n % 2 == 1)
    if not (odd_lo <= c_odd <= odd_hi):
        return False
    
    c_span = max(reds) - min(reds)
    if not (span_lo <= c_span <= span_hi):
        return False
    
    gaps = [reds[i+1] - reds[i] for i in range(5)]
    c_cons = sum(1 for g in gaps if g == 1)
    if not (cons_lo <= c_cons <= cons_hi):
        return False
    
    low = sum(1 for n in reds if n <= 11)
    mid = sum(1 for n in reds if 12 <= n <= 22)
    high = sum(1 for n in reds if n >= 23)
    if not (low == z1 and mid == z2 and high == z3):
        return False
    
    return True


def select_numbers_structure_first(red_scores, blue_scores, draws=None):
    """
    结构优先选号：
    1. 从评分TOP20中枚举组合
    2. 先检查是否符合常见结构模板
    3. 符合的里面挑评分最高的
    """
    if not red_scores or not blue_scores:
        return None
    
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    
    # 从TOP20中枚举
    top20 = [r[0] for r in reds_sorted[:20]]
    
    best_reds = None
    best_score = -999
    best_template_idx = -1
    
    for combo in combinations(top20, 6):
        # 检查是否符任何结构模板
        for tidx, tmpl in enumerate(STRUCTURE_TEMPLATES):
            if check_structure(combo, tmpl):
                # 评分分 = 因子总分
                score = sum(r[1] for r in reds_sorted if r[0] in combo)
                if score > best_score:
                    best_score = score
                    best_reds = sorted(combo)
                    best_template_idx = tidx
                break  # 一个组合只需匹配一个模板
    
    # 如果没找到任何符合结构的，回退到当前TOP8
    if best_reds is None:
        # fallback: TOP8最佳
        top8 = [r[0] for r in reds_sorted[:8]]
        for combo in combinations(top8, 6):
            c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
            score = sum(r[1] for r in reds_sorted if r[0] in combo)
            d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
            if score+d > best_score:
                best_score = score+d
                best_reds = sorted(combo)
    
    best_blue = blues_sorted[0][0]
    return best_reds + [best_blue]


# ============ 对照：当前TOP8 ============
def select_numbers_current(red_scores, blue_scores, draws=None):
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    top8 = [r[0] for r in reds_sorted[:8]]
    best = None; best_s = -999
    for combo in combinations(top8, 6):
        c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
        sc = sum(r[1] for r in reds_sorted if r[0] in combo)
        d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
        if sc+d > best_s: best_s, best = sc+d, sorted(combo)
    return best + [blues_sorted[0][0]]


# ============ 回测 ============
def backtest(selector, label):
    print(f"--- {label} ---")
    for periods in [50, 100, 200]:
        test = draws[-periods:]
        train = draws[:-periods]
        hits = []
        blue_hits = []
        hit_dist = {6:0,5:0,4:0,3:0,2:0,1:0,0:0}
        struct_fit = 0  # 命中结构的次数
        
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
            
            # 检查结构是否符合真实开奖
            actual_reds = sorted([actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']])
            actual_sum = sum(actual_reds)
            actual_odd = sum(1 for n in actual_reds if n%2==1)
            actual_span = max(actual_reds)-min(actual_reds)
            actual_low = sum(1 for n in actual_reds if n<=11)
            actual_mid = sum(1 for n in actual_reds if 12<=n<=22)
            actual_high = sum(1 for n in actual_reds if n>=23)
            if 80 <= actual_sum <= 130 and 2 <= actual_odd <= 4 and 18 <= actual_span <= 30:
                struct_fit += 1
        
        n = len(hits)
        avg = np.mean(hits)
        r3 = sum(1 for h in hits if h>=3)/n*100
        r4 = sum(1 for h in hits if h>=4)/n*100
        blue = sum(blue_hits)/n*100
        prize = sum(1 for h,b in zip(hits,blue_hits) if b or h>=3)/n*100
        
        print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%  4+={r4:.1f}%  blue={blue:.1f}%  中奖={prize:.1f}%  Δ{avg-6*6/33:+.3f}")
        dist_str = ", ".join(f"{k}红:{v}" for k,v in sorted(hit_dist.items()))
        print(f"    分布: {dist_str}")
    print()


backtest(select_numbers_current, "当前TOP8（对照）")
backtest(select_numbers_structure_first, "结构优先（新方案）")

print(f"随机期望: avg_red={6*6/33:.3f}  blue={100/16:.1f}%")
