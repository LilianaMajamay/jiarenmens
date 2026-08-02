#!/usr/bin/env bash
# 东方财富实盘选手爬虫 - Ubuntu/Linux 一键安装
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 创建虚拟环境"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

echo "==> 安装依赖"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> 配置 .env"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "已生成 .env，请编辑填入 SPZH_* 会话令牌"
fi

echo "==> 完成"
echo "运行: .venv/bin/python main.py --test"
