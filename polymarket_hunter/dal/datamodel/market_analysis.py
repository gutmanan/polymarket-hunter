import time
from enum import StrEnum
from typing import Optional

from pydantic import ConfigDict, BaseModel
from sqlmodel import SQLModel, Field


class NewsVerdict(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCLEAR = "UNCLEAR"


class RecommendedAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NO_ACTION = "NO_ACTION"


class AnalysisSource(BaseModel):
    name: str
    url: str


class MarketAnalysis(SQLModel, table=True):
    model_config = ConfigDict(use_enum_values=True)
    __tablename__ = "market_analysis"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True)
    question: str
    reasoning: str = Field(description="Max 2 sentence justification")
    sources: List[AnalysisSource] = Field(default=[], sa_column=Column(JSON))
    news_verdict: NewsVerdict
    recommended_action: RecommendedAction
    target_outcome: str
    estimated_probability: float = Field(description="Prob (0.0-1.0)")
    confidence_score: float = Field(description="Confidence (0.0-1.0)")
    created_ts: float = Field(default_factory=time.time)