#!/usr/bin/env python3
"""
预测引擎 - 回测、权重调整、预测
"""

import sys
import os
from collections import Counter, defaultdict
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import *
from algorithms import *

# Prize tiers for 双色球
def check_prize(reds, blue, target_reds, target_blue):
    """Check prize level for a given prediction"""
    red_hit = len(set(reds) & set(target_reds))
    blue_hit = 1 if blue == target_blue else 0
    
    if red_hit == 6 and blue_hit == 1:
        return red_hit, blue_hit, '一等奖'
    elif red_hit == 6:
        return red_hit, blue_hit, '二等奖'
    elif red_hit == 5 and blue_hit == 1:
        return red_hit, blue_hit, '三等奖'
    elif red_hit == 5 or (red_hit == 4 and blue_hit == 1):
        return red_hit, blue_hit, '四等奖'
    elif red_hit == 4 or (red_hit == 3 and blue_hit == 1):
        return red_hit, blue_hit, '五等奖'
    elif red_hit == 2 and blue_hit == 1:
        return red_hit, blue_hit, '六等奖'
    elif red_hit == 1 and blue_hit == 1:
        return red_hit, blue_hit, '六等奖'
    elif blue_hit == 1:
        return red_hit, blue_hit, '六等奖（蓝球）'
    else:
        return red_hit, blue_hit, None

def run_backtest(num_periods=100):
    """
    回测：对最近N期模拟预测，看各策略命中率
    """
    draws = get_all_draws()
    if len(draws) < num_periods + 50:
        return "数据不足，需要至少50期历史数据才能回测"
    
    results = defaultdict(lambda: {
        'total': 0, 'red_hits': [], 'blue_hits': [], 'prizes': [],
        'hit_rate_3plus': 0, 'hit_rate_blue': 0
    })
    
    algorithms_list = ['association_break', 'density_drift', 'interval_pattern', 'embedding_anomaly', 'fusion']
    
    for i in range(len(draws) - num_periods, len(draws)):
        # Use data up to i-1 to predict period i
        train_draws = draws[:i]
        if len(train_draws) < 50:
            continue
        
        actual = draws[i]
        actual_reds = [actual['red1'], actual['red2'], actual['red3'], 
                       actual['red4'], actual['red5'], actual['red6']]
        actual_blue = actual['blue']
        
        # Run predictions
        preds = {}
        try:
            rc, bc = algorithm_association_break(train_draws)
            preds['association_break'] = pick_numbers(rc, bc)
            
            rc, bc = algorithm_density_drift(train_draws)
            preds['density_drift'] = pick_numbers(rc, bc)
            
            rc, bc = algorithm_interval_pattern(train_draws)
            preds['interval_pattern'] = pick_numbers(rc, bc)
            
            rc, bc = algorithm_embedding_anomaly(train_draws)
            preds['embedding_anomaly'] = pick_numbers(rc, bc)
            
            # Fusion
            weights = {a: 1.0 for a in algorithms_list[:4]}
            fusion_votes = defaultdict(int)
            for algo_key in algorithms_list[:4]:
                nums = preds[algo_key]
                if nums:
                    for r in nums[:6]:
                        fusion_votes[r] += weights[algo_key]
                    fusion_votes[('blue', nums[6])] += weights[algo_key]
            
            red_votes = {k: v for k, v in fusion_votes.items() if not isinstance(k, tuple)}
            blue_votes = {k[1]: v for k, v in fusion_votes.items() if isinstance(k, tuple)}
            
            fusion_reds = sorted(red_votes.keys(), key=lambda x: red_votes[x], reverse=True)[:6]
            fusion_blue = sorted(blue_votes.keys(), key=lambda x: blue_votes[x], reverse=True)[0]
            preds['fusion'] = sorted(fusion_reds) + [fusion_blue]
            
        except Exception as e:
            continue
        
        # Evaluate each
        for algo_key, nums in preds.items():
            if not nums:
                continue
            red_hit, blue_hit, prize = check_prize(nums[:6], nums[6], actual_reds, actual_blue)
            
            results[algo_key]['total'] += 1
            results[algo_key]['red_hits'].append(red_hit)
            results[algo_key]['blue_hits'].append(blue_hit)
            if prize:
                results[algo_key]['prizes'].append(prize)
            if red_hit >= 3:
                results[algo_key]['hit_rate_3plus'] += 1
            if blue_hit:
                results[algo_key]['hit_rate_blue'] += 1
    
    # Format results
    output = f"📊 回测报告（最近{num_periods}期）\n"
    output += "─" * 40 + "\n"
    
    best_algo = None
    best_score = 0
    
    for algo_key in algorithms_list:
        r = results[algo_key]
        if r['total'] == 0:
            continue
        
        avg_red = sum(r['red_hits']) / len(r['red_hits']) if r['red_hits'] else 0
        hit3_rate = r['hit_rate_3plus'] / r['total'] * 100
        blue_rate = r['hit_rate_blue'] / r['total'] * 100
        
        name_map = {
            'association_break': '关联断裂',
            'density_drift': '密度漂移',
            'interval_pattern': '间隔周期',
            'embedding_anomaly': '异常回归',
            'fusion': '综合决策'
        }
        
        output += f"{name_map.get(algo_key, algo_key)}\n"
        output += f"  平均红球命中: {avg_red:.2f} | 3+红率: {hit3_rate:.1f}%\n"
        output += f"  蓝球命中率: {blue_rate:.1f}%\n"
        if r['prizes']:
            output += f"  中奖: {' | '.join(r['prizes'][:5])}\n"
        output += "\n"
        
        # Score: combination of avg red hits + blue rate
        score = avg_red * 0.6 + (blue_rate / 100) * 2
        if score > best_score:
            best_score = score
            best_algo = algo_key
    
    if best_algo:
        name_map = {
            'association_break': '关联断裂',
            'density_drift': '密度漂移',
            'interval_pattern': '间隔周期',
            'embedding_anomaly': '异常回归',
            'fusion': '综合决策'
        }
        output += f"🏆 最佳策略: {name_map.get(best_algo, best_algo)}\n"
    
    return output


