#!/bin/bash
# 克隆所有项目到 issue-diagnosis-billing skill 期望的目录结构
# 用法：bash clone-all.sh
#
# 目录结构（与 skill 路径规则对齐）：
#   $BASE_DIR/input-project/standard/input/{repo-name}   ← 标准版收票服务
#   $BASE_DIR/input-project/refactor/{repo-name}         ← 重构版服务
#
# GITLAB_BASE 默认使用内网转发地址，可通过环境变量覆盖：
#   export GITLAB_BASE=http://123.207.158.7:5000/ai-agent/git
#   export GITLAB_TOKEN=your_token

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
GITLAB_BASE="${GITLAB_BASE:-http://123.207.158.7:5000/ai-agent/git}"
GITLAB_TOKEN=_VzevV42UrVFtJ4Wy4Ky

# 构造带 token 的 clone URL
git_url() {
  local path="$1"
  if [ -n "$GITLAB_TOKEN" ]; then
    echo "$GITLAB_BASE" | sed "s|://|://token:${GITLAB_TOKEN}@|"
    echo "${path}.git" | sed "s|^|$(echo $GITLAB_BASE | sed "s|://|://token:${GITLAB_TOKEN}@|")/|"
  else
    echo "${GITLAB_BASE}/${path}.git"
  fi
}

clone_if_missing() {
  local target_dir="$1"
  local repo_path="$2"
  local repo_url

  if [ -n "$GITLAB_TOKEN" ]; then
    repo_url="$(echo $GITLAB_BASE | sed "s|://|://token:${GITLAB_TOKEN}@|")/${repo_path}.git"
  else
    repo_url="${GITLAB_BASE}/${repo_path}.git"
  fi

  if [ -d "$target_dir/.git" ]; then
    echo "[skip] $target_dir 已存在"
  else
    echo "[clone] $repo_url -> $target_dir"
    mkdir -p "$(dirname "$target_dir")"
    git clone "$repo_url" "$target_dir"
  fi
}

STANDARD="$BASE_DIR/input-project/standard/input"
FRONTEND="$BASE_DIR/input-project/standard/frontend"
REFACTOR="$BASE_DIR/input-project/refactor"

echo "BASE_DIR: $BASE_DIR"
echo "GITLAB_BASE: $GITLAB_BASE"
echo ""

# ── 标准版收票服务（piaozone/input）────────────────────────
clone_if_missing "$STANDARD/api-expense"              piaozone/input/api-expense
clone_if_missing "$STANDARD/api-invoice-check"        piaozone/input/api-invoice-check
clone_if_missing "$STANDARD/api-invoice-collector"    piaozone/input/api-invoice-collector
clone_if_missing "$STANDARD/api-invoice-recognition"  piaozone/input/api-invoice-recognition
clone_if_missing "$STANDARD/api-invoice-input-db"     piaozone/input/api-invoice-input-db
clone_if_missing "$STANDARD/api-invoice-input-query"  piaozone/input/api-invoice-input-query
clone_if_missing "$STANDARD/api-fpzs"                 piaozone/input/api-fpzs
clone_if_missing "$STANDARD/api-invoice-manage"       piaozone/input/api-invoice-manage
clone_if_missing "$STANDARD/api-invoice-image"        piaozone/input/api-invoice-image
clone_if_missing "$STANDARD/api-invoice-ofd-analysis" piaozone/input/api-invoice-ofd-analysis
clone_if_missing "$STANDARD/api-invoice-erp-client"   piaozone/input/api-invoice-erp-client
clone_if_missing "$STANDARD/api-invoice-pdf-analysis" piaozone/input/api-invoice-pdf-analysis
clone_if_missing "$STANDARD/bill-bm-ocr-invoice"      piaozone/input/bill-bm-ocr-invoice
clone_if_missing "$STANDARD/bill-wechat-mini-program" piaozone/input/bill-wechat-mini-program
clone_if_missing "$STANDARD/api-invoice-input-utils"  piaozone/common/api-invoice-input-utils

