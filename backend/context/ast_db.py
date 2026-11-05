"""
ast_db.py  –  Day 4 + Day 5 update: SQLite schema for DevSwarm Local.

Creates three tables:
  tasks      – one row per coding task the orchestrator is working on
  thoughts   – one row per "explanation" an agent produces (planner/coder/reviewer)
  telemetry  – one row per task run, storing token counts and execution time

Schema updated to match backend/schemas.py:
  thoughts now stores step_number and why_this_decision from ExplainabilityLog.
  tasks now stores risk_score from ReviewerVerdict.

We use only the Python standard library (sqlite3, pathlib).
No log_thought() or get_task_history() yet – those are Week 2.
"""

import sqlite3          # Built-in Python module for SQLite databases
import sys              # Read command-line arguments in __main__
from pathlib import Path  # Clean path handling


# ---------------------------------------------------------------------------
# SECTION 1  –  get_connection  (helper used by init_db and by tests)
# ---------------------------------------------------------------------------

def get_connection(db_path="devswarm.db"):
    """Open a SQLite connection to *db_path* and enable foreign-key enforcement.

    SQLite does NOT enforce foreign keys by default; we must run this PRAGMA
    on every new connection or INSERT/UPDATE violations are silently ignored.
    Returning the connection object lets callers use it in a 'with' block.
    """
    # isolation_level=None would auto-commit; we leave it at the default so
    # we control commits manually with conn.commit().
    conn = sqlite3.connect(db_path)

    # PRAGMA foreign_keys = ON must be re-issued every time we open a connection
    # because SQLite resets it to OFF for each new connection by default.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# ---------------------------------------------------------------------------
# SECTION 2  –  init_db
# ---------------------------------------------------------------------------

def init_db(db_path="devswarm.db"):
    """Create the DevSwarm database schema if it does not already exist.

    Uses CREATE TABLE IF NOT EXISTS so running this twice is safe (idempotent).
    Foreign-key constraints and CHECK constraints are enforced at the DB level
    so invalid data is rejected even if the Python code has a bug.
    """

    # We open the connection, do all our work, then close it explicitly.
    # We do NOT use 'with conn:' here because sqlite3's context manager only
    # manages transactions (commit/rollback) – it does NOT close the connection.
    # On Windows, an unclosed connection keeps a file lock, which prevents
    # other code (such as tests) from deleting the temp database file.
    conn = get_connection(db_path)
    try:

        # ------------------------------------------------------------------
        # TABLE: tasks
        # Each row represents one coding task handed to the agent pipeline.
        #
        # Columns that map to schemas.py:
        #   id          – matches SubTask.task_id (the identifier used everywhere)
        #   description – matches SubTask.description
        #   status      – not in schemas.py; tracks pipeline progress
        #   branch_name – the git worktree branch for this task
        #   risk_score  – matches ReviewerVerdict.risk_score; nullable because it
        #                 is only filled in after the reviewer agent has run
        #   created_at  – auto-filled by SQLite using CURRENT_TIMESTAMP
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'queued'
                            CHECK(status IN (
                                'queued',
                                'coding',
                                'testing',
                                'review',
                                'ready_to_merge',
                                'needs_human_help'
                            )),
                branch_name TEXT,
                risk_score  TEXT
                            CHECK(risk_score IN ('LOW', 'MEDIUM', 'HIGH')
                                  OR risk_score IS NULL),
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ------------------------------------------------------------------
        # TABLE: thoughts
        # Each row is one "explainability" entry from an agent.
        #
        # Columns that map to schemas.py ExplainabilityLog:
        #   step_number       – ExplainabilityLog.step_number (which coding step
        #                       this thought belongs to; INTEGER, nullable for
        #                       planner/reviewer thoughts that have no step number)
        #   explanation       – ExplainabilityLog.human_explanation: the plain-
        #                       English sentence a human can read and understand
        #   why_this_decision – ExplainabilityLog.why_this_decision: the technical
        #                       reasoning behind the agent's choice
        #
        # Other columns:
        #   task_id    – foreign key to tasks.id; matches SubTask.task_id
        #   agent_role – which pipeline agent wrote this thought.
        #                Values: 'planner', 'coder', 'reviewer' – these map to
        #                AgentOrchestrator.run_planner/run_coder/run_reviewer.
        #                NOTE: schemas.py's SubTask.role ('BACKEND_DATA',
        #                'FRONTEND_UI') is a *task-assignment* role, not an
        #                agent-pipeline stage – so agent_role uses different values.
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thoughts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id           TEXT NOT NULL
                                  REFERENCES tasks(id),
                agent_role        TEXT NOT NULL
                                  CHECK(agent_role IN ('planner', 'coder', 'reviewer')),
                step_number       INTEGER,
                explanation       TEXT NOT NULL,
                why_this_decision TEXT,
                created_at        TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ------------------------------------------------------------------
        # TABLE: telemetry
        # Stores token-count and timing data for a task run.
        # Populated from compression_stats() and execution timing in Week 2.
        #
        # Columns:
        #   tokens_before      – raw source token estimate (from skeletonizer)
        #   tokens_after       – skeleton token estimate (from skeletonizer)
        #   execution_seconds  – how long the pipeline took (REAL = float)
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id            TEXT NOT NULL
                                   REFERENCES tasks(id),
                tokens_before      INTEGER,
                tokens_after       INTEGER,
                execution_seconds  REAL,
                created_at         TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ------------------------------------------------------------------
        # INDEXES
        # An index lets SQLite find all thoughts/telemetry rows for a given
        # task_id quickly without scanning the whole table.
        # IF NOT EXISTS makes this safe to run more than once.
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thoughts_task_id
            ON thoughts(task_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_task_id
            ON telemetry(task_id)
        """)

        # Commit all the CREATE TABLE and CREATE INDEX statements at once.
        conn.commit()
    finally:
        # Explicitly close the connection so Windows releases the file lock.
        # This matters in tests where we delete the temp DB right after init_db().
        conn.close()

    # Return nothing – the caller only needs the side-effect of the DB existing.


# ---------------------------------------------------------------------------
# SECTION 3  –  __main__ block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Allow an optional path argument so tests can point to a temp file.
    db_path = sys.argv[1] if len(sys.argv) > 1 else "devswarm.db"

    print(f"Initialising database: {db_path}")
    init_db(db_path)

    # Open a fresh connection to verify what was created.
    conn = get_connection(db_path)

    # Print all objects (tables + indexes) so we can see they exist.
    rows = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','index') ORDER BY name"
    ).fetchall()
    print("\nObjects created:")
    for name, kind in rows:
        print(f"  [{kind}] {name}")

    # Print the full CREATE TABLE SQL for tasks and thoughts so the developer
    # can verify the new columns are present without opening an external tool.
    print("\n--- CREATE TABLE: tasks ---")
    sql_tasks = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()[0]
    print(sql_tasks)

    print("\n--- CREATE TABLE: thoughts ---")
    sql_thoughts = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='thoughts'"
    ).fetchone()[0]
    print(sql_thoughts)

    conn.close()
