| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建/更新时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **/** | **公开** | 创建 | **2025-09-28** | **欧浩斌** |


# 文档说明：
本文档为PostgreSQL数据库运维操作指南，面向非专业数据库管理人员，提供日常运维所需的常用命令和操作说明。文档旨在帮助用户快速掌握基本的数据库管理操作，确保数据库稳定运行。

# 数据库连接命令
```shell
bash
#基本连接格式
psql -h [主机地址] -p [端口号] -U [用户名] -d [数据库名]
#示例：
psql -h 127.0.0.1 -p 5432 -U postgres -d myapp_db
#本地pgsql数据库，也可省略后面参数，直接执行psql登录，如：
psql
```

# 数据库信息查询
```shell
sql
#系统信息查询
SELECT version();  -- 返回数据库版本详细信息

#会话信息查询
SELECT current_user,current_database(),inet_client_addr(),current_schema();  

#数据库列表查看
\l		-- 间接列表
\l+		-- 详细列表（包括大小、描述等信息）

#查看数据库大小统计
SELECT 
    datname AS "数据库名",
    pg_size_pretty(pg_database_size(datname)) AS "大小",
    datconnlimit AS "连接限制"
FROM pg_database 
ORDER BY pg_database_size(datname) DESC;
```

#  数据库创建与维护
```shell
sql

#创建数据库（基础语法）
CREATE DATABASE new_database;

#创建数据库（完整参数）
CREATE DATABASE new_database
    OWNER = dbowner           -- 指定所有者
    TEMPLATE = template0      -- 使用模板
    ENCODING = 'UTF8'         -- 字符编码
    LC_COLLATE = 'en_US.UTF-8' -- 排序规则
    LC_CTYPE = 'en_US.UTF-8'  -- 字符分类
    CONNECTION LIMIT = 100;   -- 连接数限制

#修改数据库参数
ALTER DATABASE my_database 
    SET connection_limit = 50;

#重命名数据库
ALTER DATABASE old_name RENAME TO new_name;

#安全删除数据库（先确保无连接）
  #1. 先断开所有连接
  SELECT pg_terminate_backend(pid) 
  FROM pg_stat_activity 
  WHERE datname = 'database_to_drop';
  
  #2. 删除数据库
  DROP DATABASE database_to_drop;
```

# 表空间管理
<font style="color:rgb(15, 17, 21);">表空间用于控制数据库文件的物理存储位置。</font>

```shell
sql

#查看表空间
\db+  -- 显示详细信息

#创建表空间
CREATE TABLESPACE fast_space
    LOCATION '/opt/postgresql/data';

#在表空间中创建表
CREATE TABLE fast_table (
    id SERIAL PRIMARY KEY,
    data TEXT
) TABLESPACE fast_space;
```

# 用户账户管理
<font style="color:rgb(15, 17, 21);">管理数据库用户账户，包括创建、修改和删除操作。</font>

```shell
sql
#创建用户（两种语法）
CREATE USER username WITH PASSWORD 'password';
CREATE ROLE username WITH LOGIN PASSWORD 'password';

#用户属性设置
CREATE USER developer WITH 
    PASSWORD 'secure_password'
    VALID UNTIL '2024-12-31'   -- 密码有效期
    CONNECTION LIMIT 10;       -- 连接限制

#修改用户属性
ALTER USER username 
    WITH PASSWORD 'new_password'
    VALID UNTIL 'infinity';    -- 永久有效

#查看用户信息
\du  -- 用户列表
\du+ -- 详细用户信息

-#安全删除用户
  #1. 先转移对象所有权
  REASSIGN OWNED BY old_user TO new_user;

  #2. 删除用户权限
  DROP OWNED BY old_user;

  #3. 删除用户
  DROP USER old_user;
```

# 用户权限管理
<font style="color:rgb(15, 17, 21);">权限类型说明</font>

+ **<font style="color:rgb(15, 17, 21);">SELECT</font>**<font style="color:rgb(15, 17, 21);">: 查询数据</font>
+ **<font style="color:rgb(15, 17, 21);">INSERT</font>**<font style="color:rgb(15, 17, 21);">: 插入数据</font>
+ **<font style="color:rgb(15, 17, 21);">UPDATE</font>**<font style="color:rgb(15, 17, 21);">: 更新数据</font>
+ **<font style="color:rgb(15, 17, 21);">DELETE</font>**<font style="color:rgb(15, 17, 21);">: 删除数据</font>
+ **<font style="color:rgb(15, 17, 21);">CREATE</font>**<font style="color:rgb(15, 17, 21);">: 创建对象</font>
+ **<font style="color:rgb(15, 17, 21);">CONNECT</font>**<font style="color:rgb(15, 17, 21);">: 连接数据库</font>
+ **<font style="color:rgb(15, 17, 21);">TEMPORARY</font>**<font style="color:rgb(15, 17, 21);">: 创建临时表</font>

```shell
#数据库级别权限
GRANT CONNECT, CREATE ON DATABASE mydb TO username;

#模式级别权限
GRANT USAGE ON SCHEMA public TO username;
GRANT CREATE ON SCHEMA public TO username;

#表级别权限
GRANT SELECT, INSERT, UPDATE ON TABLE users TO username;
GRANT ALL PRIVILEGES ON TABLE products TO username;

#列级别权限（精细控制）
GRANT SELECT (id, name) ON TABLE employees TO username;

#权限回收
REVOKE DELETE ON TABLE users FROM username;

#查看权限信息
#查看表权限
\dp 表名

#查看用户权限
SELECT * FROM information_schema.table_privileges 
WHERE grantee = 'username';
```

# 备份与恢复
pgsql备份详细操作：

```shell
# 完整数据库备份
pg_dump -h localhost -U postgres -d mydb \
    --verbose \          # 显示详细进度
    --format=custom \    # 自定义格式（压缩）
    --file=mydb.backup

# 参数说明：
# --format=custom: 二进制格式，支持选择性恢复
# --format=plain:  文本格式，可编辑查看
# --jobs=4:        并行备份（加快速度）

# 仅备份数据（不含表结构）
pg_dump -h localhost -U postgres -d mydb \
    --data-only \
    --file=mydb_data.sql

# 仅备份表结构
pg_dump -h localhost -U postgres -d mydb \
    --schema-only \
    --file=mydb_schema.sql

# 备份特定表
pg_dump -h localhost -U postgres -d mydb \
    --table=users \
    --table=orders \
    --file=important_tables.sql

# 大型数据库并行备份
pg_dump -h localhost -U postgres -d large_db \
    --jobs=4 \
    --format=directory \    # 目录格式，支持并行
    --file=large_db_backup
```



pgsql数据库恢复操作详解：

```shell
# 完整恢复
pg_restore -h localhost -U postgres -d mydb \
    --verbose \
    --clean \          # 恢复前清理对象
    --if-exists \      # 配合clean使用
    mydb.backup

# 选择性恢复
pg_restore -h localhost -U postgres -d mydb \
    --table=users \    # 仅恢复特定表
    --data-only \      # 仅恢复数据
    mydb.backup

# 文本格式恢复
psql -h localhost -U postgres -d mydb -f mydb_backup.sql

# 恢复时遇到错误的处理
psql -h localhost -U postgres -d mydb \
    --set=ON_ERROR_STOP=on \  # 遇到错误停止
    -f mydb_backup.sql
```

# 连接监控与管理
<font style="color:rgb(15, 17, 21);">监控数据库连接状态，识别异常连接，管理连接资源。</font>

```shell
#查看当前所有连接
SELECT 
    pid AS "进程ID",
    usename AS "用户名",
    datname AS "数据库",
    client_addr AS "客户端IP",
    application_name AS "应用名称",
    state AS "状态",
    query_start AS "查询开始时间",
    query AS "执行语句"
FROM pg_stat_activity 
WHERE state = 'active';  -- 只显示活动连接

#按用户分组统计连接数
SELECT 
    usename,
    count(*) as connection_count
FROM pg_stat_activity 
GROUP BY usename 
ORDER BY connection_count DESC;

#识别长时间运行的查询
SELECT 
    pid,
    now() - query_start as duration,
    query 
FROM pg_stat_activity 
WHERE state = 'active' 
AND now() - query_start > interval '5 minutes';

#安全终止连接
  #1. 先尝试优雅终止
  SELECT pg_cancel_backend(pid) FROM pg_stat_activity 
  WHERE datname = 'problem_db' AND state = 'active';
  
  #2. 强制终止（谨慎使用）
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
  WHERE datname = 'problem_db';
```

