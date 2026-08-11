# MCP stdio 配置

`database-schema-bootstrap` 分为两个进程：

1. 根目录 `mcp/database-schema-bootstrap/server.py` 是受信任的独立 metadata service，负责读取 profile、Windows Credential Manager 和 PostgreSQL。
2. skill 目录下的 `mcp_server.py` 是 AI 侧 stdio MCP adapter，只负责调用固定 loopback RPC，不包含数据库驱动、profile 或凭据代码。

独立 metadata service 必须由人工、Windows Service 或其他受控进程提前启动，MCP 客户端不能负责启动它。

## 安装依赖

独立服务使用项目指定的 Python 环境安装数据库依赖：

```powershell
D:\Anaconda\envs\xcyl\python.exe -m pip install -r E:\code\skills\mcp\database-schema-bootstrap\requirements.txt
```

AI 侧 adapter 只需安装 MCP 依赖：

```powershell
D:\Anaconda\envs\xcyl\python.exe -m pip install -r E:\code\skills\.agents\skills\database-schema-bootstrap\requirements-mcp.txt
```

## 启动命令

先由人工或受控服务管理器启动独立服务。它才可以读取目标项目 profile：

```powershell
D:\Anaconda\envs\xcyl\python.exe E:\code\skills\mcp\database-schema-bootstrap\server.py --config E:\code\xcyl-voltflow\.agents\database-schema-bootstrap\profiles\default.json --port 8765
```

然后配置 MCP 客户端启动 AI 侧 adapter：

```powershell
D:\Anaconda\envs\xcyl\python.exe E:\code\skills\.agents\skills\database-schema-bootstrap\mcp_server.py --endpoint http://127.0.0.1:8765
```

MCP 配置的等价结构如下；不同客户端的外层键名可能不同，但必须保持 `command`、`args` 和 `stdio` 语义：

```json
{
  "type": "stdio",
  "command": "D:\\Anaconda\\envs\\xcyl\\python.exe",
  "args": [
    "E:\\code\\skills\\.agents\\skills\\database-schema-bootstrap\\mcp_server.py",
    "--endpoint",
    "http://127.0.0.1:8765"
  ]
}
```

不要在 MCP 配置中放密码、DSN、profile 路径或密码环境变量。adapter 启动后只应显示三个工具：

- `list_databases`
- `list_tables`
- `describe_table`

MCP adapter 或独立服务不可用时，AI 不得直接运行 Python、`psql` 或任何 SQL 作为替代路径。

目录分隔和 RPC 白名单是行为边界；如果 AI 与服务使用同一 Windows 用户且能读取服务目录、profile 或凭据，不能把它们宣称为绝对安全隔离。生产环境应使用独立服务账号、ACL 和禁止 AI 直连 PostgreSQL 的网络策略。

