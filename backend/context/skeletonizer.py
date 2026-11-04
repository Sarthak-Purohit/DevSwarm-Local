"""
skeletonizer.py  –  Day 2 + Day 3.

Day 2: skeleton_node() and skeleton_of_file() produce a compact skeleton of ONE file.
Day 3: skeleton_of_folder(), estimate_tokens(), and compression_stats() extend this
       to an entire folder and report how many tokens the skeleton saves.

A skeleton keeps only class/function signatures and their first docstring line,
dropping every implementation body.  This lets an LLM understand a codebase's
public surface area without sending thousands of tokens of detail.
"""

import ast          # Built-in module: parse Python source into an Abstract Syntax Tree
import sys          # Read command-line arguments
from pathlib import Path  # Clean, OS-independent file/folder operations


# ---------------------------------------------------------------------------
# SECTION 1  –  skeleton_node  (Day 2, unchanged)
# ---------------------------------------------------------------------------

def skeleton_node(node, indent=0):
    """Return a list of skeleton lines for one AST node.

    indent  – how many nesting levels deep we are (each level = 4 spaces).
    """

    # Build the indentation string once so we don't repeat it everywhere.
    pad = "    " * indent

    # Collect output lines here; return this list at the end.
    lines = []

    # ------------------------------------------------------------------
    # CLASS
    # ------------------------------------------------------------------
    if isinstance(node, ast.ClassDef):
        lines.append(f"{pad}class {node.name}:")

        # ast.get_docstring() inspects the first statement of the node's body;
        # if it is a string literal it returns that text, otherwise returns None.
        doc = ast.get_docstring(node)
        if doc:
            # Only the first line of the docstring – keeps the skeleton short.
            first_line = doc.splitlines()[0]
            lines.append(f'{pad}    """{first_line}"""')

        # Recurse into the class body so methods appear indented under the class.
        # indent+1 adds one more level of padding for each child.
        for child in node.body:
            lines.extend(skeleton_node(child, indent + 1))

    # ------------------------------------------------------------------
    # FUNCTION  (sync)
    # ------------------------------------------------------------------
    elif isinstance(node, ast.FunctionDef):
        # ast.unparse() converts an AST fragment back to source-code text.
        # node.args is the arguments sub-tree, giving "self, a: float, b=1" etc.
        args_str = ast.unparse(node.args)

        # node.returns is None when there is no return annotation.
        if node.returns is not None:
            return_str = ast.unparse(node.returns)
            sig = f"{pad}def {node.name}({args_str}) -> {return_str}: ..."
        else:
            sig = f"{pad}def {node.name}({args_str}): ..."

        lines.append(sig)

        doc = ast.get_docstring(node)
        if doc:
            first_line = doc.splitlines()[0]
            lines.append(f'{pad}    """{first_line}"""')

    # ------------------------------------------------------------------
    # ASYNC FUNCTION
    # ------------------------------------------------------------------
    elif isinstance(node, ast.AsyncFunctionDef):
        # Same logic as FunctionDef above, just prefixed with "async ".
        args_str = ast.unparse(node.args)

        if node.returns is not None:
            return_str = ast.unparse(node.returns)
            sig = f"{pad}async def {node.name}({args_str}) -> {return_str}: ..."
        else:
            sig = f"{pad}async def {node.name}({args_str}): ..."

        lines.append(sig)

        doc = ast.get_docstring(node)
        if doc:
            first_line = doc.splitlines()[0]
            lines.append(f'{pad}    """{first_line}"""')

    # Everything else (imports, assignments, …) is silently ignored.

    return lines


# ---------------------------------------------------------------------------
# SECTION 2  –  skeleton_of_file  (Day 2, unchanged)
# ---------------------------------------------------------------------------

def skeleton_of_file(path):
    """Read *path*, parse it with ast, and return the full skeleton as a string."""

    # read_text() opens, reads, and closes the file in one call.
    source = Path(path).read_text(encoding="utf-8")

    # ast.parse() converts the source string to a Module node.
    # Module.body is a list of all top-level statements.
    tree = ast.parse(source)

    all_lines = []

    # Loop over top-level nodes only; recursion inside skeleton_node() handles
    # nested classes/functions.  We deliberately avoid ast.walk() here because
    # walk() visits every depth at once, destroying our indentation control.
    for node in tree.body:
        all_lines.extend(skeleton_node(node, indent=0))

    return "\n".join(all_lines)


# ---------------------------------------------------------------------------
# SECTION 3  –  _should_skip  (Day 3 helper)
# ---------------------------------------------------------------------------

# Folders we never want to scan: they contain generated/vendor/VCS content that
# would bloat the token count and confuse an LLM with irrelevant code.
_SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", "worktrees"}


def _should_skip(path, folder):
    """Return True if *path* is inside any of the skip directories."""

    # Path.relative_to() gives us just the parts underneath *folder*.
    # We then check whether any of those parts match a skip-directory name.
    relative = Path(path).relative_to(folder)

    # relative.parts is a tuple like ("backend", "context", "skeletonizer.py").
    # We use a set intersection to check if any part is a skip-dir name.
    return bool(set(relative.parts) & _SKIP_DIRS)


