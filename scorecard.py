#!/usr/bin/env python3
"""
评分卡模型 - 双色球号码评分系统

每个号码的得分 = Σ(因子_i × 权重_i)
权重通过历史数据回测自动优化

因子类型：
  - 统计类：历史频率、间隔、冷热等
  - 算法类：关联断裂、密度漂移等（压缩为得分因子）
  - 经验类：重号、邻号、和值等
"""

import sys
import os
import numpy as np
from collections import Counter, defaultdict
from itertools import combinations
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Lazy import database to avoid circular imports
# from database import get_all_draws, get_recent_draws

# ============================================================
# 因子计算函数
# 每个函数输入：(号码, 全部历史draws, 上期号码)
# 输出：该号码在该因子上的原始分数
# ============================================================

def factor_historical_frequency(num, draws, last_reds, last_blue):
    """因子1: 历史总出现率 — 全周期出现次数/总期数"""
    total = len(draws)
    if total == 0:
        return 0.5
    if isinstance(num, int) and 1 <= num <= 33:  # 红球
        count = sum(1 for d in draws for r in ['red1','red2','red3','red4','red5','red6'] if d[r] == num)
        return count / total
    elif isinstance(num, int) and 1 <= num <= 16:  # 蓝球
        count = sum(1 for d in draws if d['blue'] == num)
        return count / total
    return 0.5

def factor_recent_frequency(num, draws, last_reds, last_blue):
    """因子2: 近期热度 — 近30期出现次数"""
    window = min(30, len(draws))
    recent = draws[-window:]
    total = len(recent) * 6 if isinstance(num, int) and 1 <= num <= 33 else len(recent)
    if total == 0:
        return 0.5
    
    if isinstance(num, int) and 1 <= num <= 33:
        count = sum(1 for d in recent for r in ['red1','red2','red3','red4','red5','red6'] if d[r] == num)
    else:
        count = sum(1 for d in recent if d['blue'] == num)
    return count / total

def factor_interval_percentile(num, draws, last_reds, last_blue):
    """因子3: 间隔百分位 — 当前间隔在历史分布中的位置
       间隔越久分数越高（赌回归）
    """
    if len(draws) < 30:
        return 0.5
    
    intervals = []
    last_seen = -1
    
    for idx, d in enumerate(draws):
        if isinstance(num, int) and 1 <= num <= 33:
            for r in ['red1','red2','red3','red4','red5','red6']:
                if d[r] == num:
                    if last_seen >= 0:
                        intervals.append(idx - last_seen)
                    last_seen = idx
                    break
        else:
            if d['blue'] == num:
                if last_seen >= 0:
                    intervals.append(idx - last_seen)
                last_seen = idx
    
    current_interval = len(draws) - 1 - last_seen if last_seen >= 0 else len(draws)
    
    if not intervals:
        return min(current_interval / 50, 1.0)  # 从未出现，给高分
    
    # 当前间隔超过历史平均的倍数
    avg_interval = np.mean(intervals)
    if avg_interval <= 0:
        return 0.5
    
    ratio = current_interval / avg_interval
    # ratio=1是平均间隔，给0.5；ratio=2给0.75；ratio=3给0.875
    score = 1 - 0.5 ** ratio
    return min(score, 1.0)

def factor_correlation_break(num, draws, last_reds, last_blue, 
                              old_sets=None, recent_sets=None):
    """因子4: 关联断裂得分"""
    if len(draws) < 100 or not (isinstance(num, int) and 1 <= num <= 33):
        return 0.5
    
    if old_sets is None or recent_sets is None:
        window = 100
        older = draws[:-window]
        recent = draws[-window:]
        old_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in older]
        recent_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in recent]
    
    old_partners = Counter()
    for s in old_sets:
        if num in s:
            for p in s:
                if p != num:
                    old_partners[p] += 1
    
    recent_partners = Counter()
    for s in recent_sets:
        if num in s:
            for p in s:
                if p != num:
                    recent_partners[p] += 1
    
    break_score = 0
    for partner, old_count in old_partners.most_common(10):
        old_freq = old_count / len(old_sets)
        recent_freq = recent_partners.get(partner, 0) / len(recent_sets)
        if old_freq > 0.03 and recent_freq < old_freq * 0.5:
            break_score += (old_freq - recent_freq)
    
    return min(break_score * 10, 1.0)

