#!/usr/bin/env python3
"""快速回测对比：策略A(select_numbers) vs 策略B(前6高分)"""
from database import get_all_draws, init_db
from scorecard import score_all, select_numbers
import numpy as np
import sys

def run():
    init_db()
    draws = get_all_draws()
    print(f"总期数: {len(draws)}")
    
    for periods in [30, 100]:
        test = draws[-periods:]
        train = draws[:-periods]
        hits_a, hits_b = [], []
        bh_a, bh_b = [], []
        
        for i in range(1, len(test)):
            t = train + test[:i]
            if len(t) < 50:
                continue
            actual = test[i]
            ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
            rs, bs = score_all(t)
            
            # A: select_numbers
            pred_a = select_numbers(rs, bs, t)
            ha = len(set(pred_a[:6]) & ar)
            hits_a.append(ha)
            bh_a.append(1 if pred_a[6] == actual['blue'] else 0)
            
            # B: 前6高分
            sr = sorted(rs, key=lambda x: x[1], reverse=True)
            pred_b = [r[0] for r in sr[:6]]
            sb = sorted(bs, key=lambda x: x[1], reverse=True)
            pred_b.append(sb[0][0])
            hb = len(set(pred_b[:6]) & ar)
            hits_b.append(hb)
            bh_b.append(1 if pred_b[6] == actual['blue'] else 0)
        
        n = len(hits_a)
        print(f"\n--- 最近{periods}期 ---")
        print(f"A(select_nums): avg_red={np.mean(hits_a):.3f} 3+={sum(1 for h in hits_a if h>=3)/n*100:.1f}% blue={sum(bh_a)/n*100:.1f}%")
        print(f"B(前6高分):      avg_red={np.mean(hits_b):.3f} 3+={sum(1 for h in hits_b if h>=3)/n*100:.1f}% blue={sum(bh_b)/n*100:.1f}%")
        print(f"随机期望:        avg_red={6*6/33:.3f} 3+~11.5% blue={100/16:.1f}%")
    
    # 策略C: 只保留3个核心因子（去掉重号、邻号等短期因子）
    print("\n--- 策略C: 纯统计因子（历史+近期+间隔+断裂） ---")
    test = draws[-100:]
    train = draws[:-100]
    hits_c, bh_c = [], []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50:
            continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        last = t[-1]
        lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
        lb = last['blue']
        
        from scorecard import (factor_historical_frequency, factor_recent_frequency,
                              factor_interval_percentile, factor_correlation_break,
                              RED_FACTORS)
        
        # 只用历史+近期+间隔+断裂，权重1:1.5:2:1
        red_scores = []
        for r in range(1, 34):
            h = factor_historical_frequency(r, t, lr, lb) * 1.0
            rf = factor_recent_frequency(r, t, lr, lb) * 1.5
            ip = factor_interval_percentile(r, t, lr, lb) * 2.0
            cb = factor_correlation_break(r, t, lr, lb) * 1.0
            red_scores.append((r, h+rf+ip+cb, {}))
        
        blues_sorted = []
        for b in range(1, 17):
            h = factor_historical_frequency(b, t, lr, lb) * 1.0
            rf = factor_recent_frequency(b, t, lr, lb) * 1.5
            ip = factor_interval_percentile(b, t, lr, lb) * 2.0
            blues_sorted.append((b, h+rf+ip))
        
        sr = sorted(red_scores, key=lambda x: x[1], reverse=True)
        pred = [r[0] for r in sr[:6]]
        sb = sorted(blues_sorted, key=lambda x: x[1], reverse=True)
        pred.append(sb[0][0])
        
        hc = len(set(pred[:6]) & ar)
        hits_c.append(hc)
        bh_c.append(1 if pred[6] == actual['blue'] else 0)
    
    n = len(hits_c)
    print(f"C(纯统计因子):   avg_red={np.mean(hits_c):.3f} 3+={sum(1 for h in hits_c if h>=3)/n*100:.1f}% blue={sum(bh_c)/n*100:.1f}%")
    
    # 策略D: 去掉重号因子（它让模型过度追上一期的号码）
    print("\n--- 策略D: 全部因子 - 去掉重号 ---")
    test = draws[-100:]
    train = draws[:-100]
    hits_d, bh_d = [], []
    
    for i in range(1, len(test)):
        t = train + test[:i]
        if len(t) < 50:
            continue
        actual = test[i]
        ar = {actual['red1'], actual['red2'], actual['red3'], actual['red4'], actual['red5'], actual['red6']}
        last = t[-1]
        lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
        lb = last['blue']
        
        from scorecard import (factor_historical_frequency, factor_recent_frequency,
                              factor_interval_percentile, factor_correlation_break,
                              factor_repeat, factor_neighbor, factor_sum_balance,
                              factor_zone_balance, factor_historical_pattern)
        
        red_scores = []
        for r in range(1, 34):
            score = 0
            score += factor_historical_frequency(r, t, lr, lb) * 1.0  # 历史
            score += factor_recent_frequency(r, t, lr, lb) * 1.5     # 近期
            score += factor_interval_percentile(r, t, lr, lb) * 2.0  # 间隔
            score += factor_correlation_break(r, t, lr, lb) * 1.0    # 断裂
            # NOTA: 去掉重号
            score += factor_neighbor(r, t, lr, lb) * 0.5             # 邻号(降权)
            score += factor_sum_balance(r, t, lr, lb) * 0.3          # 和值
            score += factor_zone_balance(r, t, lr, lb) * 0.3         # 区平
            red_scores.append((r, score, {}))
        
        blues_sorted = []
        for b in range(1, 17):
            score = 0
            score += factor_historical_frequency(b, t, lr, lb) * 1.0
            score += factor_recent_frequency(b, t, lr, lb) * 1.5
            score += factor_interval_percentile(b, t, lr, lb) * 2.0
            blues_sorted.append((b, score))
        
        sr = sorted(red_scores, key=lambda x: x[1], reverse=True)
        pred = [r[0] for r in sr[:6]]
        sb = sorted(blues_sorted, key=lambda x: x[1], reverse=True)
        pred.append(sb[0][0])
        
        hd = len(set(pred[:6]) & ar)
        hits_d.append(hd)
        bh_d.append(1 if pred[6] == actual['blue'] else 0)
    
    n = len(hits_d)
    print(f"D(去重号):       avg_red={np.mean(hits_d):.3f} 3+={sum(1 for h in hits_d if h>=3)/n*100:.1f}% blue={sum(bh_d)/n*100:.1f}%")

if __name__ == '__main__':
    run()
