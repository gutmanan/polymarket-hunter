from decimal import Decimal
from typing import Optional, Tuple

from polymarket_hunter.config.strategies import strategies
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.notifier.formatter.exit_message_formatter import format_exit_message
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.strategy import Rule, Strategy
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side, OrderType
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import prepare_market_amount, time_left_sec

logger = setup_logger(__name__)
RESOLUTION_BUFFER_SECONDS = 10      # do not trade last 10 sec


class StrategyEvaluator:
    def __init__(self):
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._order_store = RedisOrderRequestStore()
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    # ---------- utilities ----------

    def _find_action_for_context(self, context: MarketContext, outcome: str) -> Optional[Tuple[Strategy, Rule]]:
        for strategy in strategies:
            try:
                if not strategy.condition_fn(context):
                    continue
                for rule in strategy.rules:
                    if rule.condition_fn(context) and rule.action.outcome == outcome:
                        return strategy, rule
            except Exception as error:
                logger.warning(f"Failed to evaluate strategy: {strategy.name} error: {error}")
                continue
        return None

    async def _get_active_position(self, market_id: str, asset_id: str, side: Side) -> Optional[TradeRecord]:
        existing_trade = await self._trade_store.get_latest(market_id, asset_id, side)
        return existing_trade if existing_trade and existing_trade.active else None

    async def should_enter(self, context: MarketContext, outcome: str) -> Optional[OrderRequest]:
        result = self._find_action_for_context(context, outcome)
        if result is None:
            return None

        strategy, rule = result
        action: StrategyAction = rule.action
        market_id = context.condition_id
        asset_id = context.outcome_assets[outcome]

        side = action.side
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(side)

        if current_price is None or current_price == 0:
            return None

        if action.order_type == OrderType.MARKET:
            size = prepare_market_amount(side, current_price, action.size)
        else:
            size = max(action.size, context.order_min_size)

        active_position = await self._get_active_position(market_id, asset_id, side)
        if active_position:
            return None

        # Build and return OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            outcome=outcome,
            price=current_price.__float__(),
            size=size,
            side=side,
            action=action,
            context=context,
            strategy_name=strategy.name,
            rule_name=rule.name
        )

    async def should_exit(self, context: MarketContext, outcome: str, enter_request: OrderRequest) -> Optional[OrderRequest]:
        market_id = enter_request.market_id
        asset_id = enter_request.asset_id

        active_position = await self._get_active_position(market_id, asset_id, enter_request.side)
        if not active_position:
            return None

        entry_price: float = enter_request.price
        entry_side: Side = enter_request.side
        exit_side: Side = Side.BUY if entry_side == Side.SELL else Side.SELL
        exit_size: float = active_position.matched_amount
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(exit_side)

        if current_price is None or current_price == 0:
            return None

        stop: float = enter_request.action.stop_loss
        tp: float = enter_request.action.take_profit

        if entry_side == Side.BUY:
            hit_stop = current_price <= entry_price - stop
            hit_tp = current_price >= min(entry_price + tp, 0.99)
        else:  # Side.SELL
            hit_stop = current_price >= entry_price + stop
            hit_tp = current_price <= max(entry_price - tp, 0.01)

        if not (hit_stop or hit_tp):
            return None

        # Send notifications
        if hit_stop:
            message = format_exit_message(context, outcome, Decimal.from_float(entry_price), current_price, is_stop=True)
            await self._notifier.send_message(message)
        if hit_tp:
            message = format_exit_message(context, outcome, Decimal.from_float(entry_price), current_price, is_stop=False)
            await self._notifier.send_message(message)

        # Build and return exit OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            outcome=outcome,
            price=current_price.__float__(),
            size=exit_size,
            side=exit_side,
            action=enter_request.action,
            context=context,
            strategy_name=enter_request.strategy_name,
            rule_name=enter_request.rule_name,
        )

    async def evaluate(self, context: MarketContext):
        if time_left_sec(context) <= RESOLUTION_BUFFER_SECONDS:
            return

        for outcome, asset_id in context.outcome_assets.items():
            enter_request = await self._order_store.get(context.condition_id, asset_id)
            request = await self.should_exit(context, outcome, enter_request) if enter_request else await self.should_enter(context, outcome)
            if request:
                await self._order_store.add(request)
