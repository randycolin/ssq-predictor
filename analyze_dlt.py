#!/usr/bin/env python3
"""大乐透开奖结构分析"""
from dlt_database import get_all_dlt_draws
import numpy as np
from collections import Counter

draws = get_all_dlt_draws()
print(f"总计 {len(draws)} 期\n")

# ============ 前区35选5 ============
front_sums = []
front_odds = []
front_spans = []
front_consec = []
front_zones = []  # 三区: 1-12, 13-24, 25-35

for d in draws:
    fs = sorted([d['front1'], d['front2'], d['front3'], d['front4'], d['front5']])
    front_sums.append(sum(fs))
    front_odds.append(sum(1 for n in fs if n % 2 == 1))
    front_spans.append(fs[-1] - fs[0])
    gaps = [fs[i+1]-fs[i] for i in range(4)]
    front_consec.append(sum(1 for g in gaps if g == 1))
    z1 = sum(1 for n in fs if n <= 12)
    z2 = sum(1 for n in fs if 13 <= n <= 24)
    z3 = sum(1 for n in fs if n >= 25)
    front_zones.append((z1, z2, z3))

print("=" * 60)
print("【前区】结构分布")
print("=" * 60)

print(f"\n【和值】均值={np.mean(front_sums):.1f} 中位数={np.median(front_sums):.0f} 标准差={np.std(front_sums):.1f}")
bins = [50,70,90,110,130,150,170]
print(f"{'范围':>10}: {'次数':>6} {'占比':>8}")
for i, b in enumerate(bins):
    if i == 0:
        cnt = sum(1 for s in front_sums if s < bins[0])
        print(f"{'<'+str(bins[0]):>10}: {cnt:>6}  {cnt/len(front_sums)*100:>7.1f}%")
    elif i < len(bins)-1:
        cnt = sum(1 for s in front_sums if bins[i-1] <= s < bins[i])
        print(f"{bins[i-1]:>3}-{bins[i]:>3}: {cnt:>6}  {cnt/len(front_sums)*100:>7.1f}%")
    else:
        cnt = sum(1 for s in front_sums if s >= bins[-1])
        print(f"{'>='+str(bins[-1]):>10}: {cnt:>6}  {cnt/len(front_sums)*100:>7.1f}%")
cnt_mid = sum(1 for s in front_sums if 70 <= s <= 130)
print(f"  70-130区间占比: {cnt_mid/len(front_sums)*100:.1f}%")

print(f"\n【奇偶】")
odd_counts = Counter(front_odds)
for odd in sorted(odd_counts):
    cnt = odd_counts[odd]
    bar = "█" * int(cnt / max(odd_counts.values()) * 30)
    print(f"  {odd}奇{5-odd}偶: {cnt:>5}次 ({cnt/len(front_sums)*100:>5.1f}%) {bar}")

print(f"\n【跨度】均值={np.mean(front_spans):.1f} 中位数={np.median(front_spans):.0f}")
span_bins = [(0,10),(11,15),(16,20),(21,25),(26,30),(31,34)]
print(f"{'范围':>8}: {'次数':>6} {'占比':>8}")
for lo, hi in span_bins:
    cnt = sum(1 for s in front_spans if lo <= s <= hi)
    bar = "█" * int(cnt / len(front_spans) * 100)
    print(f"  {lo:>2}-{hi:>2}: {cnt:>5}  {cnt/len(front_spans)*100:>6.1f}% {bar}")
cnt_mid_s = sum(1 for s in front_spans if 18 <= s <= 30)
print(f"  18-30区间占比: {cnt_mid_s/len(front_spans)*100:.1f}%")

print(f"\n【连号】")
consec_counts = Counter(front_consec)
for c in sorted(consec_counts):
    cnt = consec_counts[c]
    bar = "█" * int(cnt / max(consec_counts.values()) * 30)
    print(f"  {c}组连号: {cnt:>5}次 ({cnt/len(front_sums)*100:>5.1f}%) {bar}")

print(f"\n【三区分布（1-12 / 13-24 / 25-35）】")
zone_counts = Counter(front_zones)
print(f"{'分布':>10}: {'次数':>6} {'占比':>8}")
for z, cnt in sorted(zone_counts.items(), key=lambda x: -x[1])[:10]:
    bar = "█" * int(cnt / max(zone_counts.values()) * 30)
    print(f"  {z[0]}:{z[1]}:{z[2]}: {cnt:>5}次 ({cnt/len(front_sums)*100:>5.1f}%) {bar}")

# ============ 后区12选2 ============
back_sums = []
back_odds = []
back_spans = []

for d in draws:
    bs = sorted([d['back1'], d['back2']])
    back_sums.append(sum(bs))
    back_odds.append(sum(1 for n in bs if n % 2 == 1))
    back_spans.append(bs[1] - bs[0])

print()
print("=" * 60)
print("【后区】结构分布")
print("=" * 60)

print(f"\n【和值】均值={np.mean(back_sums):.1f} 中位数={np.median(back_sums):.0f}")
bins_b = [3,5,7,9,11,13,15,17,19,23]
print(f"{'范围':>8}: {'次数':>6} {'占比':>8}")
for i, b in enumerate(bins_b):
    if i == 0:
        cnt = sum(1 for s in back_sums if s < bins_b[0])
        print(f"{'<'+str(bins_b[0]):>8}: {cnt:>5}  {cnt/len(back_sums)*100:>6.1f}%")
    elif i < len(bins_b)-1:
        cnt = sum(1 for s in back_sums if bins_b[i-1] <= s < bins_b[i])
        print(f"{bins_b[i-1]:>2}-{bins_b[i]:>2}: {cnt:>5}  {cnt/len(back_sums)*100:>6.1f}%")
    else:
        cnt = sum(1 for s in back_sums if s >= bins_b[-1])
        print(f"{'>='+str(bins_b[-1]):>8}: {cnt:>5}  {cnt/len(back_sums)*100:>6.1f}%")

print(f"\n【奇偶】")
for odd in range(3):
    cnt = sum(1 for o in back_odds if o == odd)
    bar = "█" * int(cnt / len(back_odds) * 100)
    print(f"  {odd}奇{2-odd}偶: {cnt:>5}次 ({cnt/len(back_sums)*100:>5.1f}%) {bar}")

print(f"\n【跨度】")
span_b = Counter(back_spans)
for s in sorted(span_b):
    cnt = span_b[s]
    bar = "█" * int(cnt / max(span_b.values()) * 25)
    print(f"  跨度{s}: {cnt:>5}次 ({cnt/len(back_sums)*100:>5.1f}%) {bar}")
