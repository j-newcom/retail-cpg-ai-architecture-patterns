"""
EventBridge Stack — Central event bus for inter-agent communication.
"""

from aws_cdk import (
    Stack,
    aws_events as events,
    aws_sqs as sqs,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class EventBusStack(Stack):
    """Creates the supply chain event bus with DLQ and schema registry."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dead letter queue for failed event deliveries
        self.dlq = sqs.Queue(
            self,
            "EventBusDLQ",
            queue_name="supply-chain-events-dlq",
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Central event bus
        self.event_bus = events.EventBus(
            self,
            "SupplyChainEventBus",
            event_bus_name="supply-chain-events",
        )

        # Archive all events for replay capability (30-day retention)
        events.Archive(
            self,
            "EventArchive",
            source_event_bus=self.event_bus,
            event_pattern=events.EventPattern(source=[{"prefix": "supply-chain.agent"}]),
            retention=Duration.days(30),
            archive_name="supply-chain-events-archive",
        )
