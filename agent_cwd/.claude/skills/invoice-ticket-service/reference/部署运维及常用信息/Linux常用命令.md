| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建/更新时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **/** | **公开** | 创建 | **2025-09-23** | **欧浩斌** |


# 文档说明
本文档主要介绍了Linux操作系统的基础操作命令，基于RedHat系统操作系统，其他操作系统可能略有不同。文档中部分命令系统不自带，需要手动下载。

# 文件与目录操作
## 切换工作路径：cd
**语法：**

bash  
	cd [目录路径]  
**常用参数与符号：**

.. : 	切换到上一级目录

~ : 	切换到当前用户的家目录

- : 	切换回上一次所在的目录

**相关命令：**

pwd : 显示当前所在的工作路径 (Print Working Directory)

## 创建目录：mkdir
**语法：**

bash  
	mkdir [选项] 目录名...  
**常用选项：**

-p : 	递归创建多级目录。如果路径中的父目录不存在，则一并创建。

**示例：**mkdir -p /opt/app/logs 会一次性创建/opt, /opt/app, /opt/app/logs三层目录。

-m : 	在创建目录时直接指定权限。  
	**示例：**	mkdir -m 755 shared_dir

## 删除文件或目录：rm
**语法：**

bash  
	rm [选项] 文件或目录...  
**常用选项：**

-r 或 -R : 	递归删除，用于删除目录及其内容（慎用）。

-f : 		强制删除，忽略不存在的文件，从不给出提示，直接跳过确认环节（极度慎用）。

-i : 		交互式删除，在删除前逐一询问确认（推荐新手使用）。

**注意：** rm -rf / 是极其危险的命令，会导致系统被彻底删除。生产环境操作需万分谨慎。

## 移动或重命名：mv
**语法：**

bash  
	mv [选项] 源文件或目录... 目标文件或目录  
**功能说明：**

如果目标是一个已存在的目录，则会将所有源文件/目录移动至该目录下。

如果目标是一个不存在的名称或文件，则执行重命名操作。

**常用选项：**

-i : 	交互模式，覆盖前询问。

-f : 	强制模式，直接覆盖，不询问。

-v : 	显示详细操作过程。

## 拷贝：cp
**语法：**

bash  
	cp [选项] 源文件或目录... 目标文件或目录  
**常用选项：**

-r 或 -R : 	递归复制，用于复制目录。

-i : 		覆盖前询问。

-f :		强制复制，覆盖已存在的目标文件而不提示。

-p : 		保留源文件或目录的属性（包括所有者、组、权限和时间戳）。

-a 或 --archive : 等效于 -dR --preserve=all，常用于归档备份，保留所有原始信息。

Tips:

使用 \cp 或 /bin/cp 可以忽略别名设置，直接调用原生命令，避免交互式提示。

## 查看文件系统磁盘空间使用情况：df
**语法：**

bash  
	df [选项] [文件或目录...]  
**常用选项：**

-h : 	以人类易读的格式显示（如 1K, 234M, 2G）。

-i : 	显示 inode 的使用情况而非磁盘块。

-T : 	显示文件系统类型（如 ext4, xfs）。

-x : 	排除指定的文件系统类型。

**示例：**df -hT 查看所有已挂载文件系统的容量、使用情况和类型。

## 统计文件或目录大小：du
**语法：**

bash  
	du [选项] [文件或目录...]  
**常用选项：**

-s : 	仅显示总计大小，不列出子目录。

-h : 	以人类易读的格式显示。

-a : 	显示目录中所有文件的大小。

--max-depth=N : 显示指定深度（N）的目录总计。  
**示例：**du -h --max-depth=1 /var 查看/var下一级子目录的大小。

## 列出目录内容：ls
**语法：**

bash  
	ls [选项] [文件或目录...]  
**常用选项：**

-l : 	使用长格式列出详细信息（权限、所有者、大小、修改时间等）。

-a : 	显示所有文件，包括隐藏文件（以.开头的文件）。

-h : 	与 -l 配合使用，以易读格式显示文件大小。

-t : 	按修改时间排序，最新的在前。

-r : 	反向排序。

-F : 	在条目后加上文件类型指示符（例如，/ 表示目录，* 表示可执行文件）。

# 查找与过滤
## 查找文件：find
**语法：**

bash  
	find [路径...] [表达式]  
**常用查找条件：**

-name "模式" : 	按文件名查找（支持通配符 *, ?）。

-iname "模式" : 	按文件名查找（不区分大小写）。

-type 类型 : 		按文件类型查找。f（文件），d（目录），l（符号链接）。

-size [+|-]大小[cwkMG] : 按文件大小查找。+10M 表示大于10MB，-1G 表示小于1GB。

-mtime [+|-]天数 : 	按文件修改时间查找。+7 表示7天前，-1 表示1天内。

-user 用户名 : 		按文件属主查找。

-perm 权限模式 : 	按文件权限查找。

**对查找结果执行操作：**

-exec 命令 {} ; : 对匹配的文件执行指定的命令。{} 是占位符，代表找到的文件。  
**示例：**find /var/log -name "*.log" -mtime +30 -exec rm -f {} ; 删除/var/log下30天前的.log文件。

-ok 命令 {} ; : 与 -exec 类似，但在执行命令前会询问确认。

-delete : 删除匹配到的文件。

**Tips:**

可以使用管道 | 或 xargs 命令将 find 的结果传递给其他命令处理。  
	示例：find . -name "*.conf" | xargs grep -l "error" 查找当前目录下所有包含"error"字符串的.conf文件。

## 文本搜索过滤：grep
**语法：**

bash  
	grep [选项] "匹配模式" [文件...]  
**常用选项：**

-i : 	忽略大小写。

-v : 	反向选择，即显示不包含匹配模式的所有行。

-n : 	显示匹配行的行号。

-w : 	全字匹配，只匹配整个单词，而不是字符串的一部分。

-c : 	只显示匹配到的行数计数。

-A <行数> : 	除了显示匹配行，还显示之后（After）的指定行数。

-B <行数> : 	除了显示匹配行，还显示之前（Before）的指定行数。

-C <行数> : 	除了显示匹配行，还显示之前和之后的指定行数（Context）。

-r 或 -R : 递归搜索目录下的所有文件。

-l : 仅列出包含匹配模式的文件名，而不显示具体的匹配行。

--color=auto : 对匹配到的文本进行高亮显示。

**模式中的特殊字符（正则表达式）：**

^ : 	匹配行首。^# 匹配以 # 开头的行。

$： 	匹配行尾。bash$  匹配以 bash 结尾的行。

. : 	匹配任意一个字符。

* : 	匹配前一个字符0次或多次。

.* : 	匹配任意字符串。

**示例：**grep -rn "Connection refused" /var/log/ 在/var/log目录下递归搜索所有包含"Connection refused"的文件并显示行号。

# 用户、组与权限
## 用户和组的关系
每个用户账户有一个唯一的 UID (User ID)。

每个组有一个唯一的 GID (Group ID)。

一个用户必须属于一个初始组(Primary Group)，且可以加入多个附加组(Supplementary Groups)。

相关配置文件：

/etc/passwd : 存储用户账户信息。

/etc/shadow : 存储用户密码（加密）及策略信息。

/etc/group : 存储组信息。

/etc/gshadow : 存储组密码信息。

/etc/passwd 文件格式解析：  
	zhangwuji:x:520:521:mingjiao jiaozhu:/home/zhangwuji:/bin/bash

| **<font style="color:#000000;">字段编号</font>** | **<font style="color:#000000;">示例值</font>** | **<font style="color:#000000;">说明</font>** |
| :---: | :---: | :---: |
| <font style="color:#000000;">1</font> | <font style="color:#000000;">zhangwuji</font> | <font style="color:#000000;">用户名</font> |
| <font style="color:#000000;">2</font> | <font style="color:#000000;">x</font> | <font style="color:#000000;">密码占位符(实际在shadow)</font> |
| <font style="color:#000000;">3</font> | <font style="color:#000000;">520</font> | <font style="color:#000000;">用户UID</font> |
| <font style="color:#000000;">4</font> | <font style="color:#000000;">521</font> | <font style="color:#000000;">初始组GID</font> |
| <font style="color:#000000;">5</font> | <font style="color:#000000;">mingjiao jiaozhu用</font> | <font style="color:#000000;">户注释/全名</font> |
| <font style="color:#000000;">6</font> | <font style="color:#000000;">/home/zhangwuji</font> | <font style="color:#000000;">用户家目录</font> |
| <font style="color:#000000;">7</font> | <font style="color:#000000;">/bin/bash</font> | <font style="color:#000000;">用户登录Shell</font> |


## 组操作
+ **创建组：**

bash  
groupadd [-g GID] 组名  
-g GID : 	指定新组的GID。

+ **修改组：**

bash  
groupmod [-g GID] [-n 新组名] 原组名  
-g GID : 	修改组的GID。

-n 新组名 : 修改组名。

+ **删除组：**

bash  
	groupdel 组名  
注意：不能删除现有用户的主要组（初始组）。

## 用户操作
+ **创建用户：**
+ bash  
	useradd [选项] 用户名  

+ **常用选项：**

-u UID : 	指定用户的UID。

-g 初始组名/GID : 	指定用户的初始组。

-G 附加组名/GID : 	指定用户所属的附加组（多个用逗号分隔）。

-s Shell路径 : 	指定用户的登录Shell（如 /bin/bash, /sbin/nologin）。

-d 家目录路径 : 	指定用户的家目录。

-m : 	如果家目录不存在，则自动创建（通常默认行为）。

-c "注释信息" : 	添加用户注释（通常是全名）。

+ **修改用户：**
+ bash  
	usermod [选项] 用户名
+ **常用选项**与 useradd 相同，此外还有：

-l 新用户名 : 修改用户名。

-L : 锁定用户账户（无法登录）。

-U : 解锁用户账户。

+ **删除用户：**

bash  
	userdel [-r] 用户名  
	-r : 删除用户的同时，一并删除其家目录和邮件池（/var/spool/mail/用户名）。

+ **设置/修改用户密码：**

bash  
	passwd [用户名] # 如果不指定用户名，则修改当前用户自己的密码

## 权限管理
Linux文件权限分为三种：读(r)、写(w)、执行(x)。  
**权限针对三种对象：**属主(u)、属组(g)、其他用户(o)。

1. **修改文件属主和属组：**chown

bash  
	chown [选项] [属主][:属组] 文件或目录...  
**示例：**

chown root:root file.txt : 将属主和属组都改为root。

chown www-data: file.txt : 将属主改为www-data，属组改为www-data的初始组。

chown :dev file.txt : 只将属组改为dev。

-R : 递归修改目录及其下所有内容。

2. **修改文件属组：**chgrp

bash  
	chgrp [-R] 属组 文件或目录...  
	(功能已被 chown 覆盖，较少单独使用)

3. **修改权限：**chmod  

+ **方法一：符号模式**

bash  
	chmod [ugoa][+-=][rwxXst] 文件或目录...  
	[ugoa] : u(属主), g(属组), o(其他), a(所有，等价于ugo)

[+-=] : +(增加权限), -(移除权限), =(设置精确权限)

[rwxXst] :

r：读

w：写

x：执行（文件）/访问（目录）

X：特殊执行权限，仅当目标是目录或已有执行权限时才设置x

s：SetUID（u+s）/ SetGID（g+s）

t：粘滞位（o+t），常用于/tmp目录

示例：

chmod u+x script.sh : 给属主增加执行权限。

chmod go-w file.conf : 移除属组和其他用户的写权限。

chmod a=rw shared.txt : 给所有用户设置读写权限。

+ **方法二：数字（八进制）模式**

bash  
	chmod XYZ 文件或目录...  
	X : 属主权限之和 (r=4, w=2, x=1)

Y : 属组权限之和

Z : 其他用户权限之和

示例：

chmod 755 myscript : u=rwx (7), g=rx (5), o=rx (5)

chmod 644 config.txt : u=rw (6), g=r (4), o=r (4)

chmod 1777 /shared_tmp : u=rwx (7), g=rwx (7), o=rwx (7) + 粘滞位(1)

# 进程管理
## 查看进程：ps
**语法：**

bash  
	ps [选项]  
**常用组合：**

ps aux : 查看系统所有进程的详细信息。

a：显示所有用户的进程

u：显示进程的详细状态

x：显示没有控制终端的进程

ps -ef : 以完整格式列表显示所有进程。

ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head : 自定义输出字段并按内存使用率排序。

**查看进程：top / htop**

top : 动态、交互式地查看进程状态和系统资源使用情况（CPU、内存等）。

htop : top 的增强版，用户体验更好（可能需要安装）。

## 查看打开的文件：lsof
**语法：**

bash  
	lsof [选项]  
**常用用法：**

lsof -i :端口号 : 显示占用指定端口的进程。

lsof 文件名 : 显示打开指定文件的所有进程。

lsof -p PID : 显示指定PID进程所打开的所有文件。

lsof -u 用户名 : 显示指定用户打开的文件。

## 终止进程：kill / pkill
**语法：**

bash  
kill [信号] PID  
pkill [选项] [模式]

**常用信号：**

1 (SIGHUP) : 挂起，通常用于让进程重新读取配置文件。

9 (SIGKILL) : 强制终止（无法被捕获或忽略）。

15 (SIGTERM) : 优雅地终止进程（默认信号）。

**示例：**

kill -9 1234 : 强制终止PID为1234的进程。

pkill -f "python app.py" : 终止所有命令行匹配"python app.py"的进程。

killall 进程名 : 终止指定名称的所有进程。

## 后台进程管理
& : 在命令末尾加上 &，可使命令在当前终端后台运行。  
示例：./long_running_script.sh &

jobs : 查看当前Shell会话中的后台作业。

fg %作业号 : 将后台作业切换到前台运行。

bg %作业号 : 将暂停的后台作业变为继续运行。

nohup : 忽略挂起信号(SIGHUP)，使得进程在退出终端后仍继续运行。通常与 & 结合使用。  
示例：nohup ./server.sh > server.log 2>&1 &

> server.log : 将标准输出重定向到 server.log 文件。
>

2>&1 : 将标准错误(2)重定向到标准输出(1)所在的位置（即同一个文件）。

# 计划任务
## 周期性任务：cron
**服务管理 (Systemd系统)：**

bash  
	systemctl status/start/stop/enable crond.service  # 或 cron.service  
**管理用户的Cron任务：**

crontab -e : 编辑当前用户的cron计划任务表。

crontab -l : 列出当前用户的cron计划任务。

crontab -r : 删除当前用户的所有cron计划任务（慎用！）。

crontab -u 用户名 -e : 编辑指定用户的cron计划任务（需root权限）。

**Cron时间格式：**

text

*  *  *  *  *  <要执行的命令>

分   时   日   月   周  
**取值范围：**

分 (0-59)

时 (0-23)

日 (1-31)

月 (1-12)

周 (0-7, 0和7都代表周日)

**特殊符号：**

*:	任何值

, : 	值分隔符（例如 1,3,5）

-: 范围（例如 1-5）

*/N : 每隔N个单位（例如 */10 * * * * 表示每10分钟）

