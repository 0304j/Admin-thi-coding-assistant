# Administration Implementation for thiCodingAssistant
This repository contains the administration part implementation of the thiCodingAssistant project.
The thiCodingAssistant project (source): https://github.com/Balahari15/thiCodingAssistant

## Table of Contents


1. [K3s Cluster Setup](#k3s-cluster-setup)
2. [Building the Docker Image](#building-the-docker-image)
3. [Deploying to Kubernetes](#deploying-to-kubernetes)
4. [GPU Time-Slicing Configuration](#gpu-time-slicing-configuration)
5. [Accessing the Application](#accessing-the-application)
6. [Operations Guide](#operations-guide)

## Project Structure

```
Admin/
├── Dockerfile                    # Multi-stage build for Model Manager
├── README.md                     # This documentation
├── Model_manager/
│   ├── requirements.txt          # Python dependencies
│   ├── Backend/
│   │   ├── vue-api-server.py     # Flask API server
│   │   ├── k8s_client.py         # Kubernetes client utilities
│   │   └── BACKEND_DOCUMENTATION.md
│   └── Frontend/
│       ├── vue-model-manager.html # Vue.js frontend
│       └── FRONTEND_DOCUMENTATION.md
└── k8/k8s/
    ├── README.md                 # Kubernetes resources documentation
    ├── namespace.yaml            # Namespace definition
    ├── ollama-deployment.yaml    # Ollama deployment with GPU
    ├── ollama-service.yaml       # Ollama service
    ├── model-manager-deployment.yaml
    ├── model-manager-service.yaml
    ├── model-manager-nodeport.yaml
    ├── model-health-check-cronjob.yaml
    ├── model-health-script-configmap.yaml
    ├── model-usage-stats-configmap.yaml
    └── GPU_TIME_SLICING_GUIDE.md # Detailed GPU configuration
```

## Kubernetes Model Manager

A production-ready web application for managing Ollama language models on Kubernetes with GPU support. This solution provides a Vue.js frontend and Flask backend for pulling, testing, and monitoring LLM models, with built-in GPU time-slicing for efficient resource utilization.

## Overview

This project enables teams to:

- **Deploy and manage Ollama models** through an intuitive web interface
- **Monitor GPU VRAM usage** in real-time across the cluster
- **Track model usage statistics** to understand which models provide the most value
- **Share GPU resources** efficiently using NVIDIA time-slicing
- **Automate model health checks** with Kubernetes CronJobs

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                        │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │  Model Manager  │───▶│  Ollama Service │───▶│  GPU Node    │ │
│  │  (Flask + Vue)  │    │  (3 replicas)   │    │  (H100/A100) │ │
│  │    Port 8080    │    │   Port 11434    │    │  Time-Sliced │ │
│  └─────────────────┘    └─────────────────┘    └──────────────┘ │
│          │                      │                               │
│          ▼                      ▼                               │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   ConfigMaps    │    │      PVC        │                    │
│  │  (Usage Stats)  │    │ (Model Storage) │                    │
│  └─────────────────┘    └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---



---





---

## K3s Cluster Setup

### Why K3s?

K3s is chosen over standard Kubernetes (k8s) for this deployment for several compelling reasons:

**Resource Efficiency** — K3s uses approximately 512MB RAM compared to 2-4GB for standard k8s, leaving more resources available for GPU workloads and model inference.

**Single Binary Distribution** — The entire Kubernetes distribution is packaged in a single binary under 100MB, simplifying installation and maintenance.

**Rapid Deployment** — A production-ready cluster can be operational in under 60 seconds, significantly reducing setup time.

**Built-in Components** — K3s includes Traefik, CoreDNS, and local-path provisioner out of the box, eliminating the need for manual component installation.

**Edge and GPU Optimization** — Designed specifically for resource-constrained and specialized hardware environments, making it ideal for GPU-intensive workloads.

**Simplified Operations** — Features like automatic certificate rotation and embedded etcd reduce operational overhead.

For GPU-intensive model hosting where every megabyte of system RAM matters, K3s provides the full Kubernetes API with minimal overhead.

### Step 1: Install K3s

```bash
# Install K3s with GPU support flags
curl -sfL https://get.k3s.io | sh -s - \
    --write-kubeconfig-mode 644 \
    --disable traefik \
    --kubelet-arg="feature-gates=DevicePlugins=true"

# Verify installation
sudo k3s kubectl get nodes
```

### Step 2: Configure kubectl Access

```bash
# Copy kubeconfig for local access
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config

# Verify access
kubectl get nodes
```

### Step 3: Install NVIDIA Container Toolkit

```bash
# Add NVIDIA repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure containerd for NVIDIA
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart k3s
```

### Step 4: Deploy NVIDIA Device Plugin

```bash
# Deploy the NVIDIA device plugin for Kubernetes
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.1/nvidia-device-plugin.yml

# Verify GPU is detected
kubectl get nodes -o json | jq '.items[].status.capacity["nvidia.com/gpu"]'
```

Expected output: `"1"` (or the number of GPUs in your node)

---

## Building the Docker Image

### Why Docker Buildx?

Docker Buildx is used instead of the legacy `docker build` command for several critical advantages:

**Multi-platform Builds** — Build images for both `linux/amd64` and `linux/arm64` architectures from a single command, ensuring compatibility across different server types.

**BuildKit Backend** — Leverages the BuildKit engine for 2-3x faster builds through parallel layer processing and improved caching mechanisms.

**Advanced Caching** — Intelligent layer caching across builds significantly reduces CI/CD pipeline execution time.

**Build Secrets** — Secure handling of credentials and sensitive data during the build process without exposing them in the final image.

**Remote Builders** — Ability to offload builds to more powerful machines, useful for resource-intensive image creation.

For production deployments, Buildx ensures consistent images across different architectures and optimized build performance.

### Step 1: Set Up Buildx

```bash
# Create a new builder instance with BuildKit
docker buildx create --name modelmanager --driver docker-container --bootstrap

# Set as default builder
docker buildx use modelmanager

# Verify builder is active
docker buildx inspect --bootstrap
```

### Step 2: Build the Image

```bash
# Navigate to project root (where Dockerfile is located)
cd /path/to/Admin

# Build for multiple platforms and push to registry
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag your-registry/model-manager:latest \
    --tag your-registry/model-manager:v1.0.0 \
    --push \
    .
```

**Build Flags Explained**

- `--platform` — Target architectures (amd64 for x86 servers, arm64 for ARM servers)
- `--tag` — Image name and version tags for identification
- `--push` — Automatically push to registry after successful build
- `.` — Build context pointing to current directory

### Step 3: Build for Local Development

For local testing without pushing to a registry:

```bash
# Build and load into local Docker daemon
docker buildx build \
    --platform linux/amd64 \
    --tag model-manager:dev \
    --load \
    .

# Test locally
docker run -p 8080:8080 model-manager:dev
```

### Step 4: Verify the Image

```bash
# Check image was pushed successfully
docker manifest inspect your-registry/model-manager:latest

# View image layers and size
docker buildx imagetools inspect your-registry/model-manager:latest
```

---

## Deploying to Kubernetes

All Kubernetes manifests are located in the `k8/k8s/` directory. Refer to [k8/k8s/README.md](k8/k8s/README.md) for detailed documentation on each resource.

### Step 1: Create the Namespace

```bash
kubectl apply -f k8/k8s/namespace.yaml
```

This creates the `model-hosting` namespace where all resources will be deployed.

### Step 2: Create Required ConfigMaps

```bash
# Health check script for CronJob
kubectl apply -f k8/k8s/model-health-script-configmap.yaml

# Usage statistics storage
kubectl apply -f k8/k8s/model-usage-stats-configmap.yaml
```

### Step 3: Deploy Ollama

```bash
# Deploy Ollama with GPU support
kubectl apply -f k8/k8s/ollama-deployment.yaml
kubectl apply -f k8/k8s/ollama-service.yaml

# Wait for Ollama to be ready
kubectl rollout status deployment/ollama -n model-hosting --timeout=300s
```

### Step 4: Deploy Model Manager

```bash
# Deploy the Model Manager application
kubectl apply -f k8/k8s/model-manager-deployment.yaml
kubectl apply -f k8/k8s/model-manager-service.yaml
kubectl apply -f k8/k8s/model-manager-nodeport.yaml

# Wait for Model Manager to be ready
kubectl rollout status deployment/model-manager -n model-hosting --timeout=120s
```

### Step 5: Deploy Health Check CronJob (Optional)

```bash
kubectl apply -f k8/k8s/model-health-check-cronjob.yaml
```

### Quick Deploy All Resources

To deploy everything at once:

```bash
# Apply all manifests in the k8s directory
kubectl apply -f k8/k8s/

# Verify all resources are running
kubectl get all -n model-hosting
```

Expected output should show pods in `Running` status, services with assigned ClusterIPs, and deployments showing `READY` state.

---

## GPU Time-Slicing Configuration

GPU time-slicing allows multiple Ollama pods to share a single physical GPU, maximizing resource utilization for inference workloads.

### Why Time-Slicing?

Without time-slicing, a single GPU can only be allocated to one pod at a time. With time-slicing enabled, multiple pods can share the same GPU through temporal multiplexing, allowing:

- **Higher GPU utilization** — Sustained usage instead of idle periods between requests
- **Concurrent request handling** — Multiple Ollama replicas processing requests simultaneously
- **Cost efficiency** — Better return on investment for expensive GPU hardware

For detailed configuration instructions, refer to [k8/k8s/GPU_TIME_SLICING_GUIDE.md](k8/k8s/GPU_TIME_SLICING_GUIDE.md).

### Quick Setup

```bash
# Label the GPU node for time-slicing (replace <your-gpu-node> with actual node name)
kubectl label node <your-gpu-node> nvidia.com/device-plugin.config=any

# Restart NVIDIA device plugin
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n kube-system

# Verify time-slicing is active (should show "3" instead of "1")
kubectl get nodes -o json | jq '.items[].status.capacity["nvidia.com/gpu"]'

# Restart Ollama to use time-sliced GPUs
kubectl rollout restart deployment/ollama -n model-hosting
```

---

## Accessing the Application

### Via NodePort (Direct Access)

```bash
# Get node IP
kubectl get nodes -o wide

# Access the application
curl http://<node-ip>:30501/api/health
```

Open in browser: `http://<node-ip>:30501`

### Via Port Forward (Development)

```bash
kubectl port-forward svc/model-manager-service 8080:8080 -n model-hosting
```

Open in browser: `http://localhost:8080`

---

## Operations Guide

### Pulling a New Model

1. Open the Model Manager UI in your browser
2. Select a model from the dropdown or enter a custom model name (e.g., `llama3.1:8b`)
3. Click **Pull** to initiate the download
4. Monitor progress in the progress bar
5. Once complete, the model appears in the "Currently Loaded Models" table

### Testing a Model

1. Find the model in the "Currently Loaded Models" table
2. Click the **Test** button
3. View the response in the test results panel
4. Usage is automatically tracked for ranking

### Monitoring GPU Usage

The GPU summary bar at the top of the interface displays current VRAM allocation, available VRAM, and utilization percentage in real-time.

### Viewing Logs

```bash
# Model Manager logs
kubectl logs -f deployment/model-manager -n model-hosting

# Ollama logs
kubectl logs -f deployment/ollama -n model-hosting
```

### Updating the Deployment

```bash
# Update to a new image version
kubectl set image deployment/model-manager \
    model-manager=your-registry/model-manager:v2.0.0 \
    -n model-hosting

# Or restart to pull latest
kubectl rollout restart deployment/model-manager -n model-hosting
```

### Troubleshooting

**Check pod status**
```bash
kubectl get pods -n model-hosting
```

**View pod events and details**
```bash
kubectl describe pod <pod-name> -n model-hosting
```

**Check GPU allocation on nodes**
```bash
kubectl describe nodes | grep -A5 "Allocated resources"
```

**Verify Ollama connectivity from Model Manager**
```bash
kubectl exec -it deployment/model-manager -n model-hosting -- curl http://ollama-service:11434/api/tags
```

---



## Support

For issues or questions, verify the following:

1. **K3s is running:** `sudo systemctl status k3s`
2. **GPU is detected:** `nvidia-smi`
3. **Pods are healthy:** `kubectl get pods -n model-hosting`
4. **Check application logs:** `kubectl logs -f deployment/model-manager -n model-hosting`
=======
# Admin-thi-coding-assistant
>>>>>>> 4a92efa1cce7323df125778841933783b41b1b22
