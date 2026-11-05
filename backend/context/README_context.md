# backend/context — Context, AST & Audit Database

## What each file does

| File | Purpose |
|------|---------|
| `skeletonizer.py` | Reads `.py` files and produces a compact **skeleton** (signatures + first docstring line only). Runs on a single file or an entire folder. |
| `ast_db.py` | Creates and owns the **SQLite schema** (`tasks`, `thoughts`, `telemetry`). Day 4/5 — no query helpers yet. |
| `test_context.py` | Assert-based tests. Runs with `pytest` **or** plain `python3.15 test_context.py`. |
| `sample_for_testing.py` | Tiny fixture file used by the skeletonizer tests. |

---

## How to run on Windows

```powershell
# Skeletonize a single file
python3.15 backend/context/skeletonizer.py backend/context/sample_for_testing.py

# Skeletonize an entire folder (shows stats too)
python3.15 backend/context/skeletonizer.py backend/

# Create / verify the database schema
python3.15 backend/context/ast_db.py

# Run the tests (plain Python)
python3.15 backend/context/test_context.py

# Run the tests with pytest (if installed)
pytest backend/context/test_context.py -v
```

---

## Table schemas

### `tasks`
| Column | Type | Notes | schemas.py field |
|--------|------|-------|-----------------|
| `id` | TEXT PK | Unique task identifier | `SubTask.task_id` |
| `description` | TEXT NOT NULL | What the task does | `SubTask.description` |
| `status` | TEXT NOT NULL | CHECK: `queued`, `coding`, `testing`, `review`, `ready_to_merge`, `needs_human_help` | *(pipeline-only, not in schemas.py)* |
| `branch_name` | TEXT | Git worktree branch for this task | *(pipeline-only)* |
| `risk_score` | TEXT nullable | CHECK: `LOW`, `MEDIUM`, `HIGH` or NULL. Set by the Reviewer agent after review. | `ReviewerVerdict.risk_score` |
| `created_at` | TEXT | SQLite `CURRENT_TIMESTAMP` default | *(pipeline-only)* |

### `thoughts`
| Column | Type | Notes | schemas.py field |
|--------|------|-------|-----------------|
| `id` | INTEGER PK AUTOINCREMENT | | |
| `task_id` | TEXT NOT NULL | FK → `tasks.id` | `SubTask.task_id` |
| `agent_role` | TEXT NOT NULL | CHECK: `planner`, `coder`, `reviewer` — maps to `AgentOrchestrator.run_*` methods. **Different** from `SubTask.role` (`BACKEND_DATA`/`FRONTEND_UI`), which is a task-assignment category. | *(pipeline stage, not directly in schemas.py)* |
| `step_number` | INTEGER | Which coding step this thought belongs to (nullable for planner/reviewer) | `ExplainabilityLog.step_number` |
| `explanation` | TEXT NOT NULL | Plain-English description a human can read | `ExplainabilityLog.human_explanation` |
| `why_this_decision` | TEXT | Technical reasoning behind the agent's choice | `ExplainabilityLog.why_this_decision` |
| `created_at` | TEXT | SQLite `CURRENT_TIMESTAMP` default | *(pipeline-only)* |

### `telemetry`
| Column | Type | Notes | schemas.py field |
|--------|------|-------|-----------------|
| `id` | INTEGER PK AUTOINCREMENT | | |
| `task_id` | TEXT NOT NULL | FK → `tasks.id` | `SubTask.task_id` |
| `tokens_before` | INTEGER | Raw source token estimate from `estimate_tokens()` | *(pipeline-only)* |
| `tokens_after` | INTEGER | Skeleton token estimate from `estimate_tokens()` | *(pipeline-only)* |
| `execution_seconds` | REAL | Pipeline wall-clock time (float) | *(pipeline-only)* |
| `created_at` | TEXT | SQLite `CURRENT_TIMESTAMP` default | *(pipeline-only)* |

> [!NOTE]
> `thoughts.agent_role` (`planner`/`coder`/`reviewer`) is **not** the same as
> `SubTask.role` (`BACKEND_DATA`/`FRONTEND_UI`).  `SubTask.role` is a task-assignment
> role set by the planner; `agent_role` identifies which pipeline stage produced a thought.

---

## Mapping: database columns ↔ schemas.py fields

| schemas.py class | schemas.py field | Table | Column |
|-----------------|-----------------|-------|--------|
| `SubTask` | `task_id` | `tasks` | `id` |
| `SubTask` | `description` | `tasks` | `description` |
| `ReviewerVerdict` | `risk_score` | `tasks` | `risk_score` |
| `SubTask` | `task_id` | `thoughts` | `task_id` |
| `ExplainabilityLog` | `step_number` | `thoughts` | `step_number` |
| `ExplainabilityLog` | `human_explanation` | `thoughts` | `explanation` |
| `ExplainabilityLog` | `why_this_decision` | `thoughts` | `why_this_decision` |

---

## Indexes
`idx_thoughts_task_id` on `thoughts(task_id)` and `idx_telemetry_task_id` on `telemetry(task_id)` — both created by `init_db()`.
