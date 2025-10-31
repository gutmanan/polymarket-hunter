from dataclasses import dataclass


@dataclass(frozen=True)
class MsgEnvelope:
    market: str
    timestamp: int
    event_type: str
    payload: dict
