# 第三方来源与许可声明

`ui-frontend-workflow` 是本仓库改写和整合的自包含工作流，参考了 `frontend-design`、`ui-ux-pro-max` 和 `web-design-guidelines`。运行时无需安装来源 skill。

## 保留的许可证

- `licenses/frontend-design-LICENSE.txt`
- `licenses/ui-ux-pro-max-LICENSE.txt`

保留来源许可证文本，本文只记录来源与本仓库的修改，不替代许可证条款。

## 来源记录

### frontend-design

- 官方仓库：<https://github.com/anthropics/skills>。
- 本次核对文件：[固定版本 SKILL.md](https://github.com/anthropics/skills/blob/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/frontend-design/SKILL.md)。
- 文件更新提交：`41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`，2026-09-03；[提交记录](https://github.com/anthropics/skills/commit/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f)。
- 核对日期：2026-10-14；以提交 SHA 标识本次参考版本，不保证持续跟踪上游。
- 创建时本地来源：`E:\code\skills\.agents\skills\frontend-design`；当前归档为 `archive/frontend-design`。
- 原 frontmatter 许可说明：`Complete terms in LICENSE.txt`。
- 许可证副本：`licenses/frontend-design-LICENSE.txt`，Apache License 2.0。

### ui-ux-pro-max

- 创建时本地来源：`E:\code\skills\.agents\skills\ui-ux-pro-max-skill-2.5.0`；当前归档为 `archive/ui-ux-pro-max-skill-2.5.0`。
- 本地版本标识：`2.5.0`；本次未更新或核对其上游版本。
- 许可证副本：`licenses/ui-ux-pro-max-LICENSE.txt`，MIT License，版权持有人为 Next Level Builder。

### web-design-guidelines

- 创建时本地来源：`E:\code\skills\.agents\skills\web-design-guidelines`；当前归档为 `archive/web-design-guidelines`。
- 本地源元数据：作者 `vercel`，版本 `1.0.0`；本次未更新或核对其上游版本。
- 本地来源未附独立许可证文件，因此只保留来源信息，不补造许可证文本。

## 本仓库的改写与整合

原工作流已整合产品判断、实现状态、可访问性、响应式与工程审查规则。2026-10-14 的更新定向吸收 `frontend-design` 的设计依据、计划自审、克制表达和界面文案建议，并补充以下适配：

- 用户需求和已有设计系统优先；反模板示例作为检查线索，不设统一风格禁令。
- 保留完整工程审查，小型修复使用简化流程。
- 配色数量、字体数量和线框按需要确定；中文排版按实际语言与字号判断。
- 元数据 description 使用中英双语，主体内容使用中文。
- 本仓库改写的规则位于 `SKILL.md` 和 `references/ui-frontend-playbook.md`，来源许可证文本保留。

本次维护的静态审查与验证边界见 [2026-10-14 审查记录](SKILL.2026-10-14.review.md)。
