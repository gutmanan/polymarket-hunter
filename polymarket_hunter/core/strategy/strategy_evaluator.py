from decimal import Decimal
from typing import Optional, Tuple

from polymarket_hunter.config.strategies import strategies
from polymarket_hunter.core.notifier.formatter.exit_message_formatter import format_exit_message
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.order_request import OrderRequest, RequestSource
from polymarket_hunter.dal.datamodel.strategy import Rule, Strategy
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side, OrderType
from polymarket_hunter.dal.datamodel.trade_error import EventCode, TradeEvent, EventState
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.datamodel.trend_prediction import Direction
from polymarket_hunter.dal.market_context_store import RedisMarketContextStore
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.helper import time_left_sec, ts_to_seconds
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

EXIT_LOCKOUT_PERIOD_SECONDS = 0
ENTER_LOCKOUT_PERIOD_SECONDS = 0
REVERSAL_CONFIRMATION_PERIOD_SECONDS = 60
DEFAULT_TAKE_PROFIT = 0.999
DEFAULT_STOP_LOSS = 0.001


class StrategyEvaluator:
    def __init__(self):
        self._context_store = RedisMarketContextStore()
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

    async def _validate_request(self, context: MarketContext, outcome: str, request: OrderRequest) -> bool:
        if request.request_source in (RequestSource.TAKE_PROFIT, RequestSource.STOP_LOSS):
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=request.side,
                state=EventState.VALIDATED,
                request_source=request.request_source,
                strategy_name=request.strategy_name,
                rule_name=request.rule_name
            )
            return True

        trend = context.outcome_trends.get(outcome)
        if not trend or trend.direction == Direction.FLAT:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=request.side,
                state=EventState.BLOCKED,
                request_source=request.request_source,
                strategy_name=request.strategy_name,
                rule_name=request.rule_name,
                code=EventCode.TREND_FLAT,
                error="No trend detected"
            )
            return False

        now = ts_to_seconds(context.event_ts)
        if trend.reversal and (now - trend.flipped_ts) < REVERSAL_CONFIRMATION_PERIOD_SECONDS:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=request.side,
                state=EventState.BLOCKED,
                request_source=request.request_source,
                strategy_name=request.strategy_name,
                rule_name=request.rule_name,
                code=EventCode.TREND_REVERSAL,
                error="Waiting confirmation period"
            )
            return False

        expected_side = Side.BUY if trend.direction == Direction.UP else Side.SELL
        if request.side != expected_side:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=request.side,
                state=EventState.BLOCKED,
                request_source=request.request_source,
                strategy_name=request.strategy_name,
                rule_name=request.rule_name,
                code=EventCode.TREND_MISMATCH,
                error=f"{request.side} is not allowed with trend direction {trend.direction}"
            )
            return False

        await TradeEvent.log(
            ctx=context,
            outcome=outcome,
            side=request.side,
            state=EventState.VALIDATED,
            request_source=request.request_source,
            strategy_name=request.strategy_name,
            rule_name=request.rule_name
        )
        return True

    async def _get_active_position(self, market_id: str, asset_id: str, side: Side) -> Optional[TradeRecord]:
        existing_trade = await self._trade_store.get_active(market_id, asset_id, side)
        return existing_trade if existing_trade and existing_trade.active else None

    # ---------- Public API --------------

    async def should_enter(self, context: MarketContext, outcome: str) -> Optional[OrderRequest]:
        result = self._find_action_for_context(context, outcome)
        if result is None:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=Side.BUY,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_ENTER,
                strategy_name="N/A",
                rule_name="N/A",
                code=EventCode.NO_ENTER,
                error="No enter criteria met"
            )
            return None

        strategy, rule = result
        action: StrategyAction = rule.action

        if time_left_sec(context) <= ENTER_LOCKOUT_PERIOD_SECONDS:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=Side.BUY,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_ENTER,
                strategy_name=strategy.name,
                rule_name=rule.name,
                code=EventCode.LOCKOUT,
                error="Lockout period"
            )
            return None

        market_id = context.condition_id
        asset_id = context.outcome_assets[outcome]

        side = action.side
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(side)
        if current_price is None or current_price == 0:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=side,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_ENTER,
                strategy_name=strategy.name,
                rule_name=rule.name,
                code=EventCode.MISSING_DATA_ERROR,
                error="No price data available"
            )
            return None

        active_position = await self._get_active_position(market_id, asset_id, side)
        if active_position:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=side,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_ENTER,
                strategy_name=strategy.name,
                rule_name=rule.name,
                code=EventCode.LOCKOUT,
                error="Active position exists"
            )
            return None

        # Build and return OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            outcome=outcome,
            price=float(current_price),
            size=max(action.size, context.order_min_size),
            side=side,
            tif=action.time_in_force,
            order_type=action.order_type,
            request_source=RequestSource.STRATEGY_ENTER,
            action=action,
            context=context,
            strategy_name=strategy.name,
            rule_name=rule.name
        )

    async def should_exit(self, context: MarketContext, outcome: str, enter_request: OrderRequest) -> Optional[OrderRequest]:
        if time_left_sec(context) <= EXIT_LOCKOUT_PERIOD_SECONDS:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=Side.SELL,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_EXIT,
                strategy_name=enter_request.strategy_name,
                rule_name=enter_request.rule_name,
                code=EventCode.LOCKOUT,
                error="Lockout period"
            )
            return None

        market_id = enter_request.market_id
        asset_id = enter_request.asset_id

        active_position = await self._get_active_position(market_id, asset_id, enter_request.side)
        if not active_position:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=Side.SELL,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_EXIT,
                strategy_name=enter_request.strategy_name,
                rule_name=enter_request.rule_name,
                code=EventCode.LOCKOUT,
                error="No active position"
            )
            return None

        entry_price: float = enter_request.price
        entry_side: Side = enter_request.side
        exit_side: Side = Side.BUY if entry_side == Side.SELL else Side.SELL
        exit_size: float = active_position.matched_amount
        outcome_prices = context.outcome_prices[outcome]
        current_price: Decimal = outcome_prices.get(exit_side)

        if current_price is None or current_price == 0:
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=exit_side,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_EXIT,
                strategy_name=enter_request.strategy_name,
                rule_name=enter_request.rule_name,
                code=EventCode.MISSING_DATA_ERROR,
                error="No price data available"
            )
            return None

        stop: float = enter_request.action.stop_loss
        tp: float = enter_request.action.take_profit
        current_price_float = float(current_price)

        sl_trigger_price = DEFAULT_STOP_LOSS if stop >= 1.0 else entry_price - stop
        tp_trigger_price = min(entry_price + tp, DEFAULT_TAKE_PROFIT)

        hit_stop = current_price_float <= sl_trigger_price
        hit_tp = current_price_float >= tp_trigger_price

        if not (hit_stop or hit_tp):
            await TradeEvent.log(
                ctx=context,
                outcome=outcome,
                side=Side.SELL,
                state=EventState.BLOCKED,
                request_source=RequestSource.STRATEGY_EXIT,
                strategy_name=enter_request.strategy_name,
                rule_name=enter_request.rule_name,
                code=EventCode.NO_EXIT,
                error="No exit criteria met",
                additional_info={"sl_trigger_price": sl_trigger_price, "tp_trigger_price": tp_trigger_price}
            )
            return None

        request_source = RequestSource.STRATEGY_EXIT

        if hit_stop:
            request_source = RequestSource.STOP_LOSS
            message = format_exit_message(context, outcome, Decimal.from_float(entry_price), current_price,
                                          is_stop=True)
            await self._notifier.send_message(message)
        if hit_tp:
            request_source = RequestSource.TAKE_PROFIT
            message = format_exit_message(context, outcome, Decimal.from_float(entry_price), current_price,
                                          is_stop=False)
            await self._notifier.send_message(message)

        order_type = OrderType.MARKET
        if request_source == RequestSource.STRATEGY_EXIT and enter_request.action.order_type is not None:
            order_type = enter_request.action.order_type

        # Build and return exit OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            outcome=outcome,
            price=float(current_price),
            size=exit_size,
            side=exit_side,
            tif=enter_request.action.time_in_force,
            order_type=order_type,
            request_source=request_source,
            action=enter_request.action,
            context=context,
            strategy_name=enter_request.strategy_name,
            rule_name=enter_request.rule_name
        )

    async def evaluate(self, context: MarketContext):
        await self._context_store.publish(context)

        for outcome, asset_id in context.outcome_assets.items():
            enter_request = await self._order_store.get(context.condition_id, asset_id, Side.BUY)
            exit_request = await self._order_store.get(context.condition_id, asset_id, Side.SELL)

            if enter_request and not exit_request:
                request = await self.should_exit(context, outcome, enter_request)
            elif not enter_request and not exit_request:
                request = await self.should_enter(context, outcome)
            else:
                continue

            if request and await self._validate_request(context, outcome, request):
                await self._order_store.add(request)
