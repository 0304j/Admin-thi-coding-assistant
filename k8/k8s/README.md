# Kubernetes Manifests

This directory contains all Kubernetes manifests for the Model Manager application.

## Directory Structure

```
k8s/
├── namespace.yaml                      # Namespace definition
├── model-manager-deployment.yaml       # Model Manager deployment
├── model-manager-service.yaml          # ClusterIP service for internal access
├── model-manager-nodeport.yaml         # NodePort service for external access
├── ollama-deployment.yaml              # Ollama deployment (3 replicas with GPU)
├── ollama-service.yaml                 # Ollama ClusterIP service
├── model-health-check-cronjob.yaml     # Health check CronJob (every 5 min)
├── model-health-script-configmap.yaml  # Health check script ConfigMap
├── model-usage-stats-configmap.yaml    # Model usage statistics ConfigMap
├── GPU_TIME_SLICING_GUIDE.md           # GPU time-slicing configuration guide
└── README.md                           # This documentation
```

## Deployment Order

```bash
# 1. Create namespace
kubectl apply -f namespace.yaml

# 2. Deploy ConfigMaps
kubectl apply -f model-health-script-configmap.yaml
kubectl apply -f model-usage-stats-configmap.yaml

# 3. Deploy Ollama (requires GPU and PVC)
kubectl apply -f ollama-deployment.yaml
kubectl apply -f ollama-service.yaml

# 4. Deploy Model Manager
kubectl apply -f model-manager-deployment.yaml
kubectl apply -f model-manager-service.yaml
kubectl apply -f model-manager-nodeport.yaml

# 5. Deploy health check (optional)
kubectl apply -f model-health-check-cronjob.yaml
```

## Apply All at Once

```bash
kubectl apply -f k8s/
```

## Prerequisites

Before deploying, ensure you have:

1. **PersistentVolumeClaim** for Ollama models:
   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: ollama-pvc
     namespace: model-hosting
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: 100Gi
   ```

2. **ServiceAccount** for Model Manager:
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: model-manager
     namespace: model-hosting
   ```

3. **NVIDIA GPU** available in cluster with device plugin installed

---

## ConfigMaps

The application uses two ConfigMaps for operational functionality.

### model-health-script

**File**: `model-health-script-configmap.yaml`

**Purpose**: Contains the shell script executed by the CronJob to perform model health checks and auto-recovery.

**Data Key**: `check-models.sh`

**Usage**: Mounted as a volume in the `model-health-check` CronJob at `/scripts/check-models.sh`.

**Script Workflow**:

1. **Step 1**: Verify Ollama service connectivity
2. **Step 2**: Fetch expected models from Model Manager API (`/api/ollama/models`)
3. **Step 3**: Fetch currently available models from Ollama (`/api/tags`)
4. **Step 4**: Compare expected vs available models to identify missing models
5. **Step 5**: Auto-pull missing models if `AUTO_PULL=true` (default)
6. **Step 6**: Optional inference test if `TEST_INFERENCE=true`

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://ollama-service.model-hosting.svc.cluster.local:11434` | Ollama service endpoint |
| `MODEL_MANAGER_URL` | `http://model-manager-service.model-hosting.svc.cluster.local:8080` | Model Manager service endpoint |
| `AUTO_PULL` | `true` | Automatically re-pull missing models |
| `TEST_INFERENCE` | `false` | Run inference test on first available model |
| `REPORT_STATUS` | `false` | Report health status back to Model Manager |

**Deployment**:

```bash
kubectl apply -f model-health-script-configmap.yaml
```

**View Current Script**:

```bash
kubectl get configmap model-health-script -n model-hosting -o jsonpath='{.data.check-models\.sh}'
```

**Update Script**:

```bash
# Edit the configmap
kubectl edit configmap model-health-script -n model-hosting

# Or replace from file
kubectl apply -f model-health-script-configmap.yaml

# Restart CronJob pods to pick up changes (next scheduled run will use new script)
kubectl delete job -n model-hosting -l app=model-health-check
```

### model-usage-stats

**File**: `model-usage-stats-configmap.yaml`

**Purpose**: Stores model usage statistics and metadata. Used by the Model Manager backend to persist usage data across pod restarts without requiring a database.

