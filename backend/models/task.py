from pydantic import BaseModel
from typing import Optional, List
import uuid

class TaskRequest(BaseModel):
    prompt: str
    repo_path: Optional[str] = None
    mode: str = "auto"
    context: Optional[dict] = None

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None

class Task(BaseModel):
    task_id: str = str(uuid.uuid4())
    prompt: str
    repo_path: Optional[str] = None
    mode: str = "auto"
    status: str = "created"
    created_at: str
    updated_at: str
    result: Optional[dict] = None
    error: Optional[str] = None

class LLMConfig(BaseModel):
    provider: str
    model: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 2048

