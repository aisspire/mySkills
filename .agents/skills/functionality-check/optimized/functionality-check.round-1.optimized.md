# 优化结果
- 目标 skill：functionality-check
- 输出状态：已生成候选优化版
- 输出路径：`E:\code\skills\.agents\skills\functionality-check\optimized\functionality-check.round-1.optimized.md`
- 优化方式：基于审查报告的静态优化

# 变更摘要
## 保留项
- 中文输出
- 从代码推断功能
- 完整数据流转过程
- 业务逻辑解释
- 实现完整性判断
- 关键证据与不确定项

## 修复项
- 收紧了 `description`，避免把流程塞进触发字段
- 强化了“主动调用 skill 名称”这一触发条件
- 增加 `## 快速参考`
- 收紧段落表达，降低扫描成本

## 新增项
- workflow 所需的审查、gate、索引配套文件

## 删除项
- 无功能性删除

## 剩余风险
- 尚未进行真实 baseline pressure scenario
- 仍不能宣称完整 `writing-skills` 合规

# writing 修复状态
- 已静态修复的部分：
  - frontmatter
  - description
  - 结构扫描性
  - discoverability
- 已改进的流程约束：
  - 明确触发场景
  - 明确不适用场景
  - 明确输出骨架
- 仍需真实验证的部分：
  - baseline failure evidence
  - with-skill improved evidence
  - loophole/refactor evidence
- 当前可宣称等级：静态合规

# 优化版 Skill

