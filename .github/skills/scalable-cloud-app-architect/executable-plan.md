# Scalable Cloud Application — Executable Deployment Plan

> **Purpose:** A fully executable, step-by-step deployment plan that provisions the entire scalable cloud architecture using the Azure CLI (`az`). Every command is ordered to respect dependencies — for each Azure service the equivalent REST API spec lives under the `specification/` directory.
>
> **Org-policy fixes applied in this plan:**
>
> - Phase 1 (Entra ID app registration) is **skipped** — blocked by conditional access policy (AADSTS530084)
> - AKS is deployed to **`westus2`** (VM quota restrictions prevent D-series/DS-series in `eastus`)
> - Cosmos DB: `--disable-key-based-metadata-write-access` (no local auth)
> - SQL Server: Entra-only authentication (no local admin password)
> - Storage: `--allow-shared-key-access false` (org policy disallows shared key)
> - Storage lifecycle: no `tierToArchive` (ZRS accounts don't support archive tier)
> - APIM: `StandardV2` SKU (~5 min provisioning vs 30-45 min for classic `Standard`)

---

## Prerequisites

```bash
# ── Login & set subscription ─────────────────────────────────────
az login
az account set --subscription "faa080af-c1d8-40ad-9cce-e1a450ca5b57"

# ── Environment variables (set once, used throughout) ────────────
export SUB_ID="$(az account show --query id -o tsv)"
export RG="scalable-app-rg-qiaozhatest"
export LOCATION="eastus"
export AKS_LOCATION="westus2"          # AKS deployed here due to eastus VM quota limits

export WORKSPACE_NAME="scalable-app-law"
export APPINSIGHTS_NAME="scalable-app-ai"
export ACTION_GROUP_NAME="scalable-app-ag"
export COSMOS_ACCOUNT="scalableappcosmosdb"
export SQL_SERVER="scalableappsql"
export STORAGE_ACCOUNT="scalableappstor"
export REDIS_NAME="scalable-app-redis"
export AKS_CLUSTER="scalable-app-aks"
export AGC_NAME="scalable-app-agc"
export APIM_NAME="scalable-app-apim"
export FD_PROFILE="scalable-app-fd"
export WAF_POLICY="scalableappwafpolicy"

# ── Your identity (used for SQL Entra-only admin) ─────────────────
export MY_UPN="qiaozha@microsoft.com"
export MY_OID="$(az ad signed-in-user show --query id -o tsv)"
export MY_TENANT="$(az account show --query tenantId -o tsv)"
```

---

## Phase 0 — Resource Group

**Dependency:** None (first resource).

```bash
# ── 0.1  Create Resource Group ──────────────────────────────────
az group create \
  --name "$RG" \
  --location "$LOCATION"
```

---

## Phase 1 — Identity & Access (Entra ID + RBAC)

> ⚠️ **SKIPPED** — Entra ID app registration via `az ad app create` is blocked by the org's conditional access policy (AADSTS530084: non-interactive Graph token not allowed). All downstream resources that reference `APP_ID` or `SP_OBJECT_ID` must be configured manually after obtaining them from the Azure Portal or a privileged account.
>
> If your tenant allows interactive Graph access, run:
>
> ```bash
> APP_ID=$(az ad app create \
>   --display-name "scalable-app-api" \
>   --sign-in-audience AzureADMyOrg \
>   --query appId -o tsv)
>
> SP_OBJECT_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
>
> az role assignment create \
>   --assignee "$SP_OBJECT_ID" \
>   --role Contributor \
>   --scope "/subscriptions/${SUB_ID}/resourceGroups/${RG}"
> ```

---

## Phase 2 — Observability Foundation

> Deploy monitoring first so every subsequent resource can immediately send diagnostics.

### 2.1 Log Analytics Workspace

**API Spec:** `specification/operationalinsights/resource-manager/` — `2025-07-01`

```bash
# ── 2.1  Log Analytics Workspace ────────────────────────────────
az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$WORKSPACE_NAME" \
  --location "$LOCATION" \
  --sku PerGB2018 \
  --retention-time 90

export WORKSPACE_ID="$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$WORKSPACE_NAME" \
  --query id -o tsv)"
```

### 2.2 Application Insights (workspace-based)

**API Spec:** `specification/applicationinsights/resource-manager/` — `2020-02-02`

```bash
# ── 2.2  Application Insights ───────────────────────────────────
az monitor app-insights component create \
  --resource-group "$RG" \
  --app "$APPINSIGHTS_NAME" \
  --location "$LOCATION" \
  --kind web \
  --application-type web \
  --workspace "$WORKSPACE_ID"

export APPINSIGHTS_IKEY="$(az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APPINSIGHTS_NAME" \
  --query instrumentationKey -o tsv)"

echo "App Insights ikey: $APPINSIGHTS_IKEY"
```

### 2.3 Action Group (for Alerts)

**API Spec:** `specification/monitor/resource-manager/` — `2023-01-01`

```bash
# ── 2.3  Action Group ───────────────────────────────────────────
az monitor action-group create \
  --resource-group "$RG" \
  --name "$ACTION_GROUP_NAME" \
  --short-name SREOncall \
  --action email SRETeam qiaozha@microsoft.com

export ACTION_GROUP_ID="$(az monitor action-group show \
  --resource-group "$RG" \
  --name "$ACTION_GROUP_NAME" \
  --query id -o tsv)"
```

---

## Phase 3 — Data Layer

> Data stores are provisioned before compute because AKS microservices need connection endpoints at deployment time.

### 3.1 Azure Cosmos DB Account + Databases + Containers

**API Spec:** `specification/cosmos-db/resource-manager/` — `2025-10-15`

> **Org-policy fix:** `--disable-key-based-metadata-write-access true` prevents local-auth; Entra-only access enforced.

```bash
# ── 3.1a  Cosmos DB Account ─────────────────────────────────────
az cosmosdb create \
  --resource-group "$RG" \
  --name "$COSMOS_ACCOUNT" \
  --kind GlobalDocumentDB \
  --default-consistency-level Session \
  --locations regionName="$LOCATION" failoverPriority=0 isZoneRedundant=true \
  --locations regionName=westus failoverPriority=1 isZoneRedundant=false \
  --enable-automatic-failover true \
  --enable-multiple-write-locations false \
  --disable-key-based-metadata-write-access true
# ⏳ Wait ~5-10 minutes for provisioning to complete.
```

```bash
# ── 3.1b  Cosmos DB — Product Catalog database ──────────────────
az cosmosdb sql database create \
  --resource-group "$RG" \
  --account-name "$COSMOS_ACCOUNT" \
  --name productdb \
  --max-throughput 10000
```

```bash
# ── 3.1c  Cosmos DB — Products container ────────────────────────
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$COSMOS_ACCOUNT" \
  --database-name productdb \
  --name products \
  --partition-key-path /categoryId \
  --idx '{"indexingMode":"consistent","automatic":true,"includedPaths":[{"path":"/*"}],"excludedPaths":[{"path":"/description/*"}]}'
```

```bash
# ── 3.1d  Cosmos DB — Profiles database + container ─────────────
az cosmosdb sql database create \
  --resource-group "$RG" \
  --account-name "$COSMOS_ACCOUNT" \
  --name profiledb \
  --max-throughput 4000

az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$COSMOS_ACCOUNT" \
  --database-name profiledb \
  --name users \
  --partition-key-path /userId
```

### 3.2 Azure SQL Server & Databases

**API Spec:** `specification/sql/resource-manager/` — `2025-01-01`

> **Org-policy fix:** Local SQL authentication is not allowed. The server is created with Entra-only auth (`--enable-ad-only-auth`). No SQL admin password is set.

```bash
# ── 3.2a  SQL Logical Server (Entra-only auth) ───────────────────
az sql server create \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --location "$LOCATION" \
  --enable-ad-only-auth \
  --external-admin-principal-type User \
  --external-admin-name "$MY_UPN" \
  --external-admin-sid "$MY_OID"
# ⏳ Async — wait for Succeeded state.
```

```bash
# ── 3.2b  SQL Firewall — Allow Azure Services ────────────────────
az sql server firewall-rule create \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

```bash
# ── 3.2c  SQL Database — Orders (serverless, 4 vCores) ───────────
az sql db create \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name ordersdb \
  --edition GeneralPurpose \
  --family Gen5 \
  --capacity 4 \
  --compute-model Serverless \
  --auto-pause-delay 60 \
  --min-capacity 1 \
  --zone-redundant true
```

```bash
# ── 3.2d  SQL Database — Subscriptions (serverless, 2 vCores) ────
az sql db create \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name subscriptionsdb \
  --edition GeneralPurpose \
  --family Gen5 \
  --capacity 2 \
  --compute-model Serverless \
  --auto-pause-delay 60 \
  --min-capacity 0.5
```

### 3.3 Azure Storage Account (Blob + Data Lake Gen2)

**API Spec:** `specification/storage/resource-manager/` — `2025-08-01`

> **Org-policy fix:** `--allow-shared-key-access false` — shared-key access is disallowed by org policy. Use Entra (RBAC) to access blobs.
>
> **ZRS limitation:** Archive tier is not supported on ZRS accounts. Lifecycle policy only uses `Cool` tiering and deletion.

```bash
# ── 3.3a  Storage Account ───────────────────────────────────────
az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_ACCOUNT" \
  --location "$LOCATION" \
  --kind StorageV2 \
  --sku Standard_ZRS \
  --enable-hierarchical-namespace true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --https-only true \
  --access-tier Hot \
  --allow-shared-key-access false
```

```bash
# ── 3.3b  Blob Containers ────────────────────────────────────────
# NOTE: shared-key is disabled; authenticate with --auth-mode login
for CONTAINER in media documents archive datalake; do
  az storage container create \
    --account-name "$STORAGE_ACCOUNT" \
    --name "$CONTAINER" \
    --auth-mode login
done
```

```bash
# ── 3.3c  Lifecycle Management Policy ───────────────────────────
# NOTE: tierToArchive removed — Standard_ZRS does not support the archive tier.
az storage account management-policy create \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --policy '{
    "rules": [
      {
        "name": "moveToCool",
        "enabled": true,
        "type": "Lifecycle",
        "definition": {
          "filters": {
            "blobTypes": ["blockBlob"],
            "prefixMatch": ["media/", "documents/"]
          },
          "actions": {
            "baseBlob": {
              "tierToCool": { "daysAfterModificationGreaterThan": 30 },
              "delete":     { "daysAfterModificationGreaterThan": 730 }
            }
          }
        }
      }
    ]
  }'
