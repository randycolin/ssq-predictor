#!/usr/bin/env python3
"""
定时推送 — ssq_daily_push / dlt_daily_push
"""
import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from database import get_all_draws, get_conn, save_prediction, save_prediction_result
from fetch_data import fetch_latest
from scorecard import scorecard_predict_detailed
from bot_utils import is_ssq_draw_day, is_dlt_draw_day
from dlt_database import (
    get_all_dlt_draws, get_conn as dlt_get_conn,
    save_dlt_prediction, save_dlt_prediction_result
)
from dlt_scorecard import dlt_predict_detailed
from fetch_dlt import fetch_dlt_latest

logger = logging.getLogger(__name__)

DLT_AVAILABLE = True  # 由 bot.py 覆写


async def ssq_daily_push(context: ContextTypes.DEFAULT_TYPE):
    """双色球定时推送 — 仅周二/四/日"""
    if not is_ssq_draw_day():
        logger.info("今天不是双色球开奖日，跳过推送")
        return

    logger.info("执行双色球开奖日推送...")

    # 更新数据
    try:
        fetch_latest()
    except Exception as e:
        logger.error(f"更新数据失败: {e}")

    # 比对上一期预测
    prize_result = None
    try:
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
                    from bot_utils import ssq_prize_level
                    prize_level = ssq_prize_level(red_hit, blue_hit)
                    save_prediction_result(prev['period'], 'scorecard', red_hit, blue_hit, prize_level)
                    logger.info(f"已更新双色球中奖: 第{prev['period']}期 红{red_hit}蓝{blue_hit} {prize_level or '未中奖'}")
                    if prize_level:
                        prize_result = f"\n\n🎉 <b>上期预测结果：</b>\n第{prev['period']}期 {' '.join(f'{n:02d}' for n in pred_reds)} + {pred_blue:02d}\n红{red_hit}蓝{blue_hit} → {prize_level}！"
    except Exception as e:
        logger.error(f"比对双色球中奖失败: {e}")

    # 生成新预测
    try:
        result = scorecard_predict_detailed()
        if isinstance(result, str) or 'error' in result:
            result_text = result if isinstance(result, str) else "❌ 双色球预测失败"
        else:
            try:
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
        result_text = "❌ 双色球今日预测生成失败"

    chat_id = context.job.chat_id
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
            logger.info(f"双色球推送成功到 {chat_id}")
        except Exception as e:
            logger.error(f"双色球推送失败: {e}")


async def dlt_daily_push(context: ContextTypes.DEFAULT_TYPE):
    """大乐透定时推送 — 仅周一/三/六"""
    if not context.bot_data.get('DLT_AVAILABLE', DLT_AVAILABLE):
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

    # 比对上一期预测
    prize_result = None
    try:
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
                    pred_fronts = {p[f'front{i}'] for i in range(1, 6)}
                    pred_backs = {p[f'back{i}'] for i in range(1, 3)}
                    actual_fronts = {prev[f'front{i}'] for i in range(1, 6)}
                    actual_backs = {prev[f'back{i}'] for i in range(1, 3)}
                    fh = len(pred_fronts & actual_fronts)
                    bh = len(pred_backs & actual_backs)
                    prize = None
                    from bot_utils import dlt_prize_level
                    prize = dlt_prize_level(fh, bh)
                    save_dlt_prediction_result(p['period'], 'dlt_scorecard', fh, bh, prize)
                    logger.info(f"已更新大乐透中奖: 第{prev['period']}期 前{fh}后{bh} {prize or '未中奖'}")
                    if prize:
                        f_str = ' '.join(f"{p[f'front{i}']:02d}" for i in range(1, 6))
                        b_str = ' '.join(f"{p[f'back{i}']:02d}" for i in range(1, 3))
                        prize_result = f"\n\n🎉 <b>上期预测结果：</b>\n第{prev['period']}期 {f_str} + {b_str}\n前{fh}后{bh} → {prize}！"
    except Exception as e:
        logger.error(f"比对大乐透中奖失败: {e}")

    # 生成新预测
    try:
        result = dlt_predict_detailed()
        if isinstance(result, str) or 'error' in result:
            result_text = result if isinstance(result, str) else "❌ 大乐透预测失败"
        else:
            try:
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
        result_text = "❌ 大乐透今日预测生成失败"

    chat_id = context.job.chat_id
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
            logger.info(f"大乐透推送成功到 {chat_id}")
        except Exception as e:
            logger.error(f"大乐透推送失败: {e}")
