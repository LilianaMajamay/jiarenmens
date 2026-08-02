#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# 东方财富实盘选手爬虫 - 腾讯云 Ubuntu 一键部署脚本
# ═══════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/LilianaMajamay/jiarenmens.git"
INSTALL_DIR="${INSTALL_DIR:-/opt/jiarenmens}"
BRANCH="${BRANCH:-main}"
PYTHON="${PYTHON:-python3}"

echo "=========================================="
echo " 东方财富实盘选手爬虫 - 服务器部署"
echo "=========================================="

# ── 1. 系统依赖 ──
echo ""
echo "[1/6] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget \
    fonts-noto-cjk fonts-noto-cjk-extra \
    cron

# ── 2. 克隆/更新代码 ──
echo ""
echo "[2/6] 获取代码..."
if [ -d "$INSTALL_DIR" ]; then
    echo "目录已存在，更新代码..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    sudo mkdir -p "$(dirname "$INSTALL_DIR")"
    sudo git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── 3. 创建虚拟环境 + 安装 Python 依赖 ──
echo ""
echo "[3/6] 安装 Python 依赖..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 4. 安装 Playwright Chromium ──
echo ""
echo "[4/6] 安装 Playwright Chromium 浏览器..."
PLAYWRIGHT="$INSTALL_DIR/venv/bin/playwright"
$PLAYWRIGHT install chromium
# install-deps 内部会用 sudo 装系统库，所以给完整路径
sudo env PATH="$INSTALL_DIR/venv/bin:$PATH" "$PLAYWRIGHT" install-deps chromium

# ── 5. 配置环境变量 ──
echo ""
echo "[5/6] 配置环境变量..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  .env 文件已从 .env.example 创建，请按需编辑: sudo vim $INSTALL_DIR/.env"
    fi
fi

# 创建数据目录
mkdir -p data logs

# ── 6. 安装 systemd 服务 ──
echo ""
echo "[6/6] 安装 systemd 服务..."
sudo cp deploy/jiarenmens.service /etc/systemd/system/
sudo mkdir -p /etc/jiarenmens
sudo cp .env /etc/jiarenmens/env 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable jiarenmens.service
echo "  systemd 服务已安装: sudo systemctl start jiarenmens"

# ── 安装定时任务 ──
if [ -f "deploy/crontab" ]; then
    sudo cp deploy/crontab /etc/cron.d/jiarenmens
    sudo chmod 644 /etc/cron.d/jiarenmens
    echo "  定时任务已安装: /etc/cron.d/jiarenmens"
fi

# ── 设置权限 ──
sudo chown -R $(whoami):$(whoami) "$INSTALL_DIR" 2>/dev/null || true

echo ""
echo "=========================================="
echo " 部署完成！"
echo "=========================================="
echo ""
echo "  安装目录: $INSTALL_DIR"
echo "  启动服务: sudo systemctl start jiarenmens"
echo "  查看状态: sudo systemctl status jiarenmens"
echo "  查看日志: sudo journalctl -u jiarenmens -f"
echo "  手动运行: cd $INSTALL_DIR && venv/bin/python main.py --test"
echo ""
echo "  编辑配置: sudo vim $INSTALL_DIR/.env"
echo "  重启服务: sudo systemctl restart jiarenmens"
echo ""
