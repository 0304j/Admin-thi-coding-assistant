# GPU Time-Slicing Configuration

## Overview

GPU Time-Slicing allows multiple pods to share a single physical GPU by creating virtual GPU instances. This is essential for running multiple Ollama instances on limited GPU hardware.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Physical GPU (H100 - 80GB VRAM)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ Virtual GPU │ │ Virtual GPU │ │ Virtual GPU │ │Virtual GPU│ │
│  │   Slice 0   │ │   Slice 1   │ │   Slice 2   │ │  Slice 3  │ │
│  │             │ │             │ │             │ │           │ │
│  │ Ollama Pod  │ │ Ollama Pod  │ │ Ollama Pod  │ │  (spare)  │ │
│  │     #1      │ │     #2      │ │     #3      │ │           │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                                                                 │
│  Note: VRAM is SHARED, not partitioned                         │
│  All pods can access full 80GB, but compete for memory         │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### ConfigMap (time-slicing-config)

```yaml
version: v1
sharing:
  timeSlicing:
    resources:
      - name: nvidia.com/gpu
        replicas: 4    # Creates 4 virtual GPUs per physical GPU
```

### Replica Recommendations

| Workload Type | Replicas | Use Case |
|---------------|----------|----------|
| Heavy (7B+ LLMs) | 2-4 | Multiple Ollama instances with large models |
| Medium (1-7B models) | 4-8 | Batch processing, multiple smaller models |
| Light (< 1B models) | 8-16 | Development, testing, small inference tasks |

## How It Works

1. **Time Multiplexing**: GPU compute time is divided between pods
2. **Shared VRAM**: All pods share the total GPU memory
3. **No Isolation**: One pod can use more than its "fair share" of resources
4. **Context Switching**: Overhead from switching between workloads

### Important Considerations

| Aspect | Behavior |
|--------|----------|
| **VRAM** | Shared, not partitioned. Total = Physical VRAM |
| **Compute** | Time-shared between pods |
| **Isolation** | None - pods can affect each other's performance |
| **Scheduling** | Kubernetes sees N virtual GPUs |

## Setup Steps

### 1. Apply ConfigMap

```bash
kubectl apply -f k8s/gpu-time-slicing.yaml
```

### 2. Label GPU Node

```bash
# Find your GPU node
kubectl get nodes -o wide

# Label it for time-slicing
kubectl label node <node-name> nvidia.com/device-plugin.config=time-slicing
```

### 3. Patch ClusterPolicy (if using GPU Operator)

```bash
kubectl patch clusterpolicy cluster-policy \
  --type=merge \
  -p '{"spec":{"devicePlugin":{"config":{"name":"time-slicing-config","default":"time-slicing-config"}}}}'
```

### 4. Restart Device Plugin

```bash
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n nvidia-gpu-operator
```

### 5. Verify

```bash
# Check node capacity (should show replicas count)
kubectl get node <node-name> -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
# Expected output: 4

# Test GPU access
kubectl run gpu-test --image=nvidia/cuda:12.0-base --rm -it --restart=Never \
  --requests='nvidia.com/gpu=1' -- nvidia-smi
```

## Troubleshooting

### Virtual GPUs Not Showing

```bash
# Check device plugin logs
kubectl logs -n nvidia-gpu-operator -l app=nvidia-device-plugin-daemonset

# Check ConfigMap
kubectl get configmap time-slicing-config -n nvidia-gpu-operator -o yaml

# Check node labels
kubectl get node <node-name> --show-labels | grep nvidia
```

### Pods Stuck in Pending

```bash
# Check GPU allocation
kubectl describe node <node-name> | grep -A 10 "Allocated resources"

# Check events
kubectl get events --field-selector reason=FailedScheduling
```

### Performance Issues

- **Symptom**: Slow inference, high latency
- **Cause**: Too many pods competing for GPU time
- **Solution**: Reduce replicas or scale down workloads

## Best Practices

1. **Monitor VRAM Usage**: Use `nvidia-smi` or Model Manager UI
2. **Set Resource Limits**: Prevent OOM by limiting model sizes
3. **Use OLLAMA_MAX_LOADED_MODELS**: Limit concurrent models per pod
4. **Stagger Requests**: Avoid simultaneous heavy inference
5. **Consider MIG**: For better isolation on A100/H100 GPUs

## Related Files

- `k8s/gpu-time-slicing.yaml` - ConfigMap definition
- `k8s/ollama-deployment.yaml` - Ollama using time-sliced GPUs
- `k8s/apply-time-slicing.sh` - Setup automation script