# Agentic Supply Chain — Local Demo

Run the full 5-agent supply chain system on your laptop. No AWS account needed. Uses [Floci](https://github.com/floci-io/floci) to emulate EventBridge, Lambda, S3, DynamoDB, and Step Functions locally.

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for the agent scripts)
- No AWS credentials required

## Quick Start

```bash
cd examples/agentic-supply-chain-local
docker compose up -d
python agents/run_demo.py
```

That's it. The demo:
1. Starts Floci (local AWS emulator) with EventBridge, Lambda, S3, and DynamoDB
2. Seeds inventory, demand, and supplier data into DynamoDB
3. Publishes a demand signal event to EventBridge
4. Watches the 5 agents react in sequence (demand sensing → inventory allocation → procurement → logistics → disruption response)
5. Prints each agent's decision with reasoning trace

## What You'll See

```
[09:00:01] EVENT: demand.signal.received (SKU: CHIPS-BBQ-12OZ, location: DC-DALLAS)
[09:00:01] AGENT: Demand Sensing → analyzing signal...
[09:00:02] DECISION: Adjust forecast +12% (confidence: 0.84)
           Reasoning: POS velocity +18% over 7-day baseline, regional promo active
[09:00:02] EVENT: demand.adjustment.published → EventBridge

[09:00:03] AGENT: Inventory Allocation → rebalancing...
[09:00:03] DECISION: Transfer 2,400 units from DC-ATLANTA to DC-DALLAS
           Reasoning: Dallas at 1.8 days cover (target 4.0), Atlanta at 6.2 days
[09:00:03] EVENT: inventory.transfer.requested → EventBridge

[09:00:04] AGENT: Logistics → routing shipment...
[09:00:04] DECISION: Carrier FEDEX-FREIGHT, route ATL→DFW, ETA 2 days
           Reasoning: Lowest cost within SLA window, no congestion alerts
```

## Architecture (Local)

```
┌─────────────────────────────────────┐
│           Docker Compose            │
├─────────────────────────────────────┤
│  Floci (port 4566)                  │
│  ├── EventBridge (event bus)        │
│  ├── DynamoDB (inventory/demand)    │
│  ├── S3 (decision archive)         │
│  └── Lambda (agent handlers)        │
├─────────────────────────────────────┤
│  Agent Runner (Python)              │
│  ├── demand_sensing.py              │
│  ├── inventory_allocation.py        │
│  ├── procurement.py                 │
│  ├── logistics.py                   │
│  └── disruption_response.py         │
└─────────────────────────────────────┘
```

## Files

```
examples/agentic-supply-chain-local/
├── docker-compose.yml          # Floci + agent runner
├── config/
│   ├── event-rules.json        # EventBridge rules connecting agents
│   └── agent-config.yaml       # Agent thresholds and boundaries
├── agents/
│   ├── run_demo.py             # Main demo orchestrator
│   ├── demand_sensing.py       # Agent 1
│   ├── inventory_allocation.py # Agent 2
│   ├── procurement.py          # Agent 3
│   ├── logistics.py            # Agent 4
│   └── disruption_response.py  # Agent 5
├── seed-data/
│   ├── inventory.json          # Starting inventory positions
│   ├── demand-history.json     # 30 days of demand baseline
│   └── suppliers.json          # Supplier catalog
└── README.md
```

## Customization

Edit `config/agent-config.yaml` to change:
- Decision thresholds (when to escalate vs. act autonomously)
- Confidence requirements per agent
- Simulated processing delays (default: 1s per agent for demo visibility)

Edit `seed-data/` to simulate different scenarios:
- Low inventory → triggers procurement agent
- Demand spike → triggers reallocation
- Supplier disruption → triggers disruption response cascade

## Tearing Down

```bash
docker compose down -v
```

Removes all containers and volumes. No state persists between runs.

## Notes

- This demo uses rule-based decision logic (no LLM calls) to keep it runnable offline with zero cost. The production architecture uses Bedrock for reasoning. The agent boundaries, event patterns, and decision flows are identical.
- Floci emulates 68 AWS services locally. Only EventBridge, DynamoDB, S3, and Lambda are used here.
- For the full CDK-based production deployment, see `architectures/agentic-supply-chain/aws-implementation/`.