**Data Key**: `usage_data`

**Initial Value**: `{}` (empty JSON object)

**Usage**: Read and written by the Model Manager Python backend (`vue-api-server.py`) to track:
- Model pull counts
- Model inference request counts
- Last used timestamps
- Error counts per model

**Deployment**:

```bash
kubectl apply -f model-usage-stats-configmap.yaml
```

**View Current Data**:

```bash
kubectl get configmap model-usage-stats -n model-hosting -o jsonpath='{.data.usage_data}' | jq .
```

**Reset Usage Statistics**:

```bash
kubectl patch configmap model-usage-stats -n model-hosting --type merge -p '{"data":{"usage_data":"{}"}}'
```

**Backup Usage Data**:

```bash
kubectl get configmap model-usage-stats -n model-hosting -o jsonpath='{.data.usage_data}' > usage_backup.json
```

### ConfigMap Reference in Deployments

**CronJob Mount** (model-health-check-cronjob.yaml):

```yaml
spec:
  template:
    spec:
      volumes:
        - name: health-script
          configMap:
            name: model-health-script
            defaultMode: 0755
      containers:
        - name: health-checker
          volumeMounts:
            - name: health-script
              mountPath: /scripts
          command: ["/scripts/check-models.sh"]
```

**Model Manager Environment** (model-manager-deployment.yaml):

The Model Manager accesses `model-usage-stats` via the Kubernetes API using its ServiceAccount, not as a mounted volume. This allows dynamic read/write operations.

---

## Resource Summary

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit | GPU |
|-----------|-------------|-----------|----------------|--------------|-----|
| model-manager | 250m | 500m | 512Mi | 2Gi | - |
| ollama | 500m | 2000m | 4Gi | 16Gi | 1 |
| health-checker | 50m | 100m | 64Mi | 128Mi | - |

## ConfigMap Summary

| ConfigMap | Purpose | Used By |
|-----------|---------|---------|
| model-health-script | Health check shell script | CronJob |
| model-usage-stats | Usage statistics storage | Model Manager |
| kube-root-ca.crt | Kubernetes CA certificate (auto-created) | Internal TLS |

## Access

- **Internal**: `http://model-manager-service.model-hosting:8080`
- **External**: `http://<node-ip>:30501`

## Update Deployment

```bash
# Update image
kubectl set image deployment/model-manager model-manager=arnoldt04/model-manager:latest -n model-hosting

# Or restart to pull latest
kubectl rollout restart deployment/model-manager -n model-hosting
```

## Monitoring

```bash
# Check status
kubectl get all -n model-hosting

# View logs
kubectl logs -f deployment/model-manager -n model-hosting
kubectl logs -f deployment/ollama -n model-hosting

# Check health check job history
kubectl get jobs -n model-hosting

# View ConfigMaps
kubectl get configmap -n model-hosting

# Check health script output from last job
kubectl logs -n model-hosting job/$(kubectl get jobs -n model-hosting -o jsonpath='{.items[-1].metadata.name}')
```

## Troubleshooting ConfigMaps

### Health Check Script Not Executing

```bash
# Verify ConfigMap exists
kubectl get configmap model-health-script -n model-hosting

# Check CronJob configuration
kubectl describe cronjob model-health-check -n model-hosting

# Check if script is mounted correctly
kubectl get pods -n model-hosting -l app=model-health-check -o yaml | grep -A 10 volumeMounts
```

### Usage Stats Not Persisting

```bash
# Check Model Manager ServiceAccount permissions
kubectl auth can-i get configmaps --as=system:serviceaccount:model-hosting:model-manager -n model-hosting
kubectl auth can-i update configmaps --as=system:serviceaccount:model-hosting:model-manager -n model-hosting

# View Model Manager logs for ConfigMap errors
kubectl logs deployment/model-manager -n model-hosting | grep -i configmap
```

### Recreate ConfigMaps

```bash
# Delete and recreate
kubectl delete configmap model-health-script model-usage-stats -n model-hosting
kubectl apply -f model-health-script-configmap.yaml
kubectl apply -f model-usage-stats-configmap.yaml
```
