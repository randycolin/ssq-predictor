#!/usr/bin/env python3
"""分析双色球开奖结构分布"""
from database import get_all_draws, init_db
import numpy as np
from collections import Counter

init_db()
draws = get_all_draws()

print(f"总计 {len(draws)} 期\n")

# ============ 采集结构数据 ============
sums = []
odds = []
spans = []
consecutive_counts = []
repeats = []
zones = []  # 三区分布，如 (2,2,2), (3,2,1)

for i in range(1, len(draws)):
    d = draws[i]
    prev = draws[i-1]
    
    reds = sorted([d['red1'], d['red2'], d['red3'], d['red4'], d['red5'], d['red6']])
    prev_reds = [prev['red1'], prev['red2'], prev['red3'], prev['red4'], prev['red5'], prev['red6']]
    
    sums.append(sum(reds))
    odds.append(sum(1 for n in reds if n % 2 == 1))
    spans.append(reds[-1] - reds[0])
    
    gaps = [reds[i+1] - reds[i] for i in range(5)]
    consecutive_counts.append(sum(1 for g in gaps if g == 1))
    
    repeats.append(len(set(reds) & set(prev_reds)))
    
    low = sum(1 for n in reds if n <= 11)
    mid = sum(1 for n in reds if 12 <= n <= 22)
    high = sum(1 for n in reds if n >= 23)
    zones.append((low, mid, high))

# ============ 输出 ============
print("=" * 60)
print("1️⃣  和值分布")
print("=" * 60)
sum_arr = np.array(sums)
print(f"  均值: {np.mean(sum_arr):.1f}  中位数: {np.median(sum_arr):.0f}")
print(f"  标准差: {np.std(sum_arr):.1f}")
print(f"  最小值: {sum_arr.min()}  最大值: {sum_arr.max()}")
print()
# 分段统计
bins = [70, 80, 90, 100, 110, 120, 130, 140]
print(f"{'范围':>12}: {'次数':>6} {'占比':>8}")
for i in range(len(bins)):
    if i == 0:
        cnt = sum(1 for s in sums if s < bins[0])
        print(f"{'<'+str(bins[0]):>12}: {cnt:>6}  {cnt/len(sums)*100:>7.1f}%")
    elif i < len(bins) - 1:
        cnt = sum(1 for s in sums if bins[i-1] <= s < bins[i])
        print(f"{bins[i-1]:>3}-{bins[i]:>3}: {cnt:>6}  {cnt/len(sums)*100:>7.1f}%")
    else:
        cnt = sum(1 for s in sums if s >= bins[-1])
        print(f"{'>='+str(bins[-1]):>12}: {cnt:>6}  {cnt/len(sums)*100:>7.1f}%")
cnt_80_130 = sum(1 for s in sums if 80 <= s <= 130)
print(f"\n  80-130区间占比: {cnt_80_130/len(sums)*100:.1f}%")

print()
print("=" * 60)
print("2️⃣  奇偶分布")
print("=" * 60)
odd_counts = Counter(odds)
for odd in sorted(odd_counts):
    cnt = odd_counts[odd]
    bar = "█" * int(cnt / max(odd_counts.values()) * 30)
    print(f"  {odd}奇{6-odd}偶: {cnt:>5}次 ({cnt/len(sums)*100:>5.1f}%) {bar}")

print()
print("=" * 60)
print("3️⃣  跨度分布")
print("=" * 60)
span_arr = np.array(spans)
print(f"  均值: {np.mean(span_arr):.1f}  中位数: {np.median(span_arr):.0f}")
span_bins = [(0,10),(11,15),(16,20),(21,25),(26,30),(31,32)]
print(f"{'范围':>10}: {'次数':>6} {'占比':>8}")
for lo, hi in span_bins:
    cnt = sum(1 for s in spans if lo <= s <= hi)
    bar = "█" * int(cnt / len(spans) * 100)
    print(f"{lo:>2}-{hi:>2}: {cnt:>6}  {cnt/len(spans)*100:>6.1f}% {bar}")

print()
print("=" * 60)
print("4️⃣  连号分布（相邻两号差=1的组数）")
print("=" * 60)
consec_counts = Counter(consecutive_counts)
for c in sorted(consec_counts):
    cnt = consec_counts[c]
    bar = "█" * int(cnt / max(consec_counts.values()) * 30)
    print(f"  {c}组连号: {cnt:>5}次 ({cnt/len(sums)*100:>5.1f}%) {bar}")

print()
print("=" * 60)
print("5️⃣  重号分布（跟上期重复的个数）")
print("=" * 60)
repeat_counts = Counter(repeats)
for r in sorted(repeat_counts):
    cnt = repeat_counts[r]
    bar = "█" * int(cnt / max(repeat_counts.values()) * 30)
    print(f"  {r}个重号: {cnt:>5}次 ({cnt/len(sums)*100:>5.1f}%) {bar}")

print()
print("=" * 60)
print("6️⃣  三区分布（一区1-11 / 二区12-22 / 三区23-33）")
print("=" * 60)
zone_counts = Counter(zones)
print(f"{'分布':>12}: {'次数':>6} {'占比':>8}")
for z, cnt in sorted(zone_counts.items(), key=lambda x: -x[1])[:15]:
    bar = "█" * int(cnt / max(zone_counts.values()) * 30)
    print(f"  {z[0]}:{z[1]}:{z[2]}: {cnt:>5}次 ({cnt/len(sums)*100:>5.1f}%) {bar}")
