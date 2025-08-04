"""
Aggregators module.

This module contains result aggregation components that collect and combine
processing results from multiple workers.
"""

from .result_aggregator import ResultAggregator, ChunkAggregationState

__all__ = [
    "ResultAggregator",
    "ChunkAggregationState"
]