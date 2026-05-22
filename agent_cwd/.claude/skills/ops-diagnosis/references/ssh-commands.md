# SSH 采集命令模板

根据告警类型选择对应的采集命令。所有命令均为只读操作。

---

## CPU 使用率高

```bash
echo "=== 全局 CPU 使用率 ==="
top -bn1 | head -5

echo "=== CPU 核心数 ==="
nproc

echo "=== 系统负载 ==="
uptime

echo "=== Top 15 CPU 消耗进程 ==="
ps aux --sort=-%cpu | head -16

echo "=== 内存概况 ==="
free -h

echo "=== 最近 OOM 记录 ==="
dmesg -T 2>/dev/null | grep -i "oom\|killed process" | tail -10

echo "=== Docker 容器资源 ==="
if command -v docker &>/dev/null; then
  docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | head -20
elif command -v crictl &>/dev/null; then
  crictl stats 2>/dev/null | head -20
fi

# 查看网络连接积压情况（排查被打流或死锁）
ss -s

# ===========================================================================
# 高 CPU 进程深度诊断：自动识别 Java / Python，宿主机直跑 + Docker 容器内都覆盖
# Java 链路：top -Hp → 16进制 TID → jstack 匹配 nid 定位代码
# Python 链路：py-spy dump 直接拿到线程栈，或 /proc/<tid>/stack 回退
# ===========================================================================
echo "=== 高 CPU 进程线程栈定位 ==="

# 找 Top 1 高 CPU 进程（排除内核线程和自身 awk）
HIGH_CPU_PID=$(ps aux --sort=-%cpu | awk 'NR>1 && !/awk/ && !/\[.*\]/ {print $2; exit}')

if [ -n "$HIGH_CPU_PID" ]; then
  CMDLINE=$(cat /proc/$HIGH_CPU_PID/cmdline 2>/dev/null | tr '\0' ' ' | cut -c1-300)
  echo "[宿主机视角] PID: $HIGH_CPU_PID"
  echo "[宿主机视角] CMD: $CMDLINE"
  echo ""

  # 判断进程类型
  PROC_TYPE="unknown"
  if echo "$CMDLINE" | grep -qE 'java\b|-jar |\.jar'; then
    PROC_TYPE="java"
  elif echo "$CMDLINE" | grep -qE 'python[0-9.]*\b|uvicorn|gunicorn|celery'; then
    PROC_TYPE="python"
  fi
  echo "[识别] 进程类型: $PROC_TYPE"

  # 判断是否在 Docker 容器内（通过 cgroup）
  CONTAINER_ID=$(cat /proc/$HIGH_CPU_PID/cgroup 2>/dev/null | grep -oE 'docker[/-][0-9a-f]{12,}' | head -1 | grep -oE '[0-9a-f]{12,}' | cut -c1-12)
  CONTAINER_NAME=""
  CONTAINER_INNER_PID=""
  if [ -n "$CONTAINER_ID" ]; then
    CONTAINER_NAME=$(docker inspect --format '{{.Name}}' $CONTAINER_ID 2>/dev/null | sed 's|^/||')
    echo "[容器视角] 容器: $CONTAINER_NAME ($CONTAINER_ID)"

    # 动态查容器内的目标进程 PID（不能假设是 1，可能用 sh -c / 启动脚本包装）
    # 优先按命令关键字匹配（java 或 python），失败则 fallback 用 ps 取最高 CPU
    if [ "$PROC_TYPE" = "java" ]; then
      CONTAINER_INNER_PID=$(docker exec $CONTAINER_ID sh -c "ps -eo pid,comm,args 2>/dev/null | awk '/[j]ava/{print \$1; exit}'" 2>/dev/null)
    elif [ "$PROC_TYPE" = "python" ]; then
      CONTAINER_INNER_PID=$(docker exec $CONTAINER_ID sh -c "ps -eo pid,comm,args 2>/dev/null | awk '/[p]ython|[u]vicorn|[g]unicorn/{print \$1; exit}'" 2>/dev/null)
    fi
    # fallback：拿容器内 CPU 最高的非 ps/grep 进程
    if [ -z "$CONTAINER_INNER_PID" ]; then
      CONTAINER_INNER_PID=$(docker exec $CONTAINER_ID sh -c "ps -eo pid,pcpu --sort=-pcpu 2>/dev/null | awk 'NR==2{print \$1}'" 2>/dev/null)
    fi
    echo "[容器视角] 容器内目标 PID: ${CONTAINER_INNER_PID:-未识别}"

    echo "=== 容器内 top -H（线程级 CPU） ==="
    if [ -n "$CONTAINER_INNER_PID" ]; then
      docker exec $CONTAINER_ID top -H -bn1 -p $CONTAINER_INNER_PID 2>/dev/null | head -20
    else
      docker exec $CONTAINER_ID top -H -bn1 2>/dev/null | head -20
    fi
  fi

  # === 通用步骤：找 Top 5 高 CPU 线程（宿主机视角，TID 即 LWP） ===
  echo "=== Top 5 高 CPU 线程（PID/TID/CPU%） ==="
  TOP_TIDS=$(ps -T -p $HIGH_CPU_PID -o tid=,pcpu= --sort=-pcpu 2>/dev/null | head -5 | awk '$2+0>0 {print $1}')
  ps -T -p $HIGH_CPU_PID -o pid,tid,pcpu,time,comm --sort=-pcpu 2>/dev/null | head -10

  # ============ Java 分支 ============
  if [ "$PROC_TYPE" = "java" ]; then
    JSTACK_OUTPUT=""
    if [ -n "$CONTAINER_ID" ] && [ -n "$CONTAINER_INNER_PID" ]; then
      JSTACK_OUTPUT=$(docker exec $CONTAINER_ID sh -c "jstack $CONTAINER_INNER_PID 2>/dev/null || jcmd $CONTAINER_INNER_PID Thread.print 2>/dev/null" 2>/dev/null)
    fi
    if [ -z "$JSTACK_OUTPUT" ] && command -v jstack &>/dev/null; then
      JSTACK_OUTPUT=$(jstack $HIGH_CPU_PID 2>/dev/null)
    fi
    if [ -z "$JSTACK_OUTPUT" ] && command -v jcmd &>/dev/null; then
      JSTACK_OUTPUT=$(jcmd $HIGH_CPU_PID Thread.print 2>/dev/null)
    fi

    if [ -n "$JSTACK_OUTPUT" ] && [ -n "$TOP_TIDS" ]; then
      echo "=== 高 CPU 线程对应的 jstack 栈（nid=0xXXXX 匹配） ==="
      for tid in $TOP_TIDS; do
        hex_tid=$(printf '%x' $tid)
        echo "--- TID $tid (nid=0x$hex_tid) ---"
        echo "$JSTACK_OUTPUT" | grep -A 30 "nid=0x$hex_tid " 2>/dev/null | head -35 || \
          echo "未找到 nid=0x$hex_tid 的栈（可能是 GC 线程或 native 线程）"
        echo ""
      done
    else
      echo "无法获取 jstack/jcmd 输出（可能 JDK 未装或权限不足）"
    fi

    echo "=== JVM GC 状态（jstat -gcutil，3 次采样） ==="
    if [ -n "$CONTAINER_ID" ] && [ -n "$CONTAINER_INNER_PID" ]; then
      docker exec $CONTAINER_ID jstat -gcutil $CONTAINER_INNER_PID 1000 3 2>/dev/null
    elif command -v jstat &>/dev/null; then
      jstat -gcutil $HIGH_CPU_PID 1000 3 2>/dev/null
    fi
  fi

  # ============ Python 分支 ============
  if [ "$PROC_TYPE" = "python" ]; then
    PY_STACK_OUTPUT=""

    # 优先 py-spy dump（无侵入，专为 CPU/卡死排查设计）
    if [ -n "$CONTAINER_ID" ] && [ -n "$CONTAINER_INNER_PID" ]; then
      PY_STACK_OUTPUT=$(docker exec $CONTAINER_ID sh -c "py-spy dump --pid $CONTAINER_INNER_PID 2>/dev/null" 2>/dev/null)
    fi
    if [ -z "$PY_STACK_OUTPUT" ] && command -v py-spy &>/dev/null; then
      PY_STACK_OUTPUT=$(py-spy dump --pid $HIGH_CPU_PID 2>/dev/null)
    fi

    if [ -n "$PY_STACK_OUTPUT" ]; then
      echo "=== Python 线程栈（py-spy dump，全部线程） ==="
      echo "$PY_STACK_OUTPUT" | head -200

      # 标记高 CPU 线程对应的栈（py-spy 输出会带 Thread ID/TID）
      if [ -n "$TOP_TIDS" ]; then
        echo ""
        echo "=== 高 CPU 线程过滤（按 TID 匹配 py-spy 输出） ==="
        for tid in $TOP_TIDS; do
          echo "--- TID $tid ---"
          echo "$PY_STACK_OUTPUT" | grep -A 20 "Thread.*$tid" 2>/dev/null | head -25 || \
            echo "py-spy 输出未匹配该 TID（可能是 GIL 等待中的线程）"
          echo ""
        done
      fi
    else
      # 回退：直接读 /proc/<tid>/stack（内核态栈，能看到系统调用，但看不到 Python 代码）
      echo "py-spy 未安装或无权限，回退使用 /proc/<tid>/stack（仅显示内核态栈）"
      for tid in $TOP_TIDS; do
        echo "--- TID $tid 的内核栈 ---"
        cat /proc/$HIGH_CPU_PID/task/$tid/stack 2>/dev/null | head -10 || \
          echo "无权限读取 /proc/$HIGH_CPU_PID/task/$tid/stack（需要 root 或 ptrace 权限）"
        # cmdline + status 信息，至少能看到线程名
        cat /proc/$HIGH_CPU_PID/task/$tid/comm 2>/dev/null
        echo ""
      done
      echo "提示：建议在容器内安装 py-spy（pip install py-spy）以获取 Python 代码级栈"
    fi
  fi

  # ============ unknown 进程：通用降级 ============
  if [ "$PROC_TYPE" = "unknown" ]; then
    echo "=== 未知类型进程，展示线程级栈（/proc 内核栈） ==="
    for tid in $TOP_TIDS; do
      echo "--- TID $tid ($(cat /proc/$HIGH_CPU_PID/task/$tid/comm 2>/dev/null)) ---"
      cat /proc/$HIGH_CPU_PID/task/$tid/stack 2>/dev/null | head -10
      echo ""
    done
  fi
fi

echo "=== mpstat 各核心使用率 ==="
mpstat -P ALL 1 1 2>/dev/null || echo "mpstat not available"
```

