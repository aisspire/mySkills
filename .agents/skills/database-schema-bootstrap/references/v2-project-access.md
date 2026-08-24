# v2 项目 access

项目唯一允许 AI 读取的配置是当前 Git 根下：

```text
.agents/database-schema-bootstrap/access.json
```

示例：

```json
{
  "version": 2,
  "project_id": "9e526cf7-7781-4f41-a252-3c9f44e90c17",
  "connections": {
    "erp-prod-ro": {"enabled": true},
    "reporting-ro": {"enabled": false}
  },
  "active": "erp-prod-ro"
}
```

## 语义

- `project_id`：该 clone/worktree 在当前 Windows 或 WSL/Linux 环境中的随机 UUID。
- `connections`：项目本地 connection ID 清单；只有 `enabled=true` 可用于 MCP。
- `active`：省略 MCP `connection_id` 时的默认值，必须指向 enabled ID；可以为 `null`。

本文件不包含主机、数据库用户或密码。ID 是否出现在 access 不是最终授权，gateway 仍会校验中央 grant 与绑定 Git 根。

## AI 边界

AI 可以读取本文件来选择 connection ID，但不得：

- 修改它来绕过中央授权；
- 读取 runtime 的 connections、secrets、projects、service/install state 或日志；
- 把 `enabled=false` 当成 ID 保密；
- 猜测未登记的 connection ID。

项目移动、初始化、grant、enable、use、revoke 和 remove 由人工控制程序完成。access 由工具加入 Git `info/exclude`，不应提交。
