# Cost Optimization Guide

Strategies for managing and reducing the operational cost of the agentic supply chain system while maintaining decision quality.

## Cost Breakdown by Service

At steady state (5,000 SKUs, 12 DCs, ~50,000 decisions/day):

| Service | Monthly Cost | % of Total | Cost Driver |
|---|---|---|---|
| Amazon Bedrock (Claude Sonnet) | $8,000-12,000 | 55-65% | Inference calls: token volume × price per token |
| Amazon Neptune Serverless | $1,800 | 12% | NCU-hours consumed by graph queries |
| Amazon OpenSearch Serverless | $2,400 | 16% | OCU-hours for indexing + search |
| AWS Lambda | $400 | 3% | Invocations × duration × memory |
| Amazon EventBridge | $150 | 1% | Events published per month |
| Amazon SQS | $50 | <1% | Messages sent + received |
| AWS Step Functions | $600 | 4% | State transitions |
| Amazon S3 + CloudWatch | $300 | 2% | Storage + log ingestion + metrics |
| **Total** | **$13,700-17,700** | **100%** | |

Bedrock inference is the dominant cost. Optimization efforts should focus there first.

## Strategy 1: Model Tiering

Not every decision needs Claude Sonnet. Use a tiered model strategy:

| Decision Complexity | Model | Cost per 1K tokens (input/output) | When to Use |
|---|---|---|---|
| Complex reasoning | Claude Sonnet | $3.00 / $15.00 | Disruption response, multi-factor trade-offs |
| Standard decisions | Claude Haiku | $0.25 / $1.25 | Routine demand adjustments, carrier selection within budget |
| Classification only | Fine-tuned small model | $0.05 / $0.10 | Category assignment, signal routing |

**Implementation:** Add a pre-classification step in each agent that assesses decision complexity before invoking Bedrock. Route simple decisions to Haiku, complex ones to Sonnet.

**Expected savings:** 40-60% reduction in Bedrock costs. Most daily decisions (routine reorders, standard routing) are Haiku-eligible.

## Strategy 2: Prompt Caching and Deduplication

Many agent invocations share identical system prompts and context preambles. Bedrock prompt caching reduces cost for repeated prompt prefixes.

**Implementation:*\

\Structure prompts with a stable prefix (system instructions, agent role, constraints) and a variable suffix (current signal data\

\Enable Bedrock prompt caching for prefixes longer than 1,024 token\

\Cached prompt tokens cost 90% less than uncached

**Expected savings:** 20-30% reduction on qualifying invocations.

## Strategy 3: Decision Batching

Instead of invoking Bedrock once per signal, batch related signals and process them together.

**Example:** If 15 POS updates arrive within a 5-minute window for SKUs in the same category at the same DC, process them as a single batch prompt instead of 15 individual calls.

**Implementation:*\

\Add a batching window (configurable, default 5 minutes) to the demand sensing agen\

\Accumulate signals in a Lambda-internal buffer or short SQS delay queu\

\Process the batch as one Bedrock call with all signals in context

**Expected savings:** 50-70% reduction in demand sensing agent invocations (the highest-volume agent).

## Strategy 4: Confidence-Based Routing to Skip Bedrock

For signals that clearly fall within normal operating parameters, skip Bedrock entirely and apply a rule-based decision.

**Implementation:*\

\Before calling Bedrock, check if the signal falls within 1 standard deviation of the historical norm for that SKU/location/tim\

\If yes: no adjustment needed, suppress without invoking the mode\

\If no: proceed to Bedrock for reasoning

**Expected savings:** 30-50% reduction in demand sensing invocations. Most days, most SKUs are within normal range.

## Strategy 5: Neptune Serverless Scaling Bounds

Neptune Serverless charges per NCU-hour. Set minimum NCUs to 1 (default) and maximum based on peak query volume.

**Optimization:*\

\Review Neptune CloudWatch metrics weekl\

\If max NCUs never exceed 4, set the max to 5 (small buffer\

\If queries are primarily read-heavy, consider read replicas instead of scaling the write\

\Cache frequently-accessed graph traversals in Lambda memory (entity relationships don't change minute-to-minute)

## Strategy 6: OpenSearch Serverless Collection Management

OpenSearch Serverless charges per OCU-hour (minimum 2 OCUs for indexing, 2 for search).

**Optimization:*\

\If the vector collection is primarily queried during business hours (6 AM - 8 PM), consider time-based scaling policie\

\Archive decisions older than 90 days to S3 (cold storage) and remove from the vector inde\

\Keep only the most recent 10,000 decisions per agent in the active collection

## Strategy 7: Lambda Memory Right-Sizing

Lambda cost = (memory allocated) × (execution duration). Over-provisioning memory wastes money.

**Optimization:*\

\Use [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning) to find optimal memory for each agen\

\Most agents run well at 512MB. Disruption response (which processes larger context windows) may benefit from 1024M\

\Monitor `MaxMemoryUsed` metric — if consistently below 70% of allocated, reduce allocation

## Monthly Cost Targets

| Optimization Level | Monthly Cost | Savings vs. Baseline |
|---|---|---|
| Baseline (no optimization) | $13,700-17,700 | — |
| Model tiering only | $8,200-10,600 | ~40% |
| Tiering + batching + caching | $5,500-7,100 | ~60% |
| Full optimization (all strategies) | $4,000-5,500 | ~70% |

## Break-Even Analysis

The system pays for itself if it prevents supply chain losses that exceed its monthly cost. At the fully-optimized level ($4,000-5,500/month):

- **One prevented stockout** at a major retailer: $50K-500K saved (penalty fees + lost revenue\

\**One avoided expedited air shipment** (ocean-to-air escalation avoided): $200K+ save\

\**One week of improved demand accuracy** reducing safety stock: $30K-100K working capital freed

The system needs to prevent approximately one material incident per quarter to achieve positive ROI at the optimized cost level.
