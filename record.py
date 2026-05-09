#!/usr/bin/env python3
"""
中奖记录展示 — 双色球+大乐透合并展示
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_all_draws, get_predictions_with_results, get_conn, save_prediction_result
from dlt_database import get_all_dlt_draws, get_dlt_predictions_with_results, save_dlt_prediction_result

logger = logging.getLogger(__name__)

DLT_AVAILABLE = True  # 由 bot.py 覆写


async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /record 命令 — 双色球+大乐透合并展示"""
    # ===== 1. 双色球自动比对 =====
    try:
        draws = get_all_draws()
        conn = get_conn()
        uncheckeds = conn.execute('''
            SELECT p.* FROM predictions p
            LEFT JOIN prediction_results pr ON p.period = pr.period AND p.algorithm = pr.algorithm
            WHERE pr.id IS NULL
        ''').fetchall()
        conn.close()
        for p in uncheckeds:
            for d in draws:
                if d['period'] == p['period']:
                    pred_reds = {p['red1'], p['red2'], p['red3'], p['red4'], p['red5'], p['red6']}
                    pred_blue = p['blue']
                    actual_reds = {d['red1'], d['red2'], d['red3'], d['red4'], d['red5'], d['red6']}
                    actual_blue = d['blue']
                    red_hit = len(pred_reds & actual_reds)
                    blue_hit = 1 if pred_blue == actual_blue else 0
                    prize_level = None
                    from bot_utils import ssq_prize_level
                    prize_level = ssq_prize_level(red_hit, blue_hit)
                    save_prediction_result(p['period'], 'scorecard', red_hit, blue_hit, prize_level)
                    break
    except Exception as e:
        logger.error(f"双色球自动比对失败: {e}")

    # ===== 2. 大乐透自动比对 =====
    if context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        try:
            dlt_draws = get_all_dlt_draws()
            conn_dlt = get_conn()
            dlt_uncheckeds = conn_dlt.execute('''
                SELECT p.* FROM dlt_predictions p
                LEFT JOIN dlt_prediction_results pr ON p.period = pr.period AND p.algorithm = pr.algorithm
                WHERE pr.id IS NULL
            ''').fetchall()
            conn_dlt.close()
            for p in dlt_uncheckeds:
                for d in dlt_draws:
                    if d['period'] == p['period']:
                        pred_fronts = {p[f'front{i}'] for i in range(1, 6)}
                        pred_backs = {p[f'back{i}'] for i in range(1, 3)}
                        actual_fronts = {d[f'front{i}'] for i in range(1, 6)}
                        actual_backs = {d[f'back{i}'] for i in range(1, 3)}
                        fh = len(pred_fronts & actual_fronts)
                        bh = len(pred_backs & actual_backs)
                        prize = None
                        from bot_utils import dlt_prize_level
                        prize = dlt_prize_level(fh, bh)
                        save_dlt_prediction_result(p['period'], 'dlt_scorecard', fh, bh, prize)
                        break
        except Exception as e:
            logger.error(f"大乐透自动比对失败: {e}")

    # ===== 3. 拉取记录 =====
    ssq_records = []
    dlt_records = []
    try:
        ssq_records = get_predictions_with_results(30)
    except Exception as e:
        logger.error(f"获取双色球记录失败: {e}")

    if context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        try:
            dlt_records = get_dlt_predictions_with_results(20)
        except Exception as e:
            logger.error(f"获取大乐透记录失败: {e}")

    # ===== 4. 组合统计 =====
    output = "📋 <b>🎯 中奖记录总览</b>\n"
    output += "═" * 25 + "\n\n"

    # 双色球统计
    ssq_total = 0
    ssq_wins = 0
    ssq_prizes = {}
    for r in ssq_records:
        if r['algorithm'] != 'scorecard': continue
        ssq_total += 1
        if r['prize_level']:
            ssq_wins += 1
            ssq_prizes[r['prize_level']] = ssq_prizes.get(r['prize_level'], 0) + 1

    output += "🔴 <b>双色球</b>\n"
    if ssq_total > 0:
        output += f"  预测 {ssq_total} 次 | 中奖 {ssq_wins} 次 | 中奖率 {ssq_wins / ssq_total * 100:.1f}%\n"
        if ssq_prizes:
            for level, count in sorted(ssq_prizes.items(),
                                        key=lambda x: {'🥇': 0, '🥈': 1, '🥉': 2}.get(x[0][0], 9)):
                output += f"    {level} × {count}\n"
    else:
        output += "  暂无记录\n"
    output += "\n"

    # 大乐透统计
    if context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        dlt_total = 0
        dlt_wins = 0
        dlt_prizes = {}
        for r in dlt_records:
            if r['algorithm'] != 'dlt_scorecard': continue
            dlt_total += 1
            if r['prize_level']:
                dlt_wins += 1
                dlt_prizes[r['prize_level']] = dlt_prizes.get(r['prize_level'], 0) + 1

        output += "🟡 <b>大乐透</b>\n"
        if dlt_total > 0:
            output += f"  预测 {dlt_total} 次 | 中奖 {dlt_wins} 次 | 中奖率 {dlt_wins / dlt_total * 100:.1f}%\n"
            if dlt_prizes:
                for level, count in sorted(dlt_prizes.items(),
                                            key=lambda x: {'🥇': 0, '🥈': 1, '🥉': 2}.get(x[0][0], 9)):
                    output += f"    {level} × {count}\n"
        else:
            output += "  暂无记录\n"
        output += "\n"

    # ===== 5. 双色球最近10条 =====
    output += "═" * 25 + "\n"
    output += "🔴 <b>双色球 · 最近预测</b>\n\n"
    ssq_count = 0
    for r in ssq_records:
        if r['algorithm'] != 'scorecard': continue
        ssq_count += 1
        if ssq_count > 10: break
        red_str = ' '.join(f"{r[f'red{i}']:02d}" for i in range(1, 7))
        dt = r['created_at'][:10] if r.get('created_at') else ''
        output += f"第{r['period']}期  {red_str} + {r['blue']:02d}  ({dt})\n"
        if r['red_hit'] is not None:
            if r['prize_level']:
                output += f"  ✅ 红{r['red_hit']}+蓝{r['blue_hit']} → {r['prize_level']}\n"
            else:
                output += f"  ❌ 红{r['red_hit']}+蓝{r['blue_hit']} 未中奖\n"
        else:
            output += f"  ⏳ 等待开奖\n"
    if ssq_count == 0:
        output += "  暂无记录\n"
    output += "\n"

    # ===== 6. 大乐透最近5条 =====
    if context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        output += "═" * 25 + "\n"
        output += "🟡 <b>大乐透 · 最近预测</b>\n\n"
        dlt_count = 0
        for r in dlt_records:
            if r['algorithm'] != 'dlt_scorecard': continue
            dlt_count += 1
            if dlt_count > 5: break
            f_str = ' '.join(f"{r[f'front{i}']:02d}" for i in range(1, 6))
            b_str = ' '.join(f"{r[f'back{i}']:02d}" for i in range(1, 3))
            dt = r['created_at'][:10] if r.get('created_at') else ''
            output += f"第{r['period']}期  {f_str} + {b_str}  ({dt})\n"
            if r['front_hit'] is not None:
                if r['prize_level']:
                    output += f"  ✅ 前{r['front_hit']}+后{r['back_hit']} → {r['prize_level']}\n"
                else:
                    output += f"  ❌ 前{r['front_hit']}+后{r['back_hit']} 未中奖\n"
            else:
                output += f"  ⏳ 等待开奖\n"
        if dlt_count == 0:
            output += "  暂无记录\n"

    await update.message.reply_text(output, parse_mode='HTML')