def factor_repeat(num, draws, last_reds, last_blue):
    """因子5: 重号 — 上期号码保留"""
    if isinstance(num, int) and 1 <= num <= 33:
        return 1.0 if num in last_reds else 0.0
    else:
        return 1.0 if num == last_blue else 0.0

def factor_neighbor(num, draws, last_reds, last_blue):
    """因子6: 邻号 — 上期号码±1"""
    if isinstance(num, int) and 1 <= num <= 33:
        count = sum(1 for r in last_reds if abs(num - r) == 1)
        return min(count / 2, 1.0)  # 最多2个邻号就算满分
    else:
        return 1.0 if abs(num - last_blue) == 1 else 0.0

def factor_sum_balance(num, draws, last_reds, last_blue):
    """因子7: 和值平衡 — 靠近均值的加分（用于选号阶段）"""
    if isinstance(num, int) and 1 <= num <= 33:
        # 单个号码的理想值是17
        return max(0, 1 - abs(num - 17) / 16)
    return 0.5

def factor_zone_balance(num, draws, last_reds, last_blue):
    """因子8: 区间平衡 — 看号码所在区间的整体热度"""
    if not isinstance(num, int) or not (1 <= num <= 33):
        return 0.5
    
    # 三区
    if num <= 11:
        zone = 0
    elif num <= 22:
        zone = 1
    else:
        zone = 2
    
    window = min(50, len(draws))
    recent = draws[-window:]
    
    zone_counts = [0, 0, 0]
    for d in recent:
        for r in ['red1','red2','red3','red4','red5','red6']:
            v = d[r]
            if v <= 11:
                zone_counts[0] += 1
            elif v <= 22:
                zone_counts[1] += 1
            else:
                zone_counts[2] += 1
    
    total = sum(zone_counts)
    if total == 0:
        return 0.5
    
    zone_freq = zone_counts[zone] / total
    # 期望是 1/3, 偏离越多分数越低
    return 1 - abs(zone_freq - 1/3) * 3

def factor_odd_even(num, draws, last_reds, last_blue):
    """因子9: 奇偶偏好 — 在选号阶段用"""
    return 0.5  # 选号阶段处理

def factor_historical_pattern(num, draws, last_reds, last_blue):
    """因子10: 历史中奖号码模式匹配（异常回归算法的压缩版）"""
    if len(draws) < 50 or not (isinstance(num, int) and 1 <= num <= 33):
        return 0.5
    
    window = min(100, len(draws))
    recent = draws[-window:]
    
    # 简单特征：上期号码的和值、奇偶比、区间分布
    last_sum = sum(last_reds)
    last_odd = sum(1 for r in last_reds if r % 2 == 1)
    
    # 如果这个号码能使整体特征更接近历史均值，加分
    # 历史均值：和值102，奇偶3:3
    # 模拟加入这个号码后的影响
    # 这个因子较弱，只在边缘起作用
    return 0.5


from config import SSQ_RED_WEIGHTS, SSQ_BLUE_WEIGHTS, SSQ_STRUCT_TEMPLATES

RED_FACTORS = [
    # 纯老彩民因子（红球结构）
    ('重号', factor_repeat, SSQ_RED_WEIGHTS['repeat']),
    ('邻号', factor_neighbor, SSQ_RED_WEIGHTS['neighbor']),
    ('和值平衡', factor_sum_balance, SSQ_RED_WEIGHTS['sum_balance']),
    ('区间平衡', factor_zone_balance, SSQ_RED_WEIGHTS['zone_balance']),
    ('历史模式', factor_historical_pattern, SSQ_RED_WEIGHTS['pattern']),
    # AI因子归零
    ('历史频率', factor_historical_frequency, 0.0),
    ('近期热度', factor_recent_frequency, 0.0),
    ('间隔百分位', factor_interval_percentile, 0.0),
    ('关联断裂', factor_correlation_break, 0.0),
]

BLUE_FACTORS = [
    # 蓝球保留AI因子（近期热度有效）
    ('近期热度', factor_recent_frequency, SSQ_BLUE_WEIGHTS['recent_hot']),
    ('历史频率', factor_historical_frequency, SSQ_BLUE_WEIGHTS['history_freq']),
    ('重号', factor_repeat, SSQ_BLUE_WEIGHTS['repeat']),
    ('邻号', factor_neighbor, SSQ_BLUE_WEIGHTS['neighbor']),
    ('间隔百分位', factor_interval_percentile, 0.0),
]


# ============================================================
# 评分卡核心
# ============================================================

