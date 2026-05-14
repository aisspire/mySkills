# UI Frontend Playbook

## Purpose

This reference is the self-contained operating manual for `ui-frontend-workflow`. It distills design planning, frontend implementation, and web interface review into one portable workflow.

## Fast Routing

Use the whole workflow when the user asks to build, redesign, polish, improve, or review UI.

If the request is only:
- design advice: complete Design and Handoff Notes
- implementation: complete Design briefly, then Implement and Review
- review: complete Review first, then recommend fixes
- fix UI bug: identify the broken state, patch it, then run a focused Review

## Phase 1: Design

### Product Fit

Classify the product before choosing visuals:

| Product type | Design posture |
| --- | --- |
| SaaS, CRM, admin, ops tools | quiet, dense, scannable, predictable |
| ecommerce | product-first, trust-building, fast comparison |
| dashboard/data | hierarchy, density control, chart clarity |
| portfolio/editorial | expressive composition, strong typography |
| game/creative toy | playful, animated, immersive |
| mobile utility | direct, thumb-friendly, minimal friction |

### Design Brief

Capture:
- user and job-to-be-done
- primary screen goal
- secondary actions
- navigation model
- content density
- visual tone
- typography direction
- color role system
- motion rules
- accessibility constraints

### Visual Direction

Choose one clear direction and execute it consistently:
- refined minimal
- utilitarian professional
- editorial
- playful
- luxury
- industrial
- brutalist
- retro-futuristic
- warm human
- high-density analytical

Avoid generic UI defaults:
- anonymous purple-blue gradients
- repeated card-only layouts
- placeholder hero sections
- decorative blobs/orbs
- oversized marketing composition for internal tools
- emojis as structural icons

### Design System

Prefer semantic tokens:
- `surface`
- `surface-muted`
- `text-primary`
- `text-secondary`
- `border`
- `primary`
- `danger`
- `success`
- `warning`
- `focus`

Use component states:
- default
- hover
- active
- focus-visible
- disabled
- loading
- selected
- error
- empty

## Phase 2: Implement

### Project Fit

Before editing:
- inspect existing stack and component patterns
- reuse local UI components, icons, and helpers
- keep changes scoped to requested behavior
- avoid adding dependencies unless clearly needed

### Required UI States

Add states users expect:
- loading or skeleton for async content
- empty state with a next action
- error state with recovery path
- disabled state with semantic disabled attributes
- focus-visible state for keyboard users
- responsive layout at mobile and desktop sizes

### Layout Rules

- Use stable dimensions for fixed-format elements.
- Reserve image/video/chart space with width/height or aspect ratio.
- Avoid horizontal scrolling on mobile.
- Keep buttons and controls large enough for touch.
- Keep text inside its container; wrap before truncating.
- Use predictable spacing scales.
- Do not nest cards inside cards unless the inner card is a repeated item or modal-like object.

### Typography

- Use hierarchy through size, weight, spacing, and contrast.
- Body text should remain readable on mobile.
- Avoid negative letter spacing.
- Use tabular numbers for metrics, prices, timers, and tables.
- Reserve huge display type for true heroes, not dense tool panels.

### Color

- Use semantic color roles instead of random raw values.
- Check contrast for text and icons.
- Do not rely on color alone for errors, success, or chart meaning.
- Avoid one-note palettes dominated by one hue unless the brand requires it.

### Motion

- Use motion to explain cause and effect.
- Prefer transform and opacity.
- Keep micro-interactions responsive.
- Respect reduced-motion.
- Do not block user input during animation.

### Assets

Use real, generated, or locally appropriate visual assets when a site, app, game, or visual experience needs them. Primary media should reveal the actual product, place, object, state, gameplay, or person when relevant.

## Phase 3: Review

Findings should be concrete. For code review, cite file and line when possible.

### Accessibility

Check:
- semantic controls for actions
- labels for inputs
- accessible names for icon-only buttons
- visible focus indicators
- keyboard navigation
- modal focus management
- ARIA only when semantic HTML is insufficient
- alt text for meaningful images
- reduced-motion support

### Interaction

Check:
- hover is not the only way to discover or use functionality
- buttons show pressed/loading/disabled feedback
- destructive actions are separated and confirmed when needed
- form errors appear near fields and explain recovery
- toast/alert messages do not steal focus unnecessarily
- primary action is visually clear

### Responsive

Check:
- no unintended horizontal scroll
- mobile content priority is sensible
- fixed headers/footers do not cover content
- text wraps cleanly
- controls remain usable on small screens
- large screens do not create unreadable line lengths

### Visual Quality

Check:
- consistent icon family and stroke style
- aligned baselines and spacing
- purposeful shadows/elevation
- no awkward text overflow
- no incoherent overlaps
- no placeholder imagery in production-facing UI
- visual density matches the domain

### Performance-Sensitive UI

Check:
- image dimensions or aspect ratios prevent layout shift
- heavy media is lazy-loaded when below the fold
- lists with many rows are virtualized or paginated when needed
- animations avoid layout thrashing
- third-party embeds/scripts are justified

## Output Patterns

### For Build Requests

Report:
- what was built
- key files changed
- verification performed
- remaining risks

### For Review Requests

Lead with findings:

```text
path/to/file.tsx:42 [P1] Icon-only button has no accessible name. Add visible text or aria-label.
```

Then include:
- open questions
- brief summary
- verification gaps

### For Design-Only Requests

Return:
- design direction
- information architecture
- visual system
- interaction notes
- implementation handoff
- review checklist

## Verification

Before claiming completion:
- run the project's relevant checks when available
- inspect the UI visually when practical
- mention exactly what was and was not verified

Do not claim guideline compliance without evidence.
