# 接口文档输出模板

默认输出给人阅读的 Markdown/Wiki 文档。按模块输出，模块内按前端页面或业务调用流程排序，例如：列表 -> 详情 -> 新建 -> 编辑 -> 删除 -> 刷新列表。

如果用户明确要求 OpenAPI、Swagger、Knife4j、Apifox 或 Postman，再额外输出对应格式或映射说明。

## 1. 模块概览

- 模块名称：
- 文档版本：
- 文档状态：草稿 / 联调中 / 已确认 / 已废弃
- 负责人或归属模块：
- 代码范围：
- 入口文件：
- 接口数量：
- 主要前端页面或业务流程：
- 环境地址：
  - dev：
  - test：
  - prod：
- 鉴权方式：
- 统一响应结构：
- 主要待确认项：

## 2. 通用约定

### 2.1 请求约定

| 项 | 约定 | 示例 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- |
| Content-Type | `application/json` | `application/json` | confirmed | `ExampleController` | JSON 请求体 |
| Authorization | Bearer Token | `Bearer eyJ...` | inferred | 权限注解/网关配置 | 需要登录时传入 |
| 租户 ID | Header | `tenant-id: 1001` | uncertain | 未发现统一配置 | 需要前后端确认 |

没有特殊 Header 时明确写：无特殊 Header。

### 2.2 响应约定

| 字段 | 类型 | 必填 | 示例值 | 说明 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- | --- | --- |
| code | string | 是 | `SUCCESS` | 业务状态码 | confirmed | `R<T>` / 全局响应包装 |
| message | string | 是 | `success` | 提示信息 | confirmed | `R<T>` / 全局响应包装 |
| data | object | 否 | `{}` | 业务数据 | confirmed | `R<T>` / 接口返回类型 |
| traceId | string | 否 | `9f3b2c7a1d` | 链路追踪 ID | uncertain | 未发现统一来源 |

### 2.3 分页约定

| 字段 | 位置 | 类型 | 必填 | 默认值 | 示例值 | 说明 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pageNum | query/body | integer | 否 | 1 | 1 | 页码，从 1 开始 | confirmed | 分页对象/查询入口 |
| pageSize | query/body | integer | 否 | 10 | 20 | 每页数量 | confirmed | 分页对象/查询入口 |

不分页时明确写：本模块未发现分页接口。

### 2.4 时间和枚举约定

| 项 | 约定 | 示例 | 说明 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- | --- |
| 时间格式 | `yyyy-MM-dd HH:mm:ss` / ISO 8601 / 时间戳 | `2026-07-09 10:30:00` | 按代码实际格式填写 | confirmed | 字段注解/序列化配置 |
| 状态枚举 | 展开所有允许值 | `ACTIVE` / `DISABLED` | 写清含义 | confirmed | `StatusEnum` |

## 3. 页面或业务调用流程

调用流程按 Diataxis How-to 思路组织：面向用户要完成的任务，写清步骤、接口顺序、字段传递和失败处理。

### 3.1 {流程名称}

- 目标：
- 适用页面：
- 前置条件：
- 成功结果：
- 失败结果：

| 步骤 | 前端动作或业务动作 | 调用接口 | 依赖字段 | 传参来源 | 成功后动作 | 失败处理 | 证据等级 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 进入列表页 | 列表查询 | 无 | 页面初始化 | 渲染列表 | 展示错误提示 | inferred |
| 2 | 点击详情 | 查看详情 | `id` | 列表行 `id` | 打开详情页或弹窗 | 找不到数据时提示并刷新列表 | confirmed |
| 3 | 提交编辑表单 | 更新接口 | `id`, 表单字段 | 详情接口 + 用户输入 | 关闭弹窗并按原筛选刷新列表 | 校验失败时定位到字段 | inferred |

### 3.2 接口依赖总览

| 前端动作 | 上游接口 | 下游接口 | 关键字段 | 是否需要转换 | 前置条件 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 点击列表详情 | 列表查询 | 查看详情 | `id` | 否 | 列表行存在 | 列表行主键传给详情接口 |
| 进入编辑页 | 查看详情 | 更新接口 | `id`, 表单字段 | 可能需要 | 有编辑权限 | 提交前先拉完整数据 |
| 提交编辑表单 | 更新接口 | 列表查询 | `pageNum`, `pageSize`, 筛选条件 | 否 | 更新成功 | 按原筛选条件刷新列表 |

## 4. 接口清单

