import ollama  # Connects Python to your local Ollama AI models
from typing import Optional, Dict, Any
from backend.schemas import PlannerOutput, CoderStep, ReviewerVerdict, SubTask
from backend.systems.worktree import WorktreeManager

PRIMARY_MODEL = "qwen2.5-coder:3b"
REVIEWER_MODEL = "qwen2.5-coder:1.5b"

class AgentOrchestrator:
    def __init__(self, primary_model: str = PRIMARY_MODEL, reviewer_model: str = REVIEWER_MODEL):
        self.primary_model = primary_model
        self.reviewer_model = reviewer_model
        self.worktree_mgr = WorktreeManager()

    def run_planner(self, user_prompt: str, repo_skeleton: str = "") -> PlannerOutput:
        """1. PLANNER AGENT: Breaks a user's feature request into smaller coding subtasks."""
        system_prompt = (
            "You are the Lead Software Planner for DevSwarm Local. "
            "Break the user's request into independent, non-overlapping coding subtasks. "
            "Assign each subtask a unique task_id (e.g., 'task-1'), a strict role "
            "('BACKEND_DATA' or 'FRONTEND_UI'), a clear description, and an exact target_file path. "
            "Respond ONLY with valid JSON matching the requested schema."
        )
        user_message = f"Repository AST Skeleton:\n{repo_skeleton}\n\nFeature Request:\n{user_prompt}"

        response = ollama.chat(
            model=self.primary_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            format=PlannerOutput.model_json_schema(),
            options={"temperature": 0.1}
        )
        return PlannerOutput.model_validate_json(response["message"]["content"])

    def run_coder(
        self,
        subtask: SubTask,
        step_number: int = 1,
        existing_code: str = "",
        error_traceback: Optional[str] = None
    ) -> CoderStep:
        """2. CODER AGENT: Explains its thinking in plain English and writes the code."""
        system_prompt = (
            f"You are an autonomous {subtask.role} Engineer. "
            "Before writing code, you MUST populate the explainability_log with a clear, "
            "plain-English human_explanation of what you are doing and why_this_decision "
            "was made. Then provide the complete, working code for the target_file. "
            "Respond ONLY with valid JSON matching the requested schema."
        )

        prompt_parts = [
            f"Task ID: {subtask.task_id}",
            f"Target File: {subtask.target_file}",
            f"Task Description: {subtask.description}",
            f"Attempt Step Number: {step_number}"
        ]
        if existing_code:
            prompt_parts.append(f"Current File Content:\n{existing_code}")
        if error_traceback:
            prompt_parts.append(
                f"Previous pytest execution failed with this traceback. Fix the bug:\n{error_traceback}"
            )

        response = ollama.chat(
            model=self.primary_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(prompt_parts)}
            ],
            format=CoderStep.model_json_schema(),
            options={"temperature": 0.1}
        )
        return CoderStep.model_validate_json(response["message"]["content"])

    def run_reviewer(self, git_diff: str) -> ReviewerVerdict:
        """3. REVIEWER AGENT: Checks the final git diff for security issues or bugs."""
        system_prompt = (
            "You are a Security & Code Quality Reviewer Agent. "
            "Inspect the provided git diff for security flaws (e.g., SQL injection, hardcoded secrets), "
            "unintended deletions, or syntax bugs. Output passed (true/false), risk_score "
            "('LOW', 'MEDIUM', or 'HIGH'), and brief review notes."
        )

        response = ollama.chat(
            model=self.reviewer_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Git Diff to Audit:\n{git_diff}"}
            ],
            format=ReviewerVerdict.model_json_schema(),
            options={"temperature": 0.1}
        )
        return ReviewerVerdict.model_validate_json(response["message"]["content"])

    def execute_subtask_pipeline(
        self,
        subtask: SubTask,
        test_file_path: Optional[str] = None,
        test_code_content: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        DAY 3 PIPELINE:
        1. Creates an isolated Git worktree for the subtask.
        2. Runs the Coder Agent + pytest in a 3-retry self-healing loop.
        3. Extracts the git diff and runs the 1.5B Reviewer Agent audit.
        """
        # 1. Create isolated Git worktree folder (worktrees/<task_id>)
        wt_path = self.worktree_mgr.create_worktree(subtask.task_id)

        # Optional: Write a unit test file inside the worktree to verify the AI's code
        if test_file_path and test_code_content:
            self.worktree_mgr.write_code(subtask.task_id, test_file_path, test_code_content)

        current_code = ""
        last_error = None
        thought_history = []
        tests_passed = False

        # 2. 3-Retry Self-Healing Coding & Testing Loop
        for attempt in range(1, max_retries + 1):
            print(f"[{subtask.task_id}] Coding Attempt {attempt}/{max_retries}...")
            coder_step = self.run_coder(
                subtask=subtask,
                step_number=attempt,
                existing_code=current_code,
                error_traceback=last_error
            )
            thought_history.append(coder_step.explainability_log.model_dump())

            # Write the AI's generated code into the isolated worktree
            self.worktree_mgr.write_code(
                task_id=subtask.task_id,
                relative_file_path=subtask.target_file,
                content=coder_step.code_content
            )
            current_code = coder_step.code_content

            # Run pytest inside the isolated worktree
            passed, test_output = self.worktree_mgr.run_tests(subtask.task_id)
            if passed:
                print(f"[{subtask.task_id}] Pytest PASSED on Attempt {attempt}!")
                tests_passed = True
                break
            else:
                print(f"[{subtask.task_id}] Pytest FAILED on Attempt {attempt}. Feeding traceback to Coder...")
                last_error = test_output

        # 3. Extract Git Diff & Run Reviewer Agent Audit
        git_diff = self.worktree_mgr.get_diff(subtask.task_id)

        if tests_passed:
            review_verdict = self.run_reviewer(git_diff)
            final_status = "Ready to Merge" if review_verdict.passed else "Review"
        else:
            review_verdict = ReviewerVerdict(
                passed=False,
                risk_score="HIGH",
                notes=f"Failed unit tests after {max_retries} self-healing attempts."
            )
            final_status = "Needs Human Help"

        return {
            "task_id": subtask.task_id,
            "status": final_status,
            "worktree_path": str(wt_path),
            "attempts_used": len(thought_history),
            "thought_logs": thought_history,
            "git_diff": git_diff,
            "reviewer_verdict": review_verdict.model_dump()
        }


if __name__ == "__main__":
    print("=== Testing DevSwarm Local — Day 3 End-to-End Self-Healing Pipeline ===\n")
    orchestrator = AgentOrchestrator()

    # Create a sample subtask
    demo_subtask = SubTask(
        task_id="task-day3-demo",
        role="BACKEND_DATA",
        description=(
            "Create a Python file backend/utils/calculator.py with two functions: "
            "add(a, b) that returns a + b, and multiply(a, b) that returns a * b."
        ),
        target_file="backend/utils/calculator.py"
    )

    # Create a real pytest file to verify the AI's code inside the isolated worktree
    sample_pytest = (
        "from backend.utils.calculator import add, multiply\n\n"
        "def test_add():\n"
        "    assert add(3, 5) == 8\n\n"
        "def test_multiply():\n"
        "    assert multiply(4, 3) == 12\n"
    )

    result = orchestrator.execute_subtask_pipeline(
        subtask=demo_subtask,
        test_file_path="tests/test_calculator.py",
        test_code_content=sample_pytest
    )

    print(f"\nFinal Kanban Status: {result['status']}")
    print(f"Attempts Used: {result['attempts_used']}")
    print("\n--- Terminal of Thought Log ---")
    for log in result["thought_logs"]:
        print(f"Step {log['step_number']}: {log['human_explanation']}")
        print(f"Why: {log['why_this_decision']}\n")

    print("--- Extracted Git Diff ---")
    print(result["git_diff"])

    print("--- 1.5B Reviewer Verdict ---")
    print(result["reviewer_verdict"])

    # Clean up the demo worktree so the repo stays tidy
    orchestrator.worktree_mgr.cleanup_worktree(demo_subtask.task_id)