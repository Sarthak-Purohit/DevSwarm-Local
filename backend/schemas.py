from pydantic import BaseModel
from typing import List, Literal

class SubTask(BaseModel):
    task_id: str
    role: Literal["BACKEND_DATA", "FRONTEND_UI"]
    description: str
    target_file: str

class PlannerOutput(BaseModel):
    subtasks: List[SubTask]

class ExplainabilityLog(BaseModel):
    step_number: int
    human_explanation: str
    why_this_decision: str

class CoderStep(BaseModel):
    explainability_log: ExplainabilityLog
    target_file: str
    code_content: str

class ReviewerVerdict(BaseModel):
    passed: bool
    risk_score: Literal["LOW", "MEDIUM", "HIGH"]
    notes: str