```

### 3.4 Azure Cache for Redis (Premium, zone-redundant)

**API Spec:** `specification/redis/resource-manager/` — `2024-11-01`

```bash
# ── 3.4  Redis Premium P1 ───────────────────────────────────────
az redis create \
  --resource-group "$RG" \
  --name "$REDIS_NAME" \
  --location "$LOCATION" \
  --sku Premium \
  --vm-size P1 \
  --redis-version 6 \
  --minimum-tls-version 1.2 \
  --zones 1 2 \
  --redis-configuration maxmemory-policy=allkeys-lru \
  --replica-count 1
# ⏳ Wait ~15-20 minutes for Premium Redis to finish.
```

---

## Phase 4 — Compute Layer

### 4.1 Azure Kubernetes Service (AKS)

**API Spec:** `specification/containerservice/resource-manager/` — `2026-01-01`

> **Org-policy fix:** AKS moved to **`westus2`** — D-series, DS-series, and B-series VMs are quota-restricted in `eastus` for this subscription. `Standard_D4s_v3` is available in `westus2`.
>
> Availability zones are not specified — zone support depends on region+VM-size combination.

```bash
# ── 4.1a  AKS Cluster ────────────────────────────────────────────
az aks create \
  --resource-group "$RG" \
  --name "$AKS_CLUSTER" \
  --location "$AKS_LOCATION" \
  --kubernetes-version 1.30 \
  --node-count 1 \
  --min-count 1 \
  --max-count 3 \
  --enable-cluster-autoscaler \
  --node-vm-size Standard_D4s_v3 \
  --nodepool-name system \
  --network-plugin azure \
  --network-policy azure \
  --service-cidr 10.0.0.0/16 \
  --dns-service-ip 10.0.0.10 \
  --enable-managed-identity \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --workspace-resource-id "$WORKSPACE_ID" \
  --enable-addons monitoring \
  --generate-ssh-keys
