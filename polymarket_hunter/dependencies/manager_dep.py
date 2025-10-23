from typing import Annotated, cast

from fastapi import Depends, Request

from polymarket_hunter.core.subscription_manager import SubscriptionManager


def get_manager(request: Request) -> SubscriptionManager:
    return cast(SubscriptionManager, request.app.state.manager)

ManagerDep = Annotated[SubscriptionManager, Depends(get_manager)]