**示例：**

*  *  *  *  *  echo "hello" >> /tmp/test.log : 每分钟追加一次。

30 3  *  *  *  /root/backup.sh : 每天凌晨3:30执行备份脚本。

0 */6  *  *  *  /app/check_status.sh : 每6小时整点执行一次。

0 0 1 */2 	* /usr/bin/apt update : 每两个月的第1天零点更新软件列表。

30 20 *  * 1-5 /usr/bin/find /tmp -type f -mtime +7 -delete : 周一到周五每晚20:30删除/tmp下超过7天的普通文件。

**Tips:**

Cron任务的路径：用户的任务保存在 /var/spool/cron/ 下，以用户名命名的文件中。root用户的任务也可以在 /etc/crontab 和 /etc/cron.d/ 目录下配置。

环境变量问题：Cron执行的环境与用户Shell环境不同，非常精简。在脚本中必须使用绝对路径，或者先在Shell脚本中主动source环境变量文件（如~/.bash_profile或/etc/profile）。

## 一次性任务：at / batch
at 时间 : 在指定时间执行一次任务。  
示例：echo "shutdown -h now" | at 23:00

batch : 在系统负载较低时执行一次任务。

# 系统状态与信息
## 查看系统运行时间与负载：uptime
显示系统当前时间、已运行时间、当前登录用户数以及过去1、5、15分钟的系统平均负载。