# ⏳ Wait ~5-10 minutes.
```

```bash
# ── 4.1b  AKS — Workload Node Pool (User mode, autoscaling) ──────
az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$AKS_CLUSTER" \
  --name workload \
  --node-count 3 \
  --min-count 3 \
  --max-count 20 \
  --enable-cluster-autoscaler \
  --node-vm-size Standard_D8s_v3 \
  --mode User \
  --labels workload=microservices
```

### 4.2 Application Gateway for Containers (Traffic Controller)

**API Spec:** `specification/servicenetworking/resource-manager/` — `2025-01-01`

```bash
# ── 4.2a  Install ALB Controller extension on AKS ───────────────
az k8s-extension create \
  --resource-group "$RG" \
  --cluster-name "$AKS_CLUSTER" \
  --cluster-type managedClusters \
  --name alb-controller \
  --extension-type microsoft.app.containers.applicationlbcontroller \
  --scope cluster \
  --release-train stable
```

```bash
# ── 4.2b  Traffic Controller ─────────────────────────────────────
az network alb create \
  --resource-group "$RG" \
  --name "$AGC_NAME" \
  --location "$LOCATION"
```

```bash
# ── 4.2c  Frontend ──────────────────────────────────────────────
az network alb frontend create \
  --resource-group "$RG" \
  --alb-name "$AGC_NAME" \
  --name primary

export AGC_FQDN="$(az network alb frontend show \
  --resource-group "$RG" \
  --alb-name "$AGC_NAME" \
  --name primary \
  --query 'fqdn' -o tsv)"
echo "AGC FQDN: $AGC_FQDN"
```

```bash
# ── 4.2d  Association (link to AKS subnet) ───────────────────────
AKS_NODE_RG="$(az aks show \
  --resource-group "$RG" \
  --name "$AKS_CLUSTER" \
  --query nodeResourceGroup -o tsv)"

AKS_VNET_NAME="$(az network vnet list \
  --resource-group "$AKS_NODE_RG" \
  --query '[0].name' -o tsv)"

SUBNET_ID="$(az network vnet subnet list \
  --resource-group "$AKS_NODE_RG" \
  --vnet-name "$AKS_VNET_NAME" \
  --query '[0].id' -o tsv)"

az network alb association create \
  --resource-group "$RG" \
  --alb-name "$AGC_NAME" \
  --name aks-assoc \
  --association-type subnets \
  --subnets "$SUBNET_ID"
```

---

## Phase 5 — API Gateway

**API Spec:** `specification/apimanagement/resource-manager/` — `2024-05-01`

> **Org-policy fix:** Using `StandardV2` SKU — provisions in ~5 minutes vs 30-45 minutes for classic `Standard`.

### 5.1 APIM Instance

```bash
# ── 5.1a  API Management Instance (StandardV2) ───────────────────
az apim create \
  --resource-group "$RG" \
  --name "$APIM_NAME" \
  --location "$LOCATION" \
  --sku-name StandardV2 \
  --sku-capacity 1 \
  --publisher-email "qiaozha@microsoft.com" \
  --publisher-name "Contoso"
