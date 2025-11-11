import time
import uuid
from typing import Literal, Optional, Any, Dict

from pydantic import BaseModel, Field

Medium = Literal["telegram", "email", "slack"]

class Notification(BaseModel):
    key: Optional[str] = uuid.uuid4().hex
    text: str
    severity: Literal["info","warn","error"] = "info"
    target: Optional[str] = None
    medium: Optional[Medium] = "telegram"
    meta: Dict[str, Any] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=lambda: int(time.time()*1000))