## 查看内存使用情况：free
**语法：**

bash  
	free [-h|-m|-g]  
**常用选项：**

-h : 	以人类可读格式显示（自动使用G/M/K）。

-m : 	以MB为单位显示。

-s <间隔秒数> : 持续观察，每隔指定秒数刷新一次。

## 监控系统I/O和CPU状态：iostat
**语法：**

bash  
	iostat [选项] [间隔时间] [次数]  
**常用选项：**

-c : 显示CPU使用情况。

-d : 显示设备（磁盘）使用情况。

-x : 显示扩展统计信息。

-h : 友好格式显示。

**示例：**iostat -dxh 2 5 每隔2秒显示一次扩展磁盘信息，共显示5次。

(此命令通常需要安装sysstat包)

# 网络管理
## 查看网络连接、路由表、接口统计：netstat / ss
netstat (较老，逐渐被ss取代)：

bash  
	netstat [-tulnpa]  
**常用选项：**

-t : TCP连接

-u : UDP连接

-l : 处于监听状态的连接

-n : 以数字形式显示地址和端口号

-p : 显示进程PID和程序名

-a : 显示所有连接

ss (Socket Statistics，更快更高效)：

bash  
	ss [-tulnpa]  
选项与 netstat 类似，推荐使用。

示例：ss -tlnp 查看所有监听的TCP端口及其对应进程。