# ⏳ Wait ~5 minutes.
```

```bash
# ── 5.1b  APIM Logger — Application Insights ────────────────────
az apim logger create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --logger-id appinsights-logger \
  --logger-type applicationInsights \
  --app-insights-instrumentation-key "$APPINSIGHTS_IKEY"
```

```bash
# ── 5.1c  APIM Backend — Application Gateway for Containers ──────
az apim backend create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --backend-id agc-backend \
  --url "https://${AGC_FQDN}" \
  --protocol http \
  --description "Application Gateway for Containers"
```

```bash
# ── 5.1d  APIM Named Value — Redis Connection String (secret) ─────
export REDIS_KEY="$(az redis list-keys \
  --resource-group "$RG" \
  --name "$REDIS_NAME" \
  --query primaryKey -o tsv)"

az apim nv create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --named-value-id redis-connection \
  --display-name "redis-connection-string" \
  --value "${REDIS_NAME}.redis.cache.windows.net:6380,password=${REDIS_KEY},ssl=True,abortConnect=False" \
  --secret true
```

### 5.2 APIs — Product Service

```bash
# ── 5.2a  Product API ────────────────────────────────────────────
az apim api create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id product-api \
  --display-name "Product Service API" \
  --path products \
  --protocols https \
  --service-url "https://${AGC_FQDN}/api/products" \
  --subscription-required true

# ── 5.2b  GET /products ──────────────────────────────────────────
az apim api operation create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id product-api \
  --operation-id list-products \
  --display-name "List Products" \
  --method GET \
  --url-template "/"

# ── 5.2c  GET /products/{productId} ─────────────────────────────
az apim api operation create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id product-api \
  --operation-id get-product \
  --display-name "Get Product" \
  --method GET \
  --url-template "/{productId}"
```

### 5.3 APIs — Profile, Orders, Content

```bash
# ── 5.3a  Profile API ────────────────────────────────────────────
az apim api create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id profile-api \
  --display-name "Profile Service API" \
  --path profiles \
  --protocols https \
  --service-url "https://${AGC_FQDN}/api/profiles" \
  --subscription-required true

# ── 5.3b  Orders API ─────────────────────────────────────────────
az apim api create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id orders-api \
  --display-name "Orders & Payment Service API" \
  --path orders \
  --protocols https \
  --service-url "https://${AGC_FQDN}/api/orders" \
  --subscription-required true

# ── 5.3c  Content API ────────────────────────────────────────────
az apim api create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id content-api \
  --display-name "Content Service API" \
  --path content \
  --protocols https \
  --service-url "https://${AGC_FQDN}/api/content" \
  --subscription-required true
```

### 5.4 Policies

```bash
# ── 5.4a  Global APIM Policy (JWT + rate-limit + CORS) ───────────
az apim policy create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --xml-policy '<policies><inbound><cors allow-credentials="true"><allowed-origins><origin>https://app.contoso.com</origin></allowed-origins><allowed-methods preflight-result-max-age="300"><method>*</method></allowed-methods><allowed-headers><header>*</header></allowed-headers></cors><validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"><openid-config url="https://login.microsoftonline.com/contoso.onmicrosoft.com/v2.0/.well-known/openid-configuration" /><audiences><audience>api://scalable-app-api</audience></audiences></validate-jwt><rate-limit calls="1000" renewal-period="60" /><set-header name="X-Request-ID" exists-action="skip"><value>@(context.RequestId.ToString())</value></set-header></inbound><backend><forward-request timeout="30" /></backend><outbound /><on-error><set-header name="ErrorSource" exists-action="override"><value>@(context.LastError.Source)</value></set-header></on-error></policies>'
```

```bash
# ── 5.4b  Product API — Response Cache Policy (300 s) ────────────
az apim api policy create \
  --resource-group "$RG" \
  --service-name "$APIM_NAME" \
  --api-id product-api \
  --xml-policy '<policies><inbound><base /><cache-lookup vary-by-developer="false" vary-by-developer-groups="false" downstream-caching-type="none" /></inbound><backend><base /></backend><outbound><base /><cache-store duration="300" /></outbound><on-error><base /></on-error></policies>'
```

---

## Phase 6 — Front Door (Edge Layer)

**API Spec:** `specification/cdn/resource-manager/` — `2025-06-01`

### 6.1 WAF Policy

```bash
# ── 6.1  WAF Policy (Premium_AzureFrontDoor, Prevention mode) ────
az network front-door waf-policy create \
  --resource-group "$RG" \
  --name "$WAF_POLICY" \
  --sku Premium_AzureFrontDoor \
  --mode Prevention \
  --managed-rule-set type=Microsoft_DefaultRuleSet version=2.1 \
  --managed-rule-set type=Microsoft_BotManagerRuleSet version=1.1