---

## 内存使用率高

```bash
echo "=== 内存详情 ==="
free -h
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree"

echo "=== Top 15 内存消耗进程 ==="
ps aux --sort=-%mem | head -16

echo "=== 系统负载 ==="
uptime

# 提取占用内存最大的 10 个 Slab 缓存（排查内核态内存泄漏，如 dentry cache 泄漏）
slabtop -o | head -15 2>/dev/null

echo "=== 最近 OOM 记录 ==="
dmesg -T 2>/dev/null | grep -i "oom\|killed process" | tail -10

echo "=== Docker 容器内存 ==="
if command -v docker &>/dev/null; then
  docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null | sort -k3 -rn | head -15
elif command -v crictl &>/dev/null; then
  crictl stats 2>/dev/null | head -20
fi

echo "=== Swap 使用情况 ==="
swapon --show 2>/dev/null

echo "=== 大内存 Java 进程堆信息 ==="
HIGH_MEM_JAVA=$(ps aux --sort=-%mem | awk '/java/{print $2; exit}')
if [ -n "$HIGH_MEM_JAVA" ]; then
  echo "PID: $HIGH_MEM_JAVA"
  cat /proc/$HIGH_MEM_JAVA/cmdline 2>/dev/null | tr '\0' ' '
  echo ""
  # JVM 堆概况
  jcmd $HIGH_MEM_JAVA GC.heap_info 2>/dev/null || echo "jcmd not available"
fi
```

