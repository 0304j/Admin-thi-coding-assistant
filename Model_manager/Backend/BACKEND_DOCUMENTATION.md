# Backend Technical Documentation

## Overview

The Kubernetes Model Manager backend consists of two Python modules that work together to provide a REST API for managing machine learning models on a Kubernetes cluster with GPU resources. The system is designed specifically for managing Ollama-based model deployments with real-time GPU VRAM monitoring and usage tracking.

---

## Architecture

```
+-------------------+       +----------------------+       +------------------+
|   Vue.js Frontend |  -->  |   vue-api-server.py  |  -->  |   k8s_client.py  |
|   (HTTP Requests) |       |   (Flask REST API)   |       |   (K8s API)      |
+-------------------+       +----------------------+       +------------------+
                                      |
                                      v
                            +------------------+
                            |  Ollama Service  |
                            |  (Model Runtime) |
                            +------------------+
```

---

## Module 1: vue-api-server.py

### Role

The `vue-api-server.py` module serves as the primary REST API server for the Model Manager application. It handles all HTTP requests from the Vue.js frontend, communicates with the Ollama model runtime service, manages model usage statistics, and delegates Kubernetes operations to the `k8s_client.py` module.

### Dependencies

- Flask: Web framework for REST API endpoints
- Flask-CORS: Cross-Origin Resource Sharing support for frontend communication
- requests: HTTP client for communicating with Ollama service
- kubernetes: Python client for Kubernetes API interactions
- threading: Concurrent execution for background model pulls
- json: Data serialization for ConfigMap storage

### Global State Management

#### Usage Tracking System

```python
usage_lock = Lock()
USAGE_CONFIGMAP_NAME = "model-usage-stats"
USAGE_NAMESPACE = os.environ.get("POD_NAMESPACE", "model-hosting")
model_usage_stats = load_usage_from_configmap()
```

**Purpose**: Maintains persistent model usage statistics across pod restarts by storing data in a Kubernetes ConfigMap. The lock ensures thread-safe access when multiple requests update usage counts simultaneously.

**Implementation Rationale**: Pod restarts would lose in-memory statistics. By persisting to a ConfigMap, usage data survives container restarts and deployments, providing accurate long-term usage metrics.

#### Pull Progress Tracking System

```python
pull_progress_lock = Lock()
pull_progress = {}  # {model_name: {status, progress, total, completed, error}}
```

**Purpose**: Tracks the real-time progress of model download operations. Since model pulls can take several minutes, this allows the frontend to display accurate progress information.

**Implementation Rationale**: Ollama model pulls are long-running operations. Without progress tracking, users would have no feedback during downloads. The dictionary structure allows tracking multiple concurrent pulls.

#### HTTP Session Configuration

```python
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
```

**Purpose**: Configures connection pooling and automatic retry logic for HTTP requests to the Ollama service.

**Implementation Rationale**: Network communication with Ollama can experience transient failures. Connection pooling reduces overhead, and automatic retries handle temporary service unavailability without requiring manual intervention.

---

### Functions

#### load_usage_from_configmap()

```python
def load_usage_from_configmap():
```

**Purpose**: Retrieves persisted model usage statistics from a Kubernetes ConfigMap on application startup.

**Behavior**:
1. Attempts to load Kubernetes configuration (in-cluster first, then local kubeconfig)
2. Reads the ConfigMap named `model-usage-stats` from the configured namespace
3. Parses JSON data and converts to a defaultdict structure
4. Creates the ConfigMap if it does not exist

**Return Value**: A defaultdict containing model names as keys and usage counts as values.

**Use Case**: Called once at application startup to restore usage statistics from the previous session. Ensures data continuity across pod restarts.

---

#### save_usage_to_configmap()

```python
def save_usage_to_configmap():
```

**Purpose**: Persists the current in-memory usage statistics to a Kubernetes ConfigMap.

**Behavior**:
1. Converts the usage dictionary to a simple JSON-serializable format
2. Updates the existing ConfigMap or creates a new one if missing
3. Logs success or failure of the operation

**Use Case**: Called after each model usage event to ensure data persistence. Prevents data loss if the pod terminates unexpectedly.

---

#### track_model_usage(model_name: str)

```python
def track_model_usage(model_name: str):
```

**Purpose**: Increments the usage counter for a specific model and persists the update.

**Parameters**:
- `model_name`: The identifier of the model being used

**Behavior**:
1. Acquires the usage lock to ensure thread safety
2. Increments the count for the specified model
3. Calls `save_usage_to_configmap()` to persist immediately

**Use Case**: Called whenever a model is tested or used through the API. Enables the usage ranking feature to display accurate statistics.

