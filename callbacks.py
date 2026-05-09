#!/usr/bin/env python3
"""
按钮路由 — button_callback 处理所有内联按钮点击
"""
import logging
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_all_draws, get_latest_draw, save_prediction
from fetch_data import fetch_latest
from scorecard import scorecard_predict_detailed
from bot_utils import get_next_draw_date

from dlt_database import get_all_dlt_draws, get_latest_dlt_draw, save_dlt_prediction
from dlt_scorecard import dlt_predict_detailed

from commands_ssq import run_backtest_detail
from commands_dlt import run_dlt_backtest_detail

logger = logging.getLogger(__name__)

DLT_AVAILABLE = True  # 由 bot.py 覆写


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理内联按钮点击"""
    query = update.callback_query
    await query.answer()

    action = query.data
    msg = query.message

    if action == 'predict':
        await msg.edit_text("🔄 正在计算中...")
        try:
            result = scorecard_predict_detailed()
            if isinstance(result, str) or 'error' in result:
                text = result if isinstance(result, str) else f"❌ {result['error']}"
                await msg.edit_text(text)
                return

            num_str = ' '.join(f"{n:02d}" for n in result['red_numbers'])
            blue_str = f"{result['blue_number']:02d}"
            output = f"🎱 <b>双色球预测 · 第{result['period']}期</b>\n"
            output += f"📅 基于 {result['date']} 之前全部数据\n"
            output += f"💾 共 {result['total_draws']} 期历史数据\n"
            output += "─" * 30 + "\n\n"
            output += f"🎯 <b>{num_str} + {blue_str}</b>\n\n"
            output += "📊 红球评分TOP15:\n"
            for r, s in result['red_scores'][:15]:
                mark = "⭐" if r in result['red_numbers'] else "  "
                output += f"{mark} {r:02d}: {s:.2f}\n"
            output += "\n🔵 蓝球评分:\n"
            for b, s in result['blue_scores'][:5]:
                mark = "⭐" if b == result['blue_number'] else "  "
                output += f"{mark} {b:02d}: {s:.2f}\n"

            keyboard = [
                [InlineKeyboardButton("🎱 再预测", callback_data='predict'),
                 InlineKeyboardButton("📊 数据统计", callback_data='stats')],
                [InlineKeyboardButton("📈 回测", callback_data='backtest'),
                 InlineKeyboardButton("🔄 更新数据", callback_data='update')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
        except Exception as e:
            await msg.edit_text(f"❌ 预测失败: {str(e)}")

    elif action == 'stats':
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

        keyboard = [[InlineKeyboardButton("🎱 立即预测", callback_data='predict')]]
        await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'backtest':
        keyboard = [
            [InlineKeyboardButton("最近20期", callback_data='bt_20'),
             InlineKeyboardButton("最近50期", callback_data='bt_50')],
            [InlineKeyboardButton("最近100期", callback_data='bt_100'),
             InlineKeyboardButton("最近200期", callback_data='bt_200')],
            [InlineKeyboardButton("✏️ 手动输入", callback_data='bt_custom'),
             InlineKeyboardButton("取消", callback_data='cancel')],
        ]
        await msg.edit_text(
            "📊 <b>评分卡回测</b>\n选择回测期数：",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action in ('bt_20', 'bt_50', 'bt_100', 'bt_200'):
        periods = int(action.split('_')[1])
        await run_backtest_detail(update, context, periods)

    elif action == 'bt_custom':
        await msg.edit_text(
            "✏️ 请输入回测期数（数字，1-200）：\n\n例：<code>30</code>",
            parse_mode='HTML'
        )
        context.user_data['awaiting_backtest_input'] = True

    elif action == 'cancel':
        await msg.edit_text("已取消")

    elif action == 'update':
        await msg.edit_text("🔄 正在抓取最新数据...")
        try:
            draws = fetch_latest()
            if draws:
                await msg.edit_text(f"✅ 更新成功！新增 {len(draws)} 期")
            else:
                await msg.edit_text("✅ 数据已是最新")
        except Exception as e:
            await msg.edit_text(f"❌ 更新失败: {str(e)}")

    # ===== 大乐透按钮 =====
    elif action == 'dlt_predict':
        if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
            return
        await msg.edit_text("🔄 正在计算大乐透...")
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
                output += f"📅 基于 {result['date']} 之前数据\n"
                output += f"💾 {result['total_draws']} 期\n" + "─" * 30 + "\n\n"
                output += f"🔴 <b>前区: {front_str}</b>\n🔵 <b>后区: {back_str}</b>\n"
                keyboard = [[InlineKeyboardButton("🎯 再预测", callback_data='dlt_predict'),
                             InlineKeyboardButton("📊 数据", callback_data='dlt_stats')],
                            [InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
                try:
                    save_dlt_prediction(result['period'], 'dlt_scorecard', result['front_numbers'], result['back_numbers'])
                except:
                    pass
                await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await msg.edit_text(f"❌ 预测失败: {str(e)}")

    elif action == 'dlt_stats':
        if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
            return
        draws = get_all_dlt_draws()
        latest = get_latest_dlt_draw()
        if latest:
            output = "📊 <b>大乐透系统状态</b>\n" + "─" * 15 + "\n"
            output += f"📅 {latest['date']}\n💾 {len(draws)} 期\n"
            output += f"🆕 第{latest['period']}期\n"
            front_str = ' '.join(f"{latest[f'front{i}']:02d}" for i in range(1, 6))
            back_str = ' '.join(f"{latest[f'back{i}']:02d}" for i in range(1, 3))
            output += f"{front_str} + {back_str}\n"
            output += "\n📌 开奖日: 周一/三/六"
            keyboard = [[InlineKeyboardButton("🎯 预测", callback_data='dlt_predict'),
                         InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
            await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'dlt_backtest':
        if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
            return
        keyboard = [
            [InlineKeyboardButton("最近20期", callback_data='dlt_bt_20'),
             InlineKeyboardButton("最近50期", callback_data='dlt_bt_50')],
            [InlineKeyboardButton("最近100期", callback_data='dlt_bt_100'),
             InlineKeyboardButton("最近200期", callback_data='dlt_bt_200')],
            [InlineKeyboardButton("取消", callback_data='cancel')],
        ]
        await msg.edit_text(
            "📊 <b>大乐透回测</b>\n选择回测期数：",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action.startswith('dlt_bt_'):
        if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
            return
        periods = int(action.split('_')[2])
        await run_dlt_backtest_detail(update, context, periods)