## 配置和查看网络接口：ip
**语法：**

bash  
	ip [选项] 对象 { 命令 | help }  
**常用对象和命令：**

ip addr show 或 ip a : 查看所有网络接口的IP地址信息。

ip link show : 查看网络接口链路状态。

ip route show 或 ip r : 查看路由表。

ip neigh show : 查看ARP/NDP缓存表。

(已取代老旧的ifconfig, route, arp等命令)

## 网络测试与探测
**测试网络连通性：**ping

bash  
	ping [-c 次数] 目标主机  
	-c 次数 : 发送指定数量的包后停止。

**跟踪网络路径：**traceroute / tracepath / mtr

bash  
	traceroute 目标主机  
mtr 目标主机 # 集成了ping和traceroute功能的动态工具  
下载文件：wget / curl

wget [URL] : 命令行下载工具，支持HTTP/HTTPS/FTP。

curl [选项] [URL] : 强大的传输工具，支持多种协议，常用于测试API、下载等。

-o 文件名 : 将输出写入文件。

-I : 仅显示HTTP响应头信息。

# 文本处理
## 查看文件内容
cat [-n] 文件 : 连接并打印文件内容到标准输出。

-n : 显示行号。

less 文件 : 分页显示文件内容，支持搜索(/)、向上翻页等，比more更强大。

