#!/usr/bin/env python3
"""
CDK App Entry Point — Agentic Supply Chain
Deploys all stacks in dependency order.
"""

import aws_cdk as cdk

from stacks.event_bus_stack import EventBusStack
from stacks.reasoning_stack import ReasoningStack
from stacks.agent_compute_stack import AgentComputeStack
from stacks.integration_stack import IntegrationStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

# Stack 1: Event backbone (no dependencies)
event_bus = EventBusStack(app, "SupplyChainEventBus", env=env)

# Stack 2: Reasoning layer (Neptune, OpenSearch)
reasoning = ReasoningStack(app, "SupplyChainReasoning", env=env)

# Stack 3: Agent compute (depends on event bus + reasoning)
agents = AgentComputeStack(
    app,
    "SupplyChainAgents",
    event_bus=event_bus.event_bus,
    neptune_endpoint=reasoning.neptune_endpoint,
    opensearch_endpoint=reasoning.opensearch_endpoint,
    env=env,
)
agents.add_dependency(event_bus)
agents.add_dependency(reasoning)

# Stack 4: ERP integration (depends on event bus)
integration = IntegrationStack(
    app,
    "SupplyChainIntegration",
    event_bus=event_bus.event_bus,
    env=env,
)
integration.add_dependency(event_bus)

# Stack 5: Monitoring (depends on agents)
monitoring = MonitoringStack(
    app,
    "SupplyChainMonitoring",
    agent_functions=agents.agent_functions,
    env=env,
)
monitoring.add_dependency(agents)

app.synth()
