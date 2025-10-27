from typing import Annotated, cast

from fastapi import Depends, Request

from polymarket_hunter.core.subscriber.slug_subscriber import SlugsSubscriber


def get_manager(request: Request) -> SlugsSubscriber:
    return cast(SlugsSubscriber, request.app.state.manager)

ManagerDep = Annotated[SlugsSubscriber, Depends(get_manager)]
