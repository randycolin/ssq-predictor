#!/usr/bin/env python3
"""
双色球+大乐透预测Bot — 主入口
"""
import asyncio
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# 数据库初始化
from database import init_db, get_draw_count
from fetch_data import fetch_all_history

from bot_utils import logger

# ===== 从各模块加载命令函数 =====
from commands_ssq import predict, stats, backtest, update_data, settings
from commands_dlt import (
    dlt_predict, dlt_stats, dlt_record, dlt_backtest_command, dlt_update_command
)
from record import record
from daily_push import ssq_daily_push, dlt_daily_push
from callbacks import button_callback

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(PROJECT_DIR, 'logs'), exist_ok=True)

# ===== Token =====
TOKEN = os.environ.get("SSQ_BOT_TOKEN", "")
if not TOKEN:
    logger.error("SSQ_BOT_TOKEN 环境变量未设置！")
    sys.exit(1)

# ===== 大乐透模块检查 =====
try:
    from dlt_database import init_dlt_tables
    from fetch_dlt import fetch_all_dlt_history
    DLT_AVAILABLE = True
except Exception as e:
    logger.warning(f"大乐透模块加载失败: {e}")
    DLT_AVAILABLE = False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    chat_id = update.effective_chat.id
    from daily_push import setup_daily_push
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

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


def setup_daily_push(application, chat_id):
    """设置定时推送"""
    if application.job_queue is None:
        logger.warning("JobQueue不可用，跳过定时推送设置")
        return

    from bot_utils import is_ssq_draw_day, is_dlt_draw_day

    current_jobs = application.job_queue.jobs()
    for job in current_jobs:
        if job.name in [f'ssq_push_{chat_id}', f'dlt_push_{chat_id}', f'daily_push_{chat_id}']:
            job.schedule_removal()

    application.job_queue.run_daily(
        ssq_daily_push,
        time=datetime.strptime("08:00", "%H:%M").time(),
        chat_id=chat_id,
        name=f'ssq_push_{chat_id}'
    )

    if DLT_AVAILABLE:
        application.job_queue.run_daily(
            dlt_daily_push,
            time=datetime.strptime("08:05", "%H:%M").time(),
            chat_id=chat_id,
            name=f'dlt_push_{chat_id}'
        )

    logger.info(f"定时推送已设置 (双色球08:00/大乐透08:05, chat_id={chat_id})")


async def setup_menu(application):
    """设置Bot菜单命令"""
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


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文本消息（回测手动输入等）"""
    text = update.message.text.strip()

    if context.user_data.get('awaiting_backtest_input'):
        try:
            periods = int(text)
            if 1 <= periods <= 200:
                context.user_data['awaiting_backtest_input'] = False
                msg = await update.message.reply_text(f"🔄 正在回测最近{periods}期...")

                from bot_utils import FakeCallbackQuery
                fake_cq = FakeCallbackQuery(msg, update.message.from_user)
                fake_update = Update(update.update_id, callback_query=fake_cq)
                from commands_ssq import run_backtest_detail
                await run_backtest_detail(fake_update, context, periods)
            else:
                await update.message.reply_text("❌ 请输入1-200之间的数字")
        except ValueError:
            await update.message.reply_text("❌ 请输入有效数字")
        return

    await update.message.reply_text("使用 /help 查看可用命令")


def main():
    """主函数"""
    # 初始化数据库
    init_db()
    if DLT_AVAILABLE:
        init_dlt_tables()

    # 首次运行抓取全部数据
    if get_draw_count() == 0:
        print("首次运行，抓取双色球全部历史数据...")
        fetch_all_history()
    if DLT_AVAILABLE:
        from dlt_database import get_dlt_draw_count
        if get_dlt_draw_count() == 0:
            print("首次运行，抓取大乐透全部历史数据...")
            fetch_all_dlt_history()

    # 构建Application
    application = Application.builder().token(TOKEN).post_init(setup_menu).build()
    application.bot_data['DLT_AVAILABLE'] = DLT_AVAILABLE

    # 注册Handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # 双色球命令
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

    # 其他Handler
    application.add_error_handler(error_handler)
    application.add_handler(CallbackQueryHandler(button_callback))

    # 文本消息Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 双色球+大乐透预测Bot已启动...")
    print("📌 双色球开奖日(周二/四/日) 08:00 推送")
    print("📌 大乐透开奖日(周一/三/六) 08:05 推送")
    print("📌 首次使用请发 /start 初始化订阅")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