```

### 6.2 Front Door Profile

```bash
# ── 6.2  Front Door Profile ──────────────────────────────────────
az afd profile create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --sku Premium_AzureFrontDoor
```

### 6.3 Endpoint

```bash
# ── 6.3  AFD Endpoint ────────────────────────────────────────────
az afd endpoint create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --endpoint-name api-endpoint \
  --enabled-state Enabled

FD_HOSTNAME="$(az afd endpoint show \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --endpoint-name api-endpoint \
  --query hostName -o tsv)"
echo "Front Door endpoint: https://${FD_HOSTNAME}"
```

### 6.4 Origin Group → API Management

```bash
# ── 6.4a  Origin Group ───────────────────────────────────────────
az afd origin-group create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --origin-group-name apim-origin-group \
  --probe-request-type GET \
  --probe-protocol Https \
  --probe-interval-in-seconds 30 \
  --probe-path "/status-0123456789abcdef" \
  --sample-size 4 \
  --successful-samples-required 3 \
  --additional-latency-in-milliseconds 50

# ── 6.4b  Origin (APIM gateway URL) ──────────────────────────────
az afd origin create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --origin-group-name apim-origin-group \
  --origin-name apim-origin \
  --host-name "${APIM_NAME}.azure-api.net" \
  --origin-host-header "${APIM_NAME}.azure-api.net" \
  --https-port 443 \
  --http-port 80 \
  --priority 1 \
  --weight 1000 \
  --enabled-state Enabled \
  --enforce-certificate-name-check true
```

### 6.5 Route

```bash
# ── 6.5  Route (/* → origin group) ───────────────────────────────
az afd route create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --endpoint-name api-endpoint \
  --route-name default-route \
  --origin-group apim-origin-group \
  --supported-protocols Https \
  --https-redirect Enabled \
  --forwarding-protocol HttpsOnly \
  --patterns-to-match '/*' \
  --link-to-default-domain Enabled \
  --enabled-state Enabled
```

### 6.6 Security Policy (Attach WAF)

```bash
# ── 6.6  Security Policy ─────────────────────────────────────────
WAF_ID="$(az network front-door waf-policy show \
  --resource-group "$RG" \
  --name "$WAF_POLICY" \
  --query id -o tsv)"

az afd security-policy create \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --security-policy-name waf-policy \
  --domains "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Cdn/profiles/${FD_PROFILE}/afdEndpoints/api-endpoint" \
  --waf-policy "$WAF_ID"
```

---

## Phase 7 — Diagnostic Settings

**API Spec:** `specification/monitor/resource-manager/` — `2021-05-01-preview`

```bash
# ── 7.1  Front Door ──────────────────────────────────────────────
az monitor diagnostic-settings create \
  --name fd-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Cdn/profiles/${FD_PROFILE}" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.2  API Management ──────────────────────────────────────────
az monitor diagnostic-settings create \
  --name apim-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ApiManagement/service/${APIM_NAME}" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.3  AKS ────────────────────────────────────────────────────
az monitor diagnostic-settings create \
  --name aks-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.4  Cosmos DB ───────────────────────────────────────────────
az monitor diagnostic-settings create \
  --name cosmos-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.5  SQL Databases ───────────────────────────────────────────
az monitor diagnostic-settings create \
  --name sql-orders-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Sql/servers/${SQL_SERVER}/databases/ordersdb" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

az monitor diagnostic-settings create \
  --name sql-subs-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Sql/servers/${SQL_SERVER}/databases/subscriptionsdb" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.6  Redis ───────────────────────────────────────────────────
az monitor diagnostic-settings create \
  --name redis-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Cache/redis/${REDIS_NAME}" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'

# ── 7.7  Storage (Blob service) ──────────────────────────────────
az monitor diagnostic-settings create \
  --name storage-diag \
  --resource "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Storage/storageAccounts/${STORAGE_ACCOUNT}/blobServices/default" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'
```

---

## Phase 8 — SLI/SLO Metric Alerts

**API Spec:** `specification/monitor/resource-manager/` — `2018-03-01`

```bash
# ── 8.1  Availability Alert — Front Door (P0, Critical) ──────────
az monitor metrics alert create \
  --resource-group "$RG" \
  --name fd-availability-p0 \
  --description "P0: Front Door origin health dropped below 99%" \
  --severity 0 \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Cdn/profiles/${FD_PROFILE}" \
  --condition "avg OriginHealthPercentage < 99" \
  --window-size PT5M \
  --evaluation-frequency PT1M \
  --action "$ACTION_GROUP_ID"

# ── 8.2  Latency Alert — APIM backend P95 (P1, High) ─────────────
az monitor metrics alert create \
  --resource-group "$RG" \
  --name apim-latency-p1 \
  --description "P1: APIM backend duration exceeds 3000 ms" \
  --severity 1 \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ApiManagement/service/${APIM_NAME}" \
  --condition "avg BackendDuration > 3000" \
  --window-size PT5M \
  --evaluation-frequency PT1M \
  --action "$ACTION_GROUP_ID"