head [-n 行数] 文件 : 显示文件开头部分内容（默认10行）。

tail [-n 行数] [-f] 文件 : 显示文件末尾部分内容。

-f : 实时追踪文件末尾的新增内容，常用于监控日志（Ctrl+C退出）。

-F : 类似于 -f，但在文件被轮转(rotate)后能自动重新打开新文件。

## 流编辑器：sed
**语法：**

bash  
	sed [选项] '脚本命令' 输入文件...  
**常用操作：**

s/模式/替换字符串/标志 : 替换操作。

标志：g(全局替换)，i(忽略大小写)  
**示例：**sed 's/foo/bar/g' file.txt 将文件中所有的foo替换为bar。

d : 删除行。  
示例：sed '/^#/d' file.conf 删除所有以#开头的行（注释）。

p : 打印行。

-i[后缀] : 直接修改文件内容（危险操作，建议先测试不加-i的效果）。如果提供后缀则创建备份。  
示例：sed -i.bak 's/old/new/g' file.txt 直接修改file.txt并创建备份文件file.txt.bak。

-n : 安静模式，仅显示处理后的结果，常与p命令配合使用。  
示例：sed -n '5,10p' file.txt 只打印文件的第5到第10行。

## 文本报告生成器：awk
**语法：**

bash  
	awk '模式 { 动作 }' 输入文件...  
