import subprocess  # Lets Python run terminal commands like "git" and "pytest"
import shutil      # Used to delete folders cleanly
from pathlib import Path
from typing import Tuple

class WorktreeManager:
    def __init__(self, repo_root: str = "."):
        # Save the main project folder path
        self.repo_root = Path(repo_root).resolve()
        # Set the path for the "worktrees/" folder and create it if it doesn't exist
        self.worktrees_dir = (self.repo_root / "worktrees").resolve()
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def _validate_boundary(self, target_path: Path) -> Path:
        """Safety check: Makes sure the AI only edits files inside the 'worktrees/' folder."""
        resolved = target_path.resolve()
        if not str(resolved).startswith(str(self.worktrees_dir)):
            raise PermissionError(f"Security violation: {resolved} is outside {self.worktrees_dir}")
        return resolved

    def create_worktree(self, task_id: str, base_branch: str = "main") -> Path:
        """Creates a separate Git branch and isolated folder for a specific task."""
        branch_name = f"swarm/{task_id}"
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)

        # If an old folder for this task already exists, clean it up first
        if wt_path.exists():
            self.cleanup_worktree(task_id)

        # Run: git worktree add -B swarm/task-1 worktrees/task-1 main
        subprocess.run(
            ["git", "worktree", "add", "-B", branch_name, str(wt_path), base_branch],
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True
        )
        return wt_path

    def write_code(self, task_id: str, relative_file_path: str, content: str) -> Path:
        """Writes the AI's generated code into a file inside the task's worktree folder."""
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)
        file_path = self._validate_boundary(wt_path / relative_file_path)
        
        # Create any missing parent folders, then write the code to the file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def run_tests(self, task_id: str, timeout: int = 30) -> Tuple[bool, str]:
        """Runs pytest inside the task's worktree folder with a 30-second time limit."""
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)
        try:
            # Run pytest and capture the terminal output
            result = subprocess.run(
                ["pytest", "--tb=short", "-q"],
                cwd=wt_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = (result.stdout + "\n" + result.stderr).strip()
            # Return code 0 = all tests passed; 5 = no test files written yet (both count as pass)
            passed = result.returncode in (0, 5)
            return passed, output
        except subprocess.TimeoutExpired:
            # Stop infinite loops if the AI wrote code that hangs forever
            return False, f"TIMEOUT: Test execution exceeded {timeout} seconds."

    def get_diff(self, task_id: str) -> str:
        """Gets the 'git diff' showing exactly what lines of code the AI added or changed."""
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)
        # Track newly created files so they also show up in the diff
        subprocess.run(["git", "add", "-N", "."], cwd=wt_path, capture_output=True)
        result = subprocess.run(
            ["git", "diff"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout

    def merge_worktree(self, task_id: str, target_branch: str = "main") -> Tuple[bool, str]:
        """Merges the AI's branch into 'main' when the user clicks 'Approve & Merge'."""
        branch_name = f"swarm/{task_id}"
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)

        # Stage and commit all changes inside the task's worktree
        subprocess.run(["git", "add", "."], cwd=wt_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat({task_id}): apply approved agent changes"],
            cwd=wt_path,
            capture_output=True
        )

        # Test the merge first without committing to check if there are any merge conflicts
        check = subprocess.run(
            ["git", "merge", "--no-commit", "--no-ff", branch_name],
            cwd=self.repo_root,
            capture_output=True,
            text=True
        )
        if check.returncode != 0:
            # If there is a conflict, cancel the merge and alert the user
            subprocess.run(["git", "merge", "--abort"], cwd=self.repo_root, capture_output=True)
            return False, f"Merge conflict detected:\n{check.stderr}"

        # Finalize the merge into main and delete the temporary worktree folder
        subprocess.run(
            ["git", "commit", "-m", f"Merge branch '{branch_name}' into {target_branch}"],
            cwd=self.repo_root,
            capture_output=True
        )
        self.cleanup_worktree(task_id)
        return True, f"Successfully merged {branch_name} into {target_branch}."

    def cleanup_worktree(self, task_id: str):
        """Deletes the temporary worktree folder and removes the temporary Git branch."""
        branch_name = f"swarm/{task_id}"
        wt_path = self._validate_boundary(self.worktrees_dir / task_id)

        # Unlink the worktree from Git, delete the folder, and delete the branch
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt_path)],
            cwd=self.repo_root,
            capture_output=True
        )
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)

        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.repo_root,
            capture_output=True
        )