---

#### estimate_model_vram(model_id)

```python
def estimate_model_vram(model_id):
```

**Purpose**: Estimates the GPU VRAM requirements for a model based on its identifier.

**Parameters**:
- `model_id`: The model identifier string (e.g., "llama2:7b", "codellama:13b")

**Behavior**:
1. Parses the model identifier for parameter count indicators (70b, 13b, 7b, etc.)
2. Checks for quantization indicators (GPTQ, AWQ, int4, int8)
3. Returns estimated VRAM in gigabytes

**Estimation Logic**:
| Model Size | Estimated VRAM |
|------------|----------------|
| 70B-72B    | 14.0 GB        |
| 32B-34B    | 10.0 GB        |
| 13B-14B    | 8.0 GB         |
| 7B-8B      | 6.0 GB         |
| 3B         | 3.5 GB         |
| 1.5B       | 2.0 GB         |
| 1B         | 1.5 GB         |
| Quantized  | 40-75% of base |

**Use Case**: Used during deployment validation to ensure sufficient GPU memory is available before starting a model.

---

#### get_vram_recommendations(gpu_info)

```python
def get_vram_recommendations(gpu_info):
```

**Purpose**: Generates human-readable recommendations based on available GPU VRAM.

**Parameters**:
- `gpu_info`: Dictionary containing GPU status information from k8s_client

**Return Value**: List of recommendation strings.

**Recommendation Logic**:
- 12+ GB available: Can deploy large models (7B-70B)
- 8-12 GB available: Can deploy medium models (7B-13B)
- 4-8 GB available: Can deploy small models (1B-7B)
- 2-4 GB available: Quantized models only
- Less than 2 GB: Insufficient for new deployments

**Use Case**: Displayed in the frontend to guide users on what models they can deploy given current GPU utilization.

---

### REST API Endpoints

#### GET /

```python
@app.route('/')
def index():
```

**Purpose**: Serves the Vue.js frontend HTML file.

**Response**: The contents of `vue-model-manager.html`.

**Use Case**: Entry point for the web application. Users access this URL to load the frontend interface.

---

#### GET /api/health

```python
@app.route('/api/health')
def health():
```

**Purpose**: Health check endpoint for Kubernetes liveness and readiness probes.

**Response**:
- Success (200): `{"status": "healthy", "kubernetes": "connected"}`
- Failure (503): `{"status": "unhealthy", "kubernetes": "disconnected"}`

**Use Case**: Kubernetes uses this endpoint to determine if the pod should receive traffic and whether it needs to be restarted.

---

#### GET /api/deployments

```python
@app.route('/api/deployments')
def get_deployments():
```

**Purpose**: Lists all model deployments across namespaces in the Kubernetes cluster.

**Response**: JSON object containing:
- `success`: Boolean indicating operation success
- `models`: Array of deployment objects
- `count`: Total number of deployments

**Deployment Object Structure**:
```json
{
  "name": "deployment-name",
  "namespace": "model-hosting",
  "model_id": "llama2:7b",
  "image": "text-generation-inference",
  "status": "Running|Starting|Failed",
  "replicas": "1/1",
  "gpu": "1",
  "memory": "8Gi",
  "created": "2024-01-01T00:00:00Z"
}
```

**Filtering Logic**: Excludes system deployments (model-manager, model-dashboard) and system namespaces (kube-system, kube-public).

**Use Case**: Populates the deployed models table in the frontend, allowing users to see and manage existing deployments.

---

#### POST /api/deploy

```python
@app.route('/api/deploy', methods=['POST'])
def deploy_model():
```

**Purpose**: Deploys a new model to the Kubernetes cluster with VRAM management.

**Request Body**:
```json
{
  "model_id": "llama2:7b",
  "deployment_name": "llama2-deploy",
  "memory": "8"
}
```

**Validation Steps**:
1. Estimates model VRAM requirements
2. Validates requested memory meets model requirements
3. Checks current GPU VRAM availability
4. Verifies sufficient VRAM for the deployment

**Response**:
- Success (200): Deployment confirmation with VRAM allocation details
- Insufficient VRAM (400): Error with available VRAM and suggestions
- Server Error (500): Deployment failure details

**Use Case**: Primary endpoint for deploying new models. Implements resource protection by validating VRAM availability before deployment.

---

#### POST /api/delete

```python
@app.route('/api/delete', methods=['POST'])
def delete_deployment():
```

**Purpose**: Removes a model deployment from the cluster.

**Request Body**:
```json
{
  "deployment_name": "deployment-to-delete"
}
```

