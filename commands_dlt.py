#!/usr/bin/env python3
"""
大乐透Bot命令 — /dlt, /dlt_stats, /dlt_record, /dlt_backtest, /dlt_update
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_conn
from dlt_database import (
    get_all_dlt_draws, get_latest_dlt_draw, get_dlt_draw_count,
    save_dlt_prediction, save_dlt_prediction_result, get_dlt_predictions_with_results
)
from dlt_scorecard import dlt_predict_detailed, run_dlt_backtest
from fetch_dlt import fetch_dlt_latest

logger = logging.getLogger(__name__)

DLT_AVAILABLE = True  # 由 bot.py 实际设置，这里赋默认值；bot.py import 后会覆盖


async def dlt_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt 命令"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        await update.message.reply_text("❌ 大乐透模块未加载")
        return

    msg = await update.message.reply_text("🔄 正在计算大乐透...")

    try:
        result = dlt_predict_detailed()
        if isinstance(result, str):
            await msg.edit_text(result)
        elif 'error' in result:
            await msg.edit_text(f"❌ {result['error']}")
        else:
            front_str = ' '.join(f"{n:02d}" for n in result['front_numbers'])
            back_str = ' '.join(f"{n:02d}" for n in result['back_numbers'])

            output = f"🎯 <b>大乐透预测 · 第{result['period']}期</b>\n"
            output += f"📅 基于 {result['date']} 之前全部数据\n"
            output += f"💾 共 {result['total_draws']} 期历史数据\n"
            output += "─" * 30 + "\n\n"
            output += f"🔴 <b>前区: {front_str}</b>\n"
            output += f"🔵 <b>后区: {back_str}</b>\n\n"
            output += "📊 前区评分TOP10:\n"
            for n, s in result['front_scores'][:10]:
                mark = "⭐" if n in result['front_numbers'] else "  "
                output += f"  {mark} {n:02d}: {s:.2f}\n"
            output += "\n🔵 后区评分:\n"
            for n, s in result['back_scores'][:5]:
                mark = "⭐" if n in result['back_numbers'] else "  "
                output += f"  {mark} {n:02d}: {s:.2f}\n"

            # 保存预测
            try:
                save_dlt_prediction(result['period'], 'dlt_scorecard',
                                   result['front_numbers'], result['back_numbers'])
            except Exception as e:
                logger.error(f"保存大乐透预测失败: {e}")

            keyboard = [
                [InlineKeyboardButton("🎯 再预测", callback_data='dlt_predict'),
                 InlineKeyboardButton("📊 大乐透数据", callback_data='dlt_stats')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"DLT predict error: {e}")
        await msg.edit_text(f"❌ 预测失败: {str(e)}")


async def dlt_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """大乐透数据统计"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        return

    try:
        draws = get_all_dlt_draws()
        latest = get_latest_dlt_draw()
        if not latest:
            return

        front_str = ' '.join(f"{latest[f'front{i}']:02d}" for i in range(1, 6))
        back_str = ' '.join(f"{latest[f'back{i}']:02d}" for i in range(1, 3))

        output = f"📊 <b>大乐透系统状态</b>\n"
        output += "─" * 30 + "\n"
        output += f"📅 数据更新至: {latest['date']}\n"
        output += f"💾 历史数据: {len(draws)} 期\n"
        output += f"🆕 最新: 第{latest['period']}期\n"
        output += f"🔢 {front_str} + {back_str}\n\n"
        output += "📌 开奖日: 周一/三/六"

        keyboard = [[InlineKeyboardButton("🎯 大乐透预测", callback_data='dlt_predict'),
                     InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(output, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"DLT stats error: {e}")


async def dlt_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """大乐透预测记录"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        return

    # 自动比对未开奖预测
    try:
        draws = get_all_dlt_draws()
        conn = get_conn()
        uncheckeds = conn.execute('''
            SELECT p.* FROM dlt_predictions p
            LEFT JOIN dlt_prediction_results pr ON p.period = pr.period AND p.algorithm = pr.algorithm
            WHERE pr.id IS NULL
        ''').fetchall()
        conn.close()

        for p in uncheckeds:
            for d in draws:
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
        logger.error(f"DLT record auto-match error: {e}")

    records = get_dlt_predictions_with_results(20)
    if not records:
        await update.message.reply_text("📋 暂无大乐透预测记录")
        return

    output = "📋 <b>大乐透预测记录</b>\n" + "─" * 30 + "\n\n"

    total = 0
    wins = 0
    for r in records:
        if r['algorithm'] != 'dlt_scorecard': continue
        total += 1
        if r['prize_level']: wins += 1

    if total > 0:
        output += f"📊 预测{total}次 中奖{wins}次 ({wins / total * 100:.1f}%)\n\n"

    count = 0
    for r in records:
        if r['algorithm'] != 'dlt_scorecard': continue
        count += 1
        f_str = ' '.join(f"{r[f'front{i}']:02d}" for i in range(1, 6))
        b_str = ' '.join(f"{r[f'back{i}']:02d}" for i in range(1, 3))
        output += f"第{r['period']}期  {f_str} + {b_str}\n"
        if r['front_hit'] is not None:
            if r['prize_level']:
                output += f"  ✅ 前{r['front_hit']}+后{r['back_hit']} → {r['prize_level']}\n"
            else:
                output += f"  ❌ 前{r['front_hit']}+后{r['back_hit']} 未中奖\n"
        else:
            output += f"  ⏳ 等待开奖\n"
        if count >= 5:
            break

    keyboard = [[InlineKeyboardButton("📊 大乐透数据", callback_data='dlt_stats'),
                 InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
    await update.message.reply_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def dlt_backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt_backtest 命令"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        await update.message.reply_text("❌ 大乐透模块未加载")
        return

    keyboard = [
        [InlineKeyboardButton("最近20期", callback_data='dlt_bt_20'),
         InlineKeyboardButton("最近50期", callback_data='dlt_bt_50')],
        [InlineKeyboardButton("最近100期", callback_data='dlt_bt_100'),
         InlineKeyboardButton("最近200期", callback_data='dlt_bt_200')],
    ]
    await update.message.reply_text(
        "📊 <b>大乐透回测</b>\n选择回测期数：",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def run_dlt_backtest_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, periods: int):
    """执行大乐透详细回测"""
    msg = await update.callback_query.edit_message_text(f"🔄 正在回测大乐透最近{periods}期，请稍候...")

    try:
        result = run_dlt_backtest(periods)
        if 'error' in result:
            await msg.edit_text(f"❌ {result['error']}")
            return

        n = result['n']
        output = f"📊 <b>大乐透回测报告（最近{periods}期）</b>\n"
        output += "─" * 26 + "\n\n"
        output += "🎯 <b>中奖统计（按大乐透规则）</b>\n"
        output += f"   🥇 一等奖(5+2): {result['prize_1']}次\n"
        output += f"   🥈 二等奖(5+1): {result['prize_2']}次\n"
        output += f"   🥉 三等奖(5+0): {result['prize_3']}次\n"
        output += f"   四等奖(4+2): {result['prize_4']}次\n"
        output += f"   五等奖(4+1/3+2): {result['prize_5']}次\n"
        output += f"   六等奖(4+0/3+1/2+2): {result['prize_6']}次\n"
        output += f"   七等奖(3+0/2+1/1+2/0+2): {result['prize_7']}次\n"
        output += f"   八等奖(2+0/1+1/0+1): {result['prize_8']}次\n"
        output += f"   📊 <b>总中奖率: {result['prize_rate']}%</b>\n\n"
        output += "📈 <b>前区命中分布</b>\n"
        for h, lbl in [(5, '5前'), (4, '4前'), (3, '3前'), (2, '2前'), (1, '1前'), (0, '0前')]:
            cnt = result[f'detail_{h}']
            pct = cnt / n * 100
            bar = "█" * int(pct / 2)
            output += f"   {lbl}: {cnt}次 ({pct:.1f}%) {bar}\n"
        output += "\n📊 <b>综合指标</b>\n"
        output += f"   平均前区命中: <b>{result['avg_front_hit']}</b> 个\n"
        output += f"   3+前命中率: {result['hit_3plus_pct']}%\n"
        output += f"   4+前命中率: {result['hit_4plus_pct']}%\n"
        output += f"   后区命中率: {result['back_hit_rate']}%\n"
        output += f"   总中奖率: {result['prize_rate']}%\n\n"
        output += "💡 <b>与纯随机对比</b>\n"
        diff_avg = result['avg_front_hit'] - result['random_avg_front']
        diff_back = result['back_hit_rate'] - result['random_back_rate']
        arrow_avg = "📈" if diff_avg > 0 else "📉" if diff_avg < 0 else "➡️"
        arrow_back = "📈" if diff_back > 0 else "📉" if diff_back < 0 else "➡️"
        output += f"   纯随机期望: 前区 {result['random_avg_front']}个 | 后区 {result['random_back_rate']}%\n"
        output += f"   {arrow_avg} 模型前区 {diff_avg:+.3f} vs 随机\n"
        output += f"   {arrow_back} 模型前区 {diff_back:+.1f}% vs 随机\n\n"

        if result['avg_front_hit'] > result['random_avg_front'] * 1.05:
            verdict = f"✅ <b>模型有效</b> — 优于纯随机约{((result['avg_front_hit'] / result['random_avg_front']) - 1) * 100:.0f}%"
        elif result['avg_front_hit'] > result['random_avg_front']:
            verdict = "🟡 <b>微弱有效</b> — 略高于随机"
        else:
            verdict = "❌ <b>模型无效</b> — 与随机无差异或更差"
        output += f"<b>结论：</b>{verdict}"

        keyboard = [
            [InlineKeyboardButton("🎯 大乐透预测", callback_data='dlt_predict'),
             InlineKeyboardButton("◀️ 重新选期数", callback_data='dlt_backtest')]
        ]
        await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"DLT backtest error: {e}")
        await msg.edit_text(f"❌ 大乐透回测失败: {str(e)}")


async def dlt_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt_update 命令"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
        await update.message.reply_text("❌ 大乐透模块未加载")
        return

    msg = await update.message.reply_text("🔄 正在抓取大乐透最新开奖数据...")
    try:
        draws = fetch_dlt_latest()
        if draws:
            await msg.edit_text(
                f"✅ 大乐透更新成功！新增 {len(draws)} 期数据\n"
                f"📊 数据库现有 {get_dlt_draw_count()} 期"
            )
        else:
            await msg.edit_text("✅ 大乐透数据已是最新，无需更新")
    except Exception as e:
        logger.error(f"DLT update error: {e}")
        await msg.edit_text(f"❌ 大乐透更新失败: {str(e)}")
