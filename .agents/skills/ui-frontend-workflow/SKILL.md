---
name: ui-frontend-workflow
description: Use when a task is related to UI, UX, frontend design, web interface creation, component/page implementation, visual polishing, responsive behavior, accessibility, or UI review. This self-contained skill runs a design to implementation to review workflow for frontend/UI work without requiring frontend-design, ui-ux-pro-max, or web-design-guidelines to be installed.
---

# UI Frontend Workflow

## Overview

Use this skill for UI and frontend tasks that need more than a single code edit. It combines product-aware UX planning, distinctive frontend implementation, and post-build interface review into one self-contained workflow.

This skill learned from:
- `frontend-design`
- `ui-ux-pro-max`
- `web-design-guidelines`

It does not require those skills to be installed. Use the bundled reference in `references/ui-frontend-playbook.md` when you need detailed rules.

## Core Workflow

### 1. Design

Before implementation, identify:
- product type and target users
- primary workflow and first-screen goal
- information hierarchy
- visual direction
- design-system constraints
- accessibility and responsive requirements

Choose a deliberate visual direction that fits the domain. Operational tools should feel dense, clear, and efficient. Editorial, brand, game, or creative experiences may be more expressive.

### 2. Implement

Build the actual usable interface, not a marketing placeholder, unless the user explicitly asks for a landing page.

Prefer the existing project stack, components, icons, design tokens, and patterns. Keep changes scoped. Add states that users naturally expect: loading, empty, error, disabled, hover/focus, mobile, and reduced-motion where relevant.

For frontend applications, verify visually when possible with the available local browser or screenshot tools.

### 3. Review

After implementation or when reviewing existing UI, check:
- accessibility
- semantic HTML and ARIA
- keyboard and focus behavior
- color contrast
- responsive layout
- touch target sizing
- form and feedback states
- motion and reduced-motion
- layout stability
- performance-sensitive UI patterns

Findings should lead when the user asks for review. Fix issues when the request is implementation-oriented or when the fix is clearly within scope.

## When To Ask A Question

Ask only when a missing decision would materially change the product, brand, target platform, or implementation stack. Otherwise make a conservative, project-consistent choice and proceed.

## Reference Loading

Read `references/ui-frontend-playbook.md` when:
- creating a new page, component, app, or design system
- polishing a UI
- auditing UI quality
- deciding between visual directions
- checking accessibility or responsive behavior

## License And Attribution

This skill includes attribution and license preservation notes in `THIRD_PARTY_NOTICES.md`.

Bundled license copies:
- `licenses/frontend-design-LICENSE.txt`
- `licenses/ui-ux-pro-max-LICENSE.txt`

The `web-design-guidelines` source directory in this workspace did not include a separate license file; source attribution is preserved in the notices file.

## Common Mistakes

- Treating UI work as only CSS styling while ignoring workflow, hierarchy, and states.
- Building a landing page when the user asked for an app, tool, or usable interface.
- Making bold visuals that conflict with the product's actual workflow.
- Calling something reviewed without checking accessibility, responsive behavior, and interaction states.
- Depending on external skills or remote guideline fetches for this skill to work.
