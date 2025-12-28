# NVIDIA GPU Time-Slicing Configuration Guide

## Overview

GPU time-slicing enables multiple pods to share a single physical GPU by dividing GPU compute time among workloads. Unlike MIG (Multi-Instance GPU), time-slicing does not partition GPU memory; instead, all workloads share the full GPU memory and take turns executing on the GPU.

This document provides a complete guide to configuring GPU time-slicing for the Ollama deployment on a Kubernetes cluster with NVIDIA GPUs.

---

## Table of Contents

1. [How Time-Slicing Works](#how-time-slicing-works)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Configuration Steps](#configuration-steps)
5. [Verification](#verification)
6. [Ollama Deployment Configuration](#ollama-deployment-configuration)
7. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
8. [Limitations](#limitations)
9. [Best Practices](#best-practices)

---

## How Time-Slicing Works

### Mechanism

GPU time-slicing operates at the CUDA level through context switching:

1. **Context Scheduling**: The NVIDIA driver maintains a queue of CUDA contexts (one per process/container).
2. **Time Quantum**: Each context receives a fixed time slice (typically 1-10ms) to execute on the GPU.
3. **Preemption**: When the time quantum expires, the driver preempts the current context and schedules the next.
4. **Memory Sharing**: All contexts share the same GPU memory pool. There is no memory isolation.

### Comparison with MIG

| Feature | Time-Slicing | MIG (Multi-Instance GPU) |
|---------|--------------|--------------------------|
| Memory Isolation | No | Yes |
| Compute Isolation | No (shared) | Yes (dedicated) |
| GPU Support | All NVIDIA GPUs | A100, H100, A30 only |
| Configuration | Software only | Hardware partitioning |
| Flexibility | High (any ratio) | Fixed partition sizes |
| Overhead | Context switch overhead | Minimal |
| Use Case | Dev/test, bursty workloads | Production, SLA-bound |

### Performance Characteristics

- **Latency**: Context switching adds 10-100 microseconds per switch.
- **Throughput**: Total throughput decreases as more workloads share the GPU.
- **Memory**: Each workload sees full GPU memory but competes for allocation.
- **Fairness**: Round-robin scheduling provides equal time to all contexts.

---

## Prerequisites

### Hardware Requirements

- NVIDIA GPU (any generation supporting CUDA)
- Sufficient GPU memory for all concurrent workloads

### Software Requirements

| Component | Minimum Version |
|-----------|-----------------|
| NVIDIA Driver | 470.x or later |
| NVIDIA Container Toolkit | 1.11.0 or later |
| NVIDIA Device Plugin | 0.13.0 or later |
| Kubernetes | 1.25 or later |
| Container Runtime | containerd 1.6+ or Docker 20.10+ |

### Cluster Requirements

- NVIDIA device plugin deployed as DaemonSet
- GPU nodes labeled appropriately
- RBAC permissions to modify ConfigMaps in the device plugin namespace

---

## Architecture

```
+------------------+     +------------------+     +------------------+
|   Ollama Pod 1   |     |   Ollama Pod 2   |     |   Ollama Pod 3   |
|  nvidia.com/gpu  |     |  nvidia.com/gpu  |     |  nvidia.com/gpu  |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                    +-------------v--------------+
                    |   NVIDIA Device Plugin     |
                    |   (Time-Slicing Enabled)   |
                    +-------------+--------------+
                                  |
                    +-------------v--------------+
                    |   Physical GPU (H100)      |
                    |   23GB VRAM (Time-Sliced)  |
                    +----------------------------+
```

---

## Configuration Steps

### Step 1: Verify Current GPU Configuration

```bash
# Check GPU availability on nodes
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu: .status.capacity["nvidia.com/gpu"]}'

# Check current device plugin deployment
kubectl get pods -n gpu-operator -l app=nvidia-device-plugin-daemonset
# Or if using standalone device plugin:
kubectl get pods -n kube-system -l app=nvidia-device-plugin-daemonset

# Verify GPU driver version on a node
kubectl debug node/<node-name> -it --image=nvidia/cuda:12.0-base -- nvidia-smi
```

### Step 2: Create Time-Slicing ConfigMap

Create a ConfigMap that defines the time-slicing configuration:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: gpu-operator
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        renameByDefault: false
        failRequestsGreaterThanOne: false
        resources:
          - name: nvidia.com/gpu
            replicas: 3
EOF
```

**Configuration Parameters:**

| Parameter | Description |
|-----------|-------------|
| `replicas` | Number of virtual GPUs per physical GPU |
| `renameByDefault` | If true, renames resource to `nvidia.com/gpu.shared` |
| `failRequestsGreaterThanOne` | If true, rejects requests for >1 GPU |
| `migStrategy` | Set to `none` for time-slicing only |

### Step 3: Configure NVIDIA Device Plugin

#### Option A: GPU Operator Deployment

If using NVIDIA GPU Operator:

```bash
# Patch the ClusterPolicy to use time-slicing config
kubectl patch clusterpolicy/cluster-policy \
  --type merge \
  -p '{"spec":{"devicePlugin":{"config":{"name":"time-slicing-config","default":"any"}}}}'
```

#### Option B: Standalone Device Plugin

If using standalone NVIDIA device plugin:

```bash
# Edit the device plugin DaemonSet
kubectl edit daemonset nvidia-device-plugin-daemonset -n kube-system
```

Add the ConfigMap reference:

```yaml
spec:
  template:
    spec:
      containers:
        - name: nvidia-device-plugin-ctr
          args:
            - --config-file=/etc/nvidia/config.yaml
          volumeMounts:
            - name: time-slicing-config
              mountPath: /etc/nvidia
      volumes:
        - name: time-slicing-config
          configMap:
            name: time-slicing-config
```

### Step 4: Label Nodes for Time-Slicing

```bash
# Label GPU nodes to use time-slicing configuration
kubectl label node <node-name> nvidia.com/device-plugin.config=any

# Verify label
kubectl get nodes --show-labels | grep nvidia
```

### Step 5: Restart Device Plugin

```bash
# Restart device plugin to apply configuration
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n gpu-operator
# Or for standalone:
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n kube-system

# Wait for rollout to complete
kubectl rollout status daemonset nvidia-device-plugin-daemonset -n gpu-operator
```

### Step 6: Verify Time-Slicing is Active

```bash
# Check node capacity (should show replicas × physical GPUs)
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu: .status.capacity["nvidia.com/gpu"], allocatable: .status.allocatable["nvidia.com/gpu"]}'

# Expected output for 1 physical GPU with 3 replicas:
# {
#   "name": "gpu-node-1",
#   "gpu": "3",
#   "allocatable": "3"
# }
```

---

## Verification

### Verify GPU Capacity

```bash
# Before time-slicing (1 physical GPU):
kubectl describe node <gpu-node> | grep -A 5 "Capacity:"
# nvidia.com/gpu: 1

# After time-slicing (3 replicas):
kubectl describe node <gpu-node> | grep -A 5 "Capacity:"
# nvidia.com/gpu: 3
```

### Test with Sample Pods

```bash
# Deploy test pods to verify time-slicing
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-1
  namespace: model-hosting
spec:
  containers:
    - name: cuda-test
      image: nvidia/cuda:12.0-base
      command: ["sleep", "infinity"]
      resources:
        limits:
          nvidia.com/gpu: 1
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-2
  namespace: model-hosting
spec:
  containers:
    - name: cuda-test
      image: nvidia/cuda:12.0-base
      command: ["sleep", "infinity"]
      resources:
        limits:
          nvidia.com/gpu: 1
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-3
  namespace: model-hosting
spec:
  containers:
    - name: cuda-test
      image: nvidia/cuda:12.0-base
      command: ["sleep", "infinity"]
      resources:
        limits:
          nvidia.com/gpu: 1
EOF

# Verify all pods are running
kubectl get pods -n model-hosting -l app!=ollama

# Check GPU visibility from each pod
kubectl exec -n model-hosting gpu-test-1 -- nvidia-smi
kubectl exec -n model-hosting gpu-test-2 -- nvidia-smi
kubectl exec -n model-hosting gpu-test-3 -- nvidia-smi

# Clean up test pods
kubectl delete pod gpu-test-1 gpu-test-2 gpu-test-3 -n model-hosting
```

---

## Ollama Deployment Configuration

### Update Ollama Deployment for Time-Slicing

With time-slicing enabled (3 replicas), your Ollama deployment can run 3 pods on 1 physical GPU:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: model-hosting
  labels:
    app: ollama
    release: ollama
spec:
  replicas: 3  # Can now run 3 replicas on 1 physical GPU
  selector:
    matchLabels:
      app: ollama
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: ollama
        release: ollama
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: ollama
          image: ollama/ollama:latest
          imagePullPolicy: Always
          command:
            - ollama
            - serve
          ports:
            - name: api
              containerPort: 11434
              protocol: TCP
          env:
            - name: OLLAMA_HOST
              value: 0.0.0.0:11434
            - name: OLLAMA_MODELS
              value: /shared-models
            - name: OLLAMA_KEEP_ALIVE
              value: 5m
            - name: OLLAMA_MAX_LOADED_MODELS
              value: "1"  # Reduced due to shared memory
            - name: CUDA_MPS_PIPE_DIRECTORY
              value: /tmp/nvidia-mps
            - name: CUDA_MPS_LOG_DIRECTORY
              value: /tmp/nvidia-log
          resources:
            requests:
              cpu: 500m
              memory: 2Gi
              nvidia.com/gpu: "1"  # Requests 1 time-slice
            limits:
              cpu: 2000m
              memory: 8Gi
              nvidia.com/gpu: "1"  # Limits to 1 time-slice
          livenessProbe:
            httpGet:
              path: /api/tags
              port: 11434
            initialDelaySeconds: 60
            periodSeconds: 15
            failureThreshold: 3
            timeoutSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/tags
              port: 11434
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 5
          volumeMounts:
            - name: ollama-storage
              mountPath: /shared-models
            - name: ollama-cache
              mountPath: /root/.ollama
      volumes:
        - name: ollama-storage
          persistentVolumeClaim:
            claimName: ollama-pvc
        - name: ollama-cache
          emptyDir: {}
```

### Apply the Updated Deployment

```bash
# Apply the updated deployment
kubectl apply -f k8s/ollama-deployment.yaml

# Watch the rollout
kubectl rollout status deployment/ollama -n model-hosting

# Verify all replicas are running
kubectl get pods -n model-hosting -l app=ollama -o wide
```

### Memory Considerations for Ollama

Since all time-sliced pods share GPU memory:

| Configuration | GPU Memory | Max Concurrent Models per Pod |
|---------------|------------|-------------------------------|
| 1 replica | 23 GB | 3 (7B models) |
| 3 replicas | 23 GB shared | 1 per pod (7B models) |

Adjust `OLLAMA_MAX_LOADED_MODELS` based on:
- Total GPU memory: 23 GB
- Number of replicas: 3
- Average model size: ~4-8 GB for 7B models
- Recommendation: Set to 1 per pod to avoid OOM

---

## Monitoring and Troubleshooting

### Monitor GPU Utilization

```bash
# Watch GPU utilization across all pods
kubectl exec -n model-hosting deployment/ollama -- nvidia-smi dmon -s u -d 1

# Check GPU memory usage
kubectl exec -n model-hosting deployment/ollama -- nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv

# Monitor from node (requires SSH access)
watch -n 1 nvidia-smi
```

### Check Device Plugin Logs

```bash
# View device plugin logs
kubectl logs -n gpu-operator -l app=nvidia-device-plugin-daemonset --tail=100

# Check for time-slicing related messages
kubectl logs -n gpu-operator -l app=nvidia-device-plugin-daemonset | grep -i "time-slic\|replica"
```

### Common Issues and Solutions

#### Issue: Pods stuck in Pending state

```bash
# Check events
kubectl describe pod <pod-name> -n model-hosting | grep -A 10 Events

# Verify GPU availability
kubectl describe node <gpu-node> | grep -A 10 "Allocated resources"
```

**Solution**: Ensure time-slicing ConfigMap is correctly applied and device plugin restarted.

#### Issue: CUDA Out of Memory errors

```bash
# Check current GPU memory usage
kubectl exec -n model-hosting <pod-name> -- nvidia-smi

# Check Ollama logs
kubectl logs -n model-hosting <pod-name> --tail=50
```

**Solution**: Reduce `OLLAMA_MAX_LOADED_MODELS` or reduce number of replicas.

#### Issue: Poor inference performance

**Cause**: Too many concurrent workloads causing excessive context switching.

**Solution**: 
1. Reduce number of time-slice replicas
2. Implement request queuing at application level
3. Consider MIG for production workloads

### Health Check Commands

```bash
# Comprehensive health check script
echo "=== Node GPU Status ==="
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu_capacity: .status.capacity["nvidia.com/gpu"], gpu_allocatable: .status.allocatable["nvidia.com/gpu"]}'

echo "=== Ollama Pods ==="
kubectl get pods -n model-hosting -l app=ollama -o wide

echo "=== GPU Allocation ==="
kubectl describe nodes | grep -A 5 "Allocated resources" | grep nvidia

echo "=== Device Plugin Status ==="
kubectl get pods -n gpu-operator -l app=nvidia-device-plugin-daemonset

echo "=== Recent Events ==="
kubectl get events -n model-hosting --sort-by='.lastTimestamp' | tail -20
```

---

## Limitations

### Technical Limitations

1. **No Memory Isolation**: All pods share GPU memory. One pod can consume all memory.
2. **No Compute Isolation**: A compute-intensive pod can starve others.
3. **No QoS Guarantees**: Time-slicing provides best-effort scheduling only.
4. **Context Switch Overhead**: Each switch adds latency (~10-100 microseconds).
5. **No Priority Support**: All workloads receive equal time slices.

### Operational Limitations

1. **Monitoring Complexity**: GPU metrics are aggregated, not per-pod.
2. **Debugging Difficulty**: Hard to identify which pod causes GPU issues.
3. **Resource Accounting**: Kubernetes cannot track actual GPU usage per pod.

### When NOT to Use Time-Slicing

- Production inference with SLA requirements
- Training workloads requiring full GPU
- Memory-intensive models (>50% of GPU memory)
- Latency-sensitive real-time applications

---

## Best Practices

### Configuration Recommendations

1. **Replica Count**: Start with 2-3 replicas per GPU for inference workloads.
2. **Memory Budgeting**: Ensure total model memory < 80% of GPU memory.
3. **Keep-Alive**: Set low keep-alive times to release memory quickly.
4. **Max Loaded Models**: Set to 1 when using time-slicing.

### Deployment Recommendations

1. **Pod Anti-Affinity**: Spread pods across nodes when possible.
2. **Resource Requests**: Always set GPU requests equal to limits.
3. **Liveness Probes**: Increase timeouts to handle context switching delays.
4. **Graceful Shutdown**: Use preStop hooks for clean model unloading.

### Monitoring Recommendations

1. **Alert on OOM**: Monitor for CUDA out-of-memory events.
2. **Track Latency**: Monitor inference latency percentiles.
3. **Capacity Planning**: Track GPU utilization trends over time.

---

## Quick Reference Commands

```bash
# Create time-slicing config (3 replicas)
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: gpu-operator
data:
  any: |-
    version: v1
    sharing:
      timeSlicing:
        resources:
          - name: nvidia.com/gpu
            replicas: 3
EOF

# Label node for time-slicing
kubectl label node <node-name> nvidia.com/device-plugin.config=any

# Restart device plugin
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n gpu-operator

# Verify GPU capacity
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.capacity.'nvidia\.com/gpu'

# Check pod GPU allocation
kubectl get pods -n model-hosting -o custom-columns=NAME:.metadata.name,GPU:.spec.containers[0].resources.limits.'nvidia\.com/gpu'

# Monitor GPU in real-time
watch -n 2 "kubectl exec -n model-hosting deployment/ollama -- nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader"
```

---

## References

- [NVIDIA Device Plugin Documentation](https://github.com/NVIDIA/k8s-device-plugin)
- [NVIDIA GPU Operator Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)
- [Kubernetes Device Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
- [NVIDIA Time-Slicing GPUs in Kubernetes](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)
