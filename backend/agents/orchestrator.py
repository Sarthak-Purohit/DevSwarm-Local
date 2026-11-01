import ollama  # Connects Python to your local Ollama AI models
from typing import Optional
# Import the strict JSON templates we created on Day 1
from backend.schemas import PlannerOutput, CoderStep, ReviewerVerdict, SubTask

# Model names: 3B for planning/coding, tiny 1.5B for fast code review
PRIMARY_MODEL = "qwen2.5-coder:3b"
REVIEWER_MODEL = "qwen2.5-coder:1.5b"

class AgentOrchestrator:
    def __init__(self, primary_model: str = PRIMARY_MODEL, reviewer_model: str = REVIEWER_MODEL):
        self.primary_model = primary_model
        self.reviewer_model = reviewer_model

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

        # Send prompt to Ollama and force it to reply using the PlannerOutput JSON format
        response = ollama.chat(
            model=self.primary_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            format=PlannerOutput.model_json_schema(),
            options={"temperature": 0.1}  # Low temperature (0.1) keeps the AI focused and accurate
        )
        # Convert the AI's JSON text into a validated Python object
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

        # Build the task instructions for the Coder AI
        prompt_parts = [
            f"Task ID: {subtask.task_id}",
            f"Target File: {subtask.target_file}",
            f"Task Description: {subtask.description}",
            f"Attempt Step Number: {step_number}"
        ]
        # If the file already exists, show the current code to the AI
        if existing_code:
            prompt_parts.append(f"Current File Content:\n{existing_code}")
        # If a previous test failed, pass the error log so the AI can fix its own bug
        if error_traceback:
            prompt_parts.append(
                f"Previous pytest execution failed with this traceback. Fix the bug:\n{error_traceback}"
            )

        # Force Ollama to reply with both the explanation log and the new code
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

        # Send the git diff to the fast 1.5B Reviewer model
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


# Quick test block that runs when you execute: python3 -m backend.agents.orchestrator
if __name__ == "__main__":
    print("Testing DevSwarm Local — Day 2 Orchestrator & Worktree Prototype...\n")
    orchestrator = AgentOrchestrator()

    # Step 1: Test the Planner Agent with a sample request
    plan = orchestrator.run_planner(
        user_prompt="Create a Python utility file backend/utils/math_ops.py with an add(a, b) function.",
        repo_skeleton="backend/\n  schemas.py\n  main.py"
    )
    print("=== 1. PLANNER OUTPUT (Validated Pydantic JSON) ===")
    print(plan.model_dump_json(indent=2))

    # Step 2: Test the Coder Agent on the first task generated by the Planner
    if plan.subtasks:
        first_task = plan.subtasks[0]
        coder_step = orchestrator.run_coder(subtask=first_task, step_number=1)
        print("\n=== 2. CODER & TERMINAL OF THOUGHT OUTPUT ===")
        print(coder_step.model_dump_json(indent=2))