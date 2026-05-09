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

# 查看 Java 进程的 GC 状态（确认是否是频繁 Full GC 导致 CPU 飙高）
jstat -gcutil $HIGH_CPU_JAVA 1000 3 2>/dev/null

# 查看网络连接积压情况（排查被打流或死锁）
ss -s

echo "=== 高 CPU Java 进程线程栈 ==="
HIGH_CPU_JAVA=$(ps aux --sort=-%cpu | awk '/java/{print $2; exit}')
if [ -n "$HIGH_CPU_JAVA" ]; then
  echo "PID: $HIGH_CPU_JAVA"
  # 尝试 jstack
  if command -v jstack &>/dev/null; then
    jstack $HIGH_CPU_JAVA 2>/dev/null | head -200
  else
    # 回退到 /proc 方式获取线程信息
    ls /proc/$HIGH_CPU_JAVA/task/ 2>/dev/null | head -20
    cat /proc/$HIGH_CPU_JAVA/cmdline 2>/dev/null | tr '\0' ' '
    echo ""
  fi
  # 高 CPU 线程 top
  ps -T -p $HIGH_CPU_JAVA -o tid,%cpu,time --sort=-%cpu 2>/dev/null | head -15
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

echo "=== Top 20 大文件 (>100MB) ==="
find / -xdev -type f -size +100M -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh | head -20

echo "=== /var/log 日志大小 ==="
du -sh /var/log/* 2>/dev/null | sort -rh | head -10

echo "=== Docker 磁盘使用 ==="
if command -v docker &>/dev/null; then
  docker system df 2>/dev/null
fi

# 已删除但被进程占用导致空间未释放的幽灵文件
lsof +L1 2>/dev/null | grep deleted | sort -k7 -rn | head -10

echo "=== 最近 24h 修改的大文件 ==="
find / -xdev -type f -size +50M -mtime -1 -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh | head -10
```

---

## 磁盘 IO 利用率高

```bash
echo "=== iostat 磁盘 IO ==="
iostat -xdm 1 3 2>/dev/null || echo "iostat not available, trying /proc/diskstats"
cat /proc/diskstats 2>/dev/null | awk '{if($4+$8>0) print}' | head -20

echo "=== 系统负载 ==="
uptime

echo "=== IO 等待 ==="
vmstat 1 3 2>/dev/null

echo "=== Top IO 进程 ==="
if command -v iotop &>/dev/null; then
  iotop -bon1 2>/dev/null | head -20
else
  # 回退: 通过 /proc 获取 IO 信息
  for pid in $(ps aux --sort=-%cpu | awk 'NR>1&&NR<12{print $2}'); do
    echo "PID $pid: $(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | cut -c1-80)"
    cat /proc/$pid/io 2>/dev/null | grep -E "read_bytes|write_bytes"
    echo "---"
  done
fi

echo "=== Top 15 CPU 进程（IO 等待常伴随高 CPU）==="
ps aux --sort=-%cpu | head -16

echo "=== Docker 容器 ==="
if command -v docker &>/dev/null; then
  docker stats --no-stream --format "table {{.Name}}\t{{.BlockIO}}\t{{.CPUPerc}}" 2>/dev/null | head -15
fi
```
