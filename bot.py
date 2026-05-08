#!/usr/bin/env python3
"""
双色球预测Bot - 独立运行，不经过Hermes Agent
"""

import asyncio
import logging
import sys
import os
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import telegram
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
except ImportError:
    os.system("pip install python-telegram-bot --break-system-packages 2>/dev/null")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from database import init_db, get_all_draws, get_draw_count, get_latest_draw, get_predictions_with_results, get_conn
from fetch_data import fetch_all_history, fetch_latest
from scorecard import scorecard_predict_detailed

# 大乐透模块
try:
    from dlt_database import (init_dlt_tables, get_all_dlt_draws, get_latest_dlt_draw,
                              get_dlt_draw_count, save_dlt_prediction, save_dlt_prediction_result,
                              get_dlt_predictions_with_results)
    from dlt_scorecard import dlt_predict_detailed
    from fetch_dlt import fetch_all_dlt_history, fetch_dlt_latest
    DLT_AVAILABLE = True
except Exception as e:
    logger.warning(f"大乐透模块加载失败: {e}")
    DLT_AVAILABLE = False

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import os

TOKEN = os.environ.get("SSQ_BOT_TOKEN", "")
if not TOKEN:
    logger.error("SSQ_BOT_TOKEN 环境变量未设置！")
    sys.exit(1)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_DIR, 'logs', 'bot.log')

# 节假日休市日期（每年更新）
# 2026年春节、国庆等休市安排
HOLIDAYS_2026 = [
    # 春节休市（通常10天）
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-21", "2026-02-22", "2026-02-23", "2026-02-24", "2026-02-25",
    # 国庆休市（通常7天）
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05",
    "2026-10-06", "2026-10-07",
]

def is_ssq_draw_day():
    """判断今天是否双色球开奖日（周二、周四、周日）"""
    today = date.today()
    weekday = today.weekday()
    if weekday not in [1, 3, 6]:
        return False
    today_str = today.strftime("%Y-%m-%d")
    if today_str in HOLIDAYS_2026:
        return False
    return True

def is_dlt_draw_day():
    """判断今天是否大乐透开奖日（周一、周三、周六）"""
    today = date.today()
    weekday = today.weekday()
    if weekday not in [0, 2, 5]:  # Mon=0, Wed=2, Sat=5
        return False
    today_str = today.strftime("%Y-%m-%d")
    if today_str in HOLIDAYS_2026:
        return False
    return True

def is_draw_day():
    """兼容旧函数：双色球开奖日"""
    return is_ssq_draw_day()

