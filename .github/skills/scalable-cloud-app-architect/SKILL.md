---
name: scalable-cloud-application-architect
description: |
  Teaches agents how to build scalable, highly available cloud applications with Site Reliability Engineering (SRE) practices. 
  Based on Azure's production-grade architecture patterns for API platforms, e-commerce, and marketplace applications.

  USE FOR: Building scalable cloud apps, designing API platforms, implementing SRE practices, microservices architecture, 
  creating e-commerce systems, setting up observability, implementing autoscaling, designing multi-tier applications.

  DO NOT USE FOR: Single service deployments, simple CRUD apps without scale requirements, local-only development.

  DELEGATES TO: Infrastructure-as-Code agents for deployment (using CDKs/SDKs/APIs), monitoring agents for observability setup.
---

# Scalable Cloud Application Architecture with SRE

This skill provides comprehensive guidance for building scalable, production-grade cloud applications using Azure services with Site Reliability Engineering (SRE) practices. Based on [Microsoft's reference architecture](https://learn.microsoft.com/en-us/azure/architecture/example-scenario/apps/scalable-apps-performance-modeling-site-reliability).

## Architecture Overview

### Target Use Cases

- API-based cloud services (RESTful APIs, GraphQL)
- E-commerce and marketplace platforms
- Product browsing and catalog systems
- User registration, authentication, and profile management
- Order and subscription management
- Content delivery applications
- IoT and event-driven workloads

### Architecture Components

The architecture implements a **multi-tier API platform** with the following layers:

```
Client Applications
    ↓
Azure Front Door (Entry Point, CDN, WAF)
    ↓
Azure API Management (API Gateway)
    ↓
Application Gateway for Containers (Load Balancer)
    ↓
Azure Kubernetes Service (Microservices)
    ↓
Data Layer (Cosmos DB, SQL, Storage)
```

**Cross-cutting concerns:**

- Microsoft Entra ID: Identity & Access Management
- Azure Monitor + Application Insights: Observability
- Azure Chaos Studio: Resilience testing
- Azure Managed Redis: Distributed caching

---

## Implementation Guide: Step-by-Step

### Phase 1: Foundation Setup

#### Step 1.1: Identity and Access Management

**Service:** Microsoft Entra ID (formerly Azure Active Directory)  
**API Location:** `specification/azureactivedirectory/`

**What to implement:**

1. **Create or configure Entra ID tenant**
   - Set up application registrations for each microservice
   - Define service principals for service-to-service authentication
   - Configure managed identities for Azure resources

2. **Configure authentication flows:**
   - OAuth 2.0 for user authentication
   - Client credentials flow for service-to-service
   - Managed identity authentication for Azure services

3. **Set up RBAC (Role-Based Access Control):**
   - Define custom roles for API operations
   - Assign roles to users and service principals
   - Implement least-privilege access

**API Operations:**

- Application registration: Create/update/delete app registrations
- Service principal management: Create/configure service principals
- Role assignments: Assign roles to identities
- Graph API for user/group management

**Dependencies for later phases:**

- All services will authenticate through Entra ID
- API Management policies will validate tokens from Entra ID
- AKS workloads will use managed identities

---

### Phase 2: Networking and Security Layer

#### Step 2.1: Azure Front Door Configuration

**Service:** Azure Front Door  
**API Location:** `specification/frontdoor/resource-manager/Microsoft.Network/FrontDoor/`  
**Latest API Version:** `2025-11-01`

**What to implement:**

1. **Create Front Door profile**
   - Configure as the single entry point: `https://api.contoso.com`
   - Enable Standard or Premium tier for WAF support
   - Set up custom domain and SSL/TLS certificates

2. **Configure routing rules:**
   - Route all traffic to API Management backend
   - Set up path-based routing if needed
   - Configure session affinity (if required)

3. **Enable Azure Web Application Firewall (WAF):**
   - Apply OWASP Top 10 protection rules
   - Configure custom WAF rules for your API patterns
   - Set up rate limiting at the edge
   - Enable DDoS protection

4. **Optimize performance:**
   - Enable caching for static content
   - Configure compression
   - Set up Azure CDN integration

**Key API Resources:**

- `FrontDoor` resource: Main entry point configuration
- `FrontendEndpoint`: Custom domain configuration
- `RoutingRule`: Traffic routing rules
- `WebApplicationFirewallPolicy`: Security policies
- `Profile`: Front Door profile configuration
- `Experiment`: A/B testing (optional)

**TypeSpec Files:**

- `FrontDoor.tsp`: Core Front Door resource
- `WebApplicationFirewallPolicy.tsp`: WAF configuration
- `Profile.tsp`: Front Door profiles
- `Experiment.tsp`: A/B testing features

**Connection Pattern:**

```
Front Door → API Management Backend Pool
- Configure origin group with API Management endpoint
- Set up health probes to API Management health endpoint
- Enable end-to-end SSL/TLS
```

---

#### Step 2.2: API Management Setup

**Service:** Azure API Management  
**API Location:** `specification/apimanagement/resource-manager/Microsoft.ApiManagement/ApiManagement/`  
**Latest API Version:** `2024-06-01-preview`

**What to implement:**

1. **Provision API Management instance:**
   - Use Standard or Premium tier for autoscaling
   - Deploy in VNet (if using private networking)
   - Enable multiple regions (for Premium tier)

2. **Define APIs and operations:**
   - Import OpenAPI/Swagger specifications for each microservice
   - Define API versions and revision management
   - Set up operation-level policies

3. **Configure authentication and authorization policies:**
   - Validate JWT tokens from Entra ID
   - Implement rate limiting per subscription
   - Configure IP filtering and CORS

4. **Set up caching with Azure Managed Redis:**
   - Configure external cache (see Step 2.3)
   - Define cache-lookup and cache-store policies
   - Set cache duration per operation

5. **Implement transformation policies:**
   - Request/response transformation
   - Header manipulation
   - Mock responses for testing

6. **Configure backends:**
   - Add Application Gateway for Containers as backend
   - Set up load balancing across backend pools
   - Configure health probes and circuit breakers

**Key API Resources:**

- `ApiManagementServiceResource`: Main APIM instance
- `ApiContract`: API definitions
- `OperationContract`: Individual operations
- `PolicyContract`: Policy definitions (XML)
- `SubscriptionContract`: API subscriptions
- `BackendContract`: Backend service configuration
- `CacheContract`: Internal cache configuration
- `NamedValueContract`: Configuration values/secrets
- `ProductContract`: API products for monetization
- `AuthorizationServerContract`: OAuth server config
- `LoggerContract`: Diagnostics and logging

**TypeSpec Files:**

- `ApiManagementServiceResource.tsp`: Main service
- `ApiContract.tsp`: API definitions
- `OperationContract.tsp`: Operations
- `PolicyContract.tsp`: Policies
- `BackendContract.tsp`: Backend services
- `CacheContract.tsp`: Cache configuration
- `SubscriptionContract.tsp`: Subscriptions

**Critical Policies to Implement:**

```xml
<!-- Authentication -->
<validate-jwt header-name="Authorization">
    <openid-config url="https://login.microsoftonline.com/{tenant}/.well-known/openid-configuration" />
    <audiences>
        <audience>api://your-api-id</audience>
    </audiences>
</validate-jwt>

<!-- Rate limiting -->
<rate-limit calls="100" renewal-period="60" />

<!-- Caching -->
<cache-lookup vary-by-developer="false" vary-by-developer-groups="false" />
<cache-store duration="300" />

<!-- Backend routing -->
<set-backend-service base-url="https://aks-backend.contoso.com" />
```

**Connection Patterns:**

- **Inbound from Front Door:** Front Door routes to APIM public/private endpoint
- **Outbound to Application Gateway for Containers:** APIM forwards to AGC load balancer
- **Cache integration:** APIM connects to Azure Managed Redis for distributed caching
- **Logging:** APIM sends logs to Application Insights

---

#### Step 2.3: Azure Managed Redis (Cache Layer)

**Service:** Azure Cache for Redis  
**API Location:** `specification/redis/resource-manager/Microsoft.Cache/redis/`

**What to implement:**

1. **Provision Redis cache:**
   - Use Premium tier for persistence and clustering
   - Enable zone redundancy for high availability
   - Configure memory policies (eviction)

2. **Integrate with API Management:**
   - Configure as external cache in APIM
   - Set connection string in APIM named values
   - Use secure connection (TLS)

3. **Configure cache patterns:**
   - Cache-aside for API responses
   - Session storage for user sessions
   - Distributed locks for coordination

**Key API Resources:**

- `RedisResource`: Main Redis cache instance
- `RedisFirewallRule`: Network security rules
- `RedisLinkedServer`: Geo-replication
- `RedisPatchSchedule`: Maintenance windows

**Connection Pattern:**

```
API Management → Azure Managed Redis
- APIM uses external cache policy
- Configure connection string with TLS
- Set cache key patterns and expiration
```

---

### Phase 3: Compute and Container Orchestration

#### Step 3.1: Azure Kubernetes Service (AKS) Setup

**Service:** Azure Kubernetes Service  
**API Location:** `specification/containerservice/resource-manager/Microsoft.ContainerService/aks/`  
**Latest API Version:** `2026-01-02-preview`

**What to implement:**

1. **Create AKS cluster:**
   - Enable managed control plane
   - Configure node pools with autoscaling
   - Enable availability zones for high availability
   - Use managed identity for cluster authentication

2. **Configure networking:**
   - Use Azure CNI for advanced networking
   - Set up network policies (Calico or Azure)
   - Configure private cluster (if required)
   - Enable Azure Application Gateway for Containers ingress

3. **Set up autoscaling:**
   - **Cluster Autoscaler**: Scale nodes based on pod demands
   - **Horizontal Pod Autoscaler (HPA)**: Scale pods based on CPU/memory
   - **Vertical Pod Autoscaler (VPA)**: Adjust pod resource requests
   - **KEDA**: Event-driven autoscaling (optional)

4. **Configure workload identity:**
   - Enable workload identity federation
   - Create managed identities for each microservice
   - Configure service account bindings

5. **Deploy microservices:**
   - **Product Service**: Product catalog, browsing (500 RPS target)
   - **Profile Service**: User profiles, registration (100 RPS)
   - **Orders & Payment Service**: Transaction management (100 RPS)
   - **Content Service**: Media and articles (50 RPS)

6. **Implement health probes:**
   - Liveness probes: Check if pod is alive
   - Readiness probes: Check if pod can serve traffic
   - Startup probes: Check initial startup completion

**Key API Resources:**

- `ManagedCluster`: Main AKS cluster resource
- `AgentPool`: Node pool configuration
- `ManagedClusterUpgradeProfile`: Upgrade planning
- `MaintenanceConfiguration`: Maintenance windows
- `TrustedAccessRoleBinding`: Secure access
- `PrivateEndpointConnection`: Private networking
- `ManagedNamespace`: Namespace management
- `Machine`: Node-level operations

**TypeSpec Files:**

- `ManagedCluster.tsp`: Cluster definition
- `AgentPool.tsp`: Node pools
- `MaintenanceConfiguration.tsp`: Maintenance
- `PrivateEndpointConnection.tsp`: Private endpoints

**Autoscaling Configuration:**

```yaml
# Cluster Autoscaler
minCount: 3
maxCount: 10
enableAutoScaling: true

# Horizontal Pod Autoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 3
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

**Connection Patterns:**

- **Inbound:** Application Gateway for Containers routes traffic to Services/Pods
- **Identity:** Pods use managed identities to access Azure resources
- **Data Access:** Pods connect to Cosmos DB, SQL, Storage using managed identities
- **Observability:** Pods emit telemetry to Application Insights

---

#### Step 3.2: Application Gateway for Containers

**Service:** Azure Application Gateway for Containers (Service Networking)  
**API Location:** `specification/servicenetworking/resource-manager/Microsoft.ServiceNetworking/ServiceNetworking/`  
**Latest API Version:** `2025-03-01-preview`

**What to implement:**

1. **Create Traffic Controller:**
   - Deploy as AKS ingress controller
   - Enable layer 7 load balancing
   - Configure autoscaling capacity units

2. **Configure Frontends:**
   - Set up frontend listeners
   - Configure SSL/TLS certificates
   - Set up custom domains

3. **Create Associations:**
   - Link Traffic Controller to AKS subnets
   - Configure routing to backend pods
   - Set up health probes

4. **Configure load balancing:**
   - Round-robin distribution across pods
   - Session affinity (if needed)
   - Connection draining for graceful shutdowns

**Key API Resources:**

- `TrafficController`: Main gateway resource
- `Frontend`: Frontend listeners and domains
- `Association`: Links to backend resources
- `SecurityPolicyConfigurations`: Security settings

**TypeSpec Files:**

- `main.tsp`: Core definitions
- Contains Frontend, Association, TrafficController models

**Connection Pattern:**

```
API Management → Application Gateway for Containers → AKS Services/Pods
- APIM sends requests to AGC frontend
- AGC load balances across pod IPs
- Health probes ensure traffic to healthy pods only
```

---

### Phase 4: Data Layer

#### Step 4.1: Azure Cosmos DB (NoSQL)

**Service:** Azure Cosmos DB  
**API Location:** `specification/cosmos-db/resource-manager/Microsoft.DocumentDB/DocumentDB/`  
**Data Plane API:** `specification/cosmos-db/data-plane/`

**What to implement:**

1. **Create Cosmos DB account:**
   - Choose API: NoSQL (Core SQL API) recommended for new apps
   - Enable multi-region writes for global distribution
   - Configure automatic failover

2. **Design database and containers:**
   - **Product Catalog Database:**
     - Products container: Partition by productCategory
     - Inventory container: Partition by warehouseId
   - **Profile Database:**
     - Users container: Partition by userId
     - Preferences container: Partition by userId

3. **Configure throughput:**
   - Use autoscale throughput (400-4000 RU/s min)
   - Set partition key for optimal distribution
   - Enable serverless for unpredictable workloads (dev/test)

4. **Implement indexing policies:**
   - Configure index for query patterns
   - Exclude unused paths to save RU/s
   - Enable composite indexes for multi-property queries

5. **Set up change feed:**
   - Process changes for cache invalidation
   - Trigger event-driven workflows
   - Maintain materialized views

**Key API Resources:**
**Control Plane (Management):**

- `DatabaseAccountResource`: Cosmos DB account
- `SqlDatabaseResource`: SQL API database
- `SqlContainerResource`: Container (collection)
- `SqlStoredProcedureResource`: Stored procedures
- `SqlTriggerResource`: Triggers
- `ThroughputSettingsResource`: Throughput configuration

**Data Plane (Operations):**

- Document CRUD operations
- Query execution
- Batch operations
- Change feed processing

**Performance Tuning:**

```json
{
  "partitionKey": "/userId",
  "throughput": {
    "autoscale": {
      "minThroughput": 1000,
      "maxThroughput": 10000
    }
  },
  "indexingPolicy": {
    "automatic": true,
    "indexingMode": "consistent",
    "includedPaths": [{ "path": "/*" }],
    "excludedPaths": [{ "path": "/largeField/*" }]
  }
}
```

**Connection from AKS:**

```
AKS Pod (Managed Identity) → Cosmos DB
- Use Azure SDK with managed identity authentication
- Configure connection via environment variables
- Implement retry policies for transient failures
- Use bulk operations for high throughput
```

---

#### Step 4.2: Azure SQL Database

**Service:** Azure SQL Database  
**API Location:** `specification/sql/resource-manager/Microsoft.Sql/SQL/`

**What to implement:**

1. **Create SQL logical server:**
   - Enable Microsoft Entra authentication
   - Configure firewall rules (allow Azure services)
   - Set up private endpoints for secure access

2. **Create databases:**
   - **Orders Database:**
     - Orders table: Order header info
     - OrderItems table: Line items
     - Payments table: Payment transactions
   - **Subscriptions Database:**
     - Subscriptions table: Subscription details
     - Billing table: Billing history

3. **Configure performance tier:**
   - Use serverless for variable workloads
   - Use provisioned for consistent performance
   - Enable autoscaling (for elastic pools)
   - Configure DTU or vCore model

4. **Implement high availability:**
   - Enable zone redundancy
   - Configure geo-replication for DR
   - Set up automatic backups

5. **Security configuration:**
   - Enable Transparent Data Encryption (TDE)
   - Configure Advanced Threat Protection
   - Implement row-level security
   - Use dynamic data masking

**Key API Resources:**

- `Server`: SQL logical server
- `Database`: Individual database
- `ElasticPool`: Resource pool for multiple databases
- `FirewallRule`: Network security
- `ServerAzureADAdministrator`: Entra ID admin
- `DatabaseThreatDetectionPolicy`: Security
- `TransparentDataEncryption`: Encryption config

**Schema Design Best Practices:**

```sql
-- Partition orders table by date for performance
CREATE PARTITION FUNCTION OrderDateRange (datetime2)
AS RANGE RIGHT FOR VALUES ('2024-01-01', '2024-02-01', ...);

-- Index for common queries
CREATE NONCLUSTERED INDEX IX_Orders_UserId_Date
ON Orders(UserId, OrderDate)
INCLUDE (TotalAmount, Status);

-- Implement temporal tables for audit
ALTER TABLE Orders
ADD PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime);
ALTER TABLE Orders SET (SYSTEM_VERSIONING = ON);
```

**Connection from AKS:**

```
AKS Pod (Managed Identity) → Azure SQL
- Use connection string with managed identity
- Implement connection pooling
- Use Entity Framework Core or Dapper ORM
- Enable retry logic for transient faults
```

---

#### Step 4.3: Azure Storage and Data Lake Storage

**Service:** Azure Storage  
**API Location:** `specification/storage/resource-manager/Microsoft.Storage/Storage.Management/`  
**Data Plane:** `specification/storage/data-plane/`

**What to implement:**

1. **Create storage account:**
   - Use StorageV2 (General Purpose v2)
   - Enable hierarchical namespace for Data Lake Gen2
   - Configure redundancy: ZRS or GRS

2. **Set up Blob Storage containers:**
   - **Media Container:** Product images, videos
   - **Documents Container:** PDF files, manuals
   - **Archive Container:** Cold storage for old content
   - **Data Lake Container:** Analytics data

3. **Configure access tiers:**
   - Hot: Frequently accessed content
   - Cool: Infrequent access (>30 days)
   - Archive: Rare access (>180 days)
   - Implement lifecycle management policies

4. **Enable CDN integration:**
   - Configure Azure CDN endpoint
   - Set up custom domain
   - Enable compression and caching

5. **Implement security:**
   - Enable blob versioning
   - Configure soft delete
   - Use managed identities for access
   - Enable encryption at rest

**Key API Resources:**
**Management Plane:**

- `StorageAccount`: Storage account resource
- `BlobContainer`: Blob container
- `FileShare`: File share
- `Queue`: Queue storage
- `Table`: Table storage
- `ManagementPolicy`: Lifecycle policies

**Data Plane (Blob):**

- Upload/download operations
- Blob metadata management
- Lease operations
- Snapshots and versioning

**Lifecycle Management:**

```json
{
  "rules": [
    {
      "name": "moveToArchive",
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["media/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool": { "daysAfterModificationGreaterThan": 30 },
            "tierToArchive": { "daysAfterModificationGreaterThan": 180 }
          }
        }
      }
    }
  ]
}
```

**Connection from AKS:**

```
AKS Pod (Managed Identity) → Storage Account
- Use Azure SDK for Blob/File/Queue operations
- Implement chunked upload for large files
- Use async operations for better performance
- Enable client-side encryption (optional)
```

---

### Phase 5: Observability and Monitoring

#### Step 5.1: Azure Monitor Configuration

**Service:** Azure Monitor  
**API Location:** `specification/monitor/resource-manager/`

**What to implement:**

1. **Create Log Analytics workspace:**
   - Central repository for all telemetry
   - Configure data retention (30-730 days)
   - Set up pricing tier based on ingestion volume

2. **Enable diagnostic settings for all services:**
   - Front Door: Request logs, WAF logs
   - API Management: Gateway logs, policy execution
   - AKS: Container logs, cluster metrics
   - Cosmos DB: Request metrics, query performance
   - SQL: Query performance, deadlocks
   - Storage: Request logs, capacity metrics

3. **Configure metrics collection:**
   - Enable Azure Monitor for Containers (AKS)
   - Configure Prometheus integration
   - Set up custom metrics from applications

4. **Set up action groups:**
   - Email notifications for critical alerts
   - SMS for high-priority incidents
   - Webhook integrations for incident management tools
   - Azure Functions for automated remediation

**Key API Resources:**

- `Workspace`: Log Analytics workspace
- `DiagnosticSettings`: Enable telemetry
- `ActionGroup`: Alert notifications
- `MetricAlert`: Metric-based alerts
- `LogAlert`: Log query-based alerts
- `Workbook`: Interactive dashboards
- `DataCollectionRule`: Data collection config

---

#### Step 5.2: Application Insights Integration

**Service:** Application Insights (part of Azure Monitor)  
**API Location:** `specification/applicationinsights/resource-manager/`

**What to implement:**

1. **Create Application Insights resources:**
   - One per microservice (or shared across related services)
   - Use workspace-based model for centralization
   - Enable sampling for high-volume applications

2. **Instrument applications:**
   - Use OpenTelemetry SDKs (recommended)
   - Configure automatic dependency tracking
   - Enable distributed tracing
   - Instrument custom events and metrics

3. **Configure SLI tracking:**
   - **Availability:** Request success rate
   - **Latency:** P50, P95, P99 response times
   - **Throughput:** Requests per second
   - **Error Rate:** Failed requests percentage

4. **Set up distributed tracing:**
   - Enable correlation across services
   - Track request flow: Front Door → APIM → AKS → Database
   - Identify slow dependencies
   - Analyze failure patterns

**Key API Resources:**

- `Component`: Application Insights resource
- `ProactiveDetectionConfiguration`: Smart detection
- `WebTest`: Availability tests
- `ComponentLinkedStorageAccounts`: Storage for logs

**Telemetry to Capture by Layer:**

**Layer 1 - Front Door:**

- Request count and latency
- Cache hit/miss ratio
- WAF rule triggers
- Geographic distribution

**Layer 2 - API Management:**

- API call duration
- Policy execution time
- Rate limit violations
- Cache effectiveness

**Layer 3 - Application Gateway for Containers:**

- Backend pool health
- Connection counts
- Request distribution
- SSL/TLS handshake time

**Layer 4 - AKS Microservices:**

- Pod CPU/memory usage
- Request processing time
- Database query duration
- External API call latency
- Business metrics (items sold, users registered)

**Layer 5 - Data Stores:**

- Cosmos DB: RU consumption, throttling
- SQL: Query duration, connection pool
- Storage: Latency, egress bandwidth

---

#### Step 5.3: Define SLIs and SLOs

**Service Level Indicators (SLIs):**

Measure the ratio of good events to total events:

1. **Availability SLI:**

   ```
   Availability = (Successful Requests) / (Total Requests)
   Target: 99.9% (allows 0.1% failure)
   ```

2. **Latency SLI:**

   ```
   Latency = (Requests completed in <1000ms) / (Total Requests)
   Target: 95% of requests within 1 second
   ```

3. **Throughput SLI:**

   ```
   Throughput = Actual RPS / Target RPS
   Per service:
   - Product: 500 RPS (10x = 5000 during events)
   - Profile: 100 RPS (10x = 1000)
   - Orders: 100 RPS (10x = 1000)
   - Content: 50 RPS (10x = 500)
   ```

4. **Error Rate SLI:**

   ```
   Error Rate = (Failed Requests) / (Total Requests)
   Target: <1% error rate during peak hours
   ```

5. **Freshness SLI (for search/catalog):**
   ```
   Freshness = (Results returned within 3s after update) / (Total searches)
   Target: 95% freshness within 3 seconds
   ```

**Service Level Objectives (SLOs):**

```
Aspirational SLOs:
- 95% of READ requests respond within 1 second
- 95% of CREATE/UPDATE requests respond within 3 seconds
- 99% of all requests respond within 5 seconds
- 99.9% of all requests succeed without error
- <1% error rate during peak hours
```

**Measurement Windows:**

- Real-time: 5-minute windows for immediate detection
- Tactical: 1-hour windows for alerting
- Strategic: 24-hour and 7-day windows for SLO tracking

**Kusto Queries for SLI Calculation:**

```kql
// Availability SLI
requests
| where timestamp > ago(1h)
| summarize
    Total = count(),
    Successful = countif(success == true)