```markdown
---
name: functionality-check
description: Use when reviewing implemented backend code and needing to infer what a module, interface, or business flow actually does, whether the functional path seems complete, or when asked to summarize functionality or explain logic from code.
---

# 功能检查
## 概述

这个 skill 用于从旁观者视角，根据后端代码、配置和测试材料，推断一个功能实际上做了什么、链路是否接通，以及业务逻辑如何运转。

核心原则：
- 以代码证据为准，不把命名猜测写成事实。
- 明确区分“已确认”“推断”“不确定”。
- 全程使用中文。
- 默认给出完整数据流转过程，而不是只给功能摘要。

## 何时使用

- 用户主动调用 `功能检查` 或 `functionality-check`。
- 用户说“总结下功能”“梳理下功能”“解释这个模块做了什么”“看代码推断功能”。
- 开发完某个后端模块后，需要判断功能是否看起来已经形成闭环。
- 需要从代码中重建接口、任务、消息或事件链路的端到端流程。
- 需要站在旁观视角解释业务逻辑，而不是直接改代码。

## 何时不要使用

- 用户要的是运行结果、联调结论、线上行为或真实数据状态。
- 用户已经给出日志、监控、报错和复现步骤，目标是定位异常；这时应优先走调试流程。
- 当前任务的重点是直接实现、修复或重构，而不是推断功能。

## 分析边界

可使用的证据：
- 源码
- 配置
- 路由定义
- DTO、Schema、类型定义
- 数据访问层
- 事件、消息、队列、定时任务
- 测试

默认不能假装已确认的内容：
- 真实运行结果
- 外部系统实际返回值
- 数据库中的真实数据
- 未出现在代码里的业务规则

如果缺少运行证据，也要照常给出基于代码的分析，但必须明确哪些结论仍需人工确认。

## 工作流程

### 1. 明确分析范围

先确认用户关心的是哪一层：
- 单个接口
- 单个模块
- 一组文件
- 一条业务流程

如果范围不明确，优先根据文件名、目录名、类名、函数名、路由名来收敛。

### 2. 找到功能入口

后端场景优先从这些入口开始：
- route、router
- controller、handler
- RPC、message consumer
- cron、scheduler
- event listener
- command、job

如果没有显式入口，就向上追踪调用方，直到定位到真正的业务起点。

### 3. 追踪完整数据流

至少要回答清楚：
- 输入从哪里来
- 经过了哪些校验、转换和权限判断
- 核心业务逻辑在哪一层执行
- 读写了哪些模型、表、仓储或外部服务
- 产生了哪些副作用
- 最终返回了什么，或把结果交给了谁

主干链路默认按这个模板组织：

`请求/消息进入 -> 参数解析 -> 校验/鉴权 -> 业务服务 -> 数据访问/外部调用 -> 状态变更 -> 事件/任务/通知 -> 返回结果`

如果有关键分支，要把主干路径和关键分支分别写清楚。

### 4. 提炼业务逻辑

不要只报函数调用顺序，还要说明业务含义：
- 这个功能解决什么问题
- 成功条件是什么
- 失败条件是什么
- 哪些字段、状态或条件决定流程走向
- 哪些约束属于隐式业务规则

重点留意：
- 状态流转
- 幂等、去重、重试
- 权限或角色控制
- 数据归属约束
- 补偿、回滚、兜底逻辑

### 5. 判断是否形成闭环

主动检查这些闭环点：
- 入口是否真正接到了业务服务
- 核心服务是否真正落到了持久化或外部动作
- 关键分支是否有返回、异常或补偿处理
- 写入后的后续动作是否接上了
- 事件、队列、定时任务是否存在“只生产不消费”或“只有声明未接线”
- DTO、Schema、Entity 字段是否前后对得上
- 测试是否覆盖主流程

如果发现“像是要做这个功能，但链路断了”，要直接指出。

## 快速参考

后端优先检查清单：
- 入口文件：路由、控制器、消费者、定时任务
- 参数定义：DTO、Schema、类型、校验器
- 权限控制：鉴权、中间件、guard、角色判断
- 业务层：service、use case、domain method
- 数据层：repository、DAO、ORM、SQL、cache
- 集成层：HTTP client、RPC、MQ、事件、文件存储
- 副作用：日志、通知、异步任务、审计记录
- 输出层：响应体、事件体、返回码、错误映射
- 测试：单测、集成测试、契约测试

常用检索关键词：
- `rg "Controller|Route|router|handler|Consumer|Listener|Cron|Scheduler" <path>`
- `rg "create|update|delete|get|list|publish|consume|emit" <path>`
- `rg "dto|schema|validator|guard|middleware|repository|service" <path>`
- `rg "emit|publish|dispatch|enqueue|schedule|notify" <path>`

如果链路较长，优先抓主干，不要一开始陷入次要工具函数。

## 输出格式

除非用户明确要求更短，否则按下面结构输出：

### 1. 功能结论
### 2. 功能入口
### 3. 完整数据流转过程
### 4. 业务逻辑解释
### 5. 实现完整性判断
### 6. 关键证据
### 7. 不确定项

## 输出要求

- 使用中文。
- 明确区分“已确认”“推断”“不确定”。
- 不得把“可能”“看起来”写成确定事实。
- 不要只贴目录树或函数名，必须解释它们之间如何协作。
- 即使用户只说“总结下功能”，也仍然要保留“完整数据流转过程”和“业务逻辑解释”，只是可以写得更紧凑。

## 常见错误

- 只看 controller，不继续追到 service、repository 和副作用。
- 把命名直接当成功能事实，不核对实际实现。
- 只描述代码结构，不解释业务规则。
- 漏掉异步链路、事件链路或失败分支。
- 没区分“代码已接线”和“代码只是预留接口”。
- 因为没有运行证据，就拒绝给出基于代码的功能推断。

## 最终要求

每次分析结束时，都要给出一句简明结论：

`从代码证据看，该功能目前属于：已形成闭环 / 基本形成闭环 / 部分形成闭环 / 疑似未形成闭环。`
```

# 回归测试建议
- baseline failure scenario：
  - 用户只说“总结下这个模块功能”，观察未带 skill 时是否会漏掉完整数据流和闭环判断。
- optimized scenario：
  - 同一请求下加载该 skill，观察是否稳定给出固定七段输出。
- loophole / rationalization scenario：
  - 用户只给局部实现文件，观察是否仍会补找入口、数据层和副作用。