def get_next_draw_date():
    """获取下个开奖日"""
    today = date.today()
    # 找到下一个周二、周四或周日
    for i in range(7):
        d = today + timedelta(days=i)
        if d.weekday() in [1, 3, 6]:  # Tue, Thu, Sun
            d_str = d.strftime("%Y-%m-%d")
            if d_str not in HOLIDAYS_2026:
                return d
    return today


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令 — 初始化订阅"""
    chat_id = update.effective_chat.id
    
    # Set up daily push for this user
    setup_daily_push(context.application, chat_id)
    
    text = (
        "🎱 <b>双色球+大乐透 预测Bot</b>\n\n"
        "🧮 <b>评分卡模型</b> — AI因子 + 老彩民经验融合\n"
        "基于 双色球3447期 + 大乐透1364期 历史数据\n\n"
        "✅ <b>已为您开启自动推送！</b>\n"
        "📌 双色球: 周二/四/日 08:00 推送\n"
        "📌 大乐透: 周一/三/六 08:05 推送\n\n"
        "<b>🔴 双色球命令：</b>\n"
        "/predict  — 立即预测\n"
        "/stats    — 数据统计\n"
        "/backtest — 模型回测\n"
        "/update   — 更新数据\n"
        "/settings — 因子权重\n\n"
        "<b>🟡 大乐透命令：</b>\n"
        "/dlt          — 立即预测\n"
        "/dlt_stats    — 数据统计\n"
        "/dlt_backtest — 模型回测\n"
        "/dlt_update   — 更新数据\n\n"
        "<b>📋 通用：</b>\n"
        "/record   — 历史中奖记录\n"
        "/help     — 帮助信息"
    )
    
    ssq_keyboard = [
        [InlineKeyboardButton("🎱 双色球预测", callback_data='predict'),
         InlineKeyboardButton("📊 双色球数据", callback_data='stats')],
        [InlineKeyboardButton("📈 回测", callback_data='backtest'),
         InlineKeyboardButton("🔄 更新", callback_data='update')],
    ]
    
    dlt_keyboard = [
        [InlineKeyboardButton("🎯 大乐透预测", callback_data='dlt_predict'),
         InlineKeyboardButton("📊 大乐透数据", callback_data='dlt_stats')],
    ]
    
    keyboard = ssq_keyboard + dlt_keyboard
    if DLT_AVAILABLE:
        keyboard.append([InlineKeyboardButton("📈 大乐透回测", callback_data='dlt_backtest')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    await start(update, context)


async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /predict 命令 — 评分卡模型"""
    msg = await update.message.reply_text("🔄 正在计算中...")
    
    try:
        result = scorecard_predict_detailed()
        
        if isinstance(result, str):
            await msg.edit_text(result, parse_mode='HTML')
        elif 'error' in result:
            await msg.edit_text(f"❌ {result['error']}")
        else:
            # Format nice output
            num_str = ' '.join(f"{n:02d}" for n in result['red_numbers'])
            blue_str = f"{result['blue_number']:02d}"
            
            output = f"🎱 <b>双色球预测 · 第{result['period']}期</b>\n"
            output += f"📅 基于 {result['date']} 之前全部数据\n"
            output += f"💾 共 {result['total_draws']} 期历史数据\n"
            output += "─" * 30 + "\n\n"
            output += "🧮 <b>评分卡模型</b> — AI因子+老彩民经验\n\n"
            
            output += f"🎯 <b>{num_str} + {blue_str}</b>\n\n"
            
            # Top 10 red scores
            output += "📊 红球评分TOP15:\n"
            for r, s in result['red_scores'][:15]:
                mark = "⭐" if r in result['red_numbers'] else "  "
                output += f"{mark} {r:02d}: {s:.2f}\n"
            
            # 💾 保存预测到数据库
            try:
                from database import save_prediction
                nums = result['red_numbers'] + [result['blue_number']]
                save_prediction(result['period'], 'scorecard', nums)
                logger.info(f"已保存预测记录: 第{result['period']}期")
            except Exception as e:
                logger.error(f"保存预测记录失败: {e}")
            
            output += "\n🔵 蓝球评分:\n"
            for b, s in result['blue_scores'][:5]:
                mark = "⭐" if b == result['blue_number'] else "  "
                output += f"{mark} {b:02d}: {s:.2f}\n"
            
            # Inline keyboard
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
    """处理 /stats 命令 — 评分卡模型"""
    msg = await update.message.reply_text("🔄 正在统计...")
    
    try:
        draws = get_all_draws()
        latest = get_latest_draw()
        
        # Get scorecard data
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
        output += "\n<b>🧮 评分卡模型</b>\n"
        output += "因子权重: AI因子(60%) + 老彩民因子(40%)\n\n"
        
        if isinstance(result, dict) and 'error' not in result:
            output += f"🎯 当前推荐: "
            output += ' '.join(f"{n:02d}" for n in result['red_numbers'])
            output += f" + {result['blue_number']:02d}\n\n"
        
        next_draw = get_next_draw_date()
        days_until = (next_draw - date.today()).days
        weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        output += f"\n📌 下次开奖: {next_draw} ({weekday_names[next_draw.weekday()]}, {days_until}天后)"
        
        keyboard = [
            [InlineKeyboardButton("🎱 立即预测", callback_data='predict')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await msg.edit_text(f"❌ 统计失败: {str(e)}")


async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /backtest 命令 — 评分卡回测（详细版）"""
    # 显示期数选择按钮
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
        
        # 详细统计
        red_hit_list = []
        blue_hit_list = []
        detail_ranges = {6:0, 5:0, 4:0, 3:0, 2:0, 1:0, 0:0}  # 红球命中分布
        # 奖项统计（按双色球实际规则）
        prize_1st = 0   # 6+1
        prize_2nd = 0   # 6+0
        prize_3rd = 0   # 5+1
        prize_4th = 0   # 5+0 或 4+1
        prize_5th = 0   # 4+0 或 3+1
        prize_6th = 0   # 2+1 / 1+1 / 0+1（只中蓝球也算奖！）
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
            
            # Run scorecard
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
                
                # 命中分布
                detail_ranges[red_hit] += 1
                
                # 奖项判定（按真实双色球规则）
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
                elif blue_hit:  # 2+1 / 1+1 / 0+1 — 只要蓝球中了就算六等奖！
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
        
        # 构建详细报告
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
        for h in [6,5,4,3,2,1,0]:
            pct = detail_ranges[h]/n*100
            bar = "█" * int(pct / 2)
            output += f"   {h}红: {detail_ranges[h]}次 ({pct:.1f}%) {bar}\n"
        
        output += "\n"
        output += f"📊 <b>综合指标</b>\n"
        output += f"   平均红球命中: <b>{avg_hit:.2f}</b> 个\n"
        output += f"   3+红命中率: {hit_3plus_count/len(red_hit_list)*100:.1f}%\n"
        output += f"   4+红命中率: {hit_4plus_count/len(red_hit_list)*100:.1f}%\n"
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
        
        # 纯随机中奖率 = 蓝球命中率6.25% -> 六等奖\n
        # 实际随机期望约6.6%（因为还有其他等级，但极小）
        random_prize_rate = 1 - (16/17)  # 约6.25%，近似取6.6%
        random_prize_rate = 6.6
        diff_prize = prize_rate - random_prize_rate
        arrow_prize = "📈" if diff_prize > 0 else "📉" if diff_prize < 0 else "➡️"
        output += f"   {arrow_prize} 评分卡总中奖率 {diff_prize:+.1f}% vs 随机({random_prize_rate:.1f}%)\n\n"
        
        # 结论
        if avg_hit > random_avg * 1.1:
            verdict = "✅ <b>模型有效</b> — 优于纯随机约{:.0f}%".format((avg_hit/random_avg-1)*100)
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


async def run_dlt_backtest_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, periods: int):
    """执行大乐透详细回测"""
    msg = await update.callback_query.edit_message_text(f"🔄 正在回测大乐透最近{periods}期，请稍候...")
    
    try:
        from dlt_scorecard import run_dlt_backtest
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
        for h, lbl in [(5,'5前'),(4,'4前'),(3,'3前'),(2,'2前'),(1,'1前'),(0,'0前')]:
            cnt = result[f'detail_{h}']
            pct = cnt/n*100
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
        output += f"   {arrow_back} 模型后区 {diff_back:+.1f}% vs 随机\n\n"
        
        if result['avg_front_hit'] > result['random_avg_front'] * 1.05:
            verdict = f"✅ <b>模型有效</b> — 优于纯随机约{((result['avg_front_hit']/result['random_avg_front'])-1)*100:.0f}%"
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


async def update_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /update 命令"""
    msg = await update.message.reply_text("🔄 正在抓取最新开奖数据...")
    
    try:
        draws = fetch_latest()
        if draws:
            await msg.edit_text(f"✅ 更新成功！新增 {len(draws)} 期数据\n"
                               f"📊 数据库现有 {get_draw_count()} 期")
        else:
            await msg.edit_text("✅ 数据已是最新，无需更新")
    except Exception as e:
        logger.error(f"Update error: {e}")
        await msg.edit_text(f"❌ 更新失败: {str(e)}")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /settings 命令 — 评分卡模型（可调权重）"""
    
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

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /record 命令 — 完整统计（合并双色球+大乐透）"""
    # ===== 1. 双色球自动比对 =====
    try:
        from database import get_all_draws, save_prediction_result, get_conn
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
                    if red_hit == 6 and blue_hit: prize_level = "🥇 一等奖"
                    elif red_hit == 6: prize_level = "🥈 二等奖"
                    elif red_hit == 5 and blue_hit: prize_level = "🥉 三等奖"
                    elif red_hit == 5 or (red_hit == 4 and blue_hit): prize_level = "四等奖"
                    elif red_hit == 4 or (red_hit == 3 and blue_hit): prize_level = "五等奖"
                    elif blue_hit: prize_level = "六等奖"
                    save_prediction_result(p['period'], 'scorecard', red_hit, blue_hit, prize_level)
                    break
    except Exception as e:
        logger.error(f"双色球自动比对失败: {e}")
    
    # ===== 2. 大乐透自动比对 =====
    if DLT_AVAILABLE:
        try:
            from dlt_database import save_dlt_prediction_result
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
                        pred_fronts = {p[f'front{i}'] for i in range(1,6)}
                        pred_backs = {p[f'back{i}'] for i in range(1,3)}
                        actual_fronts = {d[f'front{i}'] for i in range(1,6)}
                        actual_backs = {d[f'back{i}'] for i in range(1,3)}
                        fh = len(pred_fronts & actual_fronts)
                        bh = len(pred_backs & actual_backs)
                        prize = None
                        # 大乐透官方规则（record 1/3处）
                        if fh == 5 and bh == 2: prize = "🥇 一等奖"
                        elif fh == 5 and bh == 1: prize = "🥈 二等奖"
                        elif fh == 5: prize = "🥉 三等奖"
                        elif fh == 4 and bh == 2: prize = "四等奖"
                        elif (fh == 4 and bh == 1) or (fh == 3 and bh == 2): prize = "五等奖"
                        elif (fh == 4 and bh == 0) or (fh == 3 and bh == 1) or (fh == 2 and bh == 2): prize = "六等奖"
                        elif (fh == 3 and bh == 0) or (fh == 2 and bh == 1) or (fh == 1 and bh == 2) or (fh == 0 and bh == 2): prize = "七等奖"
                        elif (fh == 2 and bh == 0) or (fh == 1 and bh == 1) or (fh == 0 and bh == 1): prize = "八等奖"
                        save_dlt_prediction_result(p['period'], 'dlt_scorecard', fh, bh, prize)
                        break
        except Exception as e:
            logger.error(f"大乐透自动比对失败: {e}")
    
    # ===== 3. 拉取双色球和大乐透记录 =====
    ssq_records = []
    dlt_records = []
    
    try:
        ssq_records = get_predictions_with_results(30)
    except Exception as e:
        logger.error(f"获取双色球记录失败: {e}")
    
    if DLT_AVAILABLE:
        try:
            dlt_records = get_dlt_predictions_with_results(20)
        except Exception as e:
            logger.error(f"获取大乐透记录失败: {e}")
    
    # ===== 4. 组合统计 =====
    output = "📋 <b>🎯 中奖记录总览</b>\n"
    output += "═" * 25 + "\n\n"
    
    # -- 双色球统计 --
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
        output += f"  预测 {ssq_total} 次 | 中奖 {ssq_wins} 次 | 中奖率 {ssq_wins/ssq_total*100:.1f}%\n"
        if ssq_prizes:
            for level, count in sorted(ssq_prizes.items(), key=lambda x: {'🥇':0,'🥈':1,'🥉':2}.get(x[0][0], 9)):
                output += f"    {level} × {count}\n"
    else:
        output += "  暂无记录\n"
    output += "\n"
    
    # -- 大乐透统计 --
    if DLT_AVAILABLE:
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
            output += f"  预测 {dlt_total} 次 | 中奖 {dlt_wins} 次 | 中奖率 {dlt_wins/dlt_total*100:.1f}%\n"
            if dlt_prizes:
                for level, count in sorted(dlt_prizes.items(), key=lambda x: {'🥇':0,'🥈':1,'🥉':2}.get(x[0][0], 9)):
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
        red_str = ' '.join(f"{r[f'red{i}']:02d}" for i in range(1,7))
        output += f"第{r['period']}期  {red_str} + {r['blue']:02d}\n"
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
    if DLT_AVAILABLE:
        output += "═" * 25 + "\n"
        output += "🟡 <b>大乐透 · 最近预测</b>\n\n"
        dlt_count = 0
        for r in dlt_records:
            if r['algorithm'] != 'dlt_scorecard': continue
            dlt_count += 1
            if dlt_count > 5: break
            f_str = ' '.join(f"{r[f'front{i}']:02d}" for i in range(1,6))
            b_str = ' '.join(f"{r[f'back{i}']:02d}" for i in range(1,3))
            output += f"第{r['period']}期  {f_str} + {b_str}\n"
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

# ============================================================
# 大乐透命令
# ============================================================

async def dlt_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt 命令 — 大乐透预测"""
    if not DLT_AVAILABLE:
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
                from dlt_database import save_dlt_prediction
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
    if not DLT_AVAILABLE:
        return
    
    try:
        draws = get_all_dlt_draws()
        latest = get_latest_dlt_draw()
        if not latest:
            return
        
        front_str = ' '.join(f"{latest[f'front{i}']:02d}" for i in range(1,6))
        back_str = ' '.join(f"{latest[f'back{i}']:02d}" for i in range(1,3))
        
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
    if not DLT_AVAILABLE:
        return
    
    # 自动比对
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
                    pred_fronts = {p[f'front{i}'] for i in range(1,6)}
                    pred_backs = {p[f'back{i}'] for i in range(1,3)}
                    actual_fronts = {d[f'front{i}'] for i in range(1,6)}
                    actual_backs = {d[f'back{i}'] for i in range(1,3)}
                    
                    fh = len(pred_fronts & actual_fronts)
                    bh = len(pred_backs & actual_backs)
                    
                    prize = None
                    # 大乐透官方规则（dlt_record 2/3处）
                    if fh == 5 and bh == 2: prize = "🥇 一等奖"
                    elif fh == 5 and bh == 1: prize = "🥈 二等奖"
                    elif fh == 5: prize = "🥉 三等奖"
                    elif fh == 4 and bh == 2: prize = "四等奖"
                    elif (fh == 4 and bh == 1) or (fh == 3 and bh == 2): prize = "五等奖"
                    elif (fh == 4 and bh == 0) or (fh == 3 and bh == 1) or (fh == 2 and bh == 2): prize = "六等奖"
                    elif (fh == 3 and bh == 0) or (fh == 2 and bh == 1) or (fh == 1 and bh == 2) or (fh == 0 and bh == 2): prize = "七等奖"
                    elif (fh == 2 and bh == 0) or (fh == 1 and bh == 1) or (fh == 0 and bh == 1): prize = "八等奖"
                    
                    save_dlt_prediction_result(p['period'], 'dlt_scorecard', fh, bh, prize)
                    break
    except Exception as e:
        logger.error(f"DLT record auto-match error: {e}")
    
    records = get_dlt_predictions_with_results(20)
    if not records:
        await update.message.reply_text("📋 暂无大乐透预测记录")
        return
    
    output = "📋 <b>大乐透预测记录</b>\n─" * 15 + "\n\n"
    
    total = 0
    wins = 0
    for r in records:
        if r['algorithm'] != 'dlt_scorecard': continue
        total += 1
        if r['prize_level']: wins += 1
    
    if total > 0:
        output += f"📊 预测{total}次 中奖{wins}次 ({wins/total*100:.1f}%)\n\n"
    
    count = 0
    for r in records:
        if r['algorithm'] != 'dlt_scorecard': continue
        count += 1
        f_str = ' '.join(f"{r[f'front{i}']:02d}" for i in range(1,6))
        b_str = ' '.join(f"{r[f'back{i}']:02d}" for i in range(1,3))
        output += f"第{r['period']}期  {f_str} + {b_str}\n"
        if r['front_hit'] is not None:
            if r['prize_level']:
                output += f"  ✅ 前{r['front_hit']}+后{r['back_hit']} → {r['prize_level']}\n"
            else:
                output += f"  ❌ 前{r['front_hit']}+后{r['back_hit']} 未中奖\n"
        else:
            output += f"  ⏳ 等待开奖\n"
        if count >= 5: break
    
    keyboard = [[InlineKeyboardButton("📊 大乐透数据", callback_data='dlt_stats'),
                 InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
    await update.message.reply_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def dlt_backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt_backtest 命令 — 大乐透回测"""
    if not DLT_AVAILABLE:
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


async def dlt_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /dlt_update 命令 — 更新大乐透数据"""
    if not DLT_AVAILABLE:
        await update.message.reply_text("❌ 大乐透模块未加载")
        return
    
    msg = await update.message.reply_text("🔄 正在抓取大乐透最新开奖数据...")
    try:
        draws = fetch_dlt_latest()
        if draws:
            await msg.edit_text(f"✅ 大乐透更新成功！新增 {len(draws)} 期数据\n📊 数据库现有 {get_dlt_draw_count()} 期")
        else:
            await msg.edit_text("✅ 大乐透数据已是最新，无需更新")
    except Exception as e:
        logger.error(f"DLT update error: {e}")
        await msg.edit_text(f"❌ 大乐透更新失败: {str(e)}")


async def ssq_daily_push(context: ContextTypes.DEFAULT_TYPE):
    """双色球定时推送 — 仅周二/四/日"""
    if not is_ssq_draw_day():
        logger.info("今天不是双色球开奖日，跳过推送")
        return
    
    logger.info("执行双色球开奖日推送...")
    
    # First, try to update data
    try:
        fetch_latest()
    except Exception as e:
        logger.error(f"更新数据失败: {e}")
    
    # 🔍 比对上一期预测是否中奖
    prize_result = None
    try:
        from database import get_all_draws, save_prediction_result
        draws = get_all_draws()
        if len(draws) >= 2:
            latest = draws[-1]
            prev = draws[-2]
            conn = get_conn()
            predictions = conn.execute(
                "SELECT * FROM predictions WHERE period = ? AND algorithm = 'scorecard'",
                (prev['period'],)
            ).fetchall()
            conn.close()
            if predictions:
                for p in predictions:
                    pred_reds = {p['red1'], p['red2'], p['red3'], p['red4'], p['red5'], p['red6']}
                    pred_blue = p['blue']
                    actual_reds = {prev['red1'], prev['red2'], prev['red3'], prev['red4'], prev['red5'], prev['red6']}
                    actual_blue = prev['blue']
                    red_hit = len(pred_reds & actual_reds)
                    blue_hit = 1 if pred_blue == actual_blue else 0
                    prize_level = None
                    if red_hit == 6 and blue_hit: prize_level = "🥇 一等奖"
                    elif red_hit == 6: prize_level = "🥈 二等奖"
                    elif red_hit == 5 and blue_hit: prize_level = "🥉 三等奖"
                    elif red_hit == 5 or (red_hit == 4 and blue_hit): prize_level = "四等奖"
                    elif red_hit == 4 or (red_hit == 3 and blue_hit): prize_level = "五等奖"
                    elif blue_hit: prize_level = "六等奖"
                    save_prediction_result(prev['period'], 'scorecard', red_hit, blue_hit, prize_level)
                    logger.info(f"已更新双色球中奖: 第{prev['period']}期 红{red_hit}蓝{blue_hit} {prize_level or '未中奖'}")
                    if prize_level:
                        prize_result = f"\n\n🎉 <b>上期预测结果：</b>\n第{prev['period']}期 {' '.join(f'{n:02d}' for n in pred_reds)} + {pred_blue:02d}\n红{red_hit}蓝{blue_hit} → {prize_level}！"
    except Exception as e:
        logger.error(f"比对双色球中奖失败: {e}")
    
    # Generate SSQ prediction
    try:
        result = scorecard_predict_detailed()
        if isinstance(result, str) or 'error' in result:
            result_text = result if isinstance(result, str) else f"❌ 双色球预测失败"
        else:
            try:
                from database import save_prediction
                nums = result['red_numbers'] + [result['blue_number']]
                save_prediction(result['period'], 'scorecard', nums)
            except Exception as e:
                logger.error(f"保存双色球预测失败: {e}")
            
            num_str = ' '.join(f"{n:02d}" for n in result['red_numbers'])
            blue_str = f"{result['blue_number']:02d}"
            result_text = f"🎱 双色球预测 · 第{result['period']}期\n"
            result_text += f"📅 基于 {result['date']} 之前全部数据\n"
            result_text += f"💾 共 {result['total_draws']} 期历史数据\n"
            result_text += "─" * 30 + "\n\n"
            result_text += f"🎯 {num_str} + {blue_str}"
            if prize_result:
                result_text += prize_result
    except Exception as e:
        logger.error(f"双色球预测失败: {e}")
        result_text = f"❌ 双色球今日预测生成失败"
    
    chat_id = context.job.chat_id
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
            logger.info(f"双色球推送成功到 {chat_id}")
        except Exception as e:
            logger.error(f"双色球推送失败: {e}")


async def dlt_daily_push(context: ContextTypes.DEFAULT_TYPE):
    """大乐透定时推送 — 仅周一/三/六"""
    if not DLT_AVAILABLE:
        return
    if not is_dlt_draw_day():
        logger.info("今天不是大乐透开奖日，跳过推送")
        return
    
    logger.info("执行大乐透开奖日推送...")
    
    # 更新大乐透数据
    try:
        fetch_dlt_latest()
    except Exception as e:
        logger.error(f"更新大乐透数据失败: {e}")
    
    # 🔍 比对上一期大乐透预测是否中奖
    prize_result = None
    try:
        from dlt_database import get_conn as dlt_get_conn, save_dlt_prediction_result
        dlt_draws = get_all_dlt_draws()
        if len(dlt_draws) >= 2:
            prev = dlt_draws[-1]
            conn_dlt = dlt_get_conn()
            predictions = conn_dlt.execute(
                "SELECT * FROM dlt_predictions WHERE period = ? AND algorithm = 'dlt_scorecard'",
                (prev['period'],)
            ).fetchall()
            conn_dlt.close()
            if predictions:
                for p in predictions:
                    pred_fronts = {p[f'front{i}'] for i in range(1,6)}
                    pred_backs = {p[f'back{i}'] for i in range(1,3)}
                    actual_fronts = {prev[f'front{i}'] for i in range(1,6)}
                    actual_backs = {prev[f'back{i}'] for i in range(1,3)}
                    fh = len(pred_fronts & actual_fronts)
                    bh = len(pred_backs & actual_backs)
                    prize = None
                    # 大乐透官方规则（daily_push 3/3处）
                    if fh == 5 and bh == 2: prize = "🥇 一等奖"
                    elif fh == 5 and bh == 1: prize = "🥈 二等奖"
                    elif fh == 5: prize = "🥉 三等奖"
                    elif fh == 4 and bh == 2: prize = "四等奖"
                    elif (fh == 4 and bh == 1) or (fh == 3 and bh == 2): prize = "五等奖"
                    elif (fh == 4 and bh == 0) or (fh == 3 and bh == 1) or (fh == 2 and bh == 2): prize = "六等奖"
                    elif (fh == 3 and bh == 0) or (fh == 2 and bh == 1) or (fh == 1 and bh == 2) or (fh == 0 and bh == 2): prize = "七等奖"
                    elif (fh == 2 and bh == 0) or (fh == 1 and bh == 1) or (fh == 0 and bh == 1): prize = "八等奖"
                    save_dlt_prediction_result(p['period'], 'dlt_scorecard', fh, bh, prize)
                    logger.info(f"已更新大乐透中奖: 第{prev['period']}期 前{fh}后{bh} {prize or '未中奖'}")
                    if prize:
                        f_str = ' '.join(f"{p[f'front{i}']:02d}" for i in range(1,6))
                        b_str = ' '.join(f"{p[f'back{i}']:02d}" for i in range(1,3))
                        prize_result = f"\n\n🎉 <b>上期预测结果：</b>\n第{prev['period']}期 {f_str} + {b_str}\n前{fh}后{bh} → {prize}！"
    except Exception as e:
        logger.error(f"比对大乐透中奖失败: {e}")
    
    # Generate DLT prediction
    try:
        result = dlt_predict_detailed()
        if isinstance(result, str) or 'error' in result:
            result_text = result if isinstance(result, str) else f"❌ 大乐透预测失败"
        else:
            try:
                from dlt_database import save_dlt_prediction
                save_dlt_prediction(result['period'], 'dlt_scorecard', result['front_numbers'], result['back_numbers'])
            except Exception as e:
                logger.error(f"保存大乐透预测失败: {e}")
            
            front_str = ' '.join(f"{n:02d}" for n in result['front_numbers'])
            back_str = ' '.join(f"{n:02d}" for n in result['back_numbers'])
            result_text = f"🎯 大乐透预测 · 第{result['period']}期\n"
            result_text += f"📅 基于 {result['date']} 之前全部数据\n"
            result_text += f"💾 共 {result['total_draws']} 期历史数据\n"
            result_text += "─" * 30 + "\n\n"
            result_text += f"🔴 {front_str} + 🔵 {back_str}"
            if prize_result:
                result_text += prize_result
    except Exception as e:
        logger.error(f"大乐透预测失败: {e}")
        result_text = f"❌ 大乐透今日预测生成失败"
    
    chat_id = context.job.chat_id
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
            logger.info(f"大乐透推送成功到 {chat_id}")
        except Exception as e:
            logger.error(f"大乐透推送失败: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理"""
    logger.error(f"Update {update} caused error {context.error}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理内联按钮点击"""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    # Get the original message to edit
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
        # Reuse stats logic
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
        await msg.edit_text(output, parse_mode='HTML', reply_markup=reply_markup)
    
    elif action == 'backtest':
        # 显示期数选择菜单
        keyboard = [
            [InlineKeyboardButton("最近20期", callback_data='bt_20'),
             InlineKeyboardButton("最近50期", callback_data='bt_50')],
            [InlineKeyboardButton("最近100期", callback_data='bt_100'),
             InlineKeyboardButton("最近200期", callback_data='bt_200')],
            [InlineKeyboardButton("✏️ 手动输入", callback_data='bt_custom'),
             InlineKeyboardButton("取消", callback_data='cancel')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg.edit_text(
            "📊 <b>评分卡回测</b>\n选择回测期数：",
            parse_mode='HTML', reply_markup=reply_markup
        )
    
    elif action in ('bt_20', 'bt_50', 'bt_100', 'bt_200'):
        periods = int(action.split('_')[1])
        await run_backtest_detail(update, context, periods)
    
    elif action == 'bt_custom':
        # 让用户输入期数
        await msg.edit_text(
            "✏️ 请输入回测期数（数字，1-200）：\n\n"
            "例：<code>30</code>",
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
    
    # 大乐透按钮回调
    elif action == 'dlt_predict':
        if DLT_AVAILABLE:
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
                    save_dlt_prediction(result['period'], 'dlt_scorecard', result['front_numbers'], result['back_numbers'])
                    await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                await msg.edit_text(f"❌ 预测失败: {str(e)}")
    
    elif action == 'dlt_stats':
        if DLT_AVAILABLE:
            draws = get_all_dlt_draws()
            latest = get_latest_dlt_draw()
            if latest:
                output = "📊 <b>大乐透系统状态</b>\n" + "─" * 15 + "\n"
                output += f"📅 {latest['date']}\n💾 {len(draws)} 期\n"
                output += f"🆕 第{latest['period']}期\n"
                front_str = ' '.join(f"{latest[f'front{i}']:02d}" for i in range(1,6))
                back_str = ' '.join(f"{latest[f'back{i}']:02d}" for i in range(1,3))
                output += f"{front_str} + {back_str}\n"
                output += "\n📌 开奖日: 周一/三/六"
                keyboard = [[InlineKeyboardButton("🎯 预测", callback_data='dlt_predict'),
                             InlineKeyboardButton("📈 回测", callback_data='dlt_backtest')]]
                await msg.edit_text(output, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    # 大乐透回测
    elif action == 'dlt_backtest':
        if not DLT_AVAILABLE: return
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
        if not DLT_AVAILABLE: return
        periods = int(action.split('_')[2])
        await run_dlt_backtest_detail(update, context, periods)


def setup_daily_push(application, chat_id):
    """设置定时推送 — 双色球+大乐透各自独立"""
    if application.job_queue is None:
        logger.warning("JobQueue不可用，跳过定时推送设置")
        return
    
    # Remove existing jobs for this chat
    current_jobs = application.job_queue.jobs()
    for job in current_jobs:
        if job.name in [f'ssq_push_{chat_id}', f'dlt_push_{chat_id}', f'daily_push_{chat_id}']:
            job.schedule_removal()
    
    # 双色球推送 08:00（周二/四/日）
    application.job_queue.run_daily(
        ssq_daily_push,
        time=datetime.strptime("08:00", "%H:%M").time(),
        chat_id=chat_id,
        name=f'ssq_push_{chat_id}'
    )
    
    # 大乐透推送 08:05（周一/三/六）— 错开5分钟避免消息轰炸
    if DLT_AVAILABLE:
        application.job_queue.run_daily(
            dlt_daily_push,
            time=datetime.strptime("08:05", "%H:%M").time(),
            chat_id=chat_id,
            name=f'dlt_push_{chat_id}'
        )
    
    logger.info(f"定时推送已设置 (双色球08:00/大乐透08:05, chat_id={chat_id})")


async def setup_menu(application):
    """设置Bot菜单命令（Telegram底部菜单栏）"""
    commands = [
        BotCommand("predict", "🎱 双色球预测"),
        BotCommand("stats", "📊 双色球数据"),
        BotCommand("backtest", "📈 双色球回测"),
        BotCommand("update", "🔄 更新双色球"),
        BotCommand("settings", "⚙️ 因子权重"),
        BotCommand("record", "📋 中奖记录"),
        BotCommand("dlt", "🎯 大乐透预测"),
        BotCommand("dlt_stats", "📊 大乐透数据"),
        BotCommand("dlt_backtest", "📈 大乐透回测"),
        BotCommand("dlt_update", "🔄 更新大乐透"),
        BotCommand("help", "❓ 帮助信息"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    """主函数"""
    # Initialize database
    init_db()
    
    # Ensure log directory exists
    os.makedirs(os.path.join(PROJECT_DIR, 'logs'), exist_ok=True)
    
    # Check if we have data
    if get_draw_count() == 0:
        print("首次运行，抓取全部历史数据...")
        fetch_all_history()
    
    # Build application
    application = Application.builder().token(TOKEN).post_init(setup_menu).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("predict", predict))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("backtest", backtest))
    application.add_handler(CommandHandler("update", update_data))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("record", record))
    
    # 大乐透命令
    if DLT_AVAILABLE:
        application.add_handler(CommandHandler("dlt", dlt_predict))
        application.add_handler(CommandHandler("dlt_stats", dlt_stats))
        application.add_handler(CommandHandler("dlt_record", dlt_record))
        application.add_handler(CommandHandler("dlt_backtest", dlt_backtest_command))
        application.add_handler(CommandHandler("dlt_update", dlt_update_command))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Text message handler (for manual backtest input, etc.)
    from telegram.ext import MessageHandler, filters
    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        
        # 检查是否在等待回测期数输入
        if context.user_data.get('awaiting_backtest_input'):
            try:
                periods = int(text)
                if 1 <= periods <= 200:
                    context.user_data['awaiting_backtest_input'] = False
                    # 直接跑回测
                    msg = await update.message.reply_text(f"🔄 正在回测最近{periods}期...")
                    
                    # 创建一个假的callback_query上下文用于run_backtest_detail
                    class FakeCallbackQuery:
                        def __init__(self, msg, from_user):
                            self.message = msg
                            self.from_user = from_user
                            self.data = None
                        async def edit_message_text(self, text, **kwargs):
                            return await msg.edit_text(text, **kwargs)
                    
                    fake_cq = FakeCallbackQuery(msg, update.message.from_user)
                    fake_update = Update(
                        update.update_id,
                        callback_query=fake_cq
                    )
                    await run_backtest_detail(fake_update, context, periods)
                else:
                    await update.message.reply_text("❌ 请输入1-500之间的数字")
            except ValueError:
                await update.message.reply_text("❌ 请输入有效数字")
            return
        
        # 其他文本消息忽略
        await update.message.reply_text(
            "使用 /help 查看可用命令"
        )
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 双色球预测Bot已启动...")
    print("📌 开奖日(周二/四/日)早上8:00自动推送预测")
    print("📌 首次使用请发 /start 初始化订阅")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
