#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

say() { echo -e "${GREEN}[VASP Agent]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
die() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
say "VASP Agent — 一键部署脚本"
echo ""

# ── 1. Check Docker ───────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    die "未安装 Docker。运行: curl -fsSL https://get.docker.com | bash"
fi
say "Docker ✓"

if ! docker compose version &>/dev/null 2>&1; then
    die "Docker Compose 不可用。请安装 Docker Compose v2。"
fi
say "Docker Compose ✓"

# ── 2. Check .env ──────────────────────────────────────────────────────

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        die "缺少 .env 文件。请先:\n  cp .env.example .env\n  然后编辑 .env 填入 DOMAIN 和 VASP_API_KEY"
    else
        die "缺少 .env 文件。请创建并设置 DOMAIN 和 VASP_API_KEY。"
    fi
fi

# shellcheck disable=SC2046
export $(grep -v '^#' .env | xargs)

if [ -z "${DOMAIN:-}" ] || [ "$DOMAIN" = "vasp.example.com" ]; then
    die "请在 .env 中设置你的真实域名 DOMAIN=你的域名"
fi

if [ -z "${VASP_API_KEY:-}" ] || [ "$VASP_API_KEY" = "change-me-to-a-random-hex-string" ]; then
    NEW_KEY=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))")
    warn "VASP_API_KEY 未设置，自动生成: $NEW_KEY"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/change-me-to-a-random-hex-string/$NEW_KEY/" .env
    else
        sed -i "s/change-me-to-a-random-hex-string/$NEW_KEY/" .env
    fi
    export VASP_API_KEY="$NEW_KEY"
fi

say "DOMAIN = $DOMAIN"
say "API Key = ${VASP_API_KEY:0:8}..."

# ── 3. Check POTCAR library ────────────────────────────────────────────

POTCAR_DIR="${VASP_POTCAR_HOST:-./potcar_library}"
if [ ! -d "$POTCAR_DIR" ]; then
    warn "POTCAR 库目录 '$POTCAR_DIR' 不存在，正在创建..."
    mkdir -p "$POTCAR_DIR/PBE"
    warn "请将 POTCAR 文件放入 $POTCAR_DIR/PBE/<元素>/POTCAR"
    warn "缺少 POTCAR 时生成会报错，但服务仍可启动"
fi

# ── 4. Build & start ───────────────────────────────────────────────────

say "构建 Docker 镜像..."
docker compose build --pull

say "启动服务..."
docker compose up -d

# ── 5. Verify ──────────────────────────────────────────────────────────

sleep 3
if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    say "后端健康检查通过"
else
    warn "后端未就绪，查看日志: docker compose logs vasp-agent"
fi

echo ""
say "部署完成！"
echo ""
echo "  https://$DOMAIN"
echo ""
echo "  API Key: $VASP_API_KEY"
echo ""
echo "  把上面的地址和 Key 发给用户即可。"
echo "  查看日志: docker compose logs -f"
echo "  停止服务: docker compose down"
echo ""
