# README Patterns

Use this reference when concrete README snippets are useful. Replace every placeholder with verified facts; do not publish placeholders unless the user asked for a scaffold.

## First Screen

```md
# Project Name

One-sentence positioning for the target user.

Short pain statement that explains why the project exists.

<p align="center">
  <img src="https://img.shields.io/github/v/release/OWNER/REPO?style=for-the-badge&label=release" alt="Release" />
  <img src="https://img.shields.io/github/downloads/OWNER/REPO/total?style=for-the-badge&label=downloads" alt="Downloads" />
  <img src="https://img.shields.io/github/stars/OWNER/REPO?style=for-the-badge" alt="Stars" />
  <img src="https://img.shields.io/github/license/OWNER/REPO?style=for-the-badge" alt="License" />
</p>

<p align="center">
  <a href="https://github.com/OWNER/REPO/releases/latest">
    <img src="https://img.shields.io/badge/Download-Latest_Release-2ea44f?style=for-the-badge&logo=github" alt="Download latest release" />
  </a>
</p>

<p align="center">
  <img src="docs/images/main-window.png" alt="Main window" width="900" />
</p>
```

Use release/download badges only when the project has a GitHub remote and releases are expected. Use package registry badges for published libraries.

## Feature Cards

```md
<table>
  <tr>
    <td><b>Feature 1</b><br/>User-facing explanation.</td>
    <td><b>Feature 2</b><br/>User-facing explanation.</td>
  </tr>
  <tr>
    <td><b>Feature 3</b><br/>User-facing explanation.</td>
    <td><b>Feature 4</b><br/>User-facing explanation.</td>
  </tr>
</table>
```

Use cards when the project has several peer features. Use ordinary bullets when the feature list is short or deeply technical.

## Project-Type Emphasis

| Project type | README should emphasize |
| --- | --- |
| Desktop app | Screenshot/GIF, download, safety/privacy, common workflows, troubleshooting |
| Web app | Live demo, screenshots, local setup, environment variables, deployment |
| CLI | Install, first command, examples, config, exit behavior, automation usage |
| Library/SDK | Install, minimal example, API surface, compatibility, versioning |
| Backend service | API docs, config, local run, migrations, observability, deployment |
| Data/local repair tool | Safety model, backups, dry-run behavior, recovery, exact file scope |

## Review Findings Format

When reviewing an existing README, lead with actionable issues:

```md
**Findings**
- [P1] Missing install path: users cannot run the project from the README.
- [P2] Safety behavior is implied but not stated for local data writes.
- [P3] Screenshot link points to a missing file.

**Recommended README Changes**
- Add `Installation` with the verified command.
- Add `Safety / Privacy / Data Model`.
- Replace the broken screenshot path or ask the user for a current screenshot.
```