# ---------------------------------------------------------------------------
# SECTION 4  –  skeleton_of_folder  (Day 3)
# ---------------------------------------------------------------------------

def skeleton_of_folder(folder):
    """Return a single skeleton string covering all .py files under *folder*.

    Files are processed in sorted order so the output is stable (the same
    every run), making it easy to diff or cache.
    """

    folder = Path(folder)

    # rglob("*.py") walks the entire directory tree and yields every .py file.
    # sorted() makes the order deterministic (alphabetical by full path).
    py_files = sorted(folder.rglob("*.py"))

    sections = []   # Each element will be the text block for one file.

    for py_file in py_files:
        # Skip files that live inside noise directories.
        if _should_skip(py_file, folder):
            continue

        # The header shows the path relative to the folder root – this is
        # more readable than a full absolute path in the skeleton output.
        rel = py_file.relative_to(folder)
        header = f"# {rel}"

        try:
            body = skeleton_of_file(py_file)
            # If the file has no classes/functions, body is an empty string.
            # We still emit the header so the reader knows the file exists.
            sections.append(f"{header}\n{body}" if body else header)

        except (SyntaxError, UnicodeDecodeError):
            # We catch only the two errors we expect from bad source files.
            # Any other exception (e.g., PermissionError) is intentionally
            # allowed to propagate so we don't silently swallow real problems.
            sections.append(f"{header}\n# (could not parse)")

    # Separate file blocks with a blank line so the output is easy to read.
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# SECTION 5  –  estimate_tokens  (Day 3)
# ---------------------------------------------------------------------------

def estimate_tokens(text):
    """Return a rough token count for *text*.

    Rule of thumb: 1 token ≈ 4 characters for English/code text.
    This is NOT an exact tokenizer – real tokenizers (like tiktoken) split
    on subword boundaries and give different counts, but dividing by 4
    is fast, dependency-free, and accurate enough for order-of-magnitude
    comparisons.
    """
    # Integer division by 4: cheap and requires no third-party library.
    return len(text) // 4


# ---------------------------------------------------------------------------
# SECTION 6  –  compression_stats  (Day 3)
# ---------------------------------------------------------------------------

def compression_stats(folder):
    """Return a dict describing how much the skeleton compresses *folder*.

    Keys
    ----
    tokens_before  – estimated tokens across all original .py source files
    tokens_after   – estimated tokens of the combined skeleton text
    tokens_saved   – tokens_before minus tokens_after
    percent_saved  – percentage saved, rounded to 1 decimal place
    files_scanned  – number of .py files that were processed
    """

    folder = Path(folder)

    # Gather all non-skipped .py files (same rules as skeleton_of_folder).
    py_files = sorted(folder.rglob("*.py"))
    py_files = [f for f in py_files if not _should_skip(f, folder)]

    tokens_before = 0
    files_scanned = 0

    for py_file in py_files:
        try:
            # Read the raw source and estimate its token cost.
            source = py_file.read_text(encoding="utf-8")
            tokens_before += estimate_tokens(source)
            files_scanned += 1
        except (SyntaxError, UnicodeDecodeError, PermissionError):
            # Still count the file even if we can't parse it; just skip tokens.
            files_scanned += 1

    # Build the full folder skeleton and estimate its token cost.
    skeleton_text = skeleton_of_folder(folder)
    tokens_after = estimate_tokens(skeleton_text)

    tokens_saved = tokens_before - tokens_after

    # Guard against division by zero if the folder is completely empty.
    if tokens_before == 0:
        percent_saved = 0.0
    else:
        percent_saved = round(tokens_saved / tokens_before * 100, 1)

    return {
        "tokens_before": tokens_before,
        "tokens_after":  tokens_after,
        "tokens_saved":  tokens_saved,
        "percent_saved": percent_saved,
        "files_scanned": files_scanned,
    }


# ---------------------------------------------------------------------------
# SECTION 7  –  __main__ block  (Day 2 updated for Day 3)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # sys.argv[0] is always the script name; [1] is the first user argument.
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        # Default: the backend folder one level above this script.
        target = Path(__file__).parent.parent

    # ------------------------------------------------------------------
    # Decide whether the user passed a FILE or a FOLDER.
    # ------------------------------------------------------------------
    if target.is_file():
        # ---- Single-file mode (Day 2 behaviour, preserved) ----
        original_lines = target.read_text(encoding="utf-8").splitlines()
        skeleton = skeleton_of_file(target)
        skeleton_lines = skeleton.splitlines()

        print("=== SKELETON ===")
        print(skeleton)
        print()
        print(f"Original : {len(original_lines)} lines")
        print(f"Skeleton : {len(skeleton_lines)} lines")

    else:
        # ---- Folder mode (Day 3) ----
        skeleton = skeleton_of_folder(target)
        stats = compression_stats(target)

        print("=== FOLDER SKELETON ===")
        print(skeleton)
        print()
        print("=== COMPRESSION STATS ===")
        print(f"  Files scanned  : {stats['files_scanned']}")
        print(f"  Tokens (before): {stats['tokens_before']:,}")
        print(f"  Tokens (after) : {stats['tokens_after']:,}")
        print(f"  Tokens saved   : {stats['tokens_saved']:,}")
        print(f"  Percent saved  : {stats['percent_saved']}%")
