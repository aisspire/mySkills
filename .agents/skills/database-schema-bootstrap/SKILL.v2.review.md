# Database Schema Bootstrap v2 发布审查

## 工作流状态

- 当前轮次：Stage 0-6 完成
- 当前发布等级：`static-compliant`
- 发布确认：已获得，用户明确回复“正式发布”
- 正式入口状态：`SKILL.md` 已发布 v2
- 下一动作：保持 `static-compliant`，继续完成外部平台与真实 PostgreSQL 门禁
- 格式校验：候选与正式入口均已通过官方 `quick_validate.py`
- 自动验证：依赖完整 runtime venv 中 43 项测试通过，零跳过；包含 SessionStart hook stdout 契约回归

## 范围

- 原始 skill：`.agents/skills/database-schema-bootstrap/SKILL.md`
- 候选输出：`.agents/skills/database-schema-bootstrap/SKILL.v2.candidate.md`
- 正式入口：`.agents/skills/database-schema-bootstrap/SKILL.md`
- 不可丢失：三个 metadata-only 工具、禁止 AI 直连、密码不进入 AI、失败关闭、真实数据库验收限制

## Baseline Evidence

已有实现/安全回归测试，但没有一组独立真实 writing baseline failure → 优化 → forward test 证据链。根据 `skill-maintenance`，最高只能标记 `static-compliant`，不能宣称 fully-writing-compliant。

本轮已完成 WSL 环境的干净安装、运行、升级、停止和普通卸载验证。隔离 `CODEX_HOME` 下的真实 `codex exec -C` 因缺少认证信息返回 401，未进入 MCP 工具调用；Windows 普通用户与真实 PostgreSQL 门禁仍未执行。

## 审查结论

### 安全风险

- v1 文案会误导 AI 读取 profile/Credential Manager 模型，已在候选中切换为 access-only。
- 多 connection 容易混淆结果，候选要求保留返回的 `connection_id`。
- 明文 secrets 容易被误称为强隔离，候选明确软边界并禁止 AI 主动读取 runtime。
- adapter/gateway 失败时存在直连回退诱因，候选保留绝对禁止并提供人工修复类别。

### 结构问题

- 候选 frontmatter 只有 `name` 与中英双语 `description`。
- 已补齐 Overview、When to Use、When NOT to Use、Trust Boundary、Workflow、Failure Handling 和 Common Mistakes。
- 详细 access、路由和工具契约下沉到三个 v2 references，主入口保持可路由。

### 触发条件

- 正向触发限定为依赖真实 PostgreSQL schema。
- 排除新设计、权威 DDL、业务数据、非 PostgreSQL、安装/凭据管理，避免吸引普通数据库任务或控制面操作。

## 优化摘要

- 保留：metadata-only、三个固定工具、禁止直连、失败关闭、事实/不确定性区分。
- 修复：移除 v1 profile/Credential Manager/逐项目服务语义。
- 新增：connection ID 选择、access 可读边界、中央配置不可读、软隔离、统一不可用错误、双平台验收限制。
- 删除：`target_tables`、active-profile、`credential_target`、项目 state SHA 路由、SessionEnd 暗示。
- 剩余风险：缺少真实 writing baseline；Windows/WSL 普通用户和真实 PostgreSQL 发布门禁未完成。

## 复审结论

- 风险变化：候选把 AI 可读范围缩到项目 access，并明确禁止中央/secret/state 读取；直连回退与强隔离误述风险下降。
- 新增副作用：连接不可用错误有意不提供中央细节，排错必须转交人工 control；这是协议隐私取舍，不是缺陷。
- 当前可宣称等级：`static-compliant`
- 不可宣称：fully-writing-compliant、Windows/WSL 双平台验收完成、真实 PostgreSQL 已验证。

## 发布确认

- 候选路径：`.agents/skills/database-schema-bootstrap/SKILL.v2.candidate.md`
- 正式入口路径：`.agents/skills/database-schema-bootstrap/SKILL.md`
- 当前发布等级：`static-compliant`
- 实际覆盖内容：正式 skill 主入口已切换到 v2 references；旧正式入口、v1 references 与旧审查报告已归档到明确的 v1 历史路径
- 用户确认状态：已确认并完成发布