**Use Case**: Allows users to remove models they no longer need, freeing GPU resources for other deployments.

---

#### GET /api/gpu/status

```python
@app.route('/api/gpu/status', methods=['GET'])
def gpu_status():
```

**Purpose**: Retrieves current GPU VRAM utilization status.

**Response**:
```json
{
  "success": true,
  "gpu_info": {
    "total_vram_gb": 23.0,
    "allocated_vram_gb": 8.0,
    "available_vram_gb": 15.0,
    "utilization_percent": 34.8,
    "gpu_count": 1
  },
  "recommendations": ["Can deploy medium models (7B-13B)"]
}
```

**Use Case**: Displayed in the frontend header bar to show real-time GPU utilization. Helps users understand resource availability before deploying models.

---

#### GET /api/ollama/models

```python
@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
```

**Purpose**: Retrieves the list of models currently loaded in the Ollama service.

**Service Discovery**: Attempts connection to Ollama using multiple URLs in order of preference:
1. `http://ollama-service:11434/api/tags` (Kubernetes service)
2. `http://ollama-service.model-hosting:11434/api/tags` (Namespaced service)
3. `http://ollama-service.model-hosting.svc.cluster.local:11434/api/tags` (FQDN)
4. `http://localhost:11434/api/tags` (Local development)

**Use Case**: Populates the "Currently Loaded Models" table in the frontend. Shows which models are ready for inference.

---

#### POST /api/ollama/pull

```python
@app.route('/api/ollama/pull', methods=['POST'])
def pull_ollama_model():
```

**Purpose**: Initiates a model download from the Ollama registry.

**Request Body**:
```json
{
  "model": "llama2:7b"
}
```

**Behavior**:
1. Initializes progress tracking for the model
2. Spawns a background thread to handle the download
3. Returns immediately with HTTP 202 (Accepted)
4. Background thread updates progress dictionary as download progresses

**Background Thread Logic**:
- Opens a streaming connection to Ollama's pull API
- Parses JSON progress updates from the stream
- Updates the `pull_progress` dictionary with current status
- Sets final status on completion or error

**Use Case**: Allows users to download new models without blocking the UI. The frontend polls the progress endpoint to display download status.

---

#### GET /api/ollama/pull/progress/<model_name>

```python
@app.route('/api/ollama/pull/progress/<model_name>', methods=['GET'])
def get_pull_progress(model_name):
```

**Purpose**: Returns the current download progress for a specific model.

**Response**:
```json
{
  "status": "downloading",
  "progress": 45,
  "total": 4000000000,
  "completed": 1800000000,
  "error": null,
  "message": "downloading: 45%"
}
```

**Use Case**: Frontend polls this endpoint every second during model downloads to update the progress bar.

---

#### POST /api/ollama/delete

```python
@app.route('/api/ollama/delete', methods=['POST'])
def delete_ollama_model():
```

**Purpose**: Removes a model from Ollama's local storage.

**Request Body**:
```json
{
  "model": "llama2:7b"
}
```

**Use Case**: Allows users to delete models they no longer need, freeing disk space on the Ollama pod.

---

#### POST /api/ollama/generate

```python
@app.route('/api/ollama/generate', methods=['POST'])
def test_ollama_model():
```

**Purpose**: Tests a model by generating a response and tracks usage for ranking.

**Request Body**:
```json
{
  "model": "llama2:7b",
  "prompt": "Hello! Please introduce yourself."
}
```

**Behavior**:
1. Forwards the request to Ollama's generate API
2. On success, calls `track_model_usage()` to increment the model's usage count
3. Returns the generated response

**Use Case**: Allows users to verify models are working correctly. The usage tracking enables the ranking feature to show which models are most popular.

---

#### GET /api/ollama/gguf-models

```python
@app.route('/api/ollama/gguf-models', methods=['GET'])
def get_gguf_coding_models():
```

**Purpose**: Returns a list of popular coding models available in the Ollama registry.

**Behavior**:
1. Attempts to query the Ollama registry for available models
2. Falls back to a curated list of popular models if the registry is unavailable

**Fallback Model List**:
- mistral:7b
- codellama:7b-instruct
- deepseek-coder:6.7b
- llama2:7b
- llama3.1:8b
- phi:2.7b
- tinyllama:1.1b
- And others

**Use Case**: Populates the model selection dropdown in the frontend, giving users a curated list of models to choose from.

---

#### GET /api/usage/ranking

```python
@app.route('/api/usage/ranking', methods=['GET'])
def get_usage_ranking():
```

**Purpose**: Returns model usage statistics sorted by popularity.

