from typing import Optional, Dict, Any, Tuple

from polymarket_hunter.config.strategies import strategies
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.strategy import Rule, Strategy
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side
from polymarket_hunter.notifier.telegram_notifier import TelegramNotifier
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class StrategyEvaluator:
    def __init__(self):
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._notifier = TelegramNotifier()

    def _get_active_position(self, market_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
        positions = self._data.get_positions(querystring_params={"market": market_id})
        return next((p for p in positions if p.get("asset") == asset_id), None)

    def _get_active_order(self, market_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
        orders = self._clob.get_orders(market_id)
        return next((o for o in orders if o.get("asset_id") == asset_id), None)

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

    async def _send_exit_notification(self, context: MarketContext, outcome: str, entry_price: float,current_price: float, is_stop: bool):
        diff = abs(entry_price - current_price)
        gain_loss_text = f"−{diff:.3f}" if is_stop else f"+{diff:.3f}"
        emoji = "🛑" if is_stop else "🎯"
        title = "Stop Loss Triggered" if is_stop else "Take Profit Reached"

        message = (
            f"{emoji} <b>{title}</b>\n"
            f"📊 <b>{context.slug}</b>\n"
            f"📈 <b>Outcome:</b> {outcome}\n"
            f"💸 <b>Entry:</b> {entry_price:.3f} → <b>Exit:</b> {current_price:.3f}\n"
            f"📈 <b>Gain/Loss:</b> {gain_loss_text} USDC"
        )
        await self._notifier.send_message(message)

    async def should_enter(self, context: MarketContext, outcome: str) -> Optional[OrderRequest]:
        result = self._find_action_for_context(context, outcome)
        if result is None:
            return None

        strategy, rule = result
        action: StrategyAction = rule.action
        market_id = context.conditionId
        asset_id = context.outcomeAssets[outcome]

        # Check for existing positions/orders
        active_position = self._get_active_position(market_id, asset_id)
        active_order = self._get_active_order(market_id, asset_id)

        if active_position or active_order:
            return None

        # Build and return OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            price=context.outcomePrices[outcome][action.side],
            strategy_name=strategy.name,
            rule_name=rule.name,
            action=action,
            context=context
        )

    async def should_exit(self, context: MarketContext, outcome: str, enter_request: OrderRequest) -> Optional[OrderRequest]:
        market_id = enter_request.market_id
        asset_id = enter_request.asset_id

        active_position = self._get_active_position(market_id, asset_id)
        active_order = self._get_active_order(market_id, asset_id)

        if not active_position or active_order:
            return None

        entry_price: float = enter_request.price
        entry_side: Side = enter_request.action.side
        exit_side: Side = Side.BUY if entry_side == Side.SELL else Side.SELL
        current_price = context.outcomePrices[outcome].get(exit_side)

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
            await self._send_exit_notification(context, outcome, entry_price, current_price, is_stop=True)
        if hit_tp:
            await self._send_exit_notification(context, outcome, entry_price, current_price, is_stop=False)

        # Build and return exit OrderRequest
        return OrderRequest(
            market_id=market_id,
            asset_id=asset_id,
            price=current_price,
            action=StrategyAction(
                side=exit_side,
                outcome=outcome,
                size=active_position["size"],
                # Stop/TP are not needed for the exit action itself
            ),
            context=context,
            strategy_name=enter_request.strategy_name,
            rule_name=enter_request.rule_name,
        )