def predict_today():
    """
    执行今天的预测
    返回格式化的预测结果
    """
    draws = get_all_draws()
    if len(draws) < 50:
        return "数据不足（<50期），无法预测"
    
    latest = draws[-1]
    
    predictions = run_all_algorithms()
    
    # Get algorithm weights for display
    weights = get_algorithm_weights()
    
    # Determine next period number
    latest_period = latest['period']
    year_prefix = latest_period[:2]
    period_num = int(latest_period[2:])
    
    next_period = f"{year_prefix}{period_num + 1:03d}"
    
    # Format output
    output = f"🎱 双色球预测 · 第{next_period}期\n"
    output += f"📅 基于 {latest['date']} 之前全部数据\n"
    output += f"💾 共 {len(draws)} 期历史数据\n"
    output += "─" * 35 + "\n\n"
    
    emoji_map = {
        'association_break': '🔗',
        'density_drift': '🌊',
        'interval_pattern': '⏱️',
        'embedding_anomaly': '📉',
        'fusion': '🎯',
        'traditional': '🧓'
    }
    
    for algo_key in ['association_break', 'density_drift', 'interval_pattern', 'embedding_anomaly', 'fusion', 'traditional']:
        pred = predictions.get(algo_key)
        if not pred or not pred['numbers']:
            continue
        
        nums = pred['numbers']
        weight = weights.get(algo_key, 1.0)
        emoji = emoji_map.get(algo_key, '🤖')
        
        nums_str = ' '.join(f"{n:02d}" for n in nums[:6])
        output += f"{emoji} {pred['name']}  (权重{weight:.1f})\n"
        output += f"   {nums_str} + {nums[6]:02d}\n"
        
        if algo_key != 'fusion':
            # Show top candidates
            red_top = pred.get('red_candidates', [])[:5]
            blue_top = pred.get('blue_candidates', [])[:3]
            if red_top:
                red_str = ' '.join(f"{n:02d}" for n, _ in red_top)
                blue_str = ' '.join(f"{n:02d}" for n, _ in blue_top)
                output += f"   候选红: {red_str} | 候选蓝: {blue_str}\n"
        output += "\n"
    
    return output


def update_weights_from_latest():
    """
    最新一期开奖后，更新各算法权重
    """
    draws = get_all_draws()
    if len(draws) < 2:
        return
    
    latest = draws[-1]
    actual_reds = [latest['red1'], latest['red2'], latest['red3'],
                   latest['red4'], latest['red5'], latest['red6']]
    actual_blue = latest['blue']
    
    # Get last prediction for this period
    conn = get_conn()
    predictions = conn.execute(
        'SELECT * FROM predictions WHERE period = ?', (latest['period'],)
    ).fetchall()
    conn.close()
    
    if not predictions:
        return
    
    for pred in predictions:
        algo = pred['algorithm']
        pred_reds = [pred['red1'], pred['red2'], pred['red3'],
                     pred['red4'], pred['red5'], pred['red6']]
        pred_blue = pred['blue']
        
        red_hit, blue_hit, prize = check_prize(pred_reds, pred_blue, actual_reds, actual_blue)
        
        # Save result
        save_prediction_result(latest['period'], algo, red_hit, blue_hit, prize)
        
        # Update weight
        success = red_hit >= 3 or blue_hit == 1
        update_algorithm_weight(algo, success)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='双色球预测引擎')
    parser.add_argument('--backtest', type=int, default=0, help='回测最近N期')
    parser.add_argument('--predict', action='store_true', help='执行预测')
    parser.add_argument('--update-weights', action='store_true', help='更新权重')
    
    args = parser.parse_args()
    
    if args.backtest > 0:
        print(run_backtest(args.backtest))
    elif args.predict:
        print(predict_today())
    elif args.update_weights:
        update_weights_from_latest()
        print("权重更新完成")
    else:
        print(predict_today())
