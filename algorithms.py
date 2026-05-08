#!/usr/bin/env python3
"""
4种自研双色球预测算法

算法A: 关联性断裂点检测 — 找历史常一起出但最近不出的号码组合
算法B: 分布密度偏移跟踪 — 跟踪号码分布重心的漂移方向
算法C: 间隔周期模式挖掘 — 找超过历史平均间隔的"该出"号码
算法D: 低维嵌入异常检测 — PCA降维找偏离主集群的期数，赌回归
"""

import numpy as np
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_all_draws, get_recent_draws

# 不固定种子，让每次预测有合理的变化
# np.random.seed(42)

def get_reds(draws):
    """Extract red ball numbers as list of lists"""
    return [[d['red1'], d['red2'], d['red3'], d['red4'], d['red5'], d['red6']] for d in draws]

def get_blues(draws):
    """Extract blue ball numbers"""
    return [d['blue'] for d in draws]

def pick_numbers(red_candidates, blue_candidates, count=6):
    """
    Pick 6 red + 1 blue from candidates.
    纯分数驱动：直接取最高分的6个红球 + 最高分的蓝球
    去重去0，不加任何分布约束
    """
    if not red_candidates or not blue_candidates:
        return None
    
    # Reds: sort by score descending, take top 6 (with dedup)
    if isinstance(red_candidates[0], tuple):
        sorted_reds = sorted(red_candidates, key=lambda x: x[1], reverse=True)
        reds = []
        seen = set()
        for n, s in sorted_reds:
            if n not in seen and 1 <= n <= 33:
                reds.append(n)
                seen.add(n)
            if len(reds) == 6:
                break
        reds = sorted(reds)
    else:
        # No scores, just pick 6 unique
        nums = list(set(n for n in red_candidates if 1 <= n <= 33))
        reds = sorted(nums[:6])
    
    # Blue: highest score
    if isinstance(blue_candidates[0], tuple):
        blue = sorted(blue_candidates, key=lambda x: x[1], reverse=True)[0][0]
    else:
        blues = list(set(b for b in blue_candidates if 1 <= b <= 16))
        blue = blues[0] if blues else 1
    
    return reds + [blue]