**Response**:
```json
{
  "success": true,
  "total_requests": 150,
  "models": [
    {"rank": 1, "model": "llama2:7b", "count": 75, "usage_percent": 50.0},
    {"rank": 2, "model": "codellama:7b", "count": 45, "usage_percent": 30.0},
    {"rank": 3, "model": "mistral:7b", "count": 30, "usage_percent": 20.0}
  ]
}
```

**Use Case**: Displays the usage ranking panel in the frontend, showing which models are most frequently used.

---

#### POST /api/usage/track

```python
@app.route('/api/usage/track', methods=['POST'])
def track_usage_endpoint():
```

**Purpose**: Allows external systems to manually track model usage.

**Request Body**:
```json
{
  "model": "llama2:7b"
}
```

**Use Case**: Enables integration with external systems that use models outside of the Model Manager interface. Keeps usage statistics accurate regardless of how models are accessed.

---

#### POST /api/usage/reset

```python
@app.route('/api/usage/reset', methods=['POST'])
def reset_usage_stats():
```

**Purpose**: Clears all usage statistics.

**Behavior**:
1. Resets the in-memory usage dictionary
2. Clears the ConfigMap storage

**Use Case**: Allows administrators to reset statistics, for example when starting a new tracking period or after testing.

---

## Module 2: k8s_client.py

### Role

The `k8s_client.py` module provides a clean abstraction layer for Kubernetes API operations. It handles cluster authentication, GPU resource detection, VRAM monitoring, and deployment management. This separation of concerns keeps the API server code focused on HTTP handling while delegating infrastructure operations to a specialized module.

### Dependencies

- kubernetes: Official Kubernetes Python client
- logging: Structured logging for debugging and monitoring

---

### Class: KubernetesClient

```python
class KubernetesClient:
    def __init__(self, namespace: str = "model-hosting"):
```

**Purpose**: Encapsulates all Kubernetes cluster interactions within a single class.

**Constructor Behavior**:
1. Attempts to load in-cluster configuration (for running inside Kubernetes)
2. Falls back to local kubeconfig (for development)
3. Initializes CoreV1Api for node and pod operations
4. Initializes AppsV1Api for deployment operations
5. Sets `connected` flag based on initialization success

**Design Rationale**: The dual configuration approach allows the same code to work both in production (inside the cluster) and during local development (using kubeconfig).

---

### Methods

#### check_gpu_vram_availability() -> Dict

```python
def check_gpu_vram_availability(self) -> Dict:
```

**Purpose**: Provides a complete picture of GPU VRAM status in the cluster.

**Return Value**:
```python
{
    'success': True,
    'total_vram_gb': 23.0,
    'allocated_vram_gb': 8.0,
    'available_vram_gb': 15.0,
    'gpu_count': 1,
    'utilization_percent': 34.8
}
```

**Calculation Logic**:
1. Calls `_get_gpu_total_vram()` to determine total available VRAM
2. Calls `_get_allocated_vram()` to determine current usage
3. Calculates available VRAM as total minus allocated
4. Computes utilization percentage

**Use Case**: Called by the API server for GPU status endpoints and deployment validation. Provides the data needed for resource management decisions.

---

#### _get_gpu_total_vram() -> float

```python
def _get_gpu_total_vram(self) -> float:
```

**Purpose**: Detects the total GPU VRAM available on cluster nodes.

**Detection Logic**:
1. Lists all nodes in the cluster
2. Finds nodes with `nvidia.com/gpu` in their capacity
3. Reads the `nvidia.com/gpu.product` label to identify GPU model
4. Maps the GPU model to known VRAM capacities

**GPU VRAM Mapping** (ordered by specificity):

| GPU Model Pattern | VRAM (GB) | Notes                              |
|-------------------|-----------|-------------------------------------|
| H100L-23C         | 23        | Time-sliced H100, 23GB partition    |
| H100L-15C         | 15.36     | Time-sliced H100, 15GB partition    |
| H100              | 80        | Full NVIDIA H100                    |
| A100              | 40        | NVIDIA A100                         |
| A10               | 24        | NVIDIA A10                          |
| V100              | 16        | NVIDIA V100                         |
| T4                | 16        | NVIDIA T4                           |
| RTX-A6000         | 48        | NVIDIA RTX A6000                    |

**Pattern Matching Order**: The patterns are checked in order from most specific to least specific. This prevents "H100" from matching before "H100L-23C" when the GPU label is "NVIDIA-H100L-23C-SHARED".

**Default Behavior**: Returns 23.0 GB if no known GPU pattern matches or if detection fails. This default is chosen because it represents a common time-sliced H100 configuration.

**Use Case**: Fundamental to all resource management decisions. Without accurate total VRAM detection, the system cannot prevent over-allocation.