---

## 磁盘空间不足

```bash
echo "=== 分区使用详情（按挂载点） ==="
df -h --output=target,size,used,avail,pcent | grep -v "tmpfs\|overlay\|shm\|Mounted"

echo "=== 各分区 inode 使用 ==="
df -i | grep -v "tmpfs\|overlay\|shm"

echo "=== 高使用率挂载点下 Top 子目录 ==="
for mp in $(df -h --output=target,pcent | grep -v "tmpfs\|overlay\|shm\|Mounted" | awk '{gsub(/%/,"",$2); if($2>=70) print $1}'); do
  echo "--- $mp ---"
  du -sh "$mp"/* 2>/dev/null | sort -rh | head -10
done

echo "=== Top 20 大文件 (>100MB，仅高使用率挂载点) ==="
for mp in $(df -h --output=target,pcent | grep -v "tmpfs\|overlay\|shm\|Mounted" | awk '{gsub(/%/,"",$2); if($2>=70) print $1}'); do
  timeout 30 find "$mp" -xdev -type f -size +100M -exec ls -lh {} \; 2>/dev/null
done | sort -k5 -rh | head -20

echo "=== /var/log 日志大小 ==="
du -sh /var/log/* 2>/dev/null | sort -rh | head -10

echo "=== Docker 磁盘使用 ==="
if command -v docker &>/dev/null; then
  docker system df 2>/dev/null
fi

# 已删除但被进程占用导致空间未释放的幽灵文件
lsof +L1 2>/dev/null | grep deleted | sort -k7 -rn | head -10

echo "=== 最近 24h 修改的大文件（仅高使用率挂载点） ==="
for mp in $(df -h --output=target,pcent | grep -v "tmpfs\|overlay\|shm\|Mounted" | awk '{gsub(/%/,"",$2); if($2>=70) print $1}'); do
  timeout 30 find "$mp" -xdev -type f -size +50M -mtime -1 -exec ls -lh {} \; 2>/dev/null
done | sort -k5 -rh | head -10

echo "=== PostgreSQL 数据库大小排名 ==="
if command -v psql &>/dev/null; then
  sudo -u postgres psql -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC LIMIT 15;" 2>/dev/null
  echo "=== PostgreSQL 最大表 Top 10（当前最大库） ==="
  LARGEST_DB=$(sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname NOT IN ('template0','template1','postgres') ORDER BY pg_database_size(datname) DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$LARGEST_DB" ]; then
    echo "最大库: $LARGEST_DB"
    # 使用 pg_class.relpages 预估排序，避免逐行调用 pg_total_relation_size 导致超时
    timeout 30 sudo -u postgres psql -d "$LARGEST_DB" -c "
      SELECT n.nspname AS schemaname, c.relname AS tablename,
             pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind = 'r'
        AND n.nspname NOT IN ('pg_catalog','information_schema')
      ORDER BY c.relpages DESC
      LIMIT 10;" 2>/dev/null
  fi
  echo "=== WAL 日志大小 ==="
  sudo -u postgres psql -c "SELECT pg_size_pretty(sum(size)) AS wal_total FROM pg_ls_waldir();" 2>/dev/null
  echo "=== WAL 归档状态 ==="
  sudo -u postgres psql -c "SELECT archived_count, failed_count, last_archived_wal, last_archived_time FROM pg_stat_archiver;" 2>/dev/null
  echo "=== 死元组最多的表 Top 10（需要 VACUUM） ==="
  # n_dead_tup 已在 pg_stat_user_tables 中缓存，直接排序不需要逐行计算
  timeout 30 sudo -u postgres psql -d "$LARGEST_DB" -c "
    SELECT schemaname, relname, n_dead_tup,
           pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS size,
           last_autovacuum
    FROM pg_stat_user_tables
    WHERE n_dead_tup > 1000
    ORDER BY n_dead_tup DESC
    LIMIT 10;" 2>/dev/null
fi
```

