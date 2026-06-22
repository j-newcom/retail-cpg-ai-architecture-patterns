# From POC to Production: What Actually Changes

Every enterprise AI initiative starts the same way. A small team builds a proof-of-concept in 6-8 weeks. The demo impresses leadership. A budget gets approved to "productionize it." Twelve months later, the project is either dead or stuck in an integration purgatory that bears no resemblance to the original POC.

The gap between POC and production is not a scaling problem. It is a category change. The POC and the production system share a model and an intent. They share almost nothing else.

## What the POC Proves (and What It Doesn't)

A successful POC demonstrates three things:
- The model can perform the core task with acceptable accuracy on representative data
- The latency and cost are in the right ballpark
- A business user can interpret and act on the output

A POC does NOT prove:
- The system handles edge cases, missing data, and adversarial inputs gracefully
- The model's accuracy holds when data distribution shifts seasonally or during disruptions
- The infrastructure can sustain load at 100x the demo volume
- The organization can operate the system (monitor, retrain, escalate, debug) without the original builders
- The output integrates cleanly into downstream business processes

Each of these unproven areas becomes a workstream in the production build. Most of them are harder than the model itself.

## The Eight Things That Change

### 1. Data Pipeline Becomes the Largest Workstream

In the POC, data was loaded from a CSV, a database snapshot, or a curated S3 bucket. Someone cleaned it manually. Missing values were dropped. The team worked with a point-in-time extract that represented "good" data.

In production, data arrives continuously with gaps, delays, format changes, and schema drift. The pipeline must handle: late-arriving data (a retailer's POS feed delays 6 hours), missing data (a supplier system goes down for a day), duplicate data (an EDI feed retransmits), and contradictory data (two sources disagree on the same fact).

Data pipeline engineering typically consumes 40-60% of the total production build effort. The POC spent less than 10% of its time on data.

### 2. Error Handling Becomes a Design Discipline

The POC crashes when it encounters bad input. Someone restarts it.

Production systems need defined behavior for every failure mode: model timeout, upstream data unavailable, output validation failure, confidence below threshold, downstream system rejecting the action. Each failure mode needs a response path (retry, degrade gracefully, escalate, circuit-break).

Write the failure mode catalog before writing the production code. For every input the system receives, answer: "What happens when this is wrong, missing, or delayed?"

### 3. Monitoring Becomes Operational

The POC had no monitoring. Someone checked the output manually.

Production requires:
- **Model performance monitoring** — accuracy metrics tracked daily, drift detection triggering alerts when input distributions shift beyond training bounds
- **System health monitoring** — latency, throughput, error rates, queue depth
- **Business outcome monitoring** — are the decisions producing the expected business impact?
- **Cost monitoring** — inference cost per decision, total monthly spend against budget

The monitoring system for an AI application is frequently more complex than the application itself. This is normal and correct for enterprise deployment.

### 4. Security and Access Control Multiply Complexity

The POC ran on a data scientist's laptop with admin credentials to everything.

Production requires: IAM roles scoped to minimum necessary permissions, data encryption at rest and in transit, network isolation between components, audit logging of every decision and data access, PII handling compliance (if any product or customer data touches the model), and VPC configuration that allows model endpoints to reach data sources without traversing the public internet.

Security review adds 4-8 weeks to timeline. Plan for it from day one rather than treating it as a gate at the end.

### 5. The Model Becomes a Managed Asset

The POC model was trained once and deployed once.

In production, the model is a living asset that requires:
- **Retraining cadence** — monthly, quarterly, or triggered by drift detection
- **A/B testing infrastructure** — validating that a new model version outperforms the current one before full rollout
- **Rollback capability** — reverting to the previous version within minutes if the new one underperforms
- **Version registry** — tracking which model version produced which decisions for auditability
- **Feature store** — ensuring training features match inference features exactly (training-serving skew is the most common silent failure)

### 6. Integration Becomes Bidirectional

The POC produced output that a human copied into another system.

Production requires automated bidirectional integration:
- **Inbound:** real-time or near-real-time data feeds from source systems (ERP, WMS, POS, weather APIs)
- **Outbound:** writing decisions back into execution systems through their APIs, respecting their transaction semantics, rate limits, and validation rules
- **Confirmation:** receiving acknowledgment that the downstream system accepted the decision, and handling rejections

Every integration point is a potential failure point. Every failure point needs an error handling path. The number of integration points in production is typically 5-10x what the POC had.

### 7. The Team Changes Shape

The POC was built by 2-3 data scientists and maybe one engineer.

The production system is operated by:
- **ML Engineers** — pipeline development, model serving infrastructure, feature engineering
- **Data Engineers** — data pipeline reliability, schema management, quality monitoring
- **Platform/DevOps** — infrastructure, CI/CD, security, cost management
- **Domain SMEs** (planners, merchandisers, supply chain analysts) — guardrail calibration, edge case adjudication, model feedback
- **On-call rotation** — someone must respond when the 3 AM alert fires

The operational team is typically 3-5x larger than the build team. Budget for this from the start.

### 8. Success Metrics Become Accountable

The POC reported accuracy on a held-out test set. Leadership nodded.

Production reports to the P&L. The question shifts from "does the model work?" to "is the system generating measurable business value that exceeds its fully-loaded cost (infrastructure + team + opportunity cost)?"

This means:
- Defining the business KPI before launch (stockout reduction, margin improvement, throughput increase)
- Instrumenting the system to measure its causal contribution to that KPI (not just correlation)
- Reporting quarterly in business language to a leadership audience that does not care about F1 scores
- Having the intellectual honesty to kill the system if it doesn't deliver ROI within the agreed timeframe

## The Minimum Viable Production Checklist

Before declaring an AI system "production-ready" in a Retail or CPG enterprise, verify:

- [ ] Data pipeline handles 48-hour source outage gracefully (tested)
- [ ] Model accuracy monitored daily with drift alerts configured
- [ ] Every failure mode has a defined response path (documented)
- [ ] Security review complete, IAM roles scoped, encryption verified
- [ ] Integration tested bidirectionally with real systems (not mocks)
- [ ] Rollback procedure exists and has been exercised
- [ ] On-call rotation defined with escalation paths
- [ ] Business KPI baseline measured before go-live
- [ ] Cost monitoring active with budget alerts
- [ ] Runbook written for the top 10 operational scenarios
- [ ] Human escalation path tested end-to-end
- [ ] Model retraining pipeline automated and tested

If any item is unchecked, the system is not production-ready. It is a demo with production-like infrastructure.

## Related

- [Why Retail & CPG Companies Struggle with AI Adoption](why-retail-cpg-struggles-with-ai.md)
- [Agentic Architecture Patterns for Supply Chain](agentic-architecture-patterns.md)
