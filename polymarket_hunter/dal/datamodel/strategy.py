from dataclasses import dataclass
from typing import Callable, List

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction


@dataclass(frozen=True)
class Rule:
    name: str
    condition_fn: Callable[[MarketContext], bool]
    action: StrategyAction


@dataclass(frozen=True)
class Strategy:
    name: str
    condition_fn: Callable[[MarketContext], bool]
    rules: List[Rule]