---

## 磁盘 IO 利用率高

```bash
echo "=== iostat 磁盘 IO（核心指标：rMB/s wMB/s %util） ==="
iostat -xdm 1 3 2>/dev/null || echo "iostat not available, trying /proc/diskstats"
cat /proc/diskstats 2>/dev/null | awk '{if($4+$8>0) print}' | head -20

echo "=== 系统负载 ==="
uptime

echo "=== IO 等待 (vmstat: bi/bo, wa) ==="
vmstat 1 3 2>/dev/null

echo "=== Top IO 进程（按写入速率排序） ==="
if command -v iotop &>/dev/null; then
  iotop -bon1 -P 2>/dev/null | head -20
else
  # 回退: 通过 /proc/$pid/io 计算 1 秒间隔的写入速率
  echo "iotop not available, sampling /proc/*/io with 1s interval"
  declare -A pre_write
  for pid in $(ps -eo pid --no-headers); do
    [ -r /proc/$pid/io ] && pre_write[$pid]=$(awk '/^write_bytes:/{print $2}' /proc/$pid/io 2>/dev/null)
  done
  sleep 1
  for pid in "${!pre_write[@]}"; do
    cur=$(awk '/^write_bytes:/{print $2}' /proc/$pid/io 2>/dev/null)
    [ -z "$cur" ] && continue
    diff=$((cur - ${pre_write[$pid]}))
    if [ "$diff" -gt 1048576 ]; then  # >1MB/s
      cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | cut -c1-80)
      printf "PID %s\t%s MB/s\t%s\n" "$pid" "$((diff/1024/1024))" "$cmd"
    fi
  done | sort -k2 -rn | head -10
fi

echo "=== 高写入进程的具体写入文件（lsof 定位写入目标） ==="
TOP_IO_PIDS=$(iotop -bon1 -P 2>/dev/null | awk 'NR>7 && $4+0>1024 {print $2}' | head -5)
for pid in $TOP_IO_PIDS; do
  echo "--- PID $pid: $(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | cut -c1-80) ---"
  # 列出该进程打开的写模式文件（u=读写, w=写）
  lsof -p $pid 2>/dev/null | awk '$4 ~ /[uw]$/ && $5 == "REG" {print $9, $7}' | sort -u | head -10
done

echo "=== 近 5 分钟修改且持续增长的文件（>10MB 且 mtime<5min） ==="
# 仅扫描常见日志/数据目录，避免全盘扫
for dir in /var/log /data /datadisk /mnt /opt/logs /home; do
  [ -d "$dir" ] && timeout 15 find "$dir" -xdev -type f -size +10M -mmin -5 -exec ls -lh {} \; 2>/dev/null
done | sort -k5 -rh | head -15

echo "=== Top 15 CPU 进程（IO 等待常伴随高 CPU） ==="
ps aux --sort=-%cpu | head -16

echo "=== Docker 容器 BlockIO ==="
if command -v docker &>/dev/null; then
  docker stats --no-stream --format "table {{.Name}}\t{{.BlockIO}}\t{{.CPUPerc}}" 2>/dev/null | head -15
fi

echo "=== pidstat 进程级 IO（备用） ==="
pidstat -d 1 2 2>/dev/null | tail -20
```
