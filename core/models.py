from typing import Optional
from pydantic import BaseModel
from typing import Any, Optional
class PRReviewRequest(BaseModel):
    pr_url: str
    github_token: str | None = None

class PromptRequest(BaseModel):
    prompt: str

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

class PullRequestReviewRequest(BaseModel):
    pr_url: str
    github_token: str

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Any] = None
