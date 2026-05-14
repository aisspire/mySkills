---
name: readme-generation
description: Use when creating, rewriting, reviewing, or updating README.md files, GitHub project pages, installation/usage docs, badges, screenshots, feature sections, safety notes, or when project-post-change-actions recommends a README update
---

# README Generation

## Overview

Create README files from verified project facts. Treat the README as the project's front door: first explain why the project matters, then how to use it, then how it works and how to maintain it.

Never invent screenshots, release links, safety guarantees, benchmarks, user claims, or support channels. If an important fact is missing, ask for it or leave a clear `TODO`.

## Workflow

1. Inspect the existing project facts before drafting.
   - Read any existing `README.md`, package manifests, build files, license, docs, release notes, and obvious entrypoints.
   - Run `python scripts/collect_readme_context.py <project-root>` from this skill for a first-pass inventory.
   - For changed projects, inspect the targeted diff so the README reflects the actual behavior change.
2. Choose the output mode.
   - **Create**: write a complete README when none exists or the user asks for a fresh one.
   - **Rewrite**: preserve true existing content, reorder and sharpen it.
   - **Review**: lead with findings and exact sections to change.
   - **Post-change update**: draft only the README sections affected by the current change unless the user asks for a full rewrite.
3. Ask for missing high-value resources when they matter.
   - UI screenshots or GIFs for desktop, web, mobile, games, visual tools, or demos.
   - Target users, positioning, project background, design intent, and the main pain point.
   - Install/download path, release URL, package registry, support links, logo, and license if not discoverable.
   - Safety/data facts for tools that read, write, delete, migrate, repair, upload, or back up user data.
4. Draft in reader decision order.
   - First screen: name, one-sentence positioning, pain statement, 3-5 useful badges, download/install link if applicable, screenshot/GIF when visual.
   - Main path: why it exists, features, installation/download, quick start, usage.
   - Trust path: safety/privacy/data model, limits, FAQ, support.
   - Developer path: architecture, development, build, release, contribution.
5. Apply only when appropriate.
   - If the user directly asked to write or update `README.md`, edit it.
   - If invoked from `project-post-change-actions`, follow that skill's confirmation boundary before editing.

## Default Structure

Use this order unless the project has a strong reason to differ:

```md
# Project Name

Short positioning sentence.

Pain-oriented explanation.

Badges.

Screenshot or GIF.

## Why this exists

## Features

## Download / Installation

## Quick Start

## Usage

## Safety / Privacy / Data Model

## How it works

## Development

## Build

## Release

## FAQ

## Support
```

Move maintainer-only details, long release procedures, configuration matrices, and file trees behind later sections or `<details>` blocks.

## Writing Rules

- Put user benefit before implementation detail.
- Write features as capabilities users care about, not as a list of internal modules.
- Prefer short runnable commands over vague setup prose.
- Separate ordinary user instructions from developer/build/release instructions.
- Use badges sparingly; never turn the top of the README into a badge wall.
- For UI projects, include screenshot/GIF placeholders only when the image file or user intent is known.
- For libraries, prioritize install command, minimal example, API surface, compatibility, and versioning.
- For CLIs, prioritize install, one-command quick start, common commands, examples, exit behavior, and config.
- For local-data tools, include a dedicated safety/data model section.

## Local-Data Rule

If the project reads, writes, repairs, deletes, migrates, uploads, or backs up local user data, include `Safety / Privacy / Data Model`.

Cover:

- files or directories read,
- files or directories modified,
- whether anything is uploaded,
- backup behavior,
- reversible and irreversible operations,
- operations requiring the main app to be closed,
- operations the tool refuses to perform for safety.

If any of these facts are unknown, ask the user or mark them as `TODO` instead of guessing.

## Badges and Patterns

Load `references/readme-patterns.md` only when drafting badges, screenshot blocks, feature cards, or choosing a project-type-specific structure.

## Quality Checklist

Before finishing, verify:

- The first paragraph explains what the project is and who needs it.
- A visitor can decide whether to continue within 10 seconds.
- Installation/download is easy to find.
- Quick start is practical and short.
- Visual projects have screenshots/GIFs or an explicit request for them.
- Risky operations explain safety behavior.
- Architecture comes after usage.
- Build/release content does not block ordinary users.
- README claims are backed by project files, user-provided facts, or marked `TODO`.
- Links point to real files, releases, docs, issues, or support destinations.
