---
name: building-review-design-agent-v2
description: Use when work touches the Review Design Agent Streamlit V2, including new pages or features, UI redesign, authentication, Supabase data, migration, providers, historical artifacts, tests, or Streamlit Cloud deployment.
---

# Building Review Design Agent V2

Use this Skill to create, extend, repair, verify, or deploy the private V2 without regressing the original website or losing historical capabilities.

## Read Before Editing

1. Read [references/project-contract.md](references/project-contract.md) for current invariants and authoritative paths.
2. Read [references/workflow.md](references/workflow.md) for the end-to-end creation and extension process.
3. Read [references/verification.md](references/verification.md) before choosing tests or claiming completion.
4. For parity, architecture, data, or security changes, also read `../docs/superpowers/specs/2026-07-16-review-design-agent-v2-design.md`.
5. Inspect `git status` and preserve all pre-existing user changes and untracked files.

## Non-Negotiable Contract

- Keep `app.py`, `app_legacy_current.py`, and `pages/` unchanged unless the user explicitly authorizes an original-site change.
- Keep V2 at `v2/app.py`, with a separate Streamlit app URL, `agent_v2` schema, private artifact storage, and fixed server-side owner.
- Keep single-user Secrets-based login. Do not invent Supabase Auth, registration, tenants, or client-side service keys.
- Preserve every existing result, effect image, download, history path, the 10 legacy stages, and the 7 V2 stage groups.
- Treat migration as an explicit, idempotent copy: dry-run, confirm, apply, count, and hash-check. Never mutate the source.
- Put credentials only in server-side Secrets. Mask configuration status and sanitize errors.
- Keep the sidebar shortcut for the DashScope image key, but render only a placeholder template that directs the owner to Streamlit Secrets; never accept or persist the key in a page field.
- Keep page switching fast: load the workspace progress counters in one query, reuse read-only view data for 30 seconds, invalidate the private scope immediately after every write, and serve the visual shell from the optimized WebP runtime assets instead of re-sending multi-megabyte PNG data URIs.
- Require explicit confirmation for deletion, migration writes, archive restore, and paid image generation.

## Execution Workflow

1. Establish a baseline: identify affected user journeys, current tests, persisted records, artifacts, and visual states.
2. Write the smallest failing test before implementation. For UI work, define the browser state and viewport that currently fails.
3. Change the narrowest V2 layer: UI → application use case → adapter/provider. Keep SQL, deletion, and external API calls out of UI code.
4. For schema or migration changes, use additive numbered migrations, fixed `owner_id`, parameterized SQL, RLS/revokes, idempotency, and rollback-safe deployment order.
5. For visual changes, retain the supplied dark control-console direction, real raster assets, mobile behavior, readable focus states, populated/empty/error states, and matching dark styles for upload, download, link, password-toggle, primary, secondary, hover and disabled controls.
6. Run targeted tests, the contract verifier, the full regression suite, and browser/visual checks proportional to the change.
7. Re-open the original site after V2 verification and confirm its protected hashes and primary journey still pass.

## Keep This Skill Synchronized

Any addition, removal, rename, or behavior change under `v2/`, `tests/v2/`, V2 migrations, V2 deployment configuration, or V2 QA must update this Skill in the same task.

- Update `references/project-contract.md` when paths, capabilities, stages, data, auth, providers, or invariants change.
- Update `references/workflow.md` when the implementation or release sequence changes.
- Update `references/verification.md` and `scripts/verify_contract.py` when commands, tests, gates, or expected counts change.
- Update this file and `agents/openai.yaml` when trigger conditions or the Skill’s scope change.
- Run `python building-review-design-agent-v2/scripts/verify_contract.py --repo-root . --run-all-tests` after synchronization.

The repository-level `../AGENTS.md` makes this synchronization rule mandatory for future Codex work.

## Finish With Evidence

Report changed files, tests run with exact results, browser states checked, data migration status, deployment status, and any action that still requires credentials or user-owned cloud access. Never report a production migration or deployment as complete without direct evidence.
