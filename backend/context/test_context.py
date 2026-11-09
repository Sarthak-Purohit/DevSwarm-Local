"""
test_context.py  –  Days 5 + schema-update + Day 6: tests for skeletonizer.py and ast_db.py.

Runs under pytest OR plain python3.15 (a minimal runner is at the bottom).
Every test uses a temporary database file so no devswarm.db is left behind.

Windows note: sqlite3's 'with conn:' block only manages transactions, NOT the
connection lifetime.  We therefore call conn.close() explicitly before deleting
any temp file, because Windows raises PermissionError if you try to delete a
file that is still held open by the process.
"""

import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure Python can find sibling modules when run as a plain script.
# sys.path.insert puts our folder first so "import skeletonizer" works from
# any working directory (not just backend/context/).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from skeletonizer import (
    skeleton_of_file, skeleton_of_folder, estimate_tokens,
    compression_stats, get_repo_summary,
)
from ast_db import init_db, get_connection

# Absolute path to the sample file sitting next to this test file.
SAMPLE = Path(__file__).parent / "sample_for_testing.py"
# Absolute path to the backend folder (one level above context/).
BACKEND = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Shared helper: create a temp DB path and a cleanup function.
# ---------------------------------------------------------------------------

def _temp_db_path():
    """Create an empty temp file, release its OS handle, and return the path.

    tempfile.mkstemp() gives us an open file descriptor (fd).  We close it
    immediately with os.close() so that SQLite can open the same path.
    If we skipped os.close(), Windows would raise PermissionError when
    sqlite3.connect() tries to open the file (Windows does not allow two
    processes to hold exclusive handles on the same file simultaneously).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    # Release the Windows file-descriptor lock before returning.
    os.close(fd)
    return path


def _remove_db(path):
    """Delete the temp file, ignoring errors if it is already gone."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


# ===========================================================================
# TEST a  –  skeleton_of_file on sample_for_testing.py
# ===========================================================================

def test_skeleton_of_file_contains_divide():
    """skeleton_of_file must include the exact signature for 'divide'."""
    result = skeleton_of_file(SAMPLE)
    # ast.unparse omits the space around '=' in annotated defaults, giving
    # 'b: float=1.0' (no spaces).  We test the exact string the tool prints.
    assert "def divide(self, a: float, b: float=1.0) -> float: ..." in result, (
        f"Expected signature not found in skeleton:\n{result}"
    )


def test_skeleton_of_file_no_body():
    """skeleton_of_file must NOT include any function body code."""
    result = skeleton_of_file(SAMPLE)
    # 'ValueError' lives inside the divide() body – the skeleton must hide it.
    assert "ValueError" not in result, "Function body leaked into skeleton output."


# ===========================================================================
# TEST b  –  skeleton_of_folder skip behaviour and error handling
# ===========================================================================

def test_skeleton_of_folder_skips_pycache():
    """Files inside __pycache__ must be silently skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good = tmp / "good.py"
        good.write_text("def hello(): pass\n", encoding="utf-8")

        # Create a __pycache__ sub-directory with a .py file inside.
        cache_dir = tmp / "__pycache__"
        cache_dir.mkdir()
        hidden = cache_dir / "hidden.py"
        hidden.write_text("def secret(): pass\n", encoding="utf-8")

        result = skeleton_of_folder(tmp)

        assert "good.py" in result, "Expected good.py to appear in skeleton."
        assert "hidden.py" not in result, "__pycache__ file leaked into skeleton."


def test_skeleton_of_folder_skips_venv():
    """Files inside a venv folder must also be silently skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good = tmp / "real.py"
        good.write_text("def real(): pass\n", encoding="utf-8")

        venv_dir = tmp / "venv"
        venv_dir.mkdir()
        vendor = venv_dir / "vendor.py"
        vendor.write_text("def vendor(): pass\n", encoding="utf-8")

        result = skeleton_of_folder(tmp)
        assert "real.py" in result
        assert "vendor.py" not in result, "venv file leaked into skeleton."


def test_skeleton_of_folder_handles_syntax_error():
    """A file with invalid Python syntax must produce '(could not parse)'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        broken = tmp / "broken.py"
        # 'def broken(:' is a deliberate SyntaxError.
        broken.write_text("def broken(:\n", encoding="utf-8")

        result = skeleton_of_folder(tmp)
        assert "broken.py" in result, "Header for broken file missing."
        assert "(could not parse)" in result, "Error message missing for broken file."


# ===========================================================================
# TEST c  –  estimate_tokens
# ===========================================================================

def test_estimate_tokens():
    """estimate_tokens must return len(text) // 4."""
    # "abcd" * 10 = 40 characters; 40 // 4 = 10.
    assert estimate_tokens("abcd" * 10) == 10


# ===========================================================================
# TEST d  –  init_db creates exactly the three expected tables
# ===========================================================================