# ── 8.3  Error Rate Alert — APIM (P1) ────────────────────────────
az monitor metrics alert create \
  --resource-group "$RG" \
  --name apim-error-rate-p1 \
  --description "P1: APIM failed request count exceeds 20 in 5 min" \
  --severity 1 \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ApiManagement/service/${APIM_NAME}" \
  --condition "total FailedRequests > 20" \
  --window-size PT5M \
  --evaluation-frequency PT1M \
  --action "$ACTION_GROUP_ID"

# ── 8.4  Cosmos DB Throttling Alert (P1) ─────────────────────────
az monitor metrics alert create \
  --resource-group "$RG" \
  --name cosmos-throttle-p1 \
  --description "P1: Cosmos DB RU consumption exceeds 9000 (near max autoscale)" \
  --severity 1 \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}" \
  --condition "total TotalRequestUnits > 9000" \
  --window-size PT5M \
  --evaluation-frequency PT1M \
  --action "$ACTION_GROUP_ID"

# ── 8.5  AKS High CPU Alert (P2) ─────────────────────────────────
az monitor metrics alert create \
  --resource-group "$RG" \
  --name aks-cpu-p2 \
  --description "P2: AKS CPU utilization above 85% for 10 min" \
  --severity 2 \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}" \
  --condition "avg node_cpu_usage_percentage > 85" \
  --window-size PT10M \
  --evaluation-frequency PT5M \
  --action "$ACTION_GROUP_ID"
```

---

## Phase 9 — Chaos Engineering (Resilience Testing)

**API Spec:** `specification/chaos/resource-manager/` — `2025-01-01`

> Chaos Studio does not yet have full `az chaos` CLI coverage; use `az rest` for targets/capabilities/experiments.

```bash
# ── 9.1a  Chaos Target — AKS ─────────────────────────────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}/providers/Microsoft.Chaos/targets/Microsoft-AzureKubernetesServiceChaosMesh?api-version=2025-01-01" \
  --body '{"properties":{}}'

# ── 9.1b  Chaos Target — Cosmos DB ───────────────────────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}/providers/Microsoft.Chaos/targets/Microsoft-CosmosDB?api-version=2025-01-01" \
  --body '{"properties":{}}'

# ── 9.2a  AKS Pod Chaos capability ───────────────────────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}/providers/Microsoft.Chaos/targets/Microsoft-AzureKubernetesServiceChaosMesh/capabilities/PodChaos-2.2?api-version=2025-01-01" \
  --body '{"properties":{}}'

# ── 9.2b  Cosmos DB Failover capability ──────────────────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}/providers/Microsoft.Chaos/targets/Microsoft-CosmosDB/capabilities/Failover-1.0?api-version=2025-01-01" \
  --body '{"properties":{}}'
```

```bash
# ── 9.3  Chaos Experiment — AKS Pod Failure ───────────────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Chaos/experiments/aks-pod-failure-test?api-version=2025-01-01" \
  --body "{
    \"location\": \"${LOCATION}\",
    \"identity\": {\"type\": \"SystemAssigned\"},
    \"properties\": {
      \"selectors\": [{
        \"type\": \"List\",
        \"id\": \"aks-selector\",
        \"targets\": [{
          \"type\": \"ChaosTarget\",
          \"id\": \"/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}/providers/Microsoft.Chaos/targets/Microsoft-AzureKubernetesServiceChaosMesh\"
        }]
      }],
      \"steps\": [{
        \"name\": \"Step1-KillPods\",
        \"branches\": [{
          \"name\": \"Branch1-ProductService\",
          \"actions\": [{
            \"name\": \"urn:csci:microsoft:azureKubernetesServiceChaosMesh:podChaos/2.2\",
            \"type\": \"continuous\",
            \"duration\": \"PT5M\",
            \"parameters\": [{\"key\": \"jsonSpec\", \"value\": \"{\\\"action\\\":\\\"pod-kill\\\",\\\"mode\\\":\\\"fixed\\\",\\\"value\\\":\\\"1\\\",\\\"selector\\\":{\\\"namespaces\\\":[\\\"default\\\"],\\\"labelSelectors\\\":{\\\"app\\\":\\\"product-service\\\"}}}\"}],
            \"selectorId\": \"aks-selector\"
          }]
        }]
      }]
    }
  }"
```

```bash
# ── 9.4  Chaos Experiment — Cosmos DB Region Failover ────────────
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Chaos/experiments/cosmos-failover-test?api-version=2025-01-01" \
  --body "{
    \"location\": \"${LOCATION}\",
    \"identity\": {\"type\": \"SystemAssigned\"},
    \"properties\": {
      \"selectors\": [{
        \"type\": \"List\",
        \"id\": \"cosmos-selector\",
        \"targets\": [{
          \"type\": \"ChaosTarget\",
          \"id\": \"/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}/providers/Microsoft.Chaos/targets/Microsoft-CosmosDB\"
        }]
      }],
      \"steps\": [{
        \"name\": \"Step1-Failover\",
        \"branches\": [{
          \"name\": \"Branch1-CosmosFailover\",
          \"actions\": [{
            \"name\": \"urn:csci:microsoft:cosmosDB:failover/1.0\",
            \"type\": \"continuous\",
            \"duration\": \"PT10M\",
            \"parameters\": [{\"key\": \"readRegion\", \"value\": \"West US\"}],
            \"selectorId\": \"cosmos-selector\"
          }]
        }]
      }]
    }
  }"
