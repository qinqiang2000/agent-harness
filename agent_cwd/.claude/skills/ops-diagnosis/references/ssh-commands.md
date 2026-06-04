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

# ===========================================================================
# 服务专项深度诊断（IO 告警时识别到这些服务，必须追加专项采集）
# 触发条件：lsof 写入文件路径 或 高 IO 进程 cmdline 命中以下关键字
# 目标：从"系统级 IO 高"下沉到"具体服务在做什么导致 IO 高"
# ===========================================================================

# --- Zookeeper 专项（路径含 zookeeper / zk_ / version-2，或进程含 QuorumPeerMain） ---
ZK_PID=$(ps aux | grep -E 'QuorumPeerMain|zookeeper' | grep -v grep | awk '{print $2}' | head -1)
ZK_DATA_DIR=$(lsof +L1 2>/dev/null | grep -oE '/[^ ]*zookeeper[^ ]*/version-2' | head -1)
[ -z "$ZK_DATA_DIR" ] && ZK_DATA_DIR=$(find /mnt /data /datadisk /opt -maxdepth 6 -type d -name "version-2" -path "*zookeeper*" 2>/dev/null | head -1)

if [ -n "$ZK_PID" ] || [ -n "$ZK_DATA_DIR" ]; then
  echo ""
  echo "=== 【Zookeeper 专项】事务日志/Snapshot 写入分析 ==="
  echo "ZK PID: ${ZK_PID:-未识别}, 数据目录: ${ZK_DATA_DIR:-未找到}"

  if [ -n "$ZK_DATA_DIR" ]; then
    echo "--- 近 10 分钟新增/修改的 log/snapshot 文件 ---"
    find "$ZK_DATA_DIR" -type f \( -name "log.*" -o -name "snapshot.*" \) -mmin -10 \
      -exec ls -lh {} \; 2>/dev/null | sort -k6,7 | tail -20

    echo "--- 最近 10 个 log 文件大小分布（看是否异常增大） ---"
    ls -lhS "$ZK_DATA_DIR"/log.* 2>/dev/null | head -10

    echo "--- 当前正在写入的 log 文件（最新 mtime） ---"
    LATEST_LOG=$(ls -t "$ZK_DATA_DIR"/log.* 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
      ls -lh "$LATEST_LOG"
      # 用 zk 自带工具反序列化最近的事务（看具体在写什么 path）
      # 路径里通常会包含 /brokers/ /consumers/ /clients/ 等业务前缀
      ZK_HOME=$(dirname $(dirname $(readlink -f $(which zkServer.sh) 2>/dev/null) 2>/dev/null) 2>/dev/null)
      if [ -n "$ZK_HOME" ] && [ -f "$ZK_HOME/lib/zookeeper.jar" ] || [ -f "$ZK_HOME/zookeeper.jar" ]; then
        echo "--- 解析最新事务日志的最后 50 条事务（看写入了哪些 znode path） ---"
        timeout 10 java -cp "$ZK_HOME/lib/*:$ZK_HOME/*" \
          org.apache.zookeeper.server.LogFormatter "$LATEST_LOG" 2>/dev/null | tail -50
      else
        echo "（未找到 zkServer.sh，无法反序列化日志，但文件大小和频率已能定位异常）"
      fi
    fi
  fi

  # ZK 4字命令：mntr 看请求速率、连接数、znode 数；cons 看每个客户端的请求统计
  if command -v nc &>/dev/null && [ -n "$ZK_PID" ]; then
    ZK_PORT=$(ss -tlnp 2>/dev/null | grep "pid=$ZK_PID" | awk '{print $4}' | grep -oE '[0-9]+$' | head -1)
    [ -z "$ZK_PORT" ] && ZK_PORT=2181
    echo "--- ZK mntr（写入速率/znode 数/watch 数） ---"
    echo mntr | timeout 5 nc -w 3 127.0.0.1 $ZK_PORT 2>/dev/null
    echo "--- ZK cons（按客户端 IP 排序，看哪个客户端写得最多） ---"
    echo cons | timeout 5 nc -w 3 127.0.0.1 $ZK_PORT 2>/dev/null | head -30
    echo "--- ZK wchc（watch 集中在哪些 path，反推热点 znode） ---"
    echo wchc | timeout 5 nc -w 3 127.0.0.1 $ZK_PORT 2>/dev/null | head -50
  fi
fi

# --- RabbitMQ 专项（进程含 rabbit 或 beam.smp） ---
RABBIT_PID=$(ps aux | grep -E 'rabbit@|beam.smp.*rabbit' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$RABBIT_PID" ]; then
  echo ""
  echo "=== 【RabbitMQ 专项】队列/连接/消息速率分析 ==="
  echo "RabbitMQ PID: $RABBIT_PID"

  if command -v rabbitmqctl &>/dev/null; then
    echo "--- 集群状态 ---"
    timeout 10 rabbitmqctl cluster_status 2>/dev/null | head -20
    echo "--- 队列消息堆积 Top 15（按 messages 排序） ---"
    timeout 10 rabbitmqctl list_queues name messages messages_ready messages_unacknowledged consumers --no-table-headers 2>/dev/null \
      | sort -k2 -rn | head -15
    echo "--- 高消息速率队列（messages_published 增量） ---"
    timeout 10 rabbitmqctl list_queues name message_stats.publish_details.rate message_stats.deliver_details.rate --no-table-headers 2>/dev/null \
      | sort -k2 -rn | head -10
    echo "--- 连接数及客户端 IP（按 channel 数倒序） ---"
    timeout 10 rabbitmqctl list_connections peer_host channels send_oct recv_oct --no-table-headers 2>/dev/null \
      | sort -k2 -rn | head -15
  else
    echo "（rabbitmqctl 不可用，回退查看 mnesia 日志大小）"
    find /var/lib/rabbitmq -type f -size +50M -mmin -60 -exec ls -lh {} \; 2>/dev/null | head -10
  fi
fi

# --- MySQL 专项（高 IO 进程含 mysqld） ---
MYSQL_PID=$(ps aux | grep -E '/mysqld\b|mysqld --' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$MYSQL_PID" ]; then
  echo ""
  echo "=== 【MySQL 专项】慢查询/binlog/连接数 ==="
  if command -v mysql &>/dev/null; then
    # 优先尝试无密码本地连接（仅诊断用，无密码失败也不影响其他步骤）
    timeout 10 mysql -uroot -e "
      SHOW GLOBAL STATUS LIKE 'Slow_queries';
      SHOW GLOBAL STATUS LIKE 'Innodb_rows_inserted';
      SHOW GLOBAL STATUS LIKE 'Innodb_log_writes';
      SHOW PROCESSLIST;" 2>/dev/null | head -50
    echo "--- binlog 增量（近 10 分钟） ---"
    find /var/lib/mysql -name "mysql-bin.*" -mmin -10 -exec ls -lh {} \; 2>/dev/null | tail -10
  fi
fi

# --- Nginx 专项（高 IO 文件路径含 nginx） ---
NGINX_LOG_HOT=$(lsof -p $(pgrep -d, nginx 2>/dev/null) 2>/dev/null | awk '$5=="REG" && /access\.log|error\.log/ {print $9}' | sort -u | head -5)
if [ -n "$NGINX_LOG_HOT" ]; then
  echo ""
  echo "=== 【Nginx 专项】异常访问日志分析 ==="
  for log in $NGINX_LOG_HOT; do
    [ ! -f "$log" ] && continue
    echo "--- $log（最后 1 万行 Top 来源 IP / URL / 状态码） ---"
    SIZE=$(stat -c %s "$log" 2>/dev/null)
    if [ "${SIZE:-0}" -gt 0 ]; then
      tail -10000 "$log" | awk '{print $1}' | sort | uniq -c | sort -rn | head -5
      echo "  --- Top URL ---"
      tail -10000 "$log" | awk '{print $7}' | sort | uniq -c | sort -rn | head -5
      echo "  --- 状态码分布 ---"
      tail -10000 "$log" | awk '{print $9}' | sort | uniq -c | sort -rn | head -5
    fi
  done
fi

# --- PostgreSQL 专项（已在磁盘空间章节有详细命令，IO 场景下补充活跃查询） ---
PG_PID=$(ps aux | grep -E 'postgres .* writer\b|postgres -D' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$PG_PID" ] && command -v psql &>/dev/null; then
  echo ""
  echo "=== 【PostgreSQL 专项】活跃查询 + WAL 速率 ==="
  timeout 10 sudo -u postgres psql -c "
    SELECT pid, datname, usename, state, wait_event_type, wait_event,
           now() - query_start AS runtime, left(query, 120) AS query
    FROM pg_stat_activity
    WHERE state != 'idle' AND pid != pg_backend_pid()
    ORDER BY query_start LIMIT 15;" 2>/dev/null
  timeout 5 sudo -u postgres psql -c "
    SELECT pg_current_wal_lsn(), pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')) AS wal_total;" 2>/dev/null
fi

# --- Kafka 专项（进程含 kafka.Kafka） ---
KAFKA_PID=$(ps aux | grep -E 'kafka\.Kafka' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$KAFKA_PID" ]; then
  echo ""
  echo "=== 【Kafka 专项】topic/segment 写入分析 ==="
  KAFKA_LOG_DIR=$(lsof -p $KAFKA_PID 2>/dev/null | awk '$5=="DIR" && /kafka-logs|kafka\/data/ {print $9}' | sort -u | head -1)
  [ -z "$KAFKA_LOG_DIR" ] && KAFKA_LOG_DIR=$(find /data /datadisk /var/lib /opt -maxdepth 5 -type d -name "kafka-logs" 2>/dev/null | head -1)
  if [ -n "$KAFKA_LOG_DIR" ]; then
    echo "--- 近 10 分钟写入的 topic-partition Top 15 ---"
    find "$KAFKA_LOG_DIR" -type f -name "*.log" -mmin -10 -exec ls -lh {} \; 2>/dev/null \
      | awk '{print $5, $NF}' | sort -rh | head -15
    echo "--- 各 topic 总占用 ---"
    du -sh "$KAFKA_LOG_DIR"/*/ 2>/dev/null | sort -rh | head -10
  fi
fi
```