| extend Availability = (Successful * 100.0) / Total
| project Availability, Total, Successful

// Latency SLI (P95)
requests
| where timestamp > ago(1h)
| summarize P95Latency = percentile(duration, 95)
| extend LatencySLI = iff(P95Latency < 1000, 100, 0)

// Error rate per service
requests
| where timestamp > ago(1h)
| summarize
    ErrorRate = (countif(success == false) * 100.0) / count()
    by cloud_RoleName
```

---

#### Step 5.4: Alerting Strategy

**Critical Alerts (P0 - Immediate Response):**

1. **Availability drops below 99%** (within 5-minute window)
2. **Error rate exceeds 5%** (within 5-minute window)
3. **Complete service outage** (0 successful requests)
4. **Database connection failures**

**High Priority Alerts (P1 - 15 minute response):**

1. **P95 latency exceeds 3 seconds**
2. **Error rate exceeds 2%**
3. **Cosmos DB throttling detected**
4. **CPU/Memory above 85%** for 10 minutes

**Medium Priority Alerts (P2 - 1 hour response):**

1. **Cache hit rate drops below 70%**
2. **Disk usage above 80%**
3. **Certificate expiring in 30 days**

**Dashboard Configuration:**

- Real-time SLI metrics display
- SLO burn rate visualization
- Error budget tracking
- Dependency health status

---

### Phase 6: Resilience and Testing

#### Step 6.1: Azure Chaos Studio

**Service:** Azure Chaos Studio  
**API Location:** `specification/chaos/resource-manager/Microsoft.Chaos/Chaos/`

**What to implement:**

1. **Create Chaos experiments:**
   - Target resources: AKS, Cosmos DB, SQL, VM Scale Sets
   - Enable targets for chaos testing

2. **Define fault injection scenarios:**
   - **AKS Pod Failures:**
     - Kill random pods to test recovery
     - Inject CPU stress
     - Introduce network latency
   - **Database Chaos:**
     - Simulate Cosmos DB failover
     - Introduce SQL connection failures
     - Throttle database throughput
   - **Network Chaos:**
     - Introduce latency between services
     - Simulate packet loss
     - DNS failures

3. **Create experiments:**
   - Define experiment duration
   - Set up safety checks (halt conditions)
   - Configure target selection (percentage/specific)

4. **Run and observe:**
   - Execute experiments during off-peak
   - Monitor SLI metrics during chaos
   - Validate autoscaling response
   - Verify alerting and recovery

**Key API Resources:**

- `Experiment`: Chaos experiment definition
- `ExperimentExecution`: Running experiment
- `Target`: Resources to target
- `TargetType`: Available target types
- `Capability`: Available fault types
- `CapabilityType`: Fault specifications

**TypeSpec Files:**

- `experiment.tsp`: Experiment definitions
- `experimentExecution.tsp`: Execution tracking
- `target.tsp`: Target resources
- `capability.tsp`: Fault capabilities

**Example Experiment Configuration:**

```json
{
  "experimentName": "aks-pod-failure-test",
  "steps": [
    {
      "name": "Kill-random-pods",
      "branches": [
        {
          "name": "product-service-chaos",
          "actions": [
            {
              "type": "continuous",
              "duration": "PT5M",
              "parameters": [
                {
                  "key": "podFailure",
                  "value": "20%"
                }
              ],
              "selectorId": "product-pods"
            }
          ]
        }
      ]
    }
  ],
  "selectors": [
    {
      "id": "product-pods",
      "type": "List",
      "targets": [
        {
          "id": "/subscriptions/.../resourceGroups/.../providers/Microsoft.ContainerService/managedClusters/my-aks",
          "type": "Microsoft.ContainerService/managedClusters"
        }
      ]
    }
  ]
}
```

---

### Phase 7: Alternatives and Variations

#### Alternative 1: Azure Container Apps

**Service:** Azure Container Apps  
**API Location:** `specification/app/resource-manager/Microsoft.App/`

**When to use:**

- Simplified container hosting without Kubernetes complexity
- Event-driven microservices (KEDA-based autoscaling)
- Serverless containers

**What to implement:**

1. Create Container Apps Environment
2. Deploy each microservice as Container App
3. Configure Dapr for service-to-service communication
4. Set up KEDA event-driven autoscaling
5. Configure ingress (built-in, replaces App Gateway for Containers)

**Trade-offs:**

- ✅ Simpler management, no cluster operations
- ✅ Built-in ingress and service mesh
- ✅ KEDA autoscaling out of the box
- ❌ Less control over networking
- ❌ Limited to HTTP/HTTPS ingress

---

#### Alternative 2: Azure Functions + API Management

**Service:** Azure Functions  
**API Location:** `specification/web/resource-manager/Microsoft.Web/AppService/`

**When to use:**

- Event-driven APIs
- Low to moderate traffic
- Per-endpoint isolation

**What to implement:**

1. Deploy each API endpoint as Azure Function
2. Use Premium or Dedicated plan for VNet integration
3. Front with API Management
4. Use Durable Functions for workflows

**Trade-offs:**

- ✅ True serverless, pay per execution
- ✅ Auto-scaling without configuration
- ❌ Cold start latency
- ❌ Limited execution duration (except Durable Functions)

---

#### Alternative 3: Azure App Service (Web Apps)

**Service:** Azure App Service  
**API Location:** `specification/web/resource-manager/Microsoft.Web/AppService/`

**When to use:**

- Traditional web applications
- Teams familiar with PaaS
- Simple deployment model

**What to implement:**

1. Create App Service Plan (Premium tier for VNet)
2. Deploy each microservice as Web App
3. Enable autoscaling rules
4. Configure deployment slots for blue/green deployments

**Trade-offs:**

- ✅ Fully managed platform
- ✅ Easy deployment (CI/CD)
- ❌ Less granular scaling compared to AKS
- ❌ Limited to HTTP/HTTPS

---

## Service Dependencies and Connection Matrix

### Authentication Flow

```
All Services → Microsoft Entra ID
├─ Front Door: Validates custom domain ownership
├─ API Management: Validates JWT tokens
├─ AKS Microservices: Use managed identity
├─ Cosmos DB: Authenticates using managed identity
├─ SQL: Authenticates using Entra ID
└─ Storage: Authenticates using managed identity
```

### Request Flow

```
1. Client → Front Door (SSL termination, WAF)
2. Front Door → API Management (routing)
3. API Management → Azure Managed Redis (cache lookup)
4. API Management → Application Gateway for Containers (if cache miss)
5. Application Gateway → AKS Service (load balancing)
6. AKS Pod → Data Layer (Cosmos DB/SQL/Storage)
7. Response flows back through same path
8. All layers → Application Insights (telemetry)
```

### Telemetry Flow

```
All Services → Application Insights → Log Analytics Workspace
├─ Front Door: Access logs, WAF logs
├─ API Management: Gateway logs, policy traces
├─ Application Gateway for Containers: Request logs
├─ AKS: Container logs, metrics via Azure Monitor
├─ Cosmos DB: Request metrics, query statistics
├─ SQL: Query performance, diagnostics
└─ Storage: Request logs, metrics
```

### Required Network Connectivity

```
Layer 1 (Public):
  Front Door (public endpoint) → API Management (public/private)

