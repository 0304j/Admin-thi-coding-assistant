# Connection Between Backend and LLM Hosting

This document explains how we package the **backend** into a Docker image, deploy it to **Kubernetes (k3s/K8s)**, and connect it to the **LLM hosting layer (Ollama service inside the cluster)**.

> Scope: Backend containerization + Deployment/Service manifests + rollout workflow + the backend ↔ LLM hosting integration points.

---

## 1) Dockerfile: what it is responsible for

A Dockerfile mainly solves three problems:

1. **Base runtime**: which OS/runtime the application runs on (e.g., Python base image).
2. **Dependencies**: what needs to be installed (e.g., `pip install -r requirements.txt`).
3. **Startup command**: how the container starts the backend (entrypoint / command) and which port the app listens on.

Typical directives you will see:

```dockerfile
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

Meaning:

- `WORKDIR /app` sets the working directory inside the container.
- `COPY requirements.txt .` + `RUN pip install ...` installs Python dependencies.
- `COPY . .` copies backend source code into the image (e.g., `app.py`, `service.py`, and other modules).

> Note: `EXPOSE 3000` (if present) is **only metadata** (a hint/documentation). It does not actually “open” a port by itself.

---

## 2) Build & push the backend image (local → Docker Hub)

From the directory that contains the Dockerfile:

```bash
docker build -t arnoldt04/backend:1.0.0 .
docker push arnoldt04/backend:1.0.0
```

Recommended best practice:

- Prefer **immutable tags** (e.g., `:1.0.0` or `:git-<sha>`) instead of `:latest`
- This makes rollbacks and troubleshooting much easier.

If you *do* use `:latest`, Kubernetes will **not** automatically redeploy when you push a new `latest` image (more details in the rollout section).

---

## 3) Kubernetes Deployment: keep the backend running

### 3.1 Pod vs Deployment (why we use Deployment)

- A **Pod** is the actual runtime unit (your container runs inside it).
- A **Deployment** is a controller that manages Pods and continuously reconciles the desired state.

Key points in our backend Deployment:

- **Multiple replicas** for availability:
  ```yaml
  replicas: 2
  ```
  This means: “Always keep 2 backend Pods running.”
  If one Pod disappears (deleted, node failure, etc.), the Deployment/ReplicaSet will create a replacement to return to 2 replicas.

- **Label selector** ties the Deployment to its Pods:
  ```yaml
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
  ```

- **Environment variables** inject runtime config (secrets + service endpoints), e.g.:
  - `GROQ_API_KEY` from a Kubernetes Secret
  - `OLLAMA_URL`, `DEFAULT_OLLAMA_MODEL`, `OLLAMA_TIMEOUT` for LLM hosting

### 3.2 Health checks (probes)

We use two probes:

- **readinessProbe** (`/health`):
  - A Pod becomes “Ready” only after it passes this check.
  - Service traffic is only routed to **Ready** Pods.
  - Prevents sending traffic to a backend that has not finished starting up.

- **livenessProbe** (`/health`):
  - If this fails repeatedly, Kubernetes restarts the container in the Pod.
  - This is a self-healing mechanism for “stuck” processes.

### 3.3 Resources (requests/limits)

```yaml
requests:
  memory: "128Mi"
  cpu: "100m"
limits:
  memory: "256Mi"
  cpu: "500m"
```

- **requests**: guaranteed minimum for scheduling.
- **limits**: maximum usage (memory over limit can lead to OOMKill).

---

## 4) Kubernetes Service: stable access + load balancing

Pods are ephemeral (IP changes across restarts, rescheduling, scaling). A **Service** provides:

- A stable DNS name / virtual IP (ClusterIP) for internal traffic
- Optional NodePort / LoadBalancer for external traffic
- Load balancing across matching Pods

A Service finds backend Pods via the same label:

```yaml
selector:
  app: backend
```

### Example request flow (NodePort → Service → Pods)

1. External client (VS Code extension) calls:  
   `http://<NodeIP>:30080`
