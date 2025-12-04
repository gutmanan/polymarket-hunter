import time
import uuid
from typing import Literal, Optional, Any, Dict

from pydantic import BaseModel, Field

Medium = Literal["telegram", "email", "slack"]
Severity = Literal["info", "warning", "error"]

class Notification(BaseModel):
    key: Optional[str] = uuid.uuid4().hex
    text: str
    severity: Severity = "info"
    target: Optional[str] = None
    medium: Optional[Medium] = "telegram"
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_ts: float = Field(default_factory=time.time)