def test_init_db_creates_tables():
    """init_db must create tasks, thoughts, and telemetry – nothing more."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        # Open, query, then CLOSE before we try to delete the file.
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        # Explicit close is required on Windows to release the file lock.
        conn.close()

        table_names = {row[0] for row in rows}
        # Exclude ALL internal SQLite tables (names starting with "sqlite_").
        # SQLite creates sqlite_sequence automatically whenever any table uses
        # AUTOINCREMENT, and may add other sqlite_* tables in future versions.
        # Filtering by prefix is more robust than discarding specific names.
        table_names = {n for n in table_names if not n.startswith("sqlite_")}

        assert table_names == {"tasks", "thoughts", "telemetry"}, (
            f"Unexpected tables: {table_names}"
        )
    finally:
        _remove_db(db_path)


# ===========================================================================
# TEST e  –  foreign-key violation raises IntegrityError
# ===========================================================================

def test_thought_requires_valid_task():
    """Inserting a thought for a non-existent task_id must raise IntegrityError."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        raised = False
        conn = get_connection(db_path)
        try:
            # task_id 'nonexistent' does not exist in tasks – must fail.
            conn.execute(
                "INSERT INTO thoughts (task_id, agent_role, explanation) VALUES (?, ?, ?)",
                ("nonexistent", "planner", "This should fail.")
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # This is exactly what we expect – the foreign-key check fired.
            raised = True
        finally:
            # Always close so the file lock is released before _remove_db().
            conn.close()

        assert raised, "Expected IntegrityError for missing task_id was not raised."
    finally:
        _remove_db(db_path)


# ===========================================================================
# TEST f  –  CHECK constraint rejects invalid status
# ===========================================================================

def test_invalid_status_rejected():
    """Inserting a task with status 'banana' must raise IntegrityError."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        raised = False
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO tasks (id, description, status) VALUES (?, ?, ?)",
                ("t1", "Some task", "banana")
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raised = True
        finally:
            conn.close()

        assert raised, "Expected IntegrityError for invalid status was not raised."
    finally:
        _remove_db(db_path)


# ===========================================================================
# TEST g  –  chain test: compression_stats -> insert telemetry -> read back
# ===========================================================================

def test_chain_stats_to_telemetry():
    """Run compression_stats on backend folder, store results, and read them back."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        # Get real stats from the backend folder.
        stats = compression_stats(BACKEND)

        # Confirm the skeletonizer is actually compressing something.
        assert stats["tokens_before"] > stats["tokens_after"], (
            "tokens_before should be greater than tokens_after for a real codebase."
        )

        # --- INSERT ---
        conn = get_connection(db_path)
        # Insert a parent task row first (required by the foreign key).
        conn.execute(
            "INSERT INTO tasks (id, description, status) VALUES (?, ?, ?)",
            ("task-chain-test", "Chain test task", "queued")
        )
        # We use ? placeholders – never string formatting – to prevent SQL injection.
        conn.execute(
            "INSERT INTO telemetry (task_id, tokens_before, tokens_after, execution_seconds)"
            " VALUES (?, ?, ?, ?)",
            ("task-chain-test", stats["tokens_before"], stats["tokens_after"], 0.0)
        )
        conn.commit()
        # Close before opening a second connection (also good practice).
        conn.close()

        # --- READ BACK ---
        conn2 = get_connection(db_path)
        row = conn2.execute(
            "SELECT tokens_before, tokens_after FROM telemetry WHERE task_id = ?",
            ("task-chain-test",)
        ).fetchone()
        conn2.close()

        assert row is not None, "Telemetry row not found after insert."
        tokens_before_db, tokens_after_db = row
        assert tokens_before_db > tokens_after_db, (
            "tokens_before must be greater than tokens_after in the database row."
        )
    finally:
        _remove_db(db_path)


# ===========================================================================
# TEST h  –  thoughts: step_number and why_this_decision round-trip
# ===========================================================================

def test_thought_step_number_and_why_saves_correctly():
    """step_number and why_this_decision must survive an INSERT → SELECT round-trip."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        conn = get_connection(db_path)
        # Insert the parent task first (foreign-key requirement).
        conn.execute(
            "INSERT INTO tasks (id, description, status) VALUES (?, ?, ?)",
            ("task-thought-test", "Thought round-trip task", "coding")
        )
        # Insert a coder thought with all three ExplainabilityLog fields.
        # We use ? placeholders – never string formatting – to prevent SQL injection.
        conn.execute(
            "INSERT INTO thoughts"
            " (task_id, agent_role, step_number, explanation, why_this_decision)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                "task-thought-test",
                "coder",
                3,                              # step_number  → ExplainabilityLog.step_number
                "Write the divide method.",     # explanation  → ExplainabilityLog.human_explanation
                "Chosen because it handles zero-division cleanly.",  # why_this_decision
            )
        )
        conn.commit()
        conn.close()

        # Read back the row and verify every field survived the round-trip.
        conn2 = get_connection(db_path)
        row = conn2.execute(
            "SELECT step_number, explanation, why_this_decision"
            " FROM thoughts WHERE task_id = ?",
            ("task-thought-test",)
        ).fetchone()
        conn2.close()

        assert row is not None, "Thought row not found after insert."
        step, expl, why = row
        assert step == 3, f"step_number mismatch: expected 3, got {step}"
        assert expl == "Write the divide method."
        assert why == "Chosen because it handles zero-division cleanly."
    finally:
        _remove_db(db_path)


# ===========================================================================
# TEST i  –  tasks: risk_score CHECK constraint
# ===========================================================================

def test_risk_score_check_constraint():
    """'EXTREME' must be rejected; 'HIGH' and NULL must be accepted."""
    db_path = _temp_db_path()
    try:
        init_db(db_path)

        # --- 'EXTREME' must be REJECTED ---
        raised = False
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO tasks (id, description, risk_score) VALUES (?, ?, ?)",
                ("t-extreme", "Bad risk", "EXTREME")
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # CHECK constraint fired – this is the correct behaviour.
            raised = True
        finally:
            conn.close()

        assert raised, "Expected IntegrityError for risk_score='EXTREME' was not raised."

        # --- 'HIGH' must be ACCEPTED ---
        conn2 = get_connection(db_path)
        conn2.execute(
            "INSERT INTO tasks (id, description, risk_score) VALUES (?, ?, ?)",
            ("t-high", "High-risk task", "HIGH")
        )
        conn2.commit()

        # Read back to confirm it was stored correctly.
        row = conn2.execute(
            "SELECT risk_score FROM tasks WHERE id = ?",
            ("t-high",)
        ).fetchone()
        conn2.close()

        assert row is not None, "High-risk task row not found."
        assert row[0] == "HIGH", f"risk_score mismatch: expected 'HIGH', got {row[0]}"

        # --- NULL must also be ACCEPTED (risk_score is nullable) ---
        conn3 = get_connection(db_path)
        conn3.execute(
            "INSERT INTO tasks (id, description) VALUES (?, ?)",
            ("t-null-risk", "No risk yet")
            # risk_score intentionally omitted → defaults to NULL
        )
        conn3.commit()
        row2 = conn3.execute(
            "SELECT risk_score FROM tasks WHERE id = ?",
            ("t-null-risk",)
        ).fetchone()
        conn3.close()

        assert row2 is not None, "Null-risk task row not found."
        assert row2[0] is None, f"risk_score should be NULL, got {row2[0]}"
    finally:
        _remove_db(db_path)


# ===========================================================================
# TESTS j-m  –  get_repo_summary  (Day 6)
# ===========================================================================

def test_get_repo_summary_returns_all_six_keys():
    """get_repo_summary on a temp folder with one .py file returns all six keys."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Create a minimal .py file so the folder is not completely empty.
        (tmp / "hello.py").write_text("def hi(): pass\n", encoding="utf-8")

        result = get_repo_summary(tmp)

        # Check that every required key is present in the returned dict.
        expected_keys = {
            "summary", "files_scanned",
            "tokens_before", "tokens_after",
            "tokens_saved", "percent_saved",
        }
        assert set(result.keys()) == expected_keys, (
            f"Missing or extra keys: {set(result.keys())}"
        )


def test_get_repo_summary_missing_path_raises():
    """get_repo_summary must raise FileNotFoundError for a non-existent path."""
    raised = False
    try:
        # Use a path that certainly does not exist.
        get_repo_summary("/this/path/does/not/exist/at/all")
    except FileNotFoundError:
        # This is exactly what we expect.
        raised = True

    assert raised, "Expected FileNotFoundError was not raised for a missing path."


def test_get_repo_summary_tokens_after_less_than_before():
    """On the real backend folder, tokens_after < tokens_before and saved = before - after."""
    result = get_repo_summary(BACKEND)

    assert result["tokens_after"] < result["tokens_before"], (
        "Skeleton should be smaller than the original source."
    )
    # Verify the arithmetic is consistent – saved must equal before minus after.
    assert result["tokens_saved"] == result["tokens_before"] - result["tokens_after"], (
        "tokens_saved must equal tokens_before - tokens_after."
    )


def test_get_repo_summary_contains_class_calculator():
    """The summary for the context folder must mention 'class Calculator'."""
    # We scan only the context folder (which contains sample_for_testing.py)
    # so the test does not depend on other teammates' files.
    context_folder = Path(__file__).parent
    result = get_repo_summary(context_folder)

    assert "class Calculator" in result["summary"], (
        "Expected 'class Calculator' in summary – is sample_for_testing.py present?"
    )


# ===========================================================================
# Minimal test runner  –  works with plain "python3.15 test_context.py"
# ===========================================================================

if __name__ == "__main__":
    # globals() returns a dict of everything defined in this module.
    # We filter for callable functions whose names start with "test_".
    test_functions = [
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and isinstance(obj, types.FunctionType)
    ]

    passed = 0
    failed = 0

    for name, fn in test_functions:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {name}")
            print(f"        {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed.")
    # Exit with a non-zero code if any test failed, so CI can detect failures.
    sys.exit(1 if failed else 0)