def score_number(num, draws, last_reds, last_blue, is_red=True):
    """
    对一个号码计算综合评分
    得分 = Σ(因子_i × 权重_i)
    """
    factors = RED_FACTORS if is_red else BLUE_FACTORS
    
    total_score = 0
    details = {}
    
    for name, func, weight in factors:
        try:
            raw_score = func(num, draws, last_reds, last_blue)
            weighted = raw_score * weight
            total_score += weighted
            details[name] = {'raw': round(raw_score, 3), 'weight': weight, 'weighted': round(weighted, 3)}
        except Exception as e:
            details[name] = {'raw': 0, 'weight': weight, 'weighted': 0, 'error': str(e)}
    
    return total_score, details


def score_all(draws):
    """
    给所有33红+16蓝评分
    返回：(红球得分列表, 蓝球得分列表)
    """
    if len(draws) < 10:
        return [], []
    
    last = draws[-1]
    last_reds = [last['red1'], last['red2'], last['red3'],
                 last['red4'], last['red5'], last['red6']]
    last_blue = last['blue']
    
    # 预计算关联断裂数据
    window = 100
    older = draws[:-window] if len(draws) > window else draws
    recent = draws[-window:] if len(draws) > window else draws
    corr_old_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in older]
    corr_recent_sets = [set([d[r] for r in ['red1','red2','red3','red4','red5','red6']]) for d in recent]
    
    red_scores = []
    for r in range(1, 34):
        score, details = score_number(r, draws, last_reds, last_blue, is_red=True)
        # Override correlation break with precomputed data
        if r in [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33]:
            cb = factor_correlation_break(r, draws, last_reds, last_blue, corr_old_sets, corr_recent_sets)
            # Update the total score - subtract old cb value and add new
            if '关联断裂' in details:
                old_cb_weighted = details['关联断裂'].get('weighted', 0)
                new_cb_weighted = cb * 1.0  # weight is 1.0
                score = score - old_cb_weighted + new_cb_weighted
                details['关联断裂'] = {'raw': round(cb, 3), 'weight': 1.0, 'weighted': round(new_cb_weighted, 3)}
        
        red_scores.append((r, score, details))
    
    blue_scores = []
    for b in range(1, 17):
        score, details = score_number(b, draws, last_reds, last_blue, is_red=False)
        blue_scores.append((b, score, details))
    
    return red_scores, blue_scores


# ============================================================
# 选号：基于评分+分布优化的最优组合搜索
# ============================================================

def select_numbers(red_scores, blue_scores, draws=None):
    """
    结构优先选号：
    1. 从评分TOP20中枚举组合
    2. 先检查是否符合真实开奖结构模板
    3. 符合的里面挑评分最高的
    
    结构模板基于3447期真实开奖数据统计：
    - 和值80-130占76%
    - 奇偶2:4~4:2占83%
    - 跨度20-28占71%
    - 三区2:2:2最常见(15.4%)
    """
    if not red_scores or not blue_scores:
        return None
    
    # 按评分排序
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    
    # 结构模板（从config.py读取）
    STRUCTURES = SSQ_STRUCT_TEMPLATES
    
    def match_structure(reds, tmpl):
        c_sum, c_odd, c_span = sum(reds), sum(1 for n in reds if n%2==1), max(reds)-min(reds)
        low, mid, high = sum(1 for n in reds if n<=11), sum(1 for n in reds if 12<=n<=22), sum(1 for n in reds if n>=23)
        return (tmpl[0][0] <= c_sum <= tmpl[0][1] and
                tmpl[1][0] <= c_odd <= tmpl[1][1] and
                tmpl[2][0] <= c_span <= tmpl[2][1] and
                low == tmpl[3][0] and mid == tmpl[3][1] and high == tmpl[3][2])
    
    # 从TOP20中枚举，优选符合结构的组合
    top20 = [r[0] for r in reds_sorted[:20]]
    last_draw = None
    if draws:
        last_draw = draws[-1]
        last_reds = [last_draw['red1'], last_draw['red2'], last_draw['red3'],
                     last_draw['red4'], last_draw['red5'], last_draw['red6']]
    
    best_reds = None
    best_score = -999
    
    for combo in combinations(top20, 6):
        # 重号限制：最多3个重号（历史上4+重号仅占0.5%）
        if last_reds:
            repeat_count = len(set(combo) & set(last_reds))
            if repeat_count >= 4:
                continue
        
        for tmpl in STRUCTURES:
            if match_structure(combo, tmpl):
                score = sum(r[1] for r in reds_sorted if r[0] in combo)
                if score > best_score:
                    best_score = score
                    best_reds = sorted(combo)
                break  # 匹配一个模板就行
    
    # fallback: TOP8最佳组合
    if best_reds is None:
        top8 = [r[0] for r in reds_sorted[:8]]
        for combo in combinations(top8, 6):
            score = sum(r[1] for r in reds_sorted if r[0] in combo)
            c_sum, c_odd, c_span = sum(combo), sum(1 for n in combo if n%2==1), max(combo)-min(combo)
            d = (1 if 20<=c_span<=28 else 0)+(1 if 2<=c_odd<=4 else 0)+(0.5 if 85<=c_sum<=125 else 0)
            if score+d > best_score:
                best_score = score+d
                best_reds = sorted(combo)
    
    # 蓝球取最高分
    best_blue = blues_sorted[0][0]
    
    return best_reds + [best_blue]


