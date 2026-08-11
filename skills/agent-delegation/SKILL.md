---
name: agent-delegation
description: "Use when the primary agent must decide whether to delegate via the Task tool, which subagent id to call, and how to keep child-session prompts small. Use when multiple subagents could apply, or before large read-only review, verification, security review, or external doc research."
---

# Subagent delegation (OpenCode)

Must respect `permission.task` in the active primary agent's frontmatter (`agents/<id>.md` — `build` vs `plan` vs `orchestrator` have different allowlists). The `plan` agent cannot invoke `test-verifier`, `code-reviewer`, `security-reviewer`, or `docs-reviewer` via Task. The `plan` agent **may** invoke `host-security-investigator` when it appears in `permission.task` (read-only hosting and service investigation). The **`orchestrator`** agent drives Task `plan-runner`, `code-executor`, and the usual reviewers per its prompt; it does not implement code directly.

- Always spawn the subagents respecting the models defined for each one.
- Use `code-explorer` for reading and exploring codebase files, architecture mapping, and symbol location. This is the dedicated read-only exploration agent.
- Use `explore` for fast read-only codebase discovery when `code-explorer` is unnecessary (built-in platform agent), but **not from `orchestrator`**. The `orchestrator` agent's repo-discovery path is always `code-explorer`.
- Use `code-executor` for implementing and writing code. This agent writes only — delegate exploration to `code-explorer` first when needed.
- Use `spec-critic` before implementation when the task is ambiguous, architectural, or spans multiple modules.
- Use `api-docs-researcher` before coding against third-party APIs, SDKs, migrations, or recent framework behavior.
- Use `test-verifier` after implementation.
- Use `security-reviewer` when auth, secrets, file handling, shell execution, external input, network calls, permissions, or multi-tenant logic are involved.
- Use `host-security-investigator` when you need a read-only assessment of hosting posture, exposed services, TLS, SSH access patterns, containers, or infrastructure-as-code (not for code-reviewing application logic).
- Use `code-reviewer` before finalizing any meaningful diff. This agent reviews only — it does not write or explore.
- Use `docs-reviewer` when user-facing behavior, config, env vars, CLI, API shape, or setup steps changed.

## Gold rule: minimal child prompt

Every Task invocation should include:

1. **Goal** in one or two sentences.
2. **Scope**: exact paths, commit/diff, or “read-only” constraints already known to the parent.
3. **Expected return shape**: use the numbered sections that agent’s system prompt requires (e.g. blocking vs non-blocking lists).

Do not paste the entire parent conversation into the subagent unless necessary.

## When not to delegate

- Single trivial edit or one obvious tool call.
- User asked explicitly for a single-thread reply.
- Subagent is denied for the current primary (`permission.task`).

For `orchestrator`, "do not delegate" never means "inspect or edit repo files directly." If a trivial request needs direct coding, switch to `build`; if it needs repo facts, delegate to `code-explorer`.

## Anti-patterns (avoid)

- Do **not** call `code-reviewer` until there is a **stable diff** (known paths / commit / clear scope); reviewing “what we might do” wastes context.
- Do **not** call `test-verifier` without **repo root**, **expected commands** (or confirmation to discover them from project docs), and **what “done” means** (acceptance criteria).
- Do **not** chain multiple heavy subagents in parallel on the same prompt without a reason; finish one feedback cycle first.
- Do **not** use long `@` lists for subagents that are **`hidden: true`**; use **Task** instead so permissions and tool contracts stay clear.

## Definitions location

Global defaults live under `~/.config/opencode/agents/<id>.md`. Project overrides: `.opencode/agents/<id>.md`.
