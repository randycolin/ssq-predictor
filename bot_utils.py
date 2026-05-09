#!/usr/bin/env python3
"""
双色球+大乐透 Bot 工具函数
"""
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

# ============================================================
# 节假日期市日期
# ============================================================
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
    """获取下个双色球开奖日"""
    today = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        if d.weekday() in [1, 3, 6]:  # Tue, Thu, Sun
            d_str = d.strftime("%Y-%m-%d")
            if d_str not in HOLIDAYS_2026:
                return d
    return today


class FakeCallbackQuery:
    """用于文本消息回测输入的假CallbackQuery"""
    def __init__(self, msg, from_user):
        self.message = msg
        self.from_user = from_user
        self.data = None

    async def edit_message_text(self, text, **kwargs):
        return await self.message.edit_text(text, **kwargs)


# ============================================================
# 中奖判定公共函数（所有模块共用，改一处全改）
# ============================================================

def ssq_prize_level(red_hit: int, blue_hit: int):
    """双色球奖级判定（6个奖级）
    返回奖级字符串（如 '🥇 一等奖'），未中奖返回 None
    """
    if red_hit == 6 and blue_hit: return "🥇 一等奖"
    elif red_hit == 6: return "🥈 二等奖"
    elif red_hit == 5 and blue_hit: return "🥉 三等奖"
    elif red_hit == 5 or (red_hit == 4 and blue_hit): return "四等奖"
    elif red_hit == 4 or (red_hit == 3 and blue_hit): return "五等奖"
    elif blue_hit: return "六等奖"
    return None


def dlt_prize_level(front_hit: int, back_hit: int):
    """大乐透奖级判定（8个奖级）
    返回奖级字符串（如 '🥇 一等奖'），未中奖返回 None
    ⚠️ 大乐透只有8个奖级，没有九等奖
    """
    if front_hit == 5 and back_hit == 2: return "🥇 一等奖"
    elif front_hit == 5 and back_hit == 1: return "🥈 二等奖"
    elif front_hit == 5: return "🥉 三等奖"
    elif front_hit == 4 and back_hit == 2: return "四等奖"
    elif (front_hit == 4 and back_hit == 1) or (front_hit == 3 and back_hit == 2): return "五等奖"
    elif (front_hit == 4 and back_hit == 0) or (front_hit == 3 and back_hit == 1) or (front_hit == 2 and back_hit == 2): return "六等奖"
    elif (front_hit == 3 and back_hit == 0) or (front_hit == 2 and back_hit == 1) or (front_hit == 1 and back_hit == 2) or (front_hit == 0 and back_hit == 2): return "七等奖"
    elif (front_hit == 2 and back_hit == 0) or (front_hit == 1 and back_hit == 1) or (front_hit == 0 and back_hit == 1): return "八等奖"
    return None