```

```bash
# ── 9.5  Start a Chaos Experiment ─────────────────────────────────
# First grant the experiment's managed identity the appropriate role:
EXPERIMENT_PRINCIPAL="$(az rest --method GET \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Chaos/experiments/aks-pod-failure-test?api-version=2025-01-01" \
  --query identity.principalId -o tsv)"

az role assignment create \
  --assignee "$EXPERIMENT_PRINCIPAL" \
  --role "Azure Kubernetes Service Cluster Admin Role" \
  --scope "/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.ContainerService/managedClusters/${AKS_CLUSTER}"

# Then start:
az rest --method POST \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Chaos/experiments/aks-pod-failure-test/start?api-version=2025-01-01"
```

---

## Phase 10 — Validation & Smoke Test

### 10.1 Verify All Resources

```bash
echo "=== Verifying deployment ==="

echo "--- Resource Group ---"
az group show --name "$RG" --query properties.provisioningState -o tsv

echo "--- Log Analytics ---"
az monitor log-analytics workspace show --resource-group "$RG" --workspace-name "$WORKSPACE_NAME" --query provisioningState -o tsv

echo "--- App Insights ---"
az monitor app-insights component show --resource-group "$RG" --app "$APPINSIGHTS_NAME" --query provisioningState -o tsv

echo "--- Cosmos DB ---"
az cosmosdb show --resource-group "$RG" --name "$COSMOS_ACCOUNT" --query provisioningState -o tsv

echo "--- SQL Server ---"
az sql server show --resource-group "$RG" --name "$SQL_SERVER" --query state -o tsv

echo "--- Storage ---"
az storage account show --resource-group "$RG" --name "$STORAGE_ACCOUNT" --query provisioningState -o tsv

echo "--- Redis ---"
az redis show --resource-group "$RG" --name "$REDIS_NAME" --query provisioningState -o tsv

echo "--- AKS (westus2) ---"
az aks show --resource-group "$RG" --name "$AKS_CLUSTER" --query provisioningState -o tsv

echo "--- Traffic Controller ---"
az network alb show --resource-group "$RG" --name "$AGC_NAME" --query provisioningState -o tsv

echo "--- API Management ---"
az apim show --resource-group "$RG" --name "$APIM_NAME" --query provisioningState -o tsv

echo "--- Front Door ---"
az afd profile show --resource-group "$RG" --profile-name "$FD_PROFILE" --query provisioningState -o tsv
```

### 10.2 End-to-End Smoke Test

```bash
# ── 10.2  Smoke-test the live endpoint ────────────────────────────
FD_HOSTNAME="$(az afd endpoint show \
  --resource-group "$RG" \
  --profile-name "$FD_PROFILE" \
  --endpoint-name api-endpoint \
  --query hostName -o tsv)"

echo "Front Door endpoint: https://${FD_HOSTNAME}"

# Test product browsing (after deploying microservices to AKS):
curl -sS -w "\nHTTP Status: %{http_code}\nTotal Time: %{time_total}s\n" \
  -H "Ocp-Apim-Subscription-Key: <your-subscription-key>" \
  "https://${FD_HOSTNAME}/products/"
```

---

## Appendix A — Complete Resource Dependency Graph

```
Phase 0: Resource Group
    │
    ├── Phase 1: Entra ID ⚠️ SKIPPED (org conditional access policy blocks Graph token)
    │
    ├── Phase 2: Observability (deploy FIRST for diagnostics wiring)
    │   ├── Log Analytics Workspace
    │   ├── Application Insights  ← depends on: Log Analytics
    │   └── Action Group
    │
    ├── Phase 3: Data Layer
    │   ├── Cosmos DB Account → SQL Databases → Containers
    │   │     (disableLocalAuth=true, Entra-only)
    │   ├── SQL Server (Entra-only auth, --enable-ad-only-auth) → Databases + Firewall Rules
    │   ├── Storage Account (allowSharedKeyAccess=false, ZRS, no archive tier)
    │   │   → Containers + Lifecycle Policy
    │   └── Redis Cache (Premium P1, zones 1+2)
    │
    ├── Phase 4: Compute  [AKS in westus2 due to eastus VM quota limits]
    │   ├── AKS Cluster (Standard_D4s_v3, no availability zones) + Workload Node Pool
    │   └── App Gateway for Containers
    │       ├── Traffic Controller
    │       ├── Frontend  ← exports AGC_FQDN
    │       └── Association  ← depends on: AKS subnet
    │
    ├── Phase 5: API Gateway (APIM StandardV2, ~5 min provisioning)
    │   ├── APIM Instance
    │   ├── Logger            ← depends on: App Insights IKEY
    │   ├── Backend           ← depends on: AGC_FQDN
    │   ├── Named Values      ← depends on: Redis primary key
    │   ├── APIs + Operations
    │   └── Policies
    │
    ├── Phase 6: Front Door (Edge)
    │   ├── WAF Policy
    │   ├── FD Profile
    │   ├── Endpoint          ← exports FD_HOSTNAME
    │   ├── Origin Group + Origin  ← depends on: APIM gateway hostname
    │   ├── Route                  ← depends on: Origin Group + Endpoint
    │   └── Security Policy        ← depends on: WAF Policy + Endpoint
    │
    ├── Phase 7: Diagnostics  ← depends on: ALL resources + Log Analytics
    │
    ├── Phase 8: Metric Alerts  ← depends on: ALL resources + Action Group
    │
    └── Phase 9: Chaos Engineering
        ├── Targets + Capabilities  ← depends on: AKS, Cosmos DB
        ├── Experiments
        └── Role Assignments for experiment identity