Layer 2 (Protected):
  API Management → Redis Cache (private endpoint)
  API Management → Application Gateway for Containers (private)

Layer 3 (Private):
  Application Gateway for Containers → AKS (internal)
  AKS Pods → Cosmos DB (private endpoint)
  AKS Pods → SQL (private endpoint)
  AKS Pods → Storage (private endpoint)

Cross-cutting:
  All services → Entra ID (public)
  All services → Application Insights (public/private)
```

---

## Performance Modeling and Capacity Planning

### Expected Load (Normal Peak)

- **Total users:** 1.5 million
- **Hourly active:** 450,000 (30%)
- **Load distribution:**
  - Product browsing: 75% → 500 RPS
  - Registration/Sign-in: 10% → 100 RPS
  - Orders/Subscriptions: 10% → 100 RPS
  - Content viewing: 5% → 50 RPS

### Scale During Special Events (10x)

- Product: 5,000 RPS
- Profile: 1,000 RPS
- Orders: 1,000 RPS
- Content: 500 RPS

### Resource Sizing Recommendations

**AKS:**

- Node pool: 3-10 nodes (autoscaling)
- Node size: D4s_v3 or D8s_v3 (4-8 vCPU)
- Pod replicas: 3-50 per service (HPA)

**API Management:**

- Tier: Standard or Premium
- Scale units: 1-5 (autoscaling)

**Cosmos DB:**

- Autoscale: 1000-10000 RU/s per container
- Use dedicated throughput for high-volume containers

**SQL:**

- Service tier: General Purpose or Business Critical
- Compute: 4-16 vCores
- Enable autoscaling for elastic pool

**Redis:**

- Tier: Premium P1 (6 GB) or higher
- Enable clustering for large datasets

---

## Cost Optimization

### SRE-Driven Cost Strategy

Use **error budgets** to balance reliability investment vs. feature development:

- **Under budget** (failures within SLO): Invest in features
- **Over budget** (exceeding SLO): Invest in reliability

### Key Cost Drivers and Optimization

1. **Compute (AKS):**
   - Use spot nodes for non-critical workloads
   - Right-size node pools based on utilization
   - Use Azure Hybrid Benefit for Windows nodes

2. **API Management:**
   - Start with Standard tier, upgrade to Premium when needed
   - Monitor gateway usage vs. scale units

3. **Cosmos DB:**
   - Use autoscale to avoid over-provisioning
   - Consider serverless for dev/test
   - Optimize partition key to avoid hot partitions

4. **SQL:**
   - Use serverless for variable workloads
   - Consider reserved capacity for consistent loads
   - Use elastic pools for multiple databases

5. **Monitoring:**
   - Set appropriate retention periods (30-90 days)
   - Use sampling for high-volume telemetry
   - Alert only on actionable metrics

6. **Storage:**
   - Implement lifecycle policies (Hot → Cool → Archive)
   - Enable compression for cold data
   - Use CDN for frequently accessed content

---

## Implementation Checklist

### Phase 1: Foundation ✅

- [ ] Create Entra ID tenant and app registrations
- [ ] Set up service principals and managed identities
- [ ] Configure RBAC roles

### Phase 2: Networking ✅

- [ ] Deploy Azure Front Door with custom domain
- [ ] Configure WAF policies
- [ ] Deploy API Management instance
- [ ] Set up Redis cache
- [ ] Integrate APIM with Redis
- [ ] Configure APIM policies (auth, rate limiting, caching)

### Phase 3: Compute ✅

- [ ] Create AKS cluster with autoscaling
- [ ] Deploy Application Gateway for Containers
- [ ] Deploy microservices to AKS
- [ ] Configure health probes and HPA
- [ ] Set up workload identities

### Phase 4: Data ✅

- [ ] Create Cosmos DB account and containers
- [ ] Create SQL logical server and databases
- [ ] Create Storage accounts
- [ ] Configure private endpoints
- [ ] Test connectivity from AKS

### Phase 5: Observability ✅

- [ ] Create Log Analytics workspace
- [ ] Create Application Insights resources
- [ ] Enable diagnostics on all services
- [ ] Configure SLI queries
- [ ] Create dashboards
- [ ] Set up alert rules

### Phase 6: Testing ✅

- [ ] Run load tests (K6, JMeter, Locust)
- [ ] Validate autoscaling behavior
- [ ] Set up Chaos Studio experiments
- [ ] Run resilience tests
- [ ] Validate SLI/SLO compliance

### Phase 7: Production Readiness ✅

- [ ] Configure backup and disaster recovery
- [ ] Set up CI/CD pipelines
- [ ] Document runbooks
- [ ] Train on-call teams
- [ ] Execute game days

---

## API Reference Summary

### Control Plane APIs (Infrastructure)

| Service                    | API Path                                              | Latest Version     | Key Resources                                                      |
| -------------------------- | ----------------------------------------------------- | ------------------ | ------------------------------------------------------------------ |
| Front Door                 | `specification/frontdoor/resource-manager/`           | 2025-11-01         | FrontDoor, WebApplicationFirewallPolicy, Profile                   |
| API Management             | `specification/apimanagement/resource-manager/`       | 2024-06-01-preview | ApiManagementServiceResource, ApiContract, PolicyContract          |
| AKS                        | `specification/containerservice/resource-manager/`    | 2026-01-02-preview | ManagedCluster, AgentPool, MaintenanceConfiguration                |
| App Gateway for Containers | `specification/servicenetworking/resource-manager/`   | 2025-03-01-preview | TrafficController, Frontend, Association                           |
| Cosmos DB                  | `specification/cosmos-db/resource-manager/`           | Multiple versions  | DatabaseAccountResource, SqlDatabaseResource, SqlContainerResource |
| SQL                        | `specification/sql/resource-manager/`                 | Multiple versions  | Server, Database, ElasticPool, FirewallRule                        |
| Storage                    | `specification/storage/resource-manager/`             | Multiple versions  | StorageAccount, BlobContainer, ManagementPolicy                    |
| Redis                      | `specification/redis/resource-manager/`               | Multiple versions  | RedisResource, RedisFirewallRule                                   |
| Monitor                    | `specification/monitor/resource-manager/`             | Multiple versions  | Workspace, DiagnosticSettings, MetricAlert                         |
| Application Insights       | `specification/applicationinsights/resource-manager/` | Multiple versions  | Component, WebTest                                                 |
| Chaos Studio               | `specification/chaos/resource-manager/`               | Multiple versions  | Experiment, Target, Capability                                     |

### Data Plane APIs (Operations)

| Service      | API Path                              | Purpose                             |
| ------------ | ------------------------------------- | ----------------------------------- |
| Cosmos DB    | `specification/cosmos-db/data-plane/` | Document CRUD, queries, change feed |
| Storage Blob | `specification/storage/data-plane/`   | Blob upload/download, metadata      |

---

## Additional Resources

### Microsoft Learn Paths

- [Develop an SRE strategy](https://learn.microsoft.com/en-us/training/paths/az-400-develop-sre-strategy/)
- [Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/)
- [Microservices architecture on AKS](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/containers/aks-microservices/aks-microservices)

### Performance Testing Tools

- **K6**: Modern load testing tool
- **Karate**: API testing and performance
- **JMeter**: Traditional load testing
- **Locust**: Python-based load testing

### Observability Standards

- **OpenTelemetry**: Vendor-agnostic instrumentation
- **Prometheus**: Metrics collection
- **Grafana**: Visualization (integrate with Azure Managed Grafana)

---

## Next Steps After Reading This Skill

1. **For Infrastructure Deployment:**
   - Delegate to IaC agents (Terraform, Bicep, ARM, Pulumi)
   - Use Azure CLI/PowerShell for automation
   - Leverage Azure SDKs for programmatic access

2. **For Application Development:**
   - Use the TypeSpec specifications to understand API contracts
   - Implement microservices following the architecture patterns
   - Integrate Azure SDKs for each service

3. **For Operations:**
   - Set up monitoring dashboards
   - Configure alerting rules
   - Create runbooks for incident response
   - Schedule chaos engineering experiments

4. **For Continuous Improvement:**
   - Review SLI/SLO metrics weekly
   - Conduct post-incident reviews
   - Refine autoscaling thresholds
   - Optimize costs based on usage patterns

---

## Conclusion

This skill provides a comprehensive, API-level guide for building production-grade, scalable cloud applications with Azure. Every service mentioned is backed by real Azure APIs found in the `specification/` directory, ready for automation via CDKs, SDKs, or direct API calls.

The architecture implements proven patterns for high availability, autoscaling, observability, and resilience—critical for modern cloud-native applications serving millions of users.
