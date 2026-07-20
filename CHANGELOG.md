# Changelog

## [v0.2.0] - 2026-07-20

### Added
- `/examples/agentic-supply-chain-local/` — Full 5-agent supply chain demo running locally on Floci (free AWS emulator)
- Docker Compose configuration for zero-setup local deployment
- Seed data: 7 inventory positions, 30-day demand baselines, 3 contracted suppliers
- Agent scripts: demand sensing, inventory allocation, procurement, logistics, disruption response
- Configurable decision boundaries and confidence thresholds (`config/agent-config.yaml`)
- EventBridge routing rules for inter-agent communication (`config/event-rules.json`)
- "Examples (Runnable Locally)" section added to main README

## [v0.1.0] - 2026-07-07

### Added
- Initial release
- Agentic Supply Chain architecture with Mermaid diagrams, cost model, and implementation sequence
- Full AWS CDK implementation: 5 stacks, 6 Lambda handlers, IAM policies, event schemas
- Deployment guide, operational runbook, and cost optimization docs
- GenAI Product Catalog Enrichment architecture
- MCP Enterprise Patterns stub (placeholder)
- 2 Jupyter notebooks (demand forecasting, catalog enrichment)
- 3 technical perspective docs
- Supply chain anomaly detection script with `--demo` mode
- GitHub Actions workflow for markdown linting + link checking
- Apache 2.0 license
