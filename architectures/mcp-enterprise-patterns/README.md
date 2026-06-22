# MCP Enterprise Integration Patterns

> **Status:** In progress. Architecture document coming in v0.2.0.

## Problem Statement

Enterprise AI agents need to interact with legacy systems (ERP, WMS, TMS, demand planning tools) that were never designed for AI consumption. These systems expose BAPI interfaces, IDoc message types, SOAP APIs, and proprietary protocols. Building point-to-point integrations between every agent and every backend system creates an unmaintainable web of connectors.

Model Context Protocol (MCP) provides a standard interface layer between AI agents and external tools/data sources. This architecture defines patterns for deploying MCP servers that bridge the gap between modern agentic architectures and legacy enterprise backends in Retail and CPG.

## Planned Content

- MCP server taxonomy for supply chain (read-only data servers vs. action servers vs. hybrid)
- Security model: OAuth2 token-passthrough, service-to-service auth, and audit logging
- SAP integration patterns via OData and RFC/BAPI
- Performance patterns: caching layers, connection pooling, and request batching for high-latency backends
- Deployment topology: sidecar vs. centralized gateway vs. per-system dedicated servers
- Error handling: translating backend errors into agent-comprehensible context

## Related

- [Agentic Supply Chain Optimization](../agentic-supply-chain/architecture.md) — uses MCP for ERP integration
- [Agentic Architecture Patterns](../../docs/agentic-architecture-patterns.md) — pattern context
