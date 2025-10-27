from polymarket_hunter.dal.datamodel.strategy import Strategy, Rule
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side

strategies = [
    Strategy(
        name="Crypto Up/Down Strategy",
        condition_fn=lambda context: "Crypto" in context.tags,
        rules=[
            Rule(
                name="Buy Up",
                condition_fn=lambda context: 0.75 < context.outcomePrices["Up"]["BUY"] < 0.9,
                action=StrategyAction(
                    side=Side.BUY,
                    size=5,
                    outcome="Up",
                    stop_loss=0.25
                )
            ),
            Rule(
                name="Buy Down",
                condition_fn=lambda context: 0.75 < context.outcomePrices["Down"]["BUY"] < 0.9,
                action=StrategyAction(
                    side=Side.BUY,
                    size=5,
                    outcome="Down",
                    stop_loss=0.25
                )
            ),
        ]
    )
]