2. NodePort forwards to Service `port: 80`
3. Service selects backend Pods (Endpoints) by label selector
4. Service forwards to one Pod’s `targetPort: 3000`
5. Flask backend receives request on port 3000 and returns response

---

## 5) Rolling updates: how updates actually happen

### 5.1 What triggers a rolling update?

A Deployment triggers a rolling update when the **Pod template changes**:

- `spec.template.spec.containers[].image`
- env vars under `spec.template.spec.containers[].env`
- probes/resources/ports under the Pod template, etc.

After you update the YAML, apply it:

```bash
kubectl apply -f backend-deployment.yaml -n backend
kubectl rollout status deployment/backend -n backend
```

### 5.2 Important: `imagePullPolicy: Always` is NOT auto-redeploy

`imagePullPolicy: Always` means:

- “When a container starts, always try to pull the image.”

It does **not** mean:

- “If Docker Hub updates the same tag, existing Pods will redeploy automatically.”

If you push a new image to the same tag (e.g., `:latest`) and your YAML does not change, Kubernetes will not automatically restart Pods.

To force a redeploy:

```bash
kubectl rollout restart deployment/backend -n backend
kubectl rollout status deployment/backend -n backend
```

---

## 6) End-to-end deployment steps (Docker Hub → Kubernetes)

### 6.1 Build & push

```bash
docker build -t arnoldt04/backend:1.0.0 .
docker push arnoldt04/backend:1.0.0
```

### 6.2 Update the Deployment image tag

In `backend-deployment.yaml`:

```yaml
image: arnoldt04/backend:1.0.0
imagePullPolicy: IfNotPresent
```

(Using versioned tags means `IfNotPresent` is usually enough.)

### 6.3 Apply to cluster

```bash
kubectl apply -f backend-deployment.yaml -n backend
kubectl apply -f backend-service.yaml -n backend
```

### 6.4 Verify

```bash
kubectl get pods -n backend -o wide
kubectl get svc  -n backend
kubectl rollout status deployment/backend -n backend
kubectl logs deployment/backend -n backend --tail=200
```

### 6.5 Test health endpoint

- If you have NodePort:
  ```bash
  curl http://<NodeIP>:30080/health
  ```
- Or via port-forward:
  ```bash
  kubectl port-forward -n backend deployment/backend 3000:3000
  curl http://localhost:3000/health
  ```

---

# Backend ↔ LLM Hosting (Ollama) Connection (service.py)

This section describes the **integration points** between the backend and the LLM hosting service.

## A) The contract: which configuration the backend needs

In the Deployment manifest, we inject:

- `OLLAMA_URL`  
  Example (in-cluster DNS name of the LLM hosting Service):
  ```text
  http://ollama-service.model-hosting.svc.cluster.local:11434
  ```
- `DEFAULT_OLLAMA_MODEL`  
  Example:
  ```text
  qwen2.5-coder:7b
  ```
- `OLLAMA_TIMEOUT` (seconds)  
  Example:
  ```text
  60
  ```

These values are the key bridge between **backend** and **llm-hosting**.

## B) Representative “key code” pattern in service.py

Your backend typically does these steps:

1. Read env vars (`OLLAMA_URL`, `DEFAULT_OLLAMA_MODEL`, `OLLAMA_TIMEOUT`)
2. Build an HTTP request to the Ollama service
3. Parse the response and return it to the caller (extension/front-end)
4. Handle timeouts and errors gracefully

A representative (typical) implementation looks like this:

```python
import os
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_OLLAMA_MODEL", "qwen2.5-coder:7b")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

def generate_with_ollama(prompt: str, model: str = DEFAULT_MODEL) -> str:
    # Option 1: /api/generate (prompt-based)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "")
```

> Your real `service.py` may use `/api/chat` (messages-based) or an OpenAI-compatible endpoint, but the structure is the same:
> **base URL from env → HTTP POST → parse response → return text**.