---

#### _get_allocated_vram() -> float

```python
def _get_allocated_vram(self) -> float:
```

**Purpose**: Determines how much GPU VRAM is currently in use.

**Detection Logic**:
1. Lists all deployments in the configured namespace
2. Looks for a deployment named 'ollama'
3. If Ollama is running (ready_replicas > 0), returns total VRAM as allocated
4. Returns 0.0 if no Ollama deployment is running

**Design Note**: The current implementation assumes Ollama uses the full GPU when running. This is a simplification that works for single-GPU deployments where Ollama is the primary consumer.

**Use Case**: Used in conjunction with total VRAM to calculate available resources for new deployments.

---

## Request Processing Flow

### Model Pull Request

1. Frontend sends POST to `/api/ollama/pull` with model name
2. API server initializes progress tracking entry
3. Background thread starts and connects to Ollama service
4. API server returns 202 Accepted immediately
5. Frontend begins polling `/api/ollama/pull/progress/<model_name>`
6. Background thread parses streaming JSON from Ollama
7. Progress dictionary updates trigger UI progress bar changes
8. On completion, progress status changes to "success"
9. Frontend detects success and refreshes model list

### Model Test Request

1. Frontend sends POST to `/api/ollama/generate` with model and prompt
2. API server forwards request to Ollama generate endpoint
3. Ollama processes the prompt and returns response
4. API server calls `track_model_usage()` to increment counter
5. Usage statistics persist to ConfigMap
6. Response returns to frontend for display
7. Usage ranking panel updates on next poll

### GPU Status Request

1. Frontend sends GET to `/api/gpu/status`
2. API server calls `k8s_client.check_gpu_vram_availability()`
3. k8s_client queries Kubernetes node labels for GPU model
4. k8s_client maps GPU model to known VRAM capacity
5. k8s_client checks Ollama deployment status for allocation
6. API server adds recommendations based on available VRAM
7. Response returns to frontend for status bar update

---

## Error Handling

### Connection Failures

All Ollama communication uses a fallback URL list. If one URL fails, the next is attempted. This handles:
- DNS resolution delays during pod startup
- Service endpoint changes during deployments
- Network configuration differences between environments

### Kubernetes API Errors

The k8s_client wraps all API calls in try-except blocks. Failures return dictionaries with `success: False` and error details rather than raising exceptions. This allows the API server to return meaningful error responses to the frontend.

### ConfigMap Persistence Failures

Usage tracking failures are logged but do not interrupt normal operation. Statistics may be lost on pod restart if ConfigMap operations fail, but the application continues functioning.

---

## Configuration

### Environment Variables

| Variable       | Default         | Description                              |
|----------------|-----------------|------------------------------------------|
| POD_NAMESPACE  | model-hosting   | Kubernetes namespace for operations      |

### Kubernetes Resources

| Resource Type | Name              | Purpose                          |
|---------------|-------------------|----------------------------------|
| ConfigMap     | model-usage-stats | Persistent storage for usage data |
| Service       | ollama-service    | Ollama runtime service endpoint   |

---

## Logging

Both modules use Python's standard logging module with INFO level by default. Log messages follow the pattern:

```
[COMPONENT] Message details
```

Components include:
- `[REQUEST]`: Incoming HTTP requests
- `[OLLAMA]`: Ollama service communication
- `[USAGE]`: Usage tracking operations
- `[BACKGROUND]`: Background thread operations
- `[PULL]`: Model pull progress updates

---

## Thread Safety

The application uses two locks for thread-safe access to shared state:

1. `usage_lock`: Protects `model_usage_stats` dictionary
2. `pull_progress_lock`: Protects `pull_progress` dictionary

All reads and writes to these dictionaries acquire the appropriate lock first. This prevents race conditions when multiple requests update the same data structures.

---

## Memory Management

The application implements automatic garbage collection after each request:

```python
@app.after_request
def cleanup_after_request(response):
    gc.collect()
    return response
```

This helps prevent memory growth in long-running processes, particularly important when handling large model data structures.

---

## Production Considerations

### Debug Mode

The application explicitly disables Flask debug mode and auto-reloader:

```python
app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
```

This prevents CrashLoopBackOff issues in Kubernetes caused by the Werkzeug development server's file watching behavior.

### Request Timeouts

Kubernetes API calls include explicit timeouts to prevent hanging requests:

```python
all_deployments = k8s_client.apps_v1.list_deployment_for_all_namespaces(_request_timeout=5)
```

Ollama communication uses longer timeouts (up to 600 seconds for pulls) to accommodate large model downloads.