```

## Appendix B — API Version Summary

| Phase | Service            | Resource Provider             | API Version          | Spec Path                                             |
| ----- | ------------------ | ----------------------------- | -------------------- | ----------------------------------------------------- |
| 0     | Resource Group     | Microsoft.Resources           | `2025-04-01`         | `specification/resources/resource-manager/`           |
| 1     | Entra ID           | Microsoft Graph               | `v1.0`               | N/A — SKIPPED (org policy)                            |
| 1     | Role Assignment    | Microsoft.Authorization       | `2022-04-01`         | `specification/authorization/resource-manager/`       |
| 2     | Log Analytics      | Microsoft.OperationalInsights | `2025-07-01`         | `specification/operationalinsights/resource-manager/` |
| 2     | App Insights       | Microsoft.Insights            | `2020-02-02`         | `specification/applicationinsights/resource-manager/` |
| 2     | Action Group       | Microsoft.Insights            | `2023-01-01`         | `specification/monitor/resource-manager/`             |
| 3     | Cosmos DB          | Microsoft.DocumentDB          | `2025-10-15`         | `specification/cosmos-db/resource-manager/`           |
| 3     | SQL                | Microsoft.Sql                 | `2025-01-01`         | `specification/sql/resource-manager/`                 |
| 3     | Storage            | Microsoft.Storage             | `2025-08-01`         | `specification/storage/resource-manager/`             |
| 3     | Redis              | Microsoft.Cache               | `2024-11-01`         | `specification/redis/resource-manager/`               |
| 4     | AKS                | Microsoft.ContainerService    | `2026-01-01`         | `specification/containerservice/resource-manager/`    |
| 4     | Service Networking | Microsoft.ServiceNetworking   | `2025-01-01`         | `specification/servicenetworking/resource-manager/`   |
| 5     | API Management     | Microsoft.ApiManagement       | `2024-05-01`         | `specification/apimanagement/resource-manager/`       |
| 6     | Front Door (CDN)   | Microsoft.Cdn                 | `2025-06-01`         | `specification/cdn/resource-manager/`                 |
| 7     | Diagnostics        | Microsoft.Insights            | `2021-05-01-preview` | `specification/monitor/resource-manager/`             |
| 8     | Metric Alerts      | Microsoft.Insights            | `2018-03-01`         | `specification/monitor/resource-manager/`             |
| 9     | Chaos Studio       | Microsoft.Chaos               | `2025-01-01`         | `specification/chaos/resource-manager/`               |

## Appendix C — Environment Variables Reference

```bash
# ── Set before running ───────────────────────────────────────────
export SUB_ID="faa080af-c1d8-40ad-9cce-e1a450ca5b57"
export RG="scalable-app-rg-qiaozhatest"
export LOCATION="eastus"
export AKS_LOCATION="westus2"           # AKS uses westus2 (eastus VM quota limits)

# ── Your identity ────────────────────────────────────────────────
export MY_UPN="qiaozha@microsoft.com"
export MY_OID="e0f63e9f-e67d-46b9-a50d-c5846cc99ed2"
export MY_TENANT="72f988bf-86f1-41af-91ab-2d7cd011db47"

# ── Resource names ───────────────────────────────────────────────
export WORKSPACE_NAME="scalable-app-law"
export APPINSIGHTS_NAME="scalable-app-ai"
export ACTION_GROUP_NAME="scalable-app-ag"
export COSMOS_ACCOUNT="scalableappcosmosdb"
export SQL_SERVER="scalableappsql"
export STORAGE_ACCOUNT="scalableappstor"
export REDIS_NAME="scalable-app-redis"
export AKS_CLUSTER="scalable-app-aks"
export AGC_NAME="scalable-app-agc"
export APIM_NAME="scalable-app-apim"
export FD_PROFILE="scalable-app-fd"
export WAF_POLICY="scalableappwafpolicy"

# ── Computed during execution (set as each resource is created) ──
export WORKSPACE_ID="<from: az monitor log-analytics workspace show --query id>"
export APPINSIGHTS_IKEY="b109910d-b234-4048-92f5-f978f37fb80f"   # already provisioned
export ACTION_GROUP_ID="<from: az monitor action-group show --query id>"
export AGC_FQDN="<from: az network alb frontend show --query fqdn>"
export REDIS_KEY="<from: az redis list-keys --query primaryKey>"
export FD_HOSTNAME="<from: az afd endpoint show --query hostName>"
```
