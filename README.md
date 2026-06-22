# Retail & CPG AI Architecture Patterns

Reference architectures, working prototypes, and technical perspectives on artificial intelligence adoption in Retail and Consumer Packaged Goods.

## Who This Is For

Technical leaders evaluating AI strategies for retail and CPG enterprises. Solutions architects designing production systems at the intersection of supply chain, product data, and generative AI. Anyone building beyond the proof-of-concept stage in these verticals.

## What's Inside

### Reference Architectures

Production-tested patterns drawn from real enterprise deployments (sanitized, generalized, and documented for reuse).

| Architecture | Problem Space | Key Services |
|---|---|---|
| [Agentic Supply Chain Optimization](architectures/agentic-supply-chain/) | Autonomous decision-making across Plan, Procure, Make, Move, Sell | Bedrock, Step Functions, EventBridge |
| [GenAI Product Catalog Enrichment](architectures/genai-product-catalog/) | Automated attribute extraction, description generation, and image classification at scale | Bedrock, OpenSearch, Lambda |
| [MCP Enterprise Integration Patterns](architectures/mcp-enterprise-patterns/) | Connecting AI agents to legacy ERP, WMS, and demand planning systems via Model Context Protocol | MCP Servers, AgentCore, API Gateway |

### Notebooks

Hands-on demonstrations you can run locally or in SageMaker Studio.

| Notebook | What It Shows |
|---|---|
| [Demand Forecasting with Bedrock](notebooks/demand-forecasting-bedrock.ipynb) | Using foundation models to augment statistical forecasting with unstructured market signals |
| [Catalog Enrichment Pipeline](notebooks/catalog-enrichment-demo.ipynb) | End-to-end product data enrichment from raw supplier feeds to structured taxonomy |

### Technical Perspectives

Longer-form writing on adoption patterns, failure modes, and strategic considerations.

- [Why Retail & CPG Companies Struggle with AI Adoption](docs/why-retail-cpg-struggles-with-ai.md)
- [Agentic Architecture Patterns for Supply Chain](docs/agentic-architecture-patterns.md)
- [From POC to Production: What Actually Changes](docs/from-poc-to-production-ai.md)

### Scripts

Lightweight utilities that demonstrate a concept without the overhead of a full architecture.

- [Supply Chain Anomaly Detection](scripts/supply-chain-anomaly-detection/) — Statistical + ML hybrid approach for identifying demand signal disruptions

## Design Principles

Every architecture in this repo follows these constraints:

1. **Enterprise-grade by default.** No single points of failure. IAM least-privilege. Encryption at rest and in transit. These are table stakes, not add-ons.

2. **Composable over monolithic.** Each component can be adopted independently. No architecture requires wholesale adoption to deliver value.

3. **Domain-aware.** Retail and CPG have specific data shapes (hierarchical product taxonomies, promotional calendars, seasonal demand curves, complex distribution networks). Generic AI patterns fail when they ignore these realities.

4. **Cost-conscious at scale.** Every architecture includes a cost model section. Promising results at $500/month that become $500K/month in production is not a solution.

## About

I'm a technical leader focused on cloud architecture and AI adoption for Retail and CPG enterprises. I've led architecture teams across 30+ Fortune 500 CPG accounts and personally designed or reviewed AI systems for companies spanning $1B-$100B+ in annual revenue. This repo captures patterns I've seen work repeatedly across those engagements.

## License

[Apache 2.0](LICENSE)
