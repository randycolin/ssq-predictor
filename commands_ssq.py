#!/usr/bin/env python3
"""
双色球Bot命令 — /predict, /stats, /backtest, /update, /settings
"""
import logging
from datetime import date
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_all_draws, get_draw_count, get_latest_draw, save_prediction
from fetch_data import fetch_latest
from scorecard import scorecard_predict_detailed
from bot_utils import get_next_draw_date, FakeCallbackQuery

logger = logging.getLogger(__name__)


async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /predict 命令"""
    msg = await update.message.reply_text("🔄 正在计算中...")

    try:
        result = scorecard_predict_detailed()

        if isinstance(result, str):
            await msg.edit_text(result, parse_mode='HTML')
        elif 'error' in result:
            await msg.edit_text(f"❌ {result['error']}")
        else:
            num_str = ' '.join(f"{n:02d}" for n in result['red_numbers'])
            blue_str = f"{result['blue_number']:02d}"

            output = f"🎱 <b>双色球预测 · 第{result['period']}期</b>\n"
            output += f"📅 基于 {result['date']} 之前全部数据\n"
            output += f"💾 共 {result['total_draws']} 期历史数据\n"
            output += "─" * 30 + "\n\n"
            output += "🧮 <b>评分卡模型</b> — AI因子+老彩民经验\n\n"
            output += f"🎯 <b>{num_str} + {blue_str}</b>\n\n"

            # Top 15 red scores
            output += "📊 红球评分TOP15:\n"
            for r, s in result['red_scores'][:15]:
                mark = "⭐" if r in result['red_numbers'] else "  "
                output += f"{mark} {r:02d}: {s:.2f}\n"

            # 保存预测
            try:
                nums = result['red_numbers'] + [result['blue_number']]
                save_prediction(result['period'], 'scorecard', nums)
                logger.info(f"已保存预测记录: 第{result['period']}期")
            except Exception as e:
                logger.error(f"保存预测记录失败: {e}")

            output += "\n🔵 蓝球评分:\n"
            for b, s in result['blue_scores'][:5]:
                mark = "⭐" if b == result['blue_number'] else "  "
                output += f"{mark} {b:02d}: {s:.2f}\n"

            keyboard = [
                [
                    InlineKeyboardButton("🎱 再预测", callback_data='predict'),
                    InlineKeyboardButton("📊 数据统计", callback_data='stats'),
                ],
                [
                    InlineKeyboardButton("📈 回测", callback_data='backtest'),
                    InlineKeyboardButton("🔄 更新数据", callback_data='update'),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Predict error: {e}")
        await msg.edit_text(f"❌ 预测失败: {str(e)}")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /stats 命令"""
    msg = await update.message.reply_text("🔄 正在统计...")

    try:
        draws = get_all_draws()
        latest = get_latest_draw()
        result = scorecard_predict_detailed()

        output = f"📊 <b>系统状态</b>\n"
        output += "─" * 30 + "\n"
        output += f"📅 数据更新至: {latest['date'] if latest else '无'}\n"
        output += f"💾 历史数据: {len(draws)} 期\n"
        output += f"🆕 最新期号: {latest['period'] if latest else '-'}\n"
        output += f"🔢 最新号码: "
        if latest:
            for i in range(1, 7):
                output += f"{latest[f'red{i}']:02d} "
            output += f"+ {latest['blue']:02d}\n"
        output += "\n<b>🧮 评分卡模型</b>\n\n"
        if isinstance(result, dict) and 'error' not in result:
            output += f"🎯 当前推荐: "
            output += ' '.join(f"{n:02d}" for n in result['red_numbers'])
            output += f" + {result['blue_number']:02d}\n\n"

        next_draw = get_next_draw_date()
        days_until = (next_draw - date.today()).days
        weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        output += f"📌 下次开奖: {next_draw} ({weekday_names[next_draw.weekday()]}, {days_until}天后)"

        keyboard = [
            [InlineKeyboardButton("🎱 立即预测", callback_data='predict')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(output, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await msg.edit_text(f"❌ 统计失败: {str(e)}")


async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /backtest 命令 — 选择期数"""
    keyboard = [
        [InlineKeyboardButton("最近20期", callback_data='bt_20'),
         InlineKeyboardButton("最近50期", callback_data='bt_50')],
        [InlineKeyboardButton("最近100期", callback_data='bt_100'),
         InlineKeyboardButton("最近200期", callback_data='bt_200')],
        [InlineKeyboardButton("✏️ 手动输入", callback_data='bt_custom'),
         InlineKeyboardButton("取消", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📊 <b>评分卡回测</b>\n选择回测期数：",
            parse_mode='HTML', reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "📊 <b>评分卡回测</b>\n选择回测期数：",
            parse_mode='HTML', reply_markup=reply_markup
        )


async def run_backtest_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, periods: int):
    """执行详细回测"""
    msg = await update.callback_query.edit_message_text(f"🔄 正在回测最近{periods}期，请稍候...")

    try:
        draws = get_all_draws()
        if len(draws) < periods + 50:
            await msg.edit_text("❌ 数据不足，需要至少50期历史数据")
            return

        test_draws = draws[-periods:]
        train_draws = draws[:-periods]

        red_hit_list = []
        blue_hit_list = []
        detail_ranges = {6: 0, 5: 0, 4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        prize_1st = prize_2nd = prize_3rd = 0
        prize_4th = prize_5th = prize_6th = 0
        no_prize = 0

        for i in range(len(test_draws)):
            if i == 0:
                continue
            train = train_draws + test_draws[:i]
            if len(train) < 50:
                continue

            actual = test_draws[i]
            actual_reds = {actual['red1'], actual['red2'], actual['red3'],
                          actual['red4'], actual['red5'], actual['red6']}
            actual_blue = actual['blue']

            from scorecard import score_all, select_numbers
            red_scores, blue_scores = score_all(train)
            pred = select_numbers(red_scores, blue_scores, train)

            if pred:
                pred_reds = set(pred[:6])
                pred_blue = pred[6]
                red_hit = len(pred_reds & actual_reds)
                blue_hit = 1 if pred_blue == actual_blue else 0

                red_hit_list.append(red_hit)
                blue_hit_list.append(blue_hit)
                detail_ranges[red_hit] += 1

                # 奖项判定（双色球）
                if red_hit == 6 and blue_hit:
                    prize_1st += 1
                elif red_hit == 6:
                    prize_2nd += 1
                elif red_hit == 5 and blue_hit:
                    prize_3rd += 1
                elif red_hit == 5 or (red_hit == 4 and blue_hit):
                    prize_4th += 1
                elif red_hit == 4 or (red_hit == 3 and blue_hit):
                    prize_5th += 1
                elif blue_hit:
                    prize_6th += 1
                else:
                    no_prize += 1

        n = len(test_draws) - 1
        avg_hit = sum(red_hit_list) / len(red_hit_list) if red_hit_list else 0
        blue_rate = sum(blue_hit_list) / len(blue_hit_list) * 100 if blue_hit_list else 0
        hit_3plus_count = sum(1 for h in red_hit_list if h >= 3)
        hit_4plus_count = sum(1 for h in red_hit_list if h >= 4)
        random_avg = 6 * 6 / 33
        random_blue = 100 / 16

        output = f"📊 <b>评分卡回测报告（最近{periods}期）</b>\n"
        output += "─" * 26 + "\n\n"
        output += "🎯 <b>中奖统计（按双色球规则）</b>\n"
        output += f"   🥇 一等奖(6+1): {prize_1st}次\n"
        output += f"   🥈 二等奖(6+0): {prize_2nd}次\n"
        output += f"   🥉 三等奖(5+1): {prize_3rd}次\n"
        output += f"   四等奖(5+0/4+1): {prize_4th}次\n"
        output += f"   五等奖(4+0/3+1): {prize_5th}次\n"
        output += f"   六等奖(蓝球): {prize_6th}次\n"
        total_prize = prize_1st + prize_2nd + prize_3rd + prize_4th + prize_5th + prize_6th
        prize_rate = total_prize / n * 100 if n > 0 else 0
        output += f"   📊 <b>总中奖率: {prize_rate:.1f}%</b>\n\n"
        output += "📈 <b>红球命中分布</b>\n"
        for h in [6, 5, 4, 3, 2, 1, 0]:
            pct = detail_ranges[h] / n * 100
            bar = "█" * int(pct / 2)
            output += f"   {h}红: {detail_ranges[h]}次 ({pct:.1f}%) {bar}\n"
        output += "\n📊 <b>综合指标</b>\n"
        output += f"   平均红球命中: <b>{avg_hit:.2f}</b> 个\n"
        output += f"   3+红命中率: {hit_3plus_count / len(red_hit_list) * 100:.1f}%\n"
        output += f"   4+红命中率: {hit_4plus_count / len(red_hit_list) * 100:.1f}%\n"
        output += f"   蓝球命中率: {blue_rate:.1f}%\n"
        output += f"   总中奖率: {prize_rate:.1f}%\n\n"
        output += "💡 <b>与纯随机对比</b>\n"
        diff_avg = avg_hit - random_avg
        diff_blue = blue_rate - random_blue
        arrow_avg = "📈" if diff_avg > 0 else "📉" if diff_avg < 0 else "➡️"
        arrow_blue = "📈" if diff_blue > 0 else "📉" if diff_blue < 0 else "➡️"
        output += f"   纯随机期望: 红球 {random_avg:.2f}个 | 蓝球 {random_blue:.1f}%\n"
        output += f"   {arrow_avg} 评分卡红球 {diff_avg:+.2f}个 vs 随机\n"
        output += f"   {arrow_blue} 评分卡蓝球 {diff_blue:+.1f}% vs 随机\n\n"
        random_prize_rate = 6.6
        diff_prize = prize_rate - random_prize_rate
        arrow_prize = "📈" if diff_prize > 0 else "📉" if diff_prize < 0 else "➡️"
        output += f"   {arrow_prize} 评分卡总中奖率 {diff_prize:+.1f}% vs 随机({random_prize_rate:.1f}%)\n\n"
        if avg_hit > random_avg * 1.1:
            verdict = "✅ <b>模型有效</b> — 优于纯随机约{:.0f}%".format((avg_hit / random_avg - 1) * 100)
        elif avg_hit > random_avg:
            verdict = "🟡 <b>模型微弱有效</b> — 略高于随机水平"
        else:
            verdict = "❌ <b>模型无效</b> — 与随机无差异或更差"
        output += f"<b>结论：</b>{verdict}"

        keyboard = [
            [InlineKeyboardButton("🎱 立即预测", callback_data='predict'),
             InlineKeyboardButton("◀️ 重新选期数", callback_data='backtest')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        await msg.edit_text(f"❌ 回测失败: {str(e)}")


async def update_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /update 命令"""
    msg = await update.message.reply_text("🔄 正在抓取最新开奖数据...")

    try:
        draws = fetch_latest()
        if draws:
            await msg.edit_text(
                f"✅ 更新成功！新增 {len(draws)} 期数据\n"
                f"📊 数据库现有 {get_draw_count()} 期"
            )
        else:
            await msg.edit_text("✅ 数据已是最新，无需更新")
    except Exception as e:
        logger.error(f"Update error: {e}")
        await msg.edit_text(f"❌ 更新失败: {str(e)}")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /settings 命令"""
    output = "⚙️ <b>评分卡模型 — 红球老彩民 + 蓝球AI</b>\n\n"
    output += "🧮 <b>当前权重：</b>\n\n"
    output += "🔴 <b>红球（纯老彩民因子）：</b>\n"
    output += "  重号 × 3.0 — 上期号码回归\n"
    output += "  邻号 × 2.0 — 上期号码±1\n"
    output += "  和值平衡 × 2.0 — 和值靠近102\n"
    output += "  区间平衡 × 2.0 — 三区分布均衡\n"
    output += "  历史模式 × 1.0 — 特征回归\n\n"
    output += "🔵 <b>蓝球（AI因子）：</b>\n"
    output += "  近期热度 × 2.0 — 近30期出现频率\n"
    output += "  历史频率 × 1.0 — 全周期频率\n"
    output += "  重号 × 1.5 — 上期蓝球保留\n"
    output += "  邻号 × 1.0 — 上期蓝球±1\n\n"
    output += "📊 <b>回测表现：</b>\n"
    output += "  平均红球命中: 1.14 ~ 1.20 个\n"
    output += "  纯随机期望: 1.09 个\n"
    output += "  📈 评分卡比随机高出约 5~12%\n\n"
    output += "⚠️ <b>重要提示：</b>\n"
    output += "  双色球是物理摇奖，不可能稳定预测。\n"
    output += "  评分卡只是比纯随机稍微好一点，\n"
    output += "  让你避开明显不合理的号码组合。\n"
    output += "  中了是运气，不中是常态 😄\n\n"

    keyboard = [
        [InlineKeyboardButton("🎱 立即预测", callback_data='predict'),
         InlineKeyboardButton("📊 回测", callback_data='backtest')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(output, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(output, parse_mode='HTML', reply_markup=reply_markup)