# ============================================================
# 算法A: 关联性断裂点检测 (Association Break Detection)
# ============================================================
def algorithm_association_break(draws, window_size=100):
    """
    原理：
      计算所有C(33,2)=528个红球两两组合的历史出现频率
      与近期窗口内的频率对比
      找"历史高频但近期低频"的组合（关联断裂）
      从这些断裂组合中构造号码
    
    输入: draws = 全部历史数据
    输出: (red_candidates, blue_candidates)
    """
    all_reds = get_reds(draws)
    all_blues = get_blues(draws)
    
    # Split into historical (older) and recent
    if len(draws) <= window_size:
        return list(range(1, 34)), list(range(1, 17))
    
    older = draws[:-window_size]
    recent = draws[-window_size:]
    
    old_reds = get_reds(older)
    recent_reds = get_reds(recent)
    
    # Count pair frequencies
    old_pairs = defaultdict(int)
    recent_pairs = defaultdict(int)
    
    for reds in old_reds:
        for i in range(6):
            for j in range(i+1, 6):
                pair = (min(reds[i], reds[j]), max(reds[i], reds[j]))
                old_pairs[pair] += 1
    
    for reds in recent_reds:
        for i in range(6):
            for j in range(i+1, 6):
                pair = (min(reds[i], reds[j]), max(reds[i], reds[j]))
                recent_pairs[pair] += 1
    
    # Normalize to frequency per draw
    old_total = len(older)
    recent_total = len(recent)
    
    # Find "broken" pairs: high historical freq but low recent freq
    broken_pairs = []
    for pair, old_count in old_pairs.items():
        old_freq = old_count / old_total
        recent_freq = recent_pairs.get(pair, 0) / recent_total
        
        # Ratio: how much less frequent in recent window
        if old_freq > 0.03:  # At least 3% historically
            decline = old_freq - recent_freq
            if decline > old_freq * 0.5:  # Declined by >50%
                broken_pairs.append((pair, decline))
    
    # Score individual numbers based on how many broken pairs they're in
    num_scores = defaultdict(float)
    for (n1, n2), decline in broken_pairs:
        num_scores[n1] += decline
        num_scores[n2] += decline
    
    if not num_scores:
        return list(range(1, 34)), list(range(1, 17))
    
    # Top red candidates
    red_candidates = sorted(num_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Blue: use similar logic - historical frequency vs recent
    old_blue_freq = Counter(all_blues[:-window_size])
    recent_blue_freq = Counter(all_blues[-window_size:])
    
    blue_scores = []
    for b in range(1, 17):
        old_f = old_blue_freq.get(b, 0) / len(older)
        recent_f = recent_blue_freq.get(b, 0) / len(recent)
        if old_f > 0.05 and recent_f < old_f * 0.7:
            blue_scores.append((b, old_f - recent_f))
    
    if not blue_scores:
        blue_scores = list(range(1, 17))
    
    return red_candidates, blue_scores


# ============================================================
# 算法B: 分布密度偏移跟踪 (Density Drift Tracking)
# ============================================================
def algorithm_density_drift(draws, window_size=50):
    """
    原理：
      33个红球在数轴上天然有聚类倾向
      用核密度估计(KDE)画分布曲线
      跟踪曲线的"重心漂移"
      选择重心偏移方向上的冷门号码
    
    输入: draws
    输出: (red_candidates, blue_candidates)
    """
    all_reds = get_reds(draws)
    all_blues = get_blues(draws)
    
    if len(draws) <= window_size * 2:
        return list(range(1, 34)), list(range(1, 17))
    
    # Two windows: older and more recent
    older = draws[-window_size*2:-window_size]
    newer = draws[-window_size:]
    
    old_reds = get_reds(older)
    new_reds = get_reds(newer)
    
    # Flatten and compute Kernel Density Estimate manually
    # Using weighted histogram approach
    def compute_histogram(reds_list, bandwidth=1.5):
        hist = np.zeros(34)  # index 0 unused, 1-33
        for reds in reds_list:
            for r in reds:
                # Simple gaussian kernel
                for x in range(1, 34):
                    dist = abs(x - r)
                    weight = np.exp(-(dist**2) / (2 * bandwidth**2))
                    hist[x] += weight
        return hist / len(reds_list)
    
    old_hist = compute_histogram(old_reds)
    new_hist = compute_histogram(new_reds)
    
    # Find "center of mass" for each window
    def center_of_mass(hist):
        total = hist[1:].sum()
        if total == 0:
            return 17
        return sum(i * hist[i] for i in range(1, 34)) / total
    
    old_center = center_of_mass(old_hist)
    new_center = center_of_mass(new_hist)
    
    drift_direction = new_center - old_center  # positive = moving right
    
    # The drift suggests numbers in the drift direction are "heating up"
    # But we want to catch up: pick numbers on the drift side that are still cold
    
    # Compute frequency in recent window
    recent_flat = [r for reds in new_reds for r in reds]
    recent_freq = Counter(recent_flat)
    
    # Weight: higher weight for numbers in drift direction
    red_scores = []
    for r in range(1, 34):
        # Distance from center in drift direction
        dist_from_old = r - old_center
        dist_from_new = r - new_center
        
        # If drift is positive (rightward), numbers to the right of new center get bonus
        # If drift is negative (leftward), numbers to the left get bonus
        if drift_direction > 0:
            direction_weight = max(0, dist_from_new / 16)
        else:
            direction_weight = max(0, -dist_from_new / 16)
        
        freq = recent_freq.get(r, 0) / len(new_reds)
        
        # Combine: we want numbers in drift direction that are NOT already hot
        # (mix of direction signal + slight cold preference)
        score = direction_weight * 0.7 + (1 - freq) * 0.3
        red_scores.append((r, score))
    
    red_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Blue: same drift logic applied to blue (1-16 range)
    old_blue_hist = np.zeros(17)
    new_blue_hist = np.zeros(17)
    
    for b in all_blues[-window_size*2:-window_size]:
        old_blue_hist[b] += 1
    for b in all_blues[-window_size:]:
        new_blue_hist[b] += 1
    
    old_blue_center = sum(i * old_blue_hist[i] for i in range(1, 17)) / max(old_blue_hist[1:].sum(), 1)
    new_blue_center = sum(i * new_blue_hist[i] for i in range(1, 17)) / max(new_blue_hist[1:].sum(), 1)
    blue_drift = new_blue_center - old_blue_center
    
    blue_scores = []
    for b in range(1, 17):
        if blue_drift > 0:
            dw = max(0, (b - new_blue_center) / 8)
        else:
            dw = max(0, -(b - new_blue_center) / 8)
        blue_scores.append((b, dw + (1 - new_blue_hist[b] / max(new_blue_hist[1:].sum(), 1))))
    
    blue_scores.sort(key=lambda x: x[1], reverse=True)
    
    return red_scores, blue_scores


# ============================================================
# 算法C: 间隔周期模式挖掘 (Interval Pattern Mining)
# ============================================================
def algorithm_interval_pattern(draws):
    """
    原理：
      每个号码有自己的"出现间隔"规律
      计算当前间隔在历史分布中的百分位
      百分位最高的几个号码 → 最"该"出了
    
    输入: draws (全部)
    输出: (red_candidates, blue_candidates)
    """
    all_reds = get_reds(draws)
    all_blues = get_blues(draws)
    
    n_draws = len(draws)
    
    # Track last occurrence and all intervals for each number
    red_last = {}
    red_intervals = defaultdict(list)
    blue_last = {}
    blue_intervals = defaultdict(list)
    
    for idx, reds in enumerate(all_reds):
        for r in reds:
            if r in red_last:
                interval = idx - red_last[r]
                red_intervals[r].append(interval)
            red_last[r] = idx
    
    for idx, b in enumerate(all_blues):
        if b in blue_last:
            interval = idx - blue_last[b]
            blue_intervals[b].append(interval)
        blue_last[b] = idx
    
    # Current intervals (how many draws since last appearance)
    red_current = {}
    for r in range(1, 34):
        if r in red_last:
            red_current[r] = n_draws - 1 - red_last[r]
        else:
            red_current[r] = n_draws  # Never appeared
    
    blue_current = {}
    for b in range(1, 17):
        if b in blue_last:
            blue_current[b] = n_draws - 1 - blue_last[b]
        else:
            blue_current[b] = n_draws  # Never appeared
    
    # Calculate percentile of current interval vs historical distribution
    def percentile_current(current, intervals):
        if not intervals:
            return 0
        intervals = sorted(intervals)
        count_below = sum(1 for i in intervals if i < current)
        return count_below / len(intervals)
    
    red_scores = []
    for r in range(1, 34):
        pct = percentile_current(red_current[r], red_intervals.get(r, []))
        # Also boost if the current interval is > 2x average interval
        avg_interval = np.mean(red_intervals.get(r, [0])) if red_intervals[r] else 999
        boost = min(red_current[r] / max(avg_interval, 1), 3)
        red_scores.append((r, pct * 0.6 + min(boost / 10, 0.4)))
    
    red_scores.sort(key=lambda x: x[1], reverse=True)
    
    blue_scores = []
    for b in range(1, 17):
        pct = percentile_current(blue_current[b], blue_intervals.get(b, []))
        avg_interval = np.mean(blue_intervals.get(b, [0])) if blue_intervals[b] else 999
        boost = min(blue_current[b] / max(avg_interval, 1), 3)
        blue_scores.append((b, pct * 0.6 + min(boost / 10, 0.4)))
    
    blue_scores.sort(key=lambda x: x[1], reverse=True)
    
    return red_scores, blue_scores


# ============================================================
# 算法D: 低维嵌入异常检测 (Embedding Anomaly Detection)
# ============================================================
def algorithm_embedding_anomaly(draws, window_size=100):
    """
    原理：
      把每期开奖号码映射到低维空间（PCA降维到2D）
      正常情况下，大多数期数聚集在一个区域
      那些"偏离主集群"的期数就是异常期
      下一期更大概率回归主集群
      
      没有sklearn的情况下，用随机投影代替PCA
    
    输入: draws
    输出: (red_candidates, blue_candidates)
    """
    all_reds = get_reds(draws)
    all_blues = get_blues(draws)
    
    if len(draws) < 30:
        return list(range(1, 34)), list(range(1, 17))
    
    recent_draws = draws[-window_size:]
    recent_reds = get_reds(recent_draws)
    
    # Feature engineering: transform each draw into a feature vector
    def draw_to_features(reds):
        features = []
        # 1. Odd/even ratio
        odd = sum(1 for r in reds if r % 2 == 1)
        features.append(odd / 6)
        # 2. Sum
        features.append(sum(reds) / 120)  # normalize by max approx
        # 3. Spread (max - min)
        features.append((max(reds) - min(reds)) / 32)
        # 4. Percentage of numbers in 1st third (1-11)
        features.append(sum(1 for r in reds if r <= 11) / 6)
        # 5. Percentage in 2nd third (12-22)
        features.append(sum(1 for r in reds if 12 <= r <= 22) / 6)
        # 6. Standard deviation
        features.append(np.std(reds) / 10)
        # 7-9. Consecutive pairs detection
        sorted_r = sorted(reds)
        consec = sum(1 for i in range(5) if sorted_r[i+1] - sorted_r[i] == 1)
        features.append(consec / 5)
        # 10. Prime numbers
        primes = {2,3,5,7,11,13,17,19,23,29,31}
        features.append(sum(1 for r in reds if r in primes) / 6)
        return features
    
    # Build feature matrix
    X = np.array([draw_to_features(reds) for reds in recent_reds])
    
    # Random projection to 2D (poor man's PCA)
    np.random.seed(42)
    projection = np.random.randn(X.shape[1], 2) * 0.1
    # Orthonormalize
    projection[:, 0] = projection[:, 0] / np.linalg.norm(projection[:, 0])
    projection[:, 1] = projection[:, 1] - np.dot(projection[:, 1], projection[:, 0]) * projection[:, 0]
    projection[:, 1] = projection[:, 1] / np.linalg.norm(projection[:, 1])
    
    X_2d = X @ projection
    
    # Compute centroid and distances
    centroid = np.mean(X_2d, axis=0)
    distances = np.linalg.norm(X_2d - centroid, axis=1)
    
    # The last few draws' distances
    last_distances = distances[-5:]
    mean_dist = np.mean(distances)
    std_dist = np.std(distances)
    
    # If recent draws are drifting away from center, next likely regresses
    last_mean = np.mean(last_distances)
    regression_signal = last_mean - mean_dist
    
    # Score reds: prefer numbers that would bring the draw back toward center
    # We want numbers whose feature pattern is "average"
    target_odd = 0.5  # 3 odd, 3 even
    target_sum = 102  # average sum is around 102
    target_spread = 20
    
    red_scores = []
    for r in range(1, 34):
        score = 0
        # Prefer numbers that help achieve average features
        score += 1.0  # base
        red_scores.append((r, score))
    
    # Adjust: gently nudge toward the "regression" direction
    # Use a more nuanced scoring: prefer numbers that balance the feature set
    # Calculate the "target" feature profile
    target_features = np.array([0.5, 102/120, 20/32, 0.33, 0.33, np.std(range(1,34))/10, 0.2, 0.5])
    current_features = draw_to_features(recent_reds[-1])
    feature_diff = current_features - target_features
    
    red_scores = []
    for r in range(1, 34):
        score = 0
        
        # 1. Reward numbers that help balance odd/even
        if feature_diff[0] > 0.1:  # Too many odd (4+), prefer even
            score += 1.5 if r % 2 == 0 else 0.5
        elif feature_diff[0] < -0.1:  # Too many even, prefer odd
            score += 1.5 if r % 2 == 1 else 0.5
        else:
            score += 1.0  # Balanced
            
        # 2. Reward numbers that balance sum
        if feature_diff[1] > 0.05:  # Sum too high
            score += 1.5 if r <= 16 else 0.3
        elif feature_diff[1] < -0.05:  # Sum too low
            score += 1.5 if r >= 17 else 0.3
        else:
            score += 1.0
            
        # 3. Spread adjustment
        if feature_diff[2] > 0.1:  # Spread too wide
            score += 1.0 if 11 <= r <= 22 else 0.5
        elif feature_diff[2] < -0.1:  # Spread too narrow
            score += 1.0 if r <= 11 or r >= 23 else 0.5
        else:
            score += 1.0
            
        # 4. Zone balance
        if feature_diff[3] > 0.1:  # Too many zone1 numbers
            score += 0.8 if r >= 12 else 0.3
        elif feature_diff[3] < -0.1:  # Too few zone1 numbers
            score += 0.8 if r <= 11 else 0.3
            
        if feature_diff[4] > 0.1:  # Too many zone2 numbers
            score += 0.8 if r <= 11 or r >= 23 else 0.3
        elif feature_diff[4] < -0.1:  # Too few zone2 numbers
            score += 0.8 if 12 <= r <= 22 else 0.3
            
        # 5. Avoid over-consecutive
        if feature_diff[6] > 0.2:  # Too many consecutive pairs
            is_consec_with_any = False
            for prev in recent_reds[-1]:
                if abs(r - prev) == 1:
                    is_consec_with_any = True
                    break
            score += 0.3 if not is_consec_with_any else 0.1
        else:
            score += 0.5
            
        # 6. Recency bonus
        recent_flat = [x for reds in recent_reds[-20:] for x in reds]
        recency = recent_flat.count(r) / len(recent_flat) if recent_flat else 0
        score += recency * 0.3  # Slight bonus for numbers appearing moderately recently
        
        red_scores.append((r, score))
    
    # Blue: use current anomaly score
    # Recent blues
    recent_blues = all_blues[-min(20, len(all_blues)):]
    blue_freq = Counter(recent_blues)
    
    # If recent blue is very consistent (same number), regress away from it
    if len(set(recent_blues[-5:])) <= 2:
        # Overplayed blue - pick something different
        blue_scores = [(b, 1 - blue_freq.get(b, 0) / len(recent_blues)) for b in range(1, 17)]
    else:
        blue_scores = [(b, blue_freq.get(b, 0) / len(recent_blues) + 0.5) for b in range(1, 17)]
    
    blue_scores.sort(key=lambda x: x[1], reverse=True)
    
    return red_scores, blue_scores


# ============================================================
# 统一预测接口
# ============================================================
def run_all_algorithms():
    """Run all 4 algorithms and return predictions"""
    draws = get_all_draws()
    
    if len(draws) < 50:
        print("数据不足，无法预测")
        return {}
    
    latest_period = draws[-1]['period']
    
    predictions = {}
    
    # Algorithm A
    red_candidates, blue_candidates = algorithm_association_break(draws)
    predictions['association_break'] = {
        'name': '关联断裂',
        'numbers': pick_numbers(red_candidates, blue_candidates),
        'red_candidates': red_candidates[:15],
        'blue_candidates': blue_candidates[:8],
    }
    
    # Algorithm B
    red_candidates, blue_candidates = algorithm_density_drift(draws)
    predictions['density_drift'] = {
        'name': '密度漂移',
        'numbers': pick_numbers(red_candidates, blue_candidates),
        'red_candidates': red_candidates[:15],
        'blue_candidates': blue_candidates[:8],
    }
    
    # Algorithm C
    red_candidates, blue_candidates = algorithm_interval_pattern(draws)
    predictions['interval_pattern'] = {
        'name': '间隔周期',
        'numbers': pick_numbers(red_candidates, blue_candidates),
        'red_candidates': red_candidates[:15],
        'blue_candidates': blue_candidates[:8],
    }
    
    # Algorithm D
    red_candidates, blue_candidates = algorithm_embedding_anomaly(draws)
    predictions['embedding_anomaly'] = {
        'name': '异常回归',
        'numbers': pick_numbers(red_candidates, blue_candidates),
        'red_candidates': red_candidates[:15],
        'blue_candidates': blue_candidates[:8],
    }
    
    # Weighted voting fusion
    from database import get_algorithm_weights
    weights = get_algorithm_weights()
    
    fusion_votes = defaultdict(int)
    for algo_key, pred in predictions.items():
        w = weights.get(algo_key, 1.0)
        nums = pred['numbers']
        if nums:
            for r in nums[:6]:
                fusion_votes[r] += w
            fusion_votes[('blue', nums[6])] += w
    
    # Top 6 reds by weighted votes
    red_votes = {k: v for k, v in fusion_votes.items() if not isinstance(k, tuple)}
    blue_votes = {k[1]: v for k, v in fusion_votes.items() if isinstance(k, tuple)}
    
    fusion_reds = sorted(red_votes.keys(), key=lambda x: red_votes[x], reverse=True)[:6]
    fusion_blue = sorted(blue_votes.keys(), key=lambda x: blue_votes[x], reverse=True)[0]
    
    predictions['fusion'] = {
        'name': '综合决策',
        'numbers': sorted(fusion_reds) + [fusion_blue],
    }
    
    # ============================================================
    # 算法E: 老彩民融合算法 (Traditional Wisdom Fusion)
    # ============================================================
    predictions['traditional'] = run_traditional_fusion(draws, predictions)
    
    return predictions


# ============================================================
# 算法E: 老彩民经验融合
# 在4个AI算法分数基础上，叠加老彩民的传统经验评分
# ============================================================
def run_traditional_fusion(draws, ai_predictions):
    """
    融合方案：
    1. 先取4个AI算法的候选分数作为基础
    2. 叠加老彩民传统因子评分：
       - 重号评分（上期号码保留）
       - 邻号评分（上期±1）
       - 和值评分（靠近均值102的加分）
       - 奇偶比评分（3:3和4:2加分）
       - 三区分布评分（2:2:2等常见分布加分）
    3. 从融合分数中取前6 + 蓝球
    """
    # 获取AI算法的原始候选分数
    all_scores = defaultdict(float)
    
    weights = {'association_break': 1.0, 'density_drift': 1.0, 
               'interval_pattern': 1.0, 'embedding_anomaly': 1.0}
    
    # 收集所有AI算法的分数
    # 关联断裂
    rc, bc = algorithm_association_break(draws)
    if isinstance(rc[0], tuple):
        for n, s in rc:
            all_scores[('red', n)] += s * 1.0
    if isinstance(bc[0], tuple):
        for n, s in bc:
            all_scores[('blue', n)] += s * 1.0
    
    # 密度漂移
    rc, bc = algorithm_density_drift(draws)
    if isinstance(rc[0], tuple):
        for n, s in rc:
            all_scores[('red', n)] += s * 1.0
    if isinstance(bc[0], tuple):
        for n, s in bc:
            all_scores[('blue', n)] += s * 1.0
    
    # 间隔周期
    rc, bc = algorithm_interval_pattern(draws)
    if isinstance(rc[0], tuple):
        for n, s in rc:
            all_scores[('red', n)] += s * 1.0
    if isinstance(bc[0], tuple):
        for n, s in bc:
            all_scores[('blue', n)] += s * 1.0
    
    # 异常回归
    rc, bc = algorithm_embedding_anomaly(draws)
    if isinstance(rc[0], tuple):
        for n, s in rc:
            all_scores[('red', n)] += s * 1.0
    if isinstance(bc[0], tuple):
        for n, s in bc:
            all_scores[('blue', n)] += s * 1.0
    
    # 归一化AI分数到0-1
    red_scores_norm = {}
    blue_scores_norm = {}
    
    red_scores_list = [(k[1], v) for k, v in all_scores.items() if k[0] == 'red']
    blue_scores_list = [(k[1], v) for k, v in all_scores.items() if k[0] == 'blue']
    
    if red_scores_list:
        max_r = max(v for _, v in red_scores_list)
        min_r = min(v for _, v in red_scores_list)
        for n, v in red_scores_list:
            red_scores_norm[n] = (v - min_r) / (max_r - min_r) if max_r > min_r else 0.5
    
    if blue_scores_list:
        max_b = max(v for _, v in blue_scores_list)
        min_b = min(v for _, v in blue_scores_list)
        for n, v in blue_scores_list:
            blue_scores_norm[n] = (v - min_b) / (max_b - min_b) if max_b > min_b else 0.5
    
    # 获取上期号码
    last = draws[-1]
    last_reds = [last['red1'], last['red2'], last['red3'],
                 last['red4'], last['red5'], last['red6']]
    last_blue = last['blue']
    
    # ==================== 老彩民因子 ====================
    
    # 因子1: 重号 — 上期号码保留（平均每期1.08个重号）
    repeat_bonus = {}
    for r in last_reds:
        repeat_bonus[r] = 0.8  # 重号加分
    
    # 因子2: 邻号 — 上期号码±1（平均每期1.91个邻号）
    neighbor_bonus = {}
    for r in last_reds:
        if r > 1:
            neighbor_bonus[r - 1] = neighbor_bonus.get(r - 1, 0) + 0.5
        if r < 33:
            neighbor_bonus[r + 1] = neighbor_bonus.get(r + 1, 0) + 0.5
    
    # 因子3: 和值评分 — 靠近均值102的加分
    # 给定6个号码，想让总和靠近102，每个号码的理想值≈102/6=17
    sum_bonus = {}
    for r in range(1, 34):
        # 越靠近17分的越多
        sum_bonus[r] = max(0, 1 - abs(r - 17) / 16)
    
    # 因子4: 奇偶比 — 偏爱3:3和4:2
    # 在选号阶段处理
    odd_bonus = {}
    for r in range(1, 34):
        odd_bonus[r] = 1.0  # 奇偶在选号时处理
    
    # 因子5: 三区分布 — 偏爱2:2:2等均衡分布
    # 也在选号阶段处理
    
    # ==================== 综合评分 ====================
    final_red_scores = {}
    for r in range(1, 34):
        score = 0
        # AI分数（权重0.6）
        score += red_scores_norm.get(r, 0) * 0.6
        # 重号（权重0.15）
        score += repeat_bonus.get(r, 0) * 0.15
        # 邻号（权重0.15）
        score += neighbor_bonus.get(r, 0) * 0.15
        # 和值倾向（权重0.1）
        score += sum_bonus.get(r, 0) * 0.10
        final_red_scores[r] = score
    
    # 蓝球评分
    final_blue_scores = {}
    for b in range(1, 17):
        score = 0
        # AI分数（权重0.5）
        score += blue_scores_norm.get(b, 0) * 0.5
        # 重号 — 上期蓝球（权重0.25）
        if b == last_blue:
            score += 0.25
        # 邻号 — 上期±1（权重0.25）
        if abs(b - last_blue) == 1:
            score += 0.25
        final_blue_scores[b] = score
    
    # ==================== 选号（考虑全局分布） ====================
    
    # 选号策略：从高分号码中，选出一组分布合理的6个号码
    # 不强制奇偶比，而是让号码自然分布在数轴上
    sorted_reds = sorted(final_red_scores.items(), key=lambda x: x[1], reverse=True)
    
    # 把33个红球按分数分成3档
    top_third = len(sorted_reds) // 3
    tier1 = sorted_reds[:top_third]          # 高分区
    tier2 = sorted_reds[top_third:top_third*2]  # 中分区
    tier3 = sorted_reds[top_third*2:]           # 低分区
    
    # 最佳组合搜索：从各档中选，保证分布
    best_combo = None
    best_combo_score = -999
    
    # 尝试不同档位组合
    # (从tier1选几个, 从tier2选几个, 从tier3选几个)
    tier_patterns = [
        (4, 2, 0), (3, 2, 1), (3, 3, 0), 
        (2, 2, 2), (4, 1, 1), (5, 1, 0),
    ]
    
    for t1_count, t2_count, t3_count in tier_patterns:
        if t1_count > len(tier1) or t2_count > len(tier2) or t3_count > len(tier3):
            continue
        
        t1_pick = tier1[:t1_count]
        t2_pick = tier2[:t2_count]
        t3_pick = tier3[:t3_count]
        
        combo = t1_pick + t2_pick + t3_pick
        
        # 只取号码
        combo_nums = sorted([n for n, _ in combo])[:6]
        
        # 评分：总分 + 分布评分
        score_sum = sum(s for _, s in combo[:6])
        
        # 分布评分：跨度至少15，但不能太极端
        span = combo_nums[-1] - combo_nums[0]
        span_score = 0
        if 15 <= span <= 28:
            span_score = 0.2
        elif span >= 10:
            span_score = 0.1
        
        # 间距评分：避免太多小间距聚集
        gaps = [combo_nums[i+1] - combo_nums[i] for i in range(len(combo_nums)-1)]
        small_gaps = sum(1 for g in gaps if g == 1)
        if small_gaps <= 2:
            gap_score = 0.1
        elif small_gaps <= 3:
            gap_score = 0.05
        else:
            gap_score = 0
        
        total = score_sum + span_score + gap_score
        
        if total > best_combo_score:
            best_combo_score = total
            best_combo = combo_nums
    
    # 备选：直接取前6高分（如果上面的组合都不够好）
    if not best_combo:
        best_combo = sorted([n for n, _ in sorted_reds[:6]])
    
    # 蓝球
    best_blue = sorted(final_blue_scores.items(), key=lambda x: x[1], reverse=True)[0][0]
    
    return {
        'name': '传统融合',
        'numbers': (best_combo or list(range(1, 7))) + [best_blue],
        'red_candidates': sorted(final_red_scores.items(), key=lambda x: x[1], reverse=True)[:15],
        'blue_candidates': sorted(final_blue_scores.items(), key=lambda x: x[1], reverse=True)[:8],
        'ai_weights': dict(weights),
    }


if __name__ == '__main__':
    from database import get_all_draws, init_db
    init_db()
    
    predictions = run_all_algorithms()
    latest = get_all_draws()[-1]
    
    print(f"最新期号: {latest['period']} ({latest['date']})")
    print(f"开奖号码: {' '.join(str(latest[f'red{i}']) for i in range(1,7))} + {latest['blue']}")
    print()
    
    for key, pred in predictions.items():
        nums = pred['numbers']
        if nums:
            print(f"{pred['name']:8s}: {' '.join(f'{n:02d}' for n in nums[:6])} + {nums[6]:02d}")