# ============================================================
# 权重优化：通过历史回测自动调权
# ============================================================

def optimize_weights(draws, iterations=1000):
    """
    通过回测优化因子权重
    使用简单的随机搜索
    """
    if len(draws) < 200:
        print("数据不足200期，无法有效优化权重")
        return None
    
    from database import get_all_draws
    
    # 用后300期做验证
    test_draws = draws[-300:]
    train_draws = draws[:-300]
    
    if len(train_draws) < 100:
        train_draws = draws[:-100]
        test_draws = draws[-100:]
    
    # 当前权重（默认值）
    current_weights = [(name, w) for name, _, w in RED_FACTORS]
    
    def evaluate(weights_list):
        """用给定权重跑回测，返回平均红球命中数"""
        hits = []
        # 只回测后100期
        test = test_draws[-100:]
        for i in range(1, len(test)):
            train = train_draws + test[:i]
            if len(train) < 50:
                continue
            
            actual = test[i]
            actual_reds = [actual['red1'], actual['red2'], actual['red3'],
                          actual['red4'], actual['red5'], actual['red6']]
            
            # 用当前权重评分
            last = train[-1]
            lr = [last['red1'], last['red2'], last['red3'], last['red4'], last['red5'], last['red6']]
            lb = last['blue']
            
            # 临时替换权重
            red_scores = []
            for r in range(1, 34):
                score = 0
                for idx, (name, func, _) in enumerate(RED_FACTORS):
                    raw = func(r, train, lr, lb)
                    score += raw * weights_list[idx]
                red_scores.append((r, score, {}))
            
            blues_sorted = []
            for b in range(1, 17):
                score = 0
                for idx, (name, func, _) in enumerate(BLUE_FACTORS):
                    raw = func(b, train, lr, lb)
                    score += raw * weights_list[idx]
                blues_sorted.append((b, score))
            
            # 简化选号：直接取前6高分
            pred_reds = sorted([r[0] for r in sorted(red_scores, key=lambda x: x[1], reverse=True)[:6]])
            hit = len(set(pred_reds) & set(actual_reds))
            hits.append(hit)
        
        return np.mean(hits) if hits else 0
    
    # 评估当前权重
    current_weights_list = [w for _, w in current_weights]
    baseline = evaluate(current_weights_list)
    print(f"当前权重平均红球命中: {baseline:.3f}")
    
    # 随机搜索优化
    best_weights = current_weights_list.copy()
    best_hit = baseline
    
    for i in range(iterations):
        # 随机扰动
        new_weights = []
        for w in best_weights:
            noise = np.random.uniform(-0.3, 0.3)
            new_w = max(0.1, min(5.0, w + noise))
            new_weights.append(new_w)
        
        hit = evaluate(new_weights)
        if hit > best_hit:
            best_hit = hit
            best_weights = new_weights
            # print(f"  Iter {i}: improved to {hit:.3f}")
    
    print(f"优化后平均红球命中: {best_hit:.3f}")
    print(f"提升: {(best_hit - baseline) / baseline * 100:.1f}%" if baseline > 0 else "N/A")
    
    return best_weights


# ============================================================
# 主预测接口
# ============================================================

