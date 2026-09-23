"""Builds the random walker from the application settings."""

import random

from app.config import Settings
from app.graph.driver import get_driver
from app.graph.repository import Neo4jGraphRepository
from app.graph.walk import RandomWalker, WalkSettings


def build_walker(settings: Settings, rng: random.Random | None = None) -> RandomWalker:
    return RandomWalker(
        Neo4jGraphRepository(get_driver()),
        rng,
        WalkSettings(
            min_hops=settings.walk_min_hops,
            max_hops=settings.walk_max_hops,
            top_share=settings.walk_top_share,
        ),
    )