| 顺序 | 接口名称 | Method | Path | 用途 | 所属流程 | 状态 | 入口 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 列表查询 | `GET` | `/api/example/list` | 查询分页列表 | 列表页初始化 | 已确认 | `ExampleController#list` |
| 2 | 查看详情 | `GET` | `/api/example/{id}` | 查看单条记录详情 | 点击详情/进入编辑 | 已确认 | `ExampleController#getDetail` |

## 5. 接口详情

### 5.1 {接口名称}

#### 基本信息

| 项 | 值 |
| --- | --- |
| 接口名称 | 查询用户详情 |
| 用途 | 根据用户 ID 查询用户基础信息 |
| 接口状态 | 草稿 / 联调中 / 已确认 / 已废弃 |
| 负责人或归属模块 | 用户中心后端 |
| 版本 | v1 |
| 入口 | `{文件路径}::{方法名}` |
| 请求对象 | `{RequestClass}` / 无 |
| 返回对象 | `{ResponseClass}` / 文件流 / 无 |

#### 请求信息

| 项 | 值 |
| --- | --- |
| Method | `GET` |
| URL | `/api/v1/users/{userId}` |
| 环境地址 | 见模块概览 |
| Content-Type | `application/json` |
| Auth | Bearer Token / Cookie / 签名 / 无 |
| 是否需要登录 | 是 / 否 / 未确认 |
| 是否幂等 | 是 / 否 / 未确认 |
| 是否有副作用 | 是 / 否 |

#### Header 参数

| 字段名 | 类型 | 必填 | 示例值 | 约束 | 约束来源 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Authorization | string | 是 | `Bearer eyJ...` | Bearer Token | 权限配置 | inferred | 权限注解/网关配置 | 登录凭证 |

无特殊 Header 时写：无特殊 Header。

#### Path 参数

| 字段名 | 类型 | 必填 | 示例值 | 约束 | 约束来源 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| userId | string | 是 | `u_10001` | 非空 | `@PathVariable` | confirmed | `UserController#getDetail` | 用户 ID |

无 Path 参数时写：无。

#### Query 参数

| 字段名 | 类型 | 必填 | 示例值 | 默认值 | 约束 | 约束来源 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| includeProfile | boolean | 否 | `true` | `false` | `true` / `false` | 参数类型 | confirmed | `UserQuery#includeProfile` | 是否返回扩展资料 |

无 Query 参数时写：无。

#### Body 参数

| 字段名 | 类型 | 必填 | 示例值 | 默认值 | 约束 | 约束来源 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nickname | string | 是 | `Tom` | 无 | 1-50 字符 | `@Size` | confirmed | `UserSaveBo#nickname` | 昵称 |
| status | string | 否 | `ACTIVE` | `ACTIVE` | `ACTIVE` / `DISABLED` | 枚举类 | confirmed | `UserStatusEnum` | 用户状态 |

无 Body 参数时写：无。

#### 请求示例

```http
GET /api/v1/users/u_10001?includeProfile=true
Authorization: Bearer eyJ...
Accept: application/json
```

有请求体时补充：

```json
{
  "nickname": "Tom",
  "status": "ACTIVE"
}
```

#### 成功响应

- HTTP Status：`200 OK`
- 业务状态码：`SUCCESS`

```json
{
  "code": "SUCCESS",
  "message": "success",
  "data": {
    "userId": "u_10001",
    "nickname": "Tom",
    "avatarUrl": "https://example.com/avatar.png",
    "status": "ACTIVE",
    "createdAt": "2026-07-09T10:30:00+08:00"
  },
  "traceId": "9f3b2c7a1d"
}
```

##### 响应字段

| 字段名 | 类型 | 必填/可空 | 示例值 | 约束或取值 | 证据等级 | 证据定位 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| code | string | 是 | `SUCCESS` | 业务状态码 | confirmed | 统一响应包装 | 业务处理结果 |
| message | string | 是 | `success` | 无 | confirmed | 统一响应包装 | 提示信息 |
| data.userId | string | 是 | `u_10001` | 非空 | confirmed | `UserAssembler#toDetailVO` | 用户 ID |
| data.nickname | string | 是 | `Tom` | 1-50 字符 | confirmed | `UserAssembler#toDetailVO` | 昵称 |
| data.avatarUrl | string | 否 | `https://example.com/avatar.png` | URL | inferred | `UserDetailVo#avatarUrl` | 头像地址 |
| data.status | string | 是 | `ACTIVE` | `ACTIVE` / `DISABLED` | confirmed | `UserStatusEnum` | 用户状态 |
| data.createdAt | string | 是 | `2026-07-09T10:30:00+08:00` | 时间格式见通用约定 | confirmed | `UserAssembler#toDetailVO` | 创建时间 |
| traceId | string | 否 | `9f3b2c7a1d` | 无 | uncertain | 未发现统一来源 | 链路追踪 ID |