**内置变量：**

NR : 当前记录号（行号）。

NF : 当前记录的字段数。

$0 : 整行内容。

$1，$2, ... $n : 第1, 2, ... n个字段。

**常用示例：**

awk '{print $ 1,  $3}' file.txt : 打印每行的第1和第3个字段（默认以空格分隔）。

awk -F: '{print $ 1,  $6}' /etc/passwd : 使用冒号:作为分隔符，打印/etc/passwd的第1和第6字段（用户名和家目录）。

awk 'NR<font style="background-color:#f3bb2f;">2, NR</font>5 {print NR ": " $0}' file.txt : 打印第2到第5行，并在行首加上行号。

awk '/error/ {count++} END {print count}' /var/log/syslog : 统计/var/log/syslog中出现"error"的行数。

# 压缩与归档
## 打包与压缩：tar
**语法：**

bash  
	tar [选项] 压缩包名称 文件或目录...  
**常用选项：**

-c : 创建新的归档文件（create）。

-x : 从归档文件中提取文件（extract）。

-f 文件名 : 指定归档文件名（file）（此选项后必须紧跟文件名）。

-z : 通过 gzip 过滤归档（压缩或解压 .tar.gz 或 .tgz 文件）。

-j : 通过 bzip2 过滤归档（处理 .tar.bz2 文件）。

-J : 通过 xz 过滤归档（处理 .tar.xz 文件）。

-v : 详细地列出处理的文件（verbose）。

-t : 列出归档文件的内容（list）。

-C 目录 : 改变至指定目录后再执行操作。

**常用组合：**

**打包压缩:**

tar -czvf archive_name.tar.gz /path/to/dir_or_file (gzip压缩)

tar -cjvf archive_name.tar.bz2 /path/to/dir_or_file (bzip2压缩，压缩比更高)

**查看内容:**

tar -tzvf archive_name.tar.gz

**解压:**

tar -xzvf archive_name.tar.gz (解压到当前目录)

tar -xzvf archive_name.tar.gz -C /target/directory (解压到指定目录)

## 其他压缩工具
gzip 文件 / gunzip 文件.gz : 压缩/解压单个文件为 .gz 格式（原文件会被替换）。

bzip2 文件 / bunzip2 文件.bz2 : 压缩/解压为 .bz2 格式（压缩比更高）。

zip -r 压缩包名.zip 目录或文件 : 创建zip压缩包。

unzip 压缩包名.zip : 解压zip压缩包。

