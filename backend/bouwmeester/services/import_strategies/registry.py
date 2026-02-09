"""Registry of available import strategies."""

from bouwmeester.services.import_strategies.base import ImportStrategy
from bouwmeester.services.import_strategies.motie import MotieStrategy

STRATEGIES: dict[str, type[ImportStrategy]] = {
    "motie": MotieStrategy,
}


def get_strategy(item_type: str) -> ImportStrategy:
    """Get a strategy instance by item type."""
    cls = STRATEGIES.get(item_type)
    if cls is None:
        raise ValueError(f"Unknown item type: {item_type}")
    return cls()


def get_all_strategies() -> dict[str, ImportStrategy]:
    """Get instances of all registered strategies."""
    return {k: v() for k, v in STRATEGIES.items()}
