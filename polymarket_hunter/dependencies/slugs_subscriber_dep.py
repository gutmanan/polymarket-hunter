from typing import Annotated, cast

from fastapi import Depends, Request

from polymarket_hunter.core.subscriber.slug_subscriber import SlugsSubscriber


def get_slugs_subscriber(request: Request) -> SlugsSubscriber:
    return cast(SlugsSubscriber, request.app.state.slugs_subscriber)

SlugsSubscriberDep = Annotated[SlugsSubscriber, Depends(get_slugs_subscriber)]
