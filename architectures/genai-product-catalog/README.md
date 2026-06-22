# GenAI Product Catalog Enrichment

## Problem Statement

Retail and CPG product catalogs are perpetually incomplete. Supplier-provided data arrives with missing attributes, inconsistent taxonomies, low-quality descriptions, and images that fail to meet channel requirements. A typical enterprise manages 50,000-500,000 SKUs, and at any given time 20-40% of items have data quality gaps that affect search performance, recommendation accuracy, and regulatory compliance.

Manual enrichment at scale is untenable. A single product specialist can fully enrich 15-25 items per day. At that rate, a backlog of 100,000 items represents 16-26 person-years of work. And the backlog grows continuously as new items onboard, seasonal rotations occur, and channel requirements evolve.

## What This Architecture Does

Automates the extraction, generation, and validation of product attributes from unstructured inputs (supplier PDFs, product images, web descriptions, ingredient panels). Uses foundation models for understanding and generation, with deterministic validation layers ensuring output meets taxonomy and regulatory standards.

The system does not replace human merchandisers. It produces draft enrichments that pass automated quality checks, reducing human effort from full creation to review-and-approve.

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Pipeline architecture (not real-time) | Catalog updates are batch-oriented. Processing 5,000 items overnight is more cost-effective than maintaining always-on inference endpoints for sporadic arrivals. |
| Multi-modal input processing | Product data arrives as PDFs (spec sheets), images (packaging), structured XML (supplier feeds), and plain text (web scrapes). A single-modality approach misses 40-60% of available signal. |
| Taxonomy-constrained generation | Foundation models generate candidate attributes, but a rules engine validates every output against the enterprise's taxonomy. Free-form generation without constraints produces creative but non-compliant data. |
| Human-in-the-loop for regulated categories | Food allergen declarations, nutritional claims, and safety warnings require human sign-off regardless of model confidence. The system flags these for mandatory review. |

## When to Use This Pattern

- Product catalog with more than 10,000 active SKUs
- Data quality gaps causing measurable search abandonment or recommendation failures
- Supplier onboarding velocity exceeding enrichment team capacity
- Multiple output channels requiring different attribute sets (ecommerce, marketplace, in-store, B2B)

## When NOT to Use This Pattern

- Catalog already has mature PIM (Product Information Management) with strong supplier data governance
- Fewer than 1,000 SKUs (manual enrichment is faster than building the pipeline)
- No defined product taxonomy (the system needs a target schema to enrich toward)

## Architecture Details

See [architecture.md](architecture.md) for the full technical breakdown.
