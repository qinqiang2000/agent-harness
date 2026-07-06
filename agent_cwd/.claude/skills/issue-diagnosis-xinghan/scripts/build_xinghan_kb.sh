#!/usr/bin/env bash
# build_xinghan_kb.sh
# 批量反编译星瀚 jar 包，输出到 data/kb/source/xinghan/
#
# 用法：
#   # 模式1：从补丁包 zip 自动提取（推荐）
#   ./build_xinghan_kb.sh --from-patch /path/to/CONSTELLATION.VX.X.X_XXXX.zip
#
#   # 模式2：指定已有的 jar/biz/ 目录
#   ./build_xinghan_kb.sh --jar-dir /path/to/jar/biz/
#
# 补丁包结构：
#   CONSTELLATION.VX.X.X_XXXX.zip
#     └── CONSTELLATION.IMC.VX.X.X_XXXX.zip   ← 发票云 jar 包
#           └── jar/biz/imc-bdm.zip 等

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CWD="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

DEFAULT_OUT_DIR="$AGENT_CWD/data/kb/source/xinghan"
WORK_DIR="/tmp/xinghan_build_$$"

OUT_DIR="$DEFAULT_OUT_DIR"
JAR_DIR=""
PATCH_ZIP=""

# ── 参数解析 ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-patch) PATCH_ZIP="$2"; shift 2 ;;
    --jar-dir)    JAR_DIR="$2"; shift 2 ;;
    --out-dir)    OUT_DIR="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

# ── 模式1：从补丁包自动提取 jar/biz/ ─────────────────────────────────────────
if [[ -n "$PATCH_ZIP" ]]; then
  [[ -f "$PATCH_ZIP" ]] || { echo "❌ 补丁包不存在: $PATCH_ZIP"; exit 1; }

  PATCH_NAME=$(basename "$PATCH_ZIP" .zip)
  echo "▶ 解压外层补丁包: $PATCH_NAME"

  # 版本号从补丁包文件名提取，如 CONSTELLATION.V8.0.14_0612 → 8.0.14
  VERSION=$(echo "$PATCH_NAME" | grep -oE 'V[0-9]+\.[0-9]+\.[0-9]+' | head -1 | tr -d 'V' || echo "unknown")

  OUTER_DIR="$WORK_DIR/outer"
  mkdir -p "$OUTER_DIR"
  unzip -q "$PATCH_ZIP" -d "$OUTER_DIR"

  # 找 IMC zip（发票云专属包）
  IMC_ZIP=$(find "$OUTER_DIR" -name "CONSTELLATION.IMC*.zip" | head -1)
  if [[ -z "$IMC_ZIP" ]]; then
    echo "❌ 未找到 CONSTELLATION.IMC*.zip，请确认补丁包内容"
    exit 1
  fi
  echo "  找到 IMC 包: $(basename "$IMC_ZIP")"

  # 从 IMC zip 中只解压 jar/biz/ 目录
  IMC_DIR="$WORK_DIR/imc"
  mkdir -p "$IMC_DIR"
  echo "▶ 解压 IMC 包中的 jar/biz/..."
  unzip -q "$IMC_ZIP" "jar/biz/*" -d "$IMC_DIR"

  JAR_DIR="$IMC_DIR/jar/biz"
  echo "  jar/biz 目录: $JAR_DIR"