# ── 标准版基础服务（piaozone/base）─────────────────────────
clone_if_missing "$STANDARD/api-invoice-frame"        piaozone/base/api-invoice-frame
clone_if_missing "$STANDARD/api-auth"                 piaozone/base/api-auth
clone_if_missing "$STANDARD/api-company"              piaozone/base/api-company

# ── 标准版输出层（piaozone/output）─────────────────────────
clone_if_missing "$STANDARD/api-invoice-create"       piaozone/output/api-invoice-create
clone_if_missing "$STANDARD/api-invoice-output-query" piaozone/output/api-invoice-output-query
clone_if_missing "$STANDARD/api-invoice-sm"           piaozone/output/api-invoice-sm
clone_if_missing "$STANDARD/api-interface"            piaozone/output/api-interface
clone_if_missing "$STANDARD/bill-smkp"                piaozone/output/bill-smkp

# ── 标准版影像档案（piaozone/imgsys-archive）───────────────
clone_if_missing "$STANDARD/api-archive"                piaozone/imgsys-archive/api-archive
clone_if_missing "$STANDARD/api-archive-scan"           piaozone/imgsys-archive/api-archive-scan
clone_if_missing "$STANDARD/api-archive-scan-move"      piaozone/imgsys-archive/api-archive-scan-move
clone_if_missing "$STANDARD/api-archive-organization"   piaozone/imgsys-archive/api-archive-organization
clone_if_missing "$STANDARD/api-archive-machine-manage" piaozone/imgsys-archive/api-archive-machine-manage
clone_if_missing "$STANDARD/api-archive-license"        piaozone/imgsys-archive/api-archive-license
clone_if_missing "$STANDARD/api-archive-invoice"        piaozone/imgsys-archive/api-archive-invoice
clone_if_missing "$STANDARD/api-archive-webservice"     piaozone/imgsys-archive/api-archive-webservice
clone_if_missing "$STANDARD/api-archive-job"            piaozone/imgsys-archive/api-archive-job
clone_if_missing "$STANDARD/api-archive-alarm-monitor"  piaozone/imgsys-archive/api-archive-alarm-monitor

# ── 标准版全电集成层（piaozone/elc-integration）────────────
clone_if_missing "$STANDARD/api-elc-digital-invoice"  piaozone/elc-integration/api-elc-digital-invoice
clone_if_missing "$STANDARD/api-elc-invoice-lqpt"     piaozone/elc-integration/api-elc-invoice-lqpt
clone_if_missing "$STANDARD/api-elc-invoice-create"   piaozone/elc-integration/api-elc-invoice-create
clone_if_missing "$STANDARD/api-elc-invoice-collect"  piaozone/elc-integration/api-elc-invoice-collect
clone_if_missing "$STANDARD/api-elc-invoice-gjfp"     piaozone/elc-integration/api-elc-invoice-gjfp
clone_if_missing "$STANDARD/api-elc-invoice-engine"   piaozone/elc-integration/api-elc-invoice-engine

# ── 公共工具（piaozone/common）─────────────────────────────
clone_if_missing "$STANDARD/api-pdf-utils"              piaozone/common/api-pdf-utils
clone_if_missing "$STANDARD/api-ofd-utils"              piaozone/common/api-ofd-utils

# ── 前端（piaozone/frontend）───────────────────────────────
clone_if_missing "$FRONTEND/fpzs-pc"                    piaozone/frontend/fpzs-pc
clone_if_missing "$FRONTEND/portal-web"                 piaozone/frontend/portal-web

# ── 重构版服务 ─────────────────────────────────────────────
clone_if_missing "$REFACTOR/fpy-isv"        piaozone-v2/app/fpy-isv
clone_if_missing "$REFACTOR/fpy-base-query" piaozone-v2/base/fpy-base-query

echo ""
echo "✅ 全部完成"
