from decimal import Decimal
from typing import Optional, Dict, Any, Tuple

from polymarket_hunter.config.strategies import strategies
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.notifier.formatter.exit_message_formatter import format_exit_message
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.strategy import Rule, Strategy
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side, OrderType
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import prepare_market_amount

logger = setup_logger(__name__)


class StrategyEvaluator:
    def __init__(self):
        self._clob = get_clob_client()
        self._data = get_data_client()
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

    async def _get_active_position(self, market_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
        positions = await self._data.get_positions_retry(querystring_params={"market": market_id})
        return next((p for p in positions if p.get("asset") == asset_id), None)

    async def _get_active_order(self, market_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
        orders = await self._clob.get_orders_retry(market_id)
        return next((o for o in orders if o.get("asset_id") == asset_id), None)

    async def should_enter(self, context: MarketContext, outcome: str) -> Optional[OrderRequest]:
        result = self._find_action_for_context(context, outcome)
        if result is None:
            return None

        strategy, rule = result
        action: StrategyAction = rule.action
        market_id = context.condition_id
        asset_id = context.outcome_assets[outcome]

        active_position = await self._get_active_position(market_id, asset_id)
        active_order = await self._get_active_order(market_id, asset_id)

        if active_position or active_order:
            return None

        side = action.side
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(side)

        if current_price is None or current_price == 0:
            return None

        if action.order_type == OrderType.MARKET:
            size = prepare_market_amount(side, current_price, action.size)
        else:
            size = max(action.size, context.order_min_size)

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

        active_position = await self._get_active_position(market_id, asset_id)
        active_order = await self._get_active_order(market_id, asset_id)

        if not active_position or active_order:
            return None

        entry_price: float = enter_request.price
        entry_side: Side = enter_request.side
        exit_side: Side = Side.BUY if entry_side == Side.SELL else Side.SELL
        exit_size: float = active_position["size"]
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(exit_side)

        if current_price is None or current_price == 0:
            return None

        stop: float = enter_request.action.stop_loss
        tp: float = enter_request.action.take_profit

        if entry_side == Side.BUY:
            hit_stop = current_price <= entry_price - stop
            hit_tp = current_price >= entry_price + tp
        else:  # SHORT entry (Side.SELL)
            hit_stop = current_price >= entry_price + stop
            hit_tp = current_price <= entry_price - tp

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