# ── 模式2：直接使用已有 jar/biz/ 目录 ────────────────────────────────────────
elif [[ -n "$JAR_DIR" ]]; then
  [[ -d "$JAR_DIR" ]] || { echo "❌ JAR 目录不存在: $JAR_DIR"; exit 1; }
  # 版本号从路径中提取
  VERSION=$(echo "$JAR_DIR" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")

else
  echo "用法："
  echo "  $0 --from-patch /path/to/CONSTELLATION.VX.X.X_XXXX.zip"
  echo "  $0 --jar-dir /path/to/jar/biz/"
  exit 1
fi

VERSIONED_OUT_DIR="$OUT_DIR/$VERSION"
echo ""
echo "版本号    : $VERSION"
echo "JAR 目录  : $JAR_DIR"
echo "输出目录  : $VERSIONED_OUT_DIR"

# ── 前置检查 ──────────────────────────────────────────────────────────────────
command -v jar  >/dev/null 2>&1 || { echo "❌ 需要 jar 命令（JDK）"; exit 1; }
command -v java >/dev/null 2>&1 || { echo "❌ 需要 java 命令（JRE/JDK）"; exit 1; }

# 优先用 Vineflower，找不到再用 CFR
SKILLS_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DECOMPILER_JAR=$(find "$SKILLS_DIR" -name "vineflower*.jar" 2>/dev/null | head -1)
DECOMPILER_TYPE="vineflower"
if [[ -z "$DECOMPILER_JAR" || ! -f "$DECOMPILER_JAR" ]]; then
  DECOMPILER_JAR=$(find "$SKILLS_DIR" -name "cfr*.jar" 2>/dev/null | head -1)
  DECOMPILER_TYPE="cfr"
fi
if [[ -z "$DECOMPILER_JAR" || ! -f "$DECOMPILER_JAR" ]]; then
  echo "❌ 未找到反编译器 jar，请下载以下任一："
  echo "   Vineflower: https://github.com/Vineflower/vineflower/releases"
  echo "   CFR: https://github.com/leibnitz27/cfr/releases"
  echo "   并放到 $SCRIPT_DIR/ 目录下"
  exit 1
fi
echo "反编译器   : $DECOMPILER_TYPE ($DECOMPILER_JAR)"

mkdir -p "$VERSIONED_OUT_DIR"

INDEX_FILE="$VERSIONED_OUT_DIR/index.md"
echo "# 星瀚源码 KB 索引（Vineflower 反编译）" > "$INDEX_FILE"
echo "" >> "$INDEX_FILE"
echo "版本: $VERSION" >> "$INDEX_FILE"
echo "构建时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$INDEX_FILE"
echo "" >> "$INDEX_FILE"
echo "| 类名 | 文件 | 来源 jar |" >> "$INDEX_FILE"
echo "|------|------|---------|" >> "$INDEX_FILE"

TOTAL_FILE="$WORK_DIR/.total"
FAILED_FILE="$WORK_DIR/.failed"
echo 0 > "$TOTAL_FILE"
echo 0 > "$FAILED_FILE"

# ── 函数：处理单个 jar ────────────────────────────────────────────────────────
process_jar() {
  local jar_path="$1"
  local module_name="$2"
  local out_module_dir="$VERSIONED_OUT_DIR/$module_name"

  mkdir -p "$out_module_dir"

  local class_count
  class_count=$(jar tf "$jar_path" 2>/dev/null | grep '^kd/imc/' | grep '\.class$' | grep -v '\$' | wc -l | tr -d ' \n\t' || echo 0)

  if [[ "$class_count" -eq 0 ]]; then
    return
  fi

  echo "  处理 $module_name ($class_count 个类)..."

  local decompile_ok=false
  if [[ "$DECOMPILER_TYPE" == "vineflower" ]]; then
    java -jar "$DECOMPILER_JAR" "$jar_path" "$out_module_dir/" > /dev/null 2>&1 && decompile_ok=true
  else
    java -jar "$DECOMPILER_JAR" "$jar_path" --outputdir "$out_module_dir" \
      --silent true --comments false > /dev/null 2>&1 && decompile_ok=true
  fi

  if $decompile_ok; then
    local count
    count=$(find "$out_module_dir" -name "*.java" 2>/dev/null | wc -l | tr -d ' ')
    echo $(( $(cat "$TOTAL_FILE") + count )) > "$TOTAL_FILE"
    find "$out_module_dir" -name "*.java" | while read -r java_file; do
      local rel_path="${java_file#$VERSIONED_OUT_DIR/}"
      local cls_name
      cls_name=$(basename "$java_file" .java)
      echo "| \`$cls_name\` | \`$rel_path\` | \`$(basename "$jar_path")\` |" >> "$INDEX_FILE"
    done

    # 兜底：对反编译失败的方法追加 javap 字节码
    local failed_files
    failed_files=$(grep -rl "This method has failed to decompile" "$out_module_dir" 2>/dev/null || true)
    if [[ -n "$failed_files" ]]; then
      local fallback_count=0
      local extract_dir="$WORK_DIR/${module_name}_fallback"
      mkdir -p "$extract_dir"
      while IFS= read -r java_file; do
        [[ -z "$java_file" ]] && continue
        local cls_name
        cls_name=$(basename "$java_file" .java)
        local rel_java="${java_file#$out_module_dir/}"
        local class_path="${rel_java%.java}.class"
        pushd "$extract_dir" > /dev/null
        jar xf "$jar_path" "$class_path" 2>/dev/null || true
        popd > /dev/null
        if [[ -f "$extract_dir/$class_path" ]]; then
          {
            echo ""
            echo "// ═══════════════════════════════════════════════════════════════"
            echo "// 以下方法反编译失败，自动补充 javap 字节码供参考"
            echo "// ═══════════════════════════════════════════════════════════════"
            javap -p -c "$extract_dir/$class_path" 2>/dev/null || true
          } >> "$java_file"
          fallback_count=$(( fallback_count + 1 ))
        fi
      done <<< "$failed_files"
      [[ $fallback_count -gt 0 ]] && echo "    ↳ 兜底补充 javap: $fallback_count 个类"
    fi
  else
    echo "  ⚠️  反编译 $module_name 失败，跳过"
    echo $(( $(cat "$FAILED_FILE") + 1 )) > "$FAILED_FILE"
  fi
}

# ── 处理直接目录下的 jar ───────────────────────────────────────────────────────
echo ""
echo "▶ 处理直接 jar 文件..."
while IFS= read -r jar_file; do
  [[ -z "$jar_file" ]] && continue
  module=$(basename "$jar_file" | sed 's/-[0-9]*\.[0-9]*\.jar$//')
  process_jar "$jar_file" "$module"
done < <(find "$JAR_DIR" -maxdepth 2 -name "*.jar" ! -path "*/\.*")

# ── 处理 zip 内的 jar ─────────────────────────────────────────────────────────
echo ""
echo "▶ 处理 zip 包内的 jar..."
while IFS= read -r zip_file; do
  [[ -z "$zip_file" ]] && continue
  zip_name=$(basename "$zip_file" .zip)
  zip_work="$WORK_DIR/zip_$zip_name"
  mkdir -p "$zip_work"
  echo "  解压 $zip_name.zip..."
  unzip -q "$zip_file" "*.jar" -d "$zip_work" 2>/dev/null || true
  while IFS= read -r jar_file; do
    [[ -z "$jar_file" ]] && continue
    module=$(basename "$jar_file" | sed 's/-[0-9]*\.[0-9]*\.jar$//')
    process_jar "$jar_file" "$module"
  done < <(find "$zip_work" -name "*.jar")
done < <(find "$JAR_DIR" -maxdepth 1 -name "*.zip")

# ── 汇总 ──────────────────────────────────────────────────────────────────────
TOTAL=$(cat "$TOTAL_FILE")
FAILED=$(cat "$FAILED_FILE")

echo ""
echo "✅ 完成"
echo "   成功反编译: $TOTAL 个类（Java 源码）"
[[ $FAILED -gt 0 ]] && echo "   跳过（失败）: $FAILED 个模块"
echo "   索引文件  : $INDEX_FILE"