def predict_with_scorecard():
    """评分卡主预测接口"""
    from database import get_all_draws, init_db, save_prediction
    
    draws = get_all_draws()
    if len(draws) < 10:
        return "数据不足"
    
    red_scores, blue_scores = score_all(draws)
    nums = select_numbers(red_scores, blue_scores, draws)
    
    if not nums:
        return "预测失败"
    
    # 生成详情输出
    last = draws[-1]
    last_reds = [last['red1'], last['red2'], last['red3'],
                 last['red4'], last['red5'], last['red6']]
    last_blue = last['blue']
    
    # 预测期号
    period_prefix = last['period'][:2]
    period_suffix = int(last['period'][2:]) + 1
    next_period = f"{period_prefix}{period_suffix:03d}"
    
    output = f"🎱 双色球预测 · 第{next_period}期\n"
    output += f"📅 基于 {last['date']} 之前全部数据\n"
    output += f"💾 共 {len(draws)} 期历史数据\n"
    output += "─" * 35 + "\n\n"
    output += f"🧮 <b>评分卡模型</b>\n\n"
    
    # 红球详情
    reds_sorted = sorted(red_scores, key=lambda x: x[1], reverse=True)
    output += f"📊 红球TOP15评分:\n"
    output += f"{'号码':>4} {'总分':>6}\n"
    output += "-" * 12 + "\n"
    for r, score, details in reds_sorted[:15]:
        mark = " ✓" if r in nums[:6] else ""
        output += f"  {r:02d}  {score:5.2f}{mark}\n"
    
    # 最终号码
    nums_str = ' '.join(f"{n:02d}" for n in nums[:6])
    output += f"\n🎯 <b>推荐号码: {nums_str} + {nums[6]:02d}</b>\n"
    
    # 因子贡献
    output += "\n📋 因子贡献 (已选号码):\n"
    names = [name for name, _, _ in RED_FACTORS]
    output += f"{'号码':>4} "
    for n in names[:5]:
        output += f"{n:>6}"
    output += "\n"
    for r, score, details in reds_sorted:
        if r in nums[:6]:
            output += f"  {r:02d} "
            for name in names[:5]:
                v = details.get(name, {}).get('weighted', 0)
                output += f"{v:6.3f}"
            output += "\n"
    
    # 蓝球
    blues_sorted = sorted(blue_scores, key=lambda x: x[1], reverse=True)
    output += f"\n🔵 蓝球推荐:\n"
    for b, score in blues_sorted[:5]:
        mark = " ←" if b == nums[6] else ""
        output += f"  {b:02d} ({score:.2f}){mark}\n"
    
    return output


def scorecard_predict_detailed():
    """
    返回详细评分数据（给Bot用）
    """
    from database import get_all_draws
    
    draws = get_all_draws()
    if len(draws) < 10:
        return {"error": "数据不足"}
    
    red_scores, blue_scores = score_all(draws)
    nums = select_numbers(red_scores, blue_scores, draws)
    
    last = draws[-1]
    period_prefix = last['period'][:2]
    period_suffix = int(last['period'][2:]) + 1
    next_period = f"{period_prefix}{period_suffix:03d}"
    
    result = {
        'period': next_period,
        'date': last['date'],
        'total_draws': len(draws),
        'red_numbers': nums[:6] if nums else [],
        'blue_number': nums[6] if nums else 0,
        'red_scores': [(r, round(s, 3)) for r, s, _ in red_scores],
        'blue_scores': [(b, round(s, 3)) for b, s, _ in blue_scores],
    }
    
    return result


if __name__ == '__main__':
    from database import init_db, get_all_draws
    init_db()
    draws = get_all_draws()
    
    print("=" * 50)
    print("评分卡模型预测")
    print("=" * 50)
    
    result = scorecard_predict_detailed()
    
    last = draws[-1]
    print(f"\n上期: {last['period']} {' '.join(str(last[f'red{i}']) for i in range(1,7))} + {last['blue']}")
    
    red_scores = result['red_scores']
    print(f"\n红球评分TOP 20:")
    print(f"{'号':>3} {'分':>6}")
    print("-" * 12)
    for r, s in red_scores[:20]:
        mark = " ◀" if r in result['red_numbers'] else ""
        print(f"{r:3d} {s:6.2f}{mark}")
    
    nums_str = ' '.join(f"{n:02d}" for n in result['red_numbers'])
    print(f"\n🎯 推荐: {nums_str} + {result['blue_number']:02d}")
    
    print(f"\n蓝球评分:")
    for b, s in result['blue_scores'][:5]:
        mark = " ◀" if b == result['blue_number'] else ""
        print(f"  {b:02d} {s:.2f}{mark}")
    
    # 优化权重
    # print("\n" + "=" * 50)
    # print("优化因子权重...")
    # print("=" * 50)
    # optimize_weights(draws, iterations=500)
