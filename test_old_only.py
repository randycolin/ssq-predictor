#!/usr/bin/env python3
"""纯老彩民方案 vs 当前方案 vs 纯AI"""
from database import get_all_draws, init_db
from scorecard import *
import numpy as np
from itertools import combinations

init_db()
draws = get_all_draws()

# ============ 各权重方案 ============

def backtest(weights_red, weights_blue, label):
    """用指定权重回测"""
    periods_list = [100]
    print(f"--- {label} ---")
    
    for periods in periods_list:
        test = draws[-periods:]
        train = draws[:-periods]
        hits = []
        blue_hits = []
        
        for i in range(1, len(test)):
            t = train + test[:i]
            if len(t) < 50: continue
            actual = test[i]
            ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
            ab = actual['blue']
            last = t[-1]
            lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
            lb = last['blue']
            
            # 评分
            red_scores = []
            for r in range(1, 34):
                score = 0
                for name, func, _ in RED_FACTORS:
                    w = weights_red.get(name, 0)
                    if w > 0:
                        raw = func(r, t, lr, lb)
                        score += raw * w
                red_scores.append((r, score, {}))
            
            blue_scores = []
            for b in range(1, 17):
                score = 0
                for name, func, _ in BLUE_FACTORS:
                    w = weights_blue.get(name, 0)
                    if w > 0:
                        raw = func(b, t, lr, lb)
                        score += raw * w
                blue_scores.append((b, score))
            
            # 用结构优先选号（复用scorecard里的select_numbers逻辑）
            sr = sorted(red_scores, key=lambda x: x[1], reverse=True)
            sb = sorted(blue_scores, key=lambda x: x[1], reverse=True)
            
            # 结构模板
            STRUCTURES = [
                ((90, 110), (2, 4), (20, 28), (2, 2, 2)),
                ((90, 110), (2, 4), (20, 28), (3, 2, 1)),
                ((90, 110), (2, 4), (20, 28), (2, 3, 1)),
                ((80, 100), (3, 5), (20, 28), (3, 1, 2)),
                ((100, 120), (2, 4), (22, 30), (1, 3, 2)),
                ((95, 115), (2, 4), (24, 30), (2, 1, 3)),
                ((80, 90),  (3, 5), (18, 26), (2, 2, 2)),
                ((110, 120), (1, 3), (24, 30), (2, 2, 2)),
            ]
            
            def match_structure(reds, tmpl):
                c_sum, c_odd, c_span = sum(reds), sum(1 for n in reds if n%2==1), max(reds)-min(reds)
                low, mid, high = sum(1 for n in reds if n<=11), sum(1 for n in reds if 12<=n<=22), sum(1 for n in reds if n>=23)
                return (tmpl[0][0]<=c_sum<=tmpl[0][1] and tmpl[1][0]<=c_odd<=tmpl[1][1] and 
                        tmpl[2][0]<=c_span<=tmpl[2][1] and low==tmpl[3][0] and mid==tmpl[3][1] and high==tmpl[3][2])
            
            top20 = [r[0] for r in sr[:20]]
            last_reds_set = set(lr)
            best = None; best_s = -999
            
            for combo in combinations(top20, 6):
                # 最多3个重号
                if len(set(combo) & last_reds_set) >= 4:
                    continue
                for tmpl in STRUCTURES:
                    if match_structure(combo, tmpl):
                        sc = sum(r[1] for r in sr if r[0] in combo)
                        if sc > best_s:
                            best_s = sc
                            best = sorted(combo)
                        break
            
            # fallback
            if best is None:
                top8 = [r[0] for r in sr[:8]]
                for combo in combinations(top8, 6):
                    sc = sum(r[1] for r in sr if r[0] in combo)
                    c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
                    d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
                    if sc+d > best_s:
                        best_s = sc+d
                        best = sorted(combo)
            
            pred = best + [sb[0][0]]
            h = len(set(pred[:6]) & ar)
            hits.append(h)
            blue_hits.append(1 if pred[6] == ab else 0)
        
        n = len(hits)
        avg = np.mean(hits)
        r3 = sum(1 for h in hits if h>=3)/n*100
        r4 = sum(1 for h in hits if h>=4)/n*100
        blue = sum(blue_hits)/n*100
        prize = sum(1 for h,b in zip(hits,blue_hits) if b or h>=3)/n*100
        
        print(f"  {periods}期: avg={avg:.3f}  3+={r3:.1f}%  4+={r4:.1f}%  blue={blue:.1f}%  中奖={prize:.1f}%  Δ{avg-6*6/33:+.3f}")
    print()


# ============ 方案定义 ============

# 当前方案（对照）
W_CURRENT_RED = {
    '历史频率': 1.0, '近期热度': 1.5, '间隔百分位': 0.5,
    '关联断裂': 1.5, '重号': 1.5, '邻号': 0.5,
    '和值平衡': 0.5, '区间平衡': 0.5, '历史模式': 0.3
}
W_CURRENT_BLUE = {
    '历史频率': 1.0, '近期热度': 1.5, '间隔百分位': 0.3,
    '重号': 1.5, '邻号': 1.0
}

# 纯老彩民（重号/邻号/和值/区间/历史模式，去掉统计类因子）
W_OLD_RED = {
    '历史频率': 0.0, '近期热度': 0.0, '间隔百分位': 0.0,
    '关联断裂': 0.0, '重号': 3.0, '邻号': 2.0,
    '和值平衡': 2.0, '区间平衡': 2.0, '历史模式': 1.0
}
W_OLD_BLUE = {
    '历史频率': 0.0, '近期热度': 0.0, '间隔百分位': 0.0,
    '重号': 3.0, '邻号': 2.0
}

# 纯老彩民+增强版（加大和值/区间权重）
W_OLD2_RED = {
    '历史频率': 0.0, '近期热度': 0.0, '间隔百分位': 0.0,
    '关联断裂': 0.0, '重号': 3.0, '邻号': 2.0,
    '和值平衡': 3.0, '区间平衡': 3.0, '历史模式': 1.0
}
W_OLD2_BLUE = W_OLD_BLUE

# 纯AI（统计类因子拉满）
W_AI_RED = {
    '历史频率': 2.0, '近期热度': 3.0, '间隔百分位': 1.0,
    '关联断裂': 2.0, '重号': 0.0, '邻号': 0.0,
    '和值平衡': 0.0, '区间平衡': 0.0, '历史模式': 0.0
}
W_AI_BLUE = {
    '历史频率': 2.0, '近期热度': 3.0, '间隔百分位': 1.0,
    '重号': 0.0, '邻号': 0.0
}


backtest(W_CURRENT_RED, W_CURRENT_BLUE, "当前方案（混合）")
backtest(W_OLD_RED, W_OLD_BLUE, "纯老彩民")

print(f"随机期望: avg_red={6*6/33:.3f}  blue={100/16:.1f}%")
