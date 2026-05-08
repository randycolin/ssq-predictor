# 🎯 双色球 + 大乐透 预测Bot

基于评分卡模型的彩票预测系统，通过 Telegram Bot 实现交互。

## 📋 功能

### 🔴 双色球
- 评分卡模型：老彩民因子 + AI因子融合
- 结构优先选号：匹配真实开奖结构模板
- 回测系统：验证模型有效性
- 自动推送：开奖日（周二/四/日）08:00
- 中奖记录自动比对

### 🟡 大乐透
- 前区：老彩民因子（重号/邻号/和值/区间）
- 后区：Pair直接评分（近期热度/连开趋势/邻号趋势/跨度结构）
- 结构优先选号：前区8模板 + 后区4模板
- 回测系统：大乐透完整中奖规则验证（8个奖级）
- 自动推送：开奖日（周一/三/六）08:05

## 📁 目录结构

```
ssq-predictor/
├── bot.py              # Telegram Bot 主程序
├── scorecard.py        # 双色球评分卡模型
├── dlt_scorecard.py    # 大乐透评分卡模型
├── database.py         # 双色球数据库操作
├── dlt_database.py     # 大乐透数据库操作
├── fetch_data.py       # 双色球数据爬虫
├── fetch_dlt.py        # 大乐透数据爬虫
├── algorithms.py       # 算法工具箱（备用）
├── predict_engine.py   # 预测引擎（备用）
├── tests/              # 测试/分析脚本
├── logs/               # 日志文件
└── ssq.db / dlt.db     # SQLite数据库（自动生成）
```

## 🚀 部署方式

### 环境要求
- **系统**: Linux (已在 Kali Linux 上测试)
- **Python**: 3.8+
- **依赖**: `pip install python-telegram-bot`

### 服务端部署（当前服务器）

本项目运行在 **`/root/ssq-predictor/`** 目录下，作为 systemd 服务运行。

```bash
# 1. 克隆代码
git clone https://github.com/randycolin/ssq-predictor.git /root/ssq-predictor
cd /root/ssq-predictor

# 2. 安装依赖
pip install python-telegram-bot --break-system-packages

# 3. 设置Token环境变量
export SSQ_BOT_TOKEN="你的Telegram Bot Token"

# 4. 运行（首次会自动抓取全部历史数据）
python3 bot.py
```

### 作为系统服务（推荐）

```ini
# /etc/systemd/system/ssq-bot.service
[Unit]
Description=SSQ Predictor Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ssq-predictor
ExecStart=/usr/bin/python3 -u /root/ssq-predictor/bot.py
Environment=SSQ_BOT_TOKEN=你的Telegram Bot Token
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ssq-bot
sudo systemctl start ssq-bot
```

## 🤖 Telegram Bot 命令

### 双色球
| 命令 | 功能 |
|------|------|
| `/predict` | 双色球预测 |
| `/stats` | 数据统计 |
| `/backtest` | 模型回测 |
| `/update` | 更新数据 |
| `/settings` | 因子权重 |
| `/record` | 中奖记录（合并双色球+大乐透） |

### 大乐透
| 命令 | 功能 |
|------|------|
| `/dlt` | 大乐透预测 |
| `/dlt_stats` | 大乐透数据 |
| `/dlt_backtest` | 大乐透回测 |
| `/dlt_update` | 更新大乐透数据 |
| `/dlt_record` | 大乐透中奖记录 |

## 📊 模型说明

### 双色球评分卡
- **红球**（33选6）：老彩民因子（重号×3、邻号×2、和值平衡×2、区间平衡×2）
- **蓝球**（16选1）：AI因子（近期热度×2、历史频率×1、重号×1.5、邻号×1）
- **选号策略**：TOP20候选 → 匹配8个真实结构模板 → 最高分组合
- **回测表现**：平均红球命中 1.14~1.20（随机期望1.09）

### 大乐透评分卡
- **前区**（35选5）：老彩民因子（重号×3、邻号×2、和值平衡×2、区间平衡×2）
- **后区**（12选2）：Pair直接评分（近期热度、连开趋势、邻号趋势、跨度结构）
- **选号策略**：TOP15前区 → 8模板匹配 + TOP25后区Pair → 4模板匹配
- **回测表现**：后区命中率≈37%（随机期望33.3%），总中奖率≈43%

### 中奖规则
| 等级 | 双色球 | 大乐透 |
|------|--------|--------|
| 🥇 一等奖 | 6+1 | 5+2 |
| 🥈 二等奖 | 6+0 | 5+1 |
| 🥉 三等奖 | 5+1 | 5+0 |
| 四等奖 | 5+0 / 4+1 | 4+2 |
| 五等奖 | 4+0 / 3+1 | 4+1 / 3+2 |
| 六等奖 | 2+1 / 1+1 / 0+1 | 4+0 / 3+1 / 2+2 |
| 七等奖 | — | 3+0 / 2+1 / 1+2 / 0+2 |
| 八等奖 | — | 2+0 / 1+1 / 0+1 |

## ⚠️ 免责声明

彩票开奖是随机物理事件，本系统仅基于历史数据的统计模式分析，**不能保证中奖**。评分卡模型的优势在于帮助用户避开明显不合理的号码组合，比纯随机略好。理性购彩，量力而行。

## 🔧 维护

```bash
# 查看服务状态
sudo systemctl status ssq-bot

# 查看日志
tail -f /root/ssq-predictor/logs/bot.log

# 手动更新数据（Bot内使用 /update /dlt_update）
```

## 📝 数据来源

- 双色球：2003年至今 3447+ 期历史数据
- 大乐透：2007年至今 1364+ 期历史数据
- 数据自动抓取，首次运行会爬取全部历史
- 数据库文件自动生成于项目目录