#### 错误响应

```json
{
  "code": "USER_NOT_FOUND",
  "message": "用户不存在",
  "data": null,
  "traceId": "9f3b2c7a1d"
}
```

| HTTP 状态码 | 业务错误码 | 触发场景 | 错误信息示例 | 前端处理建议 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- | --- | --- |
| 400 | `INVALID_PARAM` | `userId` 为空或格式错误 | 参数错误 | 表单或页面提示参数错误 | confirmed | 参数校验/异常处理 |
| 401 | `UNAUTHORIZED` | 未登录或 Token 无效 | 未登录或 Token 无效 | 跳转登录或刷新登录态 | inferred | 权限配置 |
| 403 | `FORBIDDEN` | 无查看权限 | 无权限 | 展示无权限提示 | inferred | 权限注解 |
| 404 | `USER_NOT_FOUND` | 用户不存在 | 用户不存在 | 提示后返回列表或刷新 | confirmed | `UserService#getDetail` |
| 500 | `INTERNAL_ERROR` | 服务端异常 | 服务端异常 | 展示通用错误提示 | inferred | 全局异常处理 |

#### 边界规则

| 场景 | 接口行为 | 前端处理建议 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- |
| 空数据 | 返回 `data: null` 或空列表 | 展示空状态 | confirmed | service 返回逻辑 |
| 无权限 | 返回 403 或业务错误码 | 展示无权限，不重试 | inferred | 权限注解 |
| 重复提交 | 返回业务错误或忽略重复请求 | 禁用按钮或使用幂等键 | uncertain | 未发现明确逻辑 |
| 状态不允许操作 | 返回业务错误码 | 保留表单并展示原因 | confirmed | 状态校验逻辑 |

#### 调用关系

| 前端动作 | 上游接口 | 本接口依赖 | 下游接口 | 关键字段 | 是否需要转换 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 点击列表详情 | 列表查询 | 列表行 `id` | 查看详情 | `id` -> `userId` | 是 | 列表字段名和详情 path 参数不同 |
| 提交编辑表单 | 查看详情 | `userId` 和表单字段 | 更新接口 | `userId` | 否 | 详情数据回填表单 |

#### 证据和待确认项

- confirmed：
  - `UserController#getDetail` 确认 Method、Path、Path 参数。
  - `UserAssembler#toDetailVO` 确认返回字段。
- inferred：
  - 鉴权来自权限注解，具体 Token 格式需结合网关确认。
- uncertain：
  - `traceId` 来源未在当前模块发现。
  - 重复提交处理未发现明确逻辑。

## 6. 错误码总览

| HTTP 状态码 | 业务错误码 | 适用接口 | 触发场景 | 前端处理建议 | 证据等级 | 证据定位 |
| --- | --- | --- | --- | --- | --- | --- |
| 400 | `INVALID_PARAM` | 全部接口 | 参数校验失败 | 展示字段级或全局错误 | confirmed | 全局异常处理 |
| 401 | `UNAUTHORIZED` | 需登录接口 | 未登录或 Token 无效 | 跳转登录或刷新登录态 | inferred | 权限配置 |
| 403 | `FORBIDDEN` | 需权限接口 | 权限不足 | 展示无权限提示 | inferred | 权限注解 |
| 404 | `RESOURCE_NOT_FOUND` | 详情/编辑/删除 | 数据不存在 | 提示并刷新列表 | confirmed | service 查询逻辑 |
| 500 | `INTERNAL_ERROR` | 全部接口 | 服务端异常 | 展示通用错误提示 | inferred | 全局异常处理 |

## 7. 版本变更记录

| 版本 | 日期 | 变更类型 | 变更内容 | 兼容性影响 | 负责人 |
| --- | --- | --- | --- | --- | --- |
| v1.0.0 | 2026-07-09 | 新增 | 初版接口文档 | 无 | 后端负责人 |
| v1.1.0 | 2026-07-09 | 变更 | 新增 `includeProfile` 查询参数 | 向后兼容 | 后端负责人 |
| v2.0.0 | 2026-07-09 | 废弃/破坏性变更 | 删除旧字段 `name`，改为 `nickname` | 前端需同步改字段 | 后端负责人 |

## 8. 风险与待确认项

- 标记为 `uncertain` 的字段或规则。
- 代码中未发现直接证据、但业务上看起来应存在的约束。
- 前端调用时容易传错的字段名、类型或状态值。
- 错误码和 HTTP 状态码是否符合项目统一约定。
- Mock 地址、测试账号、测试数据是否可用。
- 接口变更是否影响已有页面、导出、下拉、详情、编辑或审核流程。
