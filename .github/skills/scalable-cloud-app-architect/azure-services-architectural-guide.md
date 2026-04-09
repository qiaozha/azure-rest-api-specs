# Azure Services from an Architectural Perspective

## A Decision Guide for Cloud Architects

> **Audience:** Cloud architects, platform engineers, and technical leads evaluating Azure services for scalable, production-grade applications.
>
> **Scope:** This guide covers how to think about Azure service selection across every layer of a modern cloud application — from compute to data to edge networking — with concrete trade-off analysis and worked examples drawn from a real multi-tier API platform deployment.

---

## Table of Contents

1. [The Five Dimensions of Architectural Decisions](#1-the-five-dimensions-of-architectural-decisions)
2. [Service Taxonomy: Azure Services by Architectural Category](#2-service-taxonomy-azure-services-by-architectural-category)
3. [Compute: Where Your Code Runs](#3-compute-where-your-code-runs)
4. [Database: Where Your Data Lives](#4-database-where-your-data-lives)
5. [Caching: The Speed Layer](#5-caching-the-speed-layer)
6. [API Gateway & Ingress: How Traffic Enters](#6-api-gateway--ingress-how-traffic-enters)
7. [Edge & CDN: The Global Entry Point](#7-edge--cdn-the-global-entry-point)
8. [Observability: How You See What's Happening](#8-observability-how-you-see-whats-happening)
9. [Identity & Security: Who Can Do What](#9-identity--security-who-can-do-what)
10. [Messaging: How Services Talk to Each Other](#10-messaging-how-services-talk-to-each-other)
11. [Worked Example: Building a Scalable E-Commerce API Platform](#11-worked-example-building-a-scalable-e-commerce-api-platform)
12. [Parameter Reference: Tunable Knobs Across the Stack](#12-parameter-reference-tunable-knobs-across-the-stack)
13. [Decision Flowcharts](#13-decision-flowcharts)

---

## 1. The Five Dimensions of Architectural Decisions

Every Azure service choice involves balancing the same five forces. Understanding these dimensions prevents ad-hoc decision-making and gives your team a shared vocabulary.

### 1.1 Reversibility

How hard is it to change this decision later?

- **Easy to reverse:** Switching monitoring backends (Azure Monitor → Datadog), changing cache TTLs, adjusting alert thresholds
- **Medium to reverse:** Swapping API gateways (APIM → Kong), changing Front Door SKUs, adding a message broker
- **Hard to reverse:** Changing database engines (SQL → PostgreSQL), switching compute platforms (AKS → Container Apps), moving from microservices to monolith

**Rule of thumb:** Spend decision-making time proportional to reversibility cost. If it's easy to change, pick something and iterate. If it's hard to change, invest in prototyping.

### 1.2 Cost Structure

Azure services have fundamentally different pricing models:

| Pricing Model | Examples | Best When |
|---|---|---|
| **Pay-per-request** | Functions, APIM Consumption, Cosmos DB (RU) | Variable/spiky traffic |
| **Pay-per-unit-time** | AKS nodes, Redis Premium, APIM StandardV2 | Steady baseline traffic |
| **Serverless auto-pause** | SQL Serverless, Container Apps (scale-to-zero) | Dev/test, low-traffic services |
| **Reserved/committed** | Reserved VMs, Cosmos DB reserved capacity | Predictable production workloads |

The same workload can cost 10x more on the wrong pricing model. A service handling 100 requests/day on a Premium Redis P1 (~$440/mo) could use APIM's built-in cache for $0 incremental cost.

### 1.3 Operational Complexity

Who will be paged at 3 AM when this breaks?

| Complexity Level | What You Manage | Examples |
|---|---|---|
| **Fully managed** | Nothing — the platform handles scaling, patching, HA | Azure Functions, Cosmos DB, Front Door |
| **Semi-managed** | Configuration, sizing, some scaling | AKS (node pools), APIM, SQL Flexible |
| **Self-hosted** | Everything — install, patch, scale, backup, HA | PostgreSQL on VMs, Redis on AKS, NGINX on VMs |

The operational cost of a service is often larger than its Azure bill. An AKS cluster is "cheaper" than Container Apps per-unit, but requires Kubernetes expertise (RBAC, networking, upgrade cadence, node pool management) that Container Apps abstracts away entirely.

### 1.4 Resilience Ceiling

What's the maximum availability this service can achieve?

| SLA Tier | Services | Notes |
|---|---|---|
| **99.999%** (5 nines) | Cosmos DB (multi-region write) | ~5 min downtime/year |
| **99.99%** (4 nines) | Front Door, AKS (with zones), SQL Business Critical | ~52 min downtime/year |
| **99.95%** (3.5 nines) | AKS (standard), APIM Standard, Redis Premium | ~4.4 hr downtime/year |
| **99.9%** (3 nines) | App Service, SQL Serverless, Storage (LRS) | ~8.8 hr downtime/year |

Your system's overall availability is bounded by the *lowest* SLA in the critical path. Paying for Cosmos DB's 99.999% SLA is wasted if your SQL Serverless database (99.9%) is also in the hot path.

### 1.5 Lock-in Gradient

How portable is this choice?

| Lock-in Level | Examples | Mitigation |
|---|---|---|
| **Low** | PostgreSQL, Redis, Kubernetes, NGINX | OSS standards, run anywhere |
| **Medium** | AKS (K8s portable, but Azure CNI/add-ons aren't), Azure SQL (T-SQL is proprietary) | Abstract behind interfaces |
| **High** | Cosmos DB (custom query engine), Azure Functions bindings, Front Door rules | Accept or invest in abstraction layers |

---

## 2. Service Taxonomy: Azure Services by Architectural Category

Before choosing individual services, understand the full landscape organized by what they *do*, not how they're marketed.

### Compute — Where Code Executes

| Service | Model | Min Scale | Max Scale | K8s Required? |
|---|---|---|---|---|
| **Azure Kubernetes Service (AKS)** | Container orchestration | 1 node | 5,000 nodes | Yes (you own it) |
| **Azure Container Apps** | Serverless containers | 0 (scale-to-zero) | 300 replicas | No (K8s abstracted) |
| **Azure App Service** | PaaS web hosting | 1 instance | 30 instances | No |
| **Azure Functions** | Event-driven serverless | 0 | 200 instances | No |
| **Azure Container Instances** | Single container/group | 1 container | 100 container groups | No |

### Database — Relational

| Service | Engine | Compute Model | Max Size | Multi-Region |
|---|---|---|---|---|
| **Azure SQL Database** | SQL Server (T-SQL) | Provisioned / Serverless / Hyperscale | 100 TB (Hyperscale) | Failover groups |
| **Azure SQL Managed Instance** | SQL Server (near-100%) | Provisioned | 16 TB | Failover groups |
| **Azure Database for PostgreSQL Flexible** | PostgreSQL | Provisioned / Burstable | 64 TB | Read replicas |
| **Azure Database for MySQL Flexible** | MySQL | Provisioned / Burstable | 16 TB | Read replicas |
| **Cosmos DB for PostgreSQL (Citus)** | PostgreSQL + Citus | Distributed | 2 TB/shard × N | No native multi-region |

### Database — NoSQL / Document

| Service | Data Model | Pricing | Global Distribution | Consistency |
|---|---|---|---|---|
| **Cosmos DB (NoSQL API)** | JSON documents | RU-based (autoscale) | Multi-region read/write | 5 levels (Strong → Eventual) |
| **Cosmos DB (MongoDB API)** | BSON documents | RU-based | Multi-region | Same 5 levels |
| **Cosmos DB for MongoDB (vCore)** | BSON documents | vCore-based (fixed) | No native multi-region | MongoDB default |
| **Azure Table Storage** | Key-value | Per-transaction | GRS replication | Eventual |

### Caching

| Service | Engine | Latency | Persistence | Modules |
|---|---|---|---|---|
| **Azure Cache for Redis** | Redis OSS | Sub-ms | Optional (Premium+) | No |
| **Azure Managed Redis** | Redis Stack | Sub-ms | Yes | RediSearch, RedisJSON, etc. |
| **APIM built-in cache** | Internal | In-process | No | N/A (policy-driven) |

### API Management & Gateway

| Service | Scope | Developer Portal | VNet Integration | Pay Model |
|---|---|---|---|---|
| **APIM Consumption** | Serverless gateway | Yes | No | Per-call |
| **APIM StandardV2** | Dedicated gateway | Yes | No | Per-unit |
| **APIM Premium** | Enterprise gateway | Yes | Yes (VNet injection) | Per-unit |
| **Application Gateway for Containers** | K8s L7 ingress | No | Yes (AKS VNet) | Included with AKS |
| **Azure Application Gateway** | Regional L7 LB | No | Yes | Per-gateway + per-GB |

### Edge / CDN / WAF

| Service | Scope | WAF | CDN | SSL Offload |
|---|---|---|---|---|
| **Front Door Premium** | Global edge | Yes (managed rules) | Yes | Yes |
| **Front Door Standard** | Global edge | Basic custom rules | Yes | Yes |
| **Azure CDN** | Content delivery only | No | Yes | Yes |
| **Application Gateway + WAF** | Regional only | Yes (OWASP) | No | Yes |

### Observability

| Service | Type | Query Language | Integration |
|---|---|---|---|
| **Log Analytics** | Log aggregation | KQL | Native Azure |
| **Application Insights** | APM / distributed tracing | KQL | Auto-instrumentation (Java, .NET, Node, Python) |
| **Azure Monitor Metrics** | Time-series metrics | Metric queries | Native Azure |
| **Azure Managed Grafana** | Dashboarding | PromQL + KQL | Multi-source (Azure, Prometheus, etc.) |

### Messaging / Eventing

| Service | Pattern | Ordering | Max Throughput | Retention |
|---|---|---|---|---|
| **Azure Service Bus** | Queue / topic-subscription | FIFO (sessions) | ~1,000 msg/s per unit | 14 days (Standard) |
| **Azure Event Hubs** | Event streaming (log) | Per-partition | Millions/sec | 1–90 days |
| **Azure Event Grid** | Reactive event routing | No guarantee | 10M events/sec | 24 hr retry |
| **Azure Queue Storage** | Simple queue | No | 20,000 msg/s | 7 days |

---

## 3. Compute: Where Your Code Runs

This is the highest-impact, hardest-to-reverse decision in the stack. It determines your team's daily developer experience, operational burden, and cost structure.

### The Three-Way Decision: AKS vs Container Apps vs App Service

#### Choose AKS when:

- You need **Kubernetes-native features**: custom operators, CRDs, DaemonSets, init containers, sidecar injection, node-level tuning
- Your team has **dedicated platform engineering** capacity to manage cluster upgrades, node pool sizing, network policies, RBAC
- You need **GPU workloads**, **Windows containers**, or **bare-metal performance tuning**
- You're running **stateful workloads** (databases, ML training) alongside stateless APIs
- You need a **service mesh** (Istio, Linkerd) for mTLS and traffic shifting

**Operational reality:** AKS gives you a Kubernetes API. That means you own node pool upgrades, autoscaler tuning, network plugin selection (Azure CNI vs Overlay vs Kubenet), pod disruption budgets, and the entire YAML/Helm/Kustomize toolchain. For a team without Kubernetes experience, the learning curve alone can delay delivery by months.

#### Choose Container Apps when:

- You want **container-based microservices without managing Kubernetes**
- You need **scale-to-zero** (true serverless containers) to minimize cost during low traffic
- You want **built-in Dapr integration** for service discovery, state management, Pub/Sub
- **KEDA-based autoscaling** (HTTP, queue depth, custom metrics) fits your scaling triggers
- Your services are **stateless HTTP APIs** or **background processors** consuming queues

**Operational reality:** Container Apps abstracts the Kubernetes control plane entirely. You define container images, scaling rules, and ingress — the platform handles node provisioning, upgrades, and networking. The trade-off is less control: no DaemonSets, no custom CNI plugins, no node-level SSH, max 300 replicas per app.

#### Choose App Service when:

- Your workload is **traditional web apps** (ASP.NET, Node.js, Python Flask/Django, Java Spring)
- You want the **simplest deployment model**: git push, ZIP deploy, or GitHub Actions with zero container knowledge
- **Deployment slots** (blue-green) are a key requirement
- Your team is **small** and doesn't want to learn containers or Kubernetes
- You need **Windows hosting** with .NET Framework (not .NET Core)

**Operational reality:** App Service is the fastest path from code to URL. But it scales as a unit (1 app = 1 plan), pricing is per-instance (no scale-to-zero on Standard+), and you have no control over the underlying infrastructure.

### Cost Comparison (Illustrative)

For a workload running 4 microservices, each needing 0.5 vCPU / 1 GiB RAM:

| Platform | Idle Cost (0 traffic) | Moderate Load | Burst (10x) | Annual Estimate |
|---|---|---|---|---|
| **AKS** (3-node D4s_v5) | ~$440/mo (nodes always on) | ~$440/mo | ~$1,500/mo (autoscale) | ~$6,000–$18,000 |
| **Container Apps** (Consumption) | ~$0 (scale-to-zero) | ~$60/mo | ~$600/mo | ~$720–$7,200 |
| **App Service** (S1 × 4) | ~$280/mo | ~$280/mo | ~$700/mo (scale-out) | ~$3,400–$8,400 |

*AKS is the most expensive at low traffic but the cheapest per-unit at high scale. Container Apps wins at variable traffic. App Service wins at simplicity.*

---

## 4. Database: Where Your Data Lives

Database choices are the **hardest to reverse** because they involve data model design, query language expertise, and migration complexity. The first question isn't "which Azure database service?" — it's "what kind of data model does my workload need?"

### Relational vs Document: The Foundational Split

| If your data is... | Choose | Why |
|---|---|---|
| Highly structured with complex joins (orders, transactions, inventory) | **Relational** (SQL, PostgreSQL, MySQL) | ACID transactions, referential integrity, SQL standard |
| Schema-flexible with nested objects (product catalogs, user profiles, IoT telemetry) | **Document** (Cosmos DB, PostgreSQL JSONB) | Schema evolution, hierarchical data, horizontal scaling |
| Both | **PostgreSQL Flexible** (relational + JSONB) or **separate engines** | One engine vs two to operate |

### Within Relational: Azure SQL vs PostgreSQL vs MySQL

This is where the nuance matters most:

#### Azure SQL Database

- **Best for:** Microsoft-ecosystem shops (Power BI, SSIS, SSRS, .NET), T-SQL expertise, Serverless auto-pause (cost savings for intermittent workloads)
- **Unique features:** Serverless compute model (auto-pause after idle), Hyperscale (100 TB), built-in AI query tuning, temporal tables
- **Lock-in concern:** T-SQL is proprietary; migration to PostgreSQL requires query rewriting
- **Serverless nuance:** Auto-pause saves money but introduces 1–2 second cold-start latency on first request after idle. Acceptable for dev/test and background jobs; problematic for latency-sensitive user-facing APIs

#### Azure Database for PostgreSQL Flexible Server

- **Best for:** OSS-first teams, extension ecosystem (pgvector for AI embeddings, PostGIS for geospatial, pg_cron for scheduling, Citus for sharding), multi-cloud portability
- **Unique features:** 100+ extensions, JSONB columns (document-store-in-a-relational-db), logical replication, PgBouncer built-in
- **Lock-in concern:** Low — PostgreSQL runs everywhere (AWS RDS, GCP Cloud SQL, self-hosted)
- **Nuance:** If your "document store" needs are modest (< 100 GB, single-region), PostgreSQL with JSONB columns can replace Cosmos DB entirely, cutting one engine from your stack

#### Azure Database for MySQL Flexible Server

- **Best for:** WordPress/PHP ecosystems, teams with MySQL expertise, simple OLTP with fewer advanced features needed
- **Unique features:** Familiar to the widest developer base, solid InnoDB performance
- **Lock-in concern:** Low — MySQL runs everywhere
- **Nuance:** MySQL lacks PostgreSQL's extension ecosystem (no pgvector, no PostGIS). For new greenfield projects on Azure, PostgreSQL Flexible is generally preferred unless there's an existing MySQL codebase

### Within Document: Cosmos DB vs Alternatives

#### Azure Cosmos DB (NoSQL / SQL API)

- **Best for:** Global applications needing multi-region read/write, sub-10ms reads at any scale, guaranteed SLAs up to 99.999%
- **Unique features:** 5 tunable consistency levels (Strong, Bounded Staleness, Session, Consistent Prefix, Eventual), automatic indexing, turnkey global distribution
- **Cost concern:** RU-based pricing can surprise teams unfamiliar with the model. A poorly designed partition key or unoptimized query can burn 100x the expected RUs
- **When to avoid:** Single-region apps, budget-constrained projects, data < 50 GB, workloads that need complex joins or transactions across partitions

#### PostgreSQL JSONB (as a document store alternative)

- **Best for:** Teams already using PostgreSQL for relational data who want to avoid operating two database engines
- **Trade-off:** No global distribution, no RU-based autoscale, but also no RU cost surprises. Query performance is excellent for moderate document sizes (< 1 MB per document)
- **When to prefer over Cosmos DB:** Single-region, < 100 GB documents, team has PostgreSQL expertise, want one engine for both relational and document data

### The Partition Key Decision (Cosmos DB)

The single most important Cosmos DB design choice — made once, nearly impossible to change:

| Workload | Good Partition Key | Bad Partition Key | Why |
|---|---|---|---|
| Product catalog | `/categoryId` | `/id` (too granular) or `/status` (too few values) | Categories distribute evenly; status has only 3-4 values (hot partition) |
| User profiles | `/userId` | `/country` (skewed) | User IDs are uniformly distributed |
| Order history | `/customerId` | `/orderDate` (temporal hot partition) | Queries usually filter by customer |

---

## 5. Caching: The Speed Layer

Caching decisions are medium-reversibility but high-cost-impact. The question isn't just "do we need a cache?" but "at which layer should caching happen?"

### Caching Layers in a Multi-Tier Architecture

```
Client ──→ Front Door (CDN caching: static assets, 1-24 hr TTL)
              ↓
           APIM (Response caching: API responses, 30s-5min TTL)
              ↓
           App Code (In-process cache: L1, lost on restart)
              ↓
           Redis (Distributed cache: sessions, computed results, 1min-1hr TTL)
              ↓
           Database (Query result cache: Cosmos DB integrated cache)
```

Each layer has different characteristics:

| Layer | Latency | Shared Across Instances? | Survives Restart? | Cost |
|---|---|---|---|---|
| **Front Door CDN** | ~1 ms (edge POP) | Yes (globally) | Yes | Included in Front Door |
| **APIM built-in cache** | ~1 ms (in-process) | No (per APIM unit) | No | Included in APIM |
| **In-app memory** | ~0.01 ms | No | No | Free (uses app RAM) |
| **Redis** | ~1 ms (network hop) | Yes (all instances) | Yes (Premium+) | $50–$450+/mo |
| **Cosmos DB integrated cache** | ~2 ms (same region) | No (per gateway) | No | Free (uses gateway RAM) |

### When You Need Redis vs When You Don't

**Skip Redis if:**
- Your only caching need is API response caching → APIM built-in `<cache-lookup>` / `<cache-store>` policies handle this with zero extra infrastructure
- Your data layer is Cosmos DB and you only need repeated-read caching → enable Cosmos DB integrated cache
- Your app runs as a single instance → in-process `IMemoryCache` is simpler and faster

**Use Redis when:**
- You need a **shared cache** across multiple app instances (session state, shopping cart, rate limiting counters)
- You need **Pub/Sub** for real-time features (notifications, cache invalidation)
- You need **distributed data structures** (sorted sets for leaderboards, HyperLogLog for unique counts)
- You need **cache persistence** that survives app restarts

### Redis SKU Decision

| Scenario | Recommended SKU | Why |
|---|---|---|
| Dev/test | Standard C0 | Cheapest with SLA |
| Production API caching only | Standard C1 | HA, no persistence needed |
| Session store + Pub/Sub | Premium P1 | Persistence, VNet, zones |
| Full-text search, JSON queries | Enterprise E10 | Redis Stack modules |

---

## 6. API Gateway & Ingress: How Traffic Enters

The API gateway question often conflates two different concerns: **traffic management** (L7 routing, load balancing, TLS termination) and **API lifecycle management** (rate limiting, developer portal, subscription keys, policies).

### Traffic Management vs API Lifecycle

| Concern | APIM | Application Gateway for Containers (AGC) | NGINX Ingress |
|---|---|---|---|
| L7 routing | ✅ (via API paths) | ✅ (Gateway API CRDs) | ✅ (Ingress resources) |
| Rate limiting | ✅ (policy) | ❌ | ✅ (annotations) |
| JWT validation | ✅ (policy) | ❌ | ❌ (needs authz middleware) |
| Developer portal | ✅ | ❌ | ❌ |
| Subscription keys | ✅ | ❌ | ❌ |
| Response caching | ✅ (built-in) | ❌ | ❌ |
| Request/response transformation | ✅ (policy) | ❌ | Limited |
| Azure-native integration | Deep | Deep | Community |
| Cost (incremental) | $160+/mo (StandardV2) | Included with AKS | Free (self-hosted) |

### When to Use APIM vs Skip It

**Use APIM when:**
- Your APIs are consumed by **external third parties** who need self-service onboarding, API keys, usage analytics
- You need **cross-cutting API policies** (JWT validation, rate limiting, IP filtering, CORS, response transformation) without embedding them in application code
- You want a **developer portal** for API documentation and testing
- You need **multi-backend routing** where a single API fronts multiple microservices

**Skip APIM when:**
- All APIs are **internal** (service-to-service within a VNet)
- Your ingress controller (AGC, NGINX) handles routing, and your app framework handles auth
- Cost sensitivity is high and the API management features aren't needed

### APIM SKU Decision

| Scenario | SKU | Provisioning Time | Monthly Cost | Differentiator |
|---|---|---|---|---|
| Variable traffic, no VNet | Consumption | Instant | Pay-per-call (~$3.50/10K calls) | Scale-to-zero, cold starts |
| Steady production traffic | StandardV2 | ~5 min | ~$160 | Fast provisioning, no VNet |
| Enterprise, VNet-injected | Premium | ~30-45 min | ~$700+ | VNet, multi-region, capacity units |

---

## 7. Edge & CDN: The Global Entry Point

### Front Door Premium vs Standard vs Application Gateway

The decision tree is straightforward:

1. **Is this internet-facing?** If internal-only → skip Front Door, use Private Endpoints + internal load balancer
2. **Do you need WAF with managed rule sets (OWASP, bot protection)?** Yes → Front Door Premium. No → Standard may suffice
3. **Is your app single-region?** If so, consider Application Gateway (regional) + WAF v2 instead of Front Door (~$335/mo savings)
4. **Do you need CDN for static assets?** Front Door includes CDN; Application Gateway does not

### Cost Reality

| Configuration | Monthly Base Cost | CDN Included | WAF OWASP Rules |
|---|---|---|---|
| Front Door Premium | ~$330 | Yes | Yes (managed) |
| Front Door Standard | ~$35 | Yes | Custom rules only |
| Application Gateway WAF v2 | ~$225 | No | Yes (OWASP 3.2) |
| No edge layer (APIM direct) | $0 | No | No |

For a single-region app with no CDN needs, Application Gateway WAF v2 is often the better fit. Front Door Premium makes sense when you need **global distribution** (multiple regions, anycast edge POPs) or **Private Link origins**.

---

## 8. Observability: How You See What's Happening

### The Azure Monitor Stack

Azure Monitor is not one service but a family:

```
Azure Monitor
├── Log Analytics Workspace    ← stores all logs (KQL queries)
├── Application Insights       ← APM: traces, dependencies, exceptions
├── Metrics                    ← time-series: CPU, memory, latency, custom metrics
├── Alerts                     ← metric/log conditions → action groups
├── Workbooks                  ← interactive dashboards
└── Diagnostic Settings        ← per-resource log/metric routing
```

### Key Architectural Decisions

**Log retention (days):** Directly affects cost. Log Analytics charges ~$2.76/GB ingested + $0.12/GB/day beyond free retention. The default 30 days is often too short for incident investigation; 90 days is a common production baseline.

**Sampling rate (Application Insights):** At high traffic, full telemetry collection can cost more than the app itself. Adaptive sampling (default) helps, but architect your instrumentation budget:

| Traffic Level | Recommended Sampling | Rationale |
|---|---|---|
| < 10K req/day | 100% (no sampling) | Full visibility, negligible cost |
| 10K–1M req/day | Adaptive sampling (default) | AI adjusts rate automatically |
| > 1M req/day | Fixed 10–25% + always-sample errors | Cost control; keep 100% for failures |

### Azure Monitor vs External Alternatives

| Factor | Azure Monitor | Datadog | Grafana Cloud |
|---|---|---|---|
| Azure-native integration | Best (auto-discovery, diagnostic settings) | Good (Azure integration tile) | Good (Azure data source) |
| Multi-cloud | Azure-only | Yes | Yes |
| APM depth | Good (App Insights) | Excellent | Moderate (depends on backend) |
| Query language | KQL | Proprietary | PromQL + LogQL |
| Cost model | Per-GB ingested | Per-host ($15–$34/host/mo) | Per-metric, per-log-volume |
| Lock-in | Medium (KQL, Log Analytics schema) | Medium (proprietary agents) | Low (OSS standards) |

---

## 9. Identity & Security: Who Can Do What

### Entra ID as the Central Identity Plane

In Azure-native architectures, Microsoft Entra ID serves as both the **user identity provider** (OAuth 2.0 / OIDC for end users) and the **service identity provider** (Managed Identity for service-to-service).

### The Zero-Secret Architecture

Modern Azure architectures should aim for **zero stored secrets**:

| Connection | Old Way (secrets) | New Way (identity-based) |
|---|---|---|
| App → Cosmos DB | Connection string with key | Managed Identity + RBAC (`Cosmos DB Data Contributor`) |
| App → SQL | SQL username/password | Managed Identity + Entra-only auth |
| App → Storage | Storage account key | Managed Identity + RBAC (`Storage Blob Data Contributor`) |
| App → Redis | `password=...` in connection string | Managed Identity + Entra auth (Redis 6+) |
| APIM → Backend | API key in header | Managed Identity + backend credential |

This isn't just a security best practice — it eliminates secret rotation, Key Vault dependency for runtime secrets, and the entire class of leaked-credential incidents.

### WAF Mode: Prevention vs Detection

A commonly debated decision:

- **Detection mode first:** Log all WAF triggers for 2–4 weeks without blocking. Analyze false positives (legitimate requests flagged by OWASP rules). Create exclusions. Then switch to Prevention.
- **Prevention from day one:** If you're deploying a new app with no existing traffic to analyze, you can start in Prevention mode with the default rule set. False positives are less likely without legacy traffic patterns.

**Recommendation:** For greenfield deployments, start with **Prevention mode** and monitor the WAF logs for the first week. For brownfield (existing apps migrating to Front Door), start with **Detection mode**.

---

## 10. Messaging: How Services Talk to Each Other

### The Missing Layer in Many Architectures

A purely request-driven architecture (REST-only, synchronous) works for simple CRUD but breaks down when you need:

- **Order processing sagas** (payment → inventory → shipping — any step can fail)
- **Async workloads** (image processing, report generation, email sending)
- **Event-driven reactions** (user signed up → send welcome email + create profile + update analytics)
- **Decoupling** (service A doesn't need to know if service B is up)

### Service Bus vs Event Hubs vs Event Grid

These three services are often confused. They serve fundamentally different patterns:

| Pattern | Service | Analogy |
|---|---|---|
| **Command/task queue** (do this exactly once) | **Service Bus** | Post office: addressed envelope, guaranteed delivery |
| **Event stream** (what happened, replay from any point) | **Event Hubs** | Security camera: continuous recording, rewind any time |
| **Event notification** (something happened, react) | **Event Grid** | Doorbell: push notification, fire-and-forget |

**Practical test:** If you say "process this order" → Service Bus. If you say "order #1234 was placed" (and multiple systems care) → Event Grid. If you say "give me all events from the last 6 hours" → Event Hubs.

---

## 11. Worked Example: Building a Scalable E-Commerce API Platform

To ground these concepts, here's how the decisions play out for a real reference architecture: a **scalable e-commerce API platform** with product browsing, user profiles, order management, and content delivery.

### Architecture Choices Made

```
Internet Users
    ↓
Azure Front Door Premium              ← Global edge + WAF (OWASP + Bot)
    ↓
Azure API Management (StandardV2)     ← API gateway (JWT, rate limit, cache)
    ↓
Application Gateway for Containers    ← K8s-native L7 ingress
    ↓
Azure Kubernetes Service              ← 4 microservices (products, profiles, orders, content)
    ↓
┌──────────────────┬────────────────────┬──────────────────┬──────────────────┐
│ Cosmos DB        │ Azure SQL          │ Blob Storage     │ Redis Premium    │
│ (products,       │ (orders,           │ (media,          │ (session cache,  │
│  profiles)       │  subscriptions)    │  documents)      │  API cache)      │
└──────────────────┴────────────────────┴──────────────────┴──────────────────┘
```

### Why These Choices (and What the Alternatives Were)

#### Compute: AKS (not Container Apps)

**Decision rationale:** The team had Kubernetes expertise, needed custom CRDs for service mesh (Istio), and required node-level tuning for memory-intensive product search indexing.

**If starting over with a smaller team:** Container Apps would eliminate Phases 4.1–4.2 entirely (no node pool management, no AGC setup, no subnet delegation, no feature flag registration). The 4 microservices are stateless HTTP APIs — exactly what Container Apps is designed for.

**What changed in the deployment plan because of this choice:**
- Phase 4.1: AKS cluster creation + workload node pool (7 CLI commands, ~15 min)
- Phase 4.2: AGC traffic controller + frontend + association (10 CLI commands, ~10 min)
- Phase 4.2 workarounds: CLI extension cache issues required `az rest` fallbacks
- Phase 4.2 constraints: Region collocation (AGC must be same region as AKS subnet), subnet delegation

*With Container Apps: a single `az containerapp env create` + 4 × `az containerapp create` — no node pools, no AGC, no subnet delegation.*

#### Document Store: Cosmos DB (not PostgreSQL JSONB)

**Decision rationale:** The product catalog requires multi-region read distribution (users in US East and US West), and the profile store needs guaranteed sub-10ms point reads at any scale.

**If the app were single-region:** PostgreSQL Flexible with JSONB columns would work for both product catalog and user profiles. One database engine instead of two (Cosmos DB + SQL), simpler operations, lower cost (~$100/mo for a 2-vCore Flexible server vs ~$200/mo+ for Cosmos DB at 4,000+ RU/s autoscale).

**What Cosmos DB added to the deployment plan:**
- Org-policy workaround: `disableLocalAuth` and `disableKeyBasedMetadataWriteAccess` required `az rest` instead of `az cosmosdb create`
- Subscription limitation: `isZoneRedundant: true` failed in eastus — required explicit `false` for both regions
- Two separate database/container hierarchies (productdb + profiledb)
- Partition key design: `/categoryId` for products, `/userId` for profiles

#### Relational Store: Azure SQL Serverless (not PostgreSQL)

**Decision rationale:** The orders and subscriptions databases have intermittent traffic (order spikes during business hours, near-zero overnight). SQL Serverless auto-pause saves ~60% vs provisioned, and the team had T-SQL expertise from existing systems.

**Trade-off accepted:** 1–2 second cold-start latency when the database resumes from auto-pause. This was acceptable because order placement is a multi-step process (cart → checkout → payment) — the first step warms the database before the write-heavy steps.

**If cold starts were unacceptable:** Switch to Provisioned compute (always on) or consider PostgreSQL Flexible (which doesn't have auto-pause but has lower base cost for always-on workloads).

#### Cache: Redis Premium (partially over-provisioned)

**Decision rationale:** Redis was provisioned for both APIM external caching and application-level session caching.

**What actually happened:** APIM's built-in `<cache-store>` policy (Phase 5.4b) handles API response caching without Redis. The Redis named value (`redis-connection`) was created in APIM but never referenced in any policy. The Redis instance is effectively unused infrastructure costing ~$440/month.

**Lesson:** Start without a dedicated cache and add one only when a specific need (shared session state, Pub/Sub, distributed locks) is identified through load testing. APIM's built-in cache and Cosmos DB's integrated cache cover most read-heavy API caching needs.

#### Edge: Front Door Premium (not Standard, not Application Gateway)

**Decision rationale:** Need for WAF managed rule sets (OWASP 2.1 + BotManager 1.1) and global anycast for users in multiple regions.

**If single-region, internal APIs:** Skip Front Door entirely. APIM has its own public endpoint. Add Application Gateway + WAF v2 only if WAF is required by compliance.

### Dependency Chain Visualization

Every architecture choice creates a dependency chain that affects deployment order and failure modes:

```
Front Door → APIM → AGC → AKS → Data Layer
                ↑                    ↑
                │                    │
         App Insights IKEY     Connection endpoints
              (Phase 2)          (Phase 3)
```

The critical insight: **observability (Phase 2) must deploy before everything else** so diagnostic settings can wire into resources as they're created. **Data layer (Phase 3) must deploy before compute (Phase 4)** because connection strings are needed at container startup. **Compute (Phase 4) must deploy before APIM (Phase 5)** because APIM needs the AGC frontend FQDN as a backend URL.

---

## 12. Parameter Reference: Tunable Knobs Across the Stack

Every service exposes parameters that architects should treat as first-class configuration — not implementation details buried in CLI commands.

### Resilience & Redundancy Parameters

| Parameter | Service | Range | Impact |
|---|---|---|---|
| Storage replication | Blob Storage | LRS / ZRS / GRS / GZRS | Durability vs cost vs archive tier availability |
| Cosmos DB zone redundancy | Cosmos DB | true / false per region | Intra-region HA vs provisioning constraints |
| Cosmos DB consistency level | Cosmos DB | Strong → Eventual (5 levels) | Read latency vs stale-read risk |
| Cosmos DB multi-region writes | Cosmos DB | true / false | Write latency vs conflict resolution complexity |
| Cosmos DB auto-failover | Cosmos DB | true / false | RTO during region outage |
| Redis replica count | Redis | 0–3 | Read throughput vs cost |
| Redis availability zones | Redis | 1–3 zones | Intra-region HA |
| SQL zone redundancy | SQL Database | true / false | Intra-region HA (not available on Serverless) |

### Compute Sizing & Autoscaling Parameters

| Parameter | Service | Example Values | Impact |
|---|---|---|---|
| Node VM size | AKS | Standard_D4s_v5, Standard_B4ms | CPU/memory per node, cost per node |
| System pool min/max | AKS | 1 / 3 | Control plane HA vs cost |
| Workload pool min/max | AKS | 2 / 10 | Burst ceiling vs cost floor |
| Kubernetes version | AKS | 1.28, 1.29, 1.30 | Feature set, security patches, support window |
| APIM capacity units | APIM | 1–12 (StandardV2) | ~1,000 req/s per unit |
| SQL auto-pause delay | SQL Serverless | 60 min (minimum) | Cold-start frequency vs cost |
| SQL min capacity | SQL Serverless | 0.5–40 vCores | Performance floor during low traffic |

### Data Throughput Parameters

| Parameter | Service | Range | Impact |
|---|---|---|---|
| Max autoscale throughput | Cosmos DB | 1,000–1,000,000 RU/s | Cost ceiling, burst capacity |
| Partition key | Cosmos DB | Custom (per container) | Query efficiency, hot-partition risk |
| SQL vCores | SQL Serverless | 1–80 | Query parallelism |
| Redis VM size | Redis | C0–C6 (Standard), P1–P5 (Premium) | Memory, throughput, connections |
| Redis eviction policy | Redis | allkeys-lru, volatile-lru, noeviction, etc. | Behavior when memory full |

### Security Parameters

| Parameter | Service | Options | Impact |
|---|---|---|---|
| Local auth | Cosmos DB, SQL, Storage, Redis | enabled / disabled | Zero-trust posture |
| Min TLS version | Storage, Redis | 1.0 / 1.1 / 1.2 | Compliance baseline |
| WAF mode | Front Door | Prevention / Detection | Blocking vs logging |
| Rate limit | APIM | calls per renewal period | DDoS protection vs legitimate burst |
| CORS origins | APIM | URL whitelist | Frontend domain restriction |
| JWT audience | APIM | URI | Token scope validation |

### Observability Parameters

| Parameter | Service | Range | Impact |
|---|---|---|---|
| Log retention | Log Analytics | 30–730 days | Investigation window vs cost |
| Alert window size | Monitor Alerts | PT1M–PT24H | Sensitivity vs noise |
| Alert evaluation frequency | Monitor Alerts | PT1M–PT1H | Detection speed |
| SLO thresholds | Monitor Alerts | Custom per metric | Error budget definition |
| Health probe interval | Front Door | 5–255 seconds | Failure detection speed vs probe load |

---

## 13. Decision Flowcharts

### "Which compute platform should I use?"

```
Need Kubernetes-native features (CRDs, DaemonSets, node tuning)?
├── YES → AKS
└── NO
    ├── Need scale-to-zero?
    │   ├── YES → Container Apps (containers) or Functions (code-only)
    │   └── NO
    │       ├── Need deployment slots + simplest model?
    │       │   ├── YES → App Service
    │       │   └── NO → Container Apps (simpler than AKS, more flexible than App Service)
```

### "Which database engine for my relational data?"

```
Team has T-SQL expertise AND needs Serverless auto-pause?
├── YES → Azure SQL Database (Serverless)
└── NO
    ├── Need extensions (pgvector, PostGIS, Citus sharding)?
    │   ├── YES → PostgreSQL Flexible Server
    │   └── NO
    │       ├── Existing MySQL codebase?
    │       │   ├── YES → MySQL Flexible Server
    │       │   └── NO → PostgreSQL Flexible (greenfield default)
```

### "Do I need Cosmos DB?"

```
Need multi-region writes OR guaranteed sub-10ms reads at any scale?
├── YES → Cosmos DB
└── NO
    ├── Need global read distribution (multi-region)?
    │   ├── YES → Cosmos DB (with single-region write)
    │   └── NO
    │       ├── Document data < 100 GB, single-region?
    │       │   ├── YES → PostgreSQL Flexible (JSONB) — one engine for everything
    │       │   └── NO → Cosmos DB (scale advantage beyond 100 GB)
```

### "Do I need a dedicated Redis instance?"

```
Only need API response caching?
├── YES → Use APIM built-in <cache-store> policy (no Redis needed)
└── NO
    ├── Need shared state across app instances (sessions, carts, counters)?
    │   ├── YES → Azure Cache for Redis
    │   └── NO
    │       ├── Need Pub/Sub, sorted sets, or other Redis data structures?
    │       │   ├── YES → Azure Cache for Redis
    │       │   └── NO → In-process cache (IMemoryCache / node-cache)
```

---

## Summary: The Architect's Checklist

Before committing to any service combination, answer these questions:

1. **What's the hardest thing to change later?** Invest design time there (database engine, compute platform, architecture style).

2. **What's the operational cost in people-hours, not just Azure dollars?** AKS is "cheaper" per node than Container Apps — but requires a platform team. Redis is "only" $440/mo — but is it actually used?

3. **What's the simplest stack that meets requirements?** The best architecture is the one with the fewest services that still hit your SLOs. Start with Container Apps + PostgreSQL Flexible + APIM built-in cache and add complexity only when load testing proves it's needed.

4. **Are you paying for resilience you can't consume?** Cosmos DB's 99.999% SLA is meaningless if your SQL Serverless database (99.9%) is in the same critical path.

5. **Are there unused resources?** Audit named values, backends, and connection strings. If a Redis instance was provisioned "for future use" but no policy references it — delete it or defer provisioning.

---

> *This guide is maintained alongside the [executable deployment plan](executable-plan.md) which implements the specific service choices described here using Azure CLI commands.*
