# Frontend Technical Documentation

## Overview

The `vue-model-manager.html` file is a single-page application that provides the user interface for the Kubernetes Model Manager. Built with Vue.js 3 and styled with custom CSS, it enables users to manage Ollama models, monitor GPU resources, and track model usage statistics through an intuitive web interface.

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Vue.js | 3.x | Reactive UI framework |
| Axios | Latest | HTTP client for API communication |
| Font Awesome | 6.0 | Icon library |
| CSS3 | N/A | Custom styling with gradients and animations |

### CDN Dependencies

```html
<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
<script src="https://unpkg.com/axios/dist/axios.min.js"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
```

---

## Application Architecture

### Component Structure

The application uses Vue.js 3 with the Options API in a single-file format. All components are defined within one HTML file for simplicity of deployment.

```
vue-model-manager.html
|
+-- <style> (CSS definitions)
|
+-- <div id="app"> (Template)
|   +-- Toast Notifications Container
|   +-- Confirmation Modal
|   +-- Main Container
|       +-- Header (Title + Connection Status)
|       +-- GPU Summary Bar
|       +-- Ollama Model Management Panel
|       +-- Model Usage Ranking Panel
|       +-- Hidden Panels (Legacy deployment features)
|
+-- <script> (Vue.js application logic)
```

---

## User Interface Panels

### 1. Header Section

**Purpose**: Displays the application title and real-time Kubernetes connection status.

**Visual Elements**:
- Application title: "Kubernetes Model Manager"
- Connection status badge (green for connected, red for disconnected)

**Reactive Binding**:
```html
<div class="status-badge" :class="connectionStatus ? 'status-connected' : 'status-disconnected'">
    {{ connectionStatus ? 'Connected' : 'Disconnected' }}
</div>
```

**Use Case**: Provides immediate visual feedback about backend connectivity. Users can quickly identify if the system is operational.

---

### 2. GPU Summary Bar

**Purpose**: Displays real-time GPU VRAM utilization in a compact format.

**Visual Elements**:
- GPU icon
- Allocated VRAM / Total VRAM display
- Available VRAM indicator
- Utilization progress bar

**Template Structure**:
```html
<div class="gpu-summary-bar" v-if="gpuStatus.data">
    <div class="gpu-summary-item">
        <span>GPU: </span>
        <strong>{{ gpuStatus.data.gpu_info.allocated_vram_gb.toFixed(1) }}GB</strong>
        <span class="gpu-divider">/</span>
        <span>{{ gpuStatus.data.gpu_info.total_vram_gb.toFixed(1) }}GB</span>
        <span class="gpu-available">({{ gpuStatus.data.gpu_info.available_vram_gb.toFixed(1) }}GB free)</span>
    </div>
    <div class="gpu-mini-bar">
        <div class="gpu-mini-bar-fill" :style="{ width: gpuStatus.data.gpu_info.utilization_percent + '%' }"></div>
    </div>
</div>
```

**Use Case**: Allows users to monitor GPU resource consumption at a glance without navigating to a separate page.

---

### 3. Ollama Model Management Panel

**Purpose**: Primary interface for managing models in the Ollama runtime.

**Sub-components**:

#### Model Selection Dropdown

Displays a curated list of popular Ollama models fetched from the backend.

```html
<select v-model="selectedGGUFModel" @change="onGGUFModelSelected">
    <option value="">Select an Ollama coding model</option>
    <option v-for="model in ggufModels" :key="model.id" :value="model.id">
        {{ model.name }} ({{ model.size }}) - {{ model.likes }}
    </option>
</select>
```

#### Manual Model Input

Allows users to enter custom model names not in the dropdown.

```html
<input v-model="newOllamaModel" type="text" placeholder="Model name (e.g., mistral:7b)">
```

#### Pull Button

Initiates model download with progress tracking.

```html
<button @click="pullOllamaModel" :disabled="pullingOllamaModel || !newOllamaModel.trim()">
    {{ pullingOllamaModel ? 'Pulling...' : 'Pull' }}
</button>
```

#### Progress Bar

Displays real-time download progress during model pulls.

```html
<div v-if="pullingOllamaModel" class="progress-container">
    <div class="progress-bar" :style="{ width: modelPullProgress + '%' }">
        {{ modelPullProgress }}%
    </div>
    <div class="progress-text">{{ modelPullStatus }}</div>
</div>
```

#### Currently Loaded Models Table

Lists all models available in the Ollama runtime.

| Column | Description |
|--------|-------------|
| Model Name | Name with running status badge |
| Size | File size in human-readable format |
| VRAM | Estimated VRAM requirement |
| Pulled | Date when model was downloaded |
| Actions | Test and Delete buttons |

**Use Case**: Central hub for all model operations. Users can browse available models, download new ones, test functionality, and remove unused models.

---

### 4. Model Usage Ranking Panel

**Purpose**: Displays usage statistics showing which models are most frequently used.

**Sub-components**:

#### Statistics Summary

Shows aggregate usage data.

```html
<div class="ranking-stats" v-if="usageRanking.total_requests > 0">
    <div class="ranking-stat">
        <div class="ranking-stat-value">{{ usageRanking.total_requests }}</div>
        <div class="ranking-stat-label">Total Requests</div>
    </div>
    <div class="ranking-stat">
        <div class="ranking-stat-value">{{ usageRanking.models.length }}</div>
        <div class="ranking-stat-label">Models Used</div>
    </div>
    <div class="ranking-stat" v-if="topModel">
        <div class="ranking-stat-value">{{ topModel.model }}</div>
        <div class="ranking-stat-label">Most Popular</div>
    </div>
</div>
```

#### Ranking Table

Displays per-model usage breakdown with visual percentage bars.

| Column | Description |
|--------|-------------|
| Rank | Position badge (gold for 1st, silver for 2nd, bronze for 3rd) |
| Model | Model identifier |
| Usage % | Visual bar showing relative usage percentage |

**Use Case**: Helps administrators understand which models provide the most value and should be prioritized for resources.

---

### 5. Toast Notification System

**Purpose**: Displays temporary feedback messages for user actions.

**Types**:
| Type | Color | Icon | Use Case |
|------|-------|------|----------|
| success | Green | check-circle | Operation completed successfully |
| error | Red | times-circle | Operation failed |
| info | Blue | info-circle | Informational message |
| warning | Orange | exclamation-triangle | Warning or caution |

**Template**:
```html
<div class="toast-container">
    <div v-for="toast in toasts" :key="toast.id" class="toast" :class="'toast-' + toast.type">
        <i class="fas" :class="iconClass"></i>
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-close" @click="removeToast(toast.id)">
            <i class="fas fa-times"></i>
        </button>
    </div>
</div>
```

**Behavior**:
- Toasts appear in the top-right corner
- Auto-dismiss after 5 seconds
- Manual dismiss via close button
- Slide-in/slide-out animations

---

### 6. Confirmation Modal

**Purpose**: Requires explicit user confirmation for destructive actions.

**Use Cases**:
- Deleting a model
- Resetting usage statistics
- Deleting a deployment

**Template**:
```html
<div v-if="confirmModal.show" class="modal-overlay" @click.self="closeConfirmModal">
    <div class="modal-content">
        <div class="modal-header warning">
            <i class="fas fa-exclamation-triangle"></i>
            <h3>{{ confirmModal.title }}</h3>
        </div>
        <div class="modal-body">{{ confirmModal.message }}</div>
        <div class="modal-footer">
            <button @click="closeConfirmModal">{{ confirmModal.cancelText }}</button>
            <button @click="executeConfirm">{{ confirmModal.confirmText }}</button>
        </div>
    </div>
</div>
```

**Behavior**:
- Overlay blocks interaction with background
- Click outside modal to cancel
- Callback function executed on confirm

---

## Vue.js Data Properties

### Connection State

```javascript
connectionStatus: false
```

**Purpose**: Tracks whether the frontend can communicate with the backend API.

**Updated By**: `checkConnection()` method on startup.

---

### GPU Status

```javascript
gpuStatus: {
    data: null,
    loading: false,
    error: null
}
```

**Purpose**: Stores GPU VRAM information retrieved from the backend.

**Structure when populated**:
```javascript
gpuStatus.data = {
    gpu_info: {
        total_vram_gb: 23.0,
        available_vram_gb: 15.0,
        allocated_vram_gb: 8.0,
        utilization_percent: 34.8
    },
    recommendations: ['Can deploy medium models (7B-13B)']
}
```

**Updated By**: `refreshGpuStatus()` method every 30 seconds.

---

### Ollama Models

```javascript
ollamaModels: [],
loadingOllamaModels: false
```

**Purpose**: Stores the list of models currently loaded in the Ollama runtime.

**Model Object Structure**:
```javascript
{
    name: 'llama2:7b',
    size: 3800000000,  // bytes
    modified_at: '2024-01-15T10:30:00Z'
}
```

**Updated By**: `loadOllamaModels()` method on startup and every 30 seconds.

---

### Model Pull State

```javascript
newOllamaModel: '',
pullingOllamaModel: false,
modelPullProgress: 0,
modelPullStatus: 'Preparing to pull...'
```

**Purpose**: Manages the state of model download operations.

**State Transitions**:
1. User enters model name: `newOllamaModel` populated
2. User clicks Pull: `pullingOllamaModel` = true, `modelPullProgress` = 0
3. Progress updates: `modelPullProgress` increments, `modelPullStatus` updates
4. Completion: `modelPullProgress` = 100, then reset after 2 seconds

---

### Available Models (Dropdown)

```javascript
ggufModels: [],
loadingGGUFModels: false,
selectedGGUFModel: ''
```

**Purpose**: Stores the curated list of models available for download.

**Model Object Structure**:
```javascript
{
    id: 'llama3.1:8b',
    name: 'Llama 3.1 8B',
    size: '8B',
    likes: 700,
    description: 'Meta Llama 3.1 latest'
}
```

**Updated By**: `loadGGUFModels()` method on startup.

---

### Usage Ranking

```javascript
usageRanking: {
    total_requests: 0,
    models: [],
    timestamp: null
},
loadingUsageRanking: false
```

**Purpose**: Stores model usage statistics for the ranking display.

**Model Entry Structure**:
```javascript
{
    rank: 1,
    model: 'llama2:7b',
    count: 75,
    usage_percent: 50.0
}
```

**Updated By**: `loadUsageRanking()` method on startup and every 10 seconds.

---

### Toast Notifications

```javascript
toasts: [],
toastIdCounter: 0
```

**Purpose**: Manages the queue of visible toast notifications.

**Toast Object Structure**:
```javascript
{
    id: 1,
    type: 'success',
    message: 'Model pulled successfully!'
}
```

---

### Confirmation Modal

```javascript
confirmModal: {
    show: false,
    title: '',
    message: '',
    onConfirm: null,
    confirmText: 'Confirm',
    cancelText: 'Cancel'
}
```

**Purpose**: Stores the state and content of the confirmation dialog.

---

## Computed Properties

### selectedModelInfo

```javascript
selectedModelInfo() {
    return this.availableModels.find(m => m.id === this.selectedModel);
}
```

**Purpose**: Returns detailed information about the currently selected model in the deployment form.

**Use Case**: Used to display model description and quantization information below the model selector.

---

### estimatedVRAM

```javascript
estimatedVRAM() {
    if (!this.selectedModel) return null;
    return this.estimateModelVRAM(this.selectedModel);
}
```

**Purpose**: Calculates and returns the estimated VRAM requirement for the selected model.

**Use Case**: Displayed in the deployment form to help users understand resource requirements.

---

### topModel

```javascript
topModel() {
    if (this.usageRanking.models.length > 0) {
        return this.usageRanking.models[0];
    }
    return null;
}
```

**Purpose**: Returns the most frequently used model from the ranking data.

**Use Case**: Displayed in the usage statistics summary section.

---

## Methods

### Lifecycle Methods

#### mounted()

```javascript
mounted() {
    this.checkConnection();
    this.loadModels();
    this.refreshDeployments();
    this.refreshGpuStatus();
    this.loadOllamaModels();
    this.loadGGUFModels();
    this.loadUsageRanking();
    
    // Auto-refresh every 30 seconds
    setInterval(() => {
        if (this.connectionStatus) {
            this.refreshDeployments();
            this.refreshGpuStatus();
            this.loadOllamaModels();
        }
    }, 30000);
    
    // Auto-refresh usage ranking every 10 seconds
    setInterval(() => {
        if (this.connectionStatus) {
            this.loadUsageRanking();
        }
    }, 10000);
}
```

**Purpose**: Initializes the application when the Vue instance is mounted to the DOM.

**Behavior**:
1. Checks backend connectivity
2. Loads all initial data (models, GPU status, rankings)
3. Sets up automatic refresh intervals

**Refresh Intervals**:
| Data | Interval | Rationale |
|------|----------|-----------|
| Deployments | 30s | Deployment status changes infrequently |
| GPU Status | 30s | VRAM allocation changes with deployments |
| Ollama Models | 30s | Model list changes during pulls/deletes |
| Usage Ranking | 10s | Provides responsive feedback after tests |

---

### API Communication Methods

#### checkConnection()

```javascript
async checkConnection() {
    try {
        const response = await axios.get('/api/health');
        this.connectionStatus = true;
    } catch (error) {
        this.connectionStatus = false;
        this.showAlert('Failed to connect to Kubernetes cluster', 'error');
    }
}
```

**Purpose**: Verifies that the backend API is reachable.

**API Endpoint**: `GET /api/health`

**Use Case**: Called on startup to establish initial connection state. Updates the header status badge.

---

#### refreshGpuStatus()

```javascript
async refreshGpuStatus() {
    if (!this.connectionStatus) return;
    
    this.gpuStatus.loading = true;
    this.gpuStatus.error = null;
    
    try {
        const response = await axios.get('/api/gpu/status');
        if (response.data.success) {
            const gpuInfo = response.data.gpu_info || response.data;
            this.gpuStatus.data = {
                gpu_info: {
                    total_vram_gb: gpuInfo.total_vram_gb,
                    available_vram_gb: gpuInfo.available_vram_gb,
                    allocated_vram_gb: gpuInfo.allocated_vram_gb,
                    utilization_percent: gpuInfo.utilization_percent
                },
                recommendations: this.getGPURecommendations(gpuInfo)
            };
        }
    } catch (error) {
        this.gpuStatus.error = error.message;
        this.gpuStatus.data = null;
    } finally {
        this.gpuStatus.loading = false;
    }
}
```

**Purpose**: Fetches current GPU VRAM utilization from the backend.

**API Endpoint**: `GET /api/gpu/status`

**Response Handling**: Normalizes the response structure to handle variations in backend response format.

**Use Case**: Updates the GPU summary bar with current resource availability.

---

#### loadOllamaModels()

```javascript
async loadOllamaModels() {
    this.loadingOllamaModels = true;
    try {
        const response = await axios.get('/api/ollama/models');
        
        if (response.data.models) {
            this.ollamaModels = response.data.models;
        } else if (Array.isArray(response.data)) {
            this.ollamaModels = response.data;
        } else {
            this.ollamaModels = [];
        }
    } catch (error) {
        this.ollamaModels = [];
        this.showAlert('error', 'Failed to load Ollama models');
    } finally {
        this.loadingOllamaModels = false;
    }
}
```

**Purpose**: Retrieves the list of models currently loaded in Ollama.

**API Endpoint**: `GET /api/ollama/models`

**Response Handling**: Handles multiple response formats for compatibility.

**Use Case**: Populates the "Currently Loaded Models" table.

---

#### pullOllamaModel()

```javascript
async pullOllamaModel() {
    if (!this.newOllamaModel.trim()) return;
    
    // Check for duplicate
    const existingModel = this.ollamaModels.find(m => 
        m.name.toLowerCase() === this.newOllamaModel.trim().toLowerCase()
    );
    if (existingModel) {
        this.showAlert('warning', 'Model already downloaded');
        return;
    }
    
    const modelName = this.newOllamaModel.trim();
    this.pullingOllamaModel = true;
    this.modelPullProgress = 0;
    this.modelPullStatus = 'Starting pull...';
    
    try {
        await axios.post('/api/ollama/pull', { model: modelName });
        
        // Start polling for progress
        const pollProgress = async () => {
            const progressResponse = await axios.get(`/api/ollama/pull/progress/${encodeURIComponent(modelName)}`);
            const progress = progressResponse.data;
            
            this.modelPullProgress = progress.progress || 0;
            this.modelPullStatus = progress.message || progress.status;
            
            if (progress.status === 'success') {
                // Handle completion
                this.showAlert('success', 'Model pulled successfully!');
                this.loadOllamaModels();
                return;
            }
            
            if (progress.status === 'error') {
                this.showAlert('error', progress.error);
                this.pullingOllamaModel = false;
                return;
            }
            
            // Continue polling
            setTimeout(pollProgress, 1000);
        };
        
        setTimeout(pollProgress, 500);
    } catch (error) {
        this.showAlert('error', 'Failed to pull model');
        this.pullingOllamaModel = false;
    }
}
```

**Purpose**: Initiates a model download and tracks progress.

**API Endpoints**:
- `POST /api/ollama/pull` - Starts the download
- `GET /api/ollama/pull/progress/<model_name>` - Polls for progress

**Duplicate Prevention**: Checks if model already exists before initiating pull.

**Progress Tracking**:
1. Sends initial pull request
2. Polls progress endpoint every second
3. Updates progress bar and status text
4. Stops polling on success or error

**Use Case**: Primary method for downloading new models to the system.

---

#### testOllamaModel(modelName)

```javascript
async testOllamaModel(modelName) {
    this.testingOllamaModel = true;
    this.ollamaTestResult = null;
    
    try {
        this.showAlert('info', `Testing model "${modelName}"...`);
        const response = await axios.post('/api/ollama/generate', {
            model: modelName,
            prompt: 'Hello! Please introduce yourself briefly.'
        });
        
        this.ollamaTestResult = {
            model: modelName,
            response: response.data.response
        };
        
        this.showAlert('success', 'Model tested successfully!');
        this.loadUsageRanking();  // Refresh ranking since backend tracks usage
    } catch (error) {
        this.showAlert('error', 'Failed to test model');
    } finally {
        this.testingOllamaModel = false;
    }
}
```

**Purpose**: Sends a test prompt to a model and displays the response.

**API Endpoint**: `POST /api/ollama/generate`

**Test Prompt**: "Hello! Please introduce yourself briefly and tell me what you can help with."

**Side Effect**: Triggers usage tracking on the backend, which updates the usage ranking.

**Use Case**: Allows users to verify models are working correctly after download.

---

#### deleteOllamaModel(modelName)

```javascript
deleteOllamaModel(modelName) {
    this.showConfirmModal(
        'Delete Model',
        `Are you sure you want to delete "${modelName}"?`,
        () => this.confirmDeleteOllamaModel(modelName),
        'Delete',
        'Cancel'
    );
}

async confirmDeleteOllamaModel(modelName) {
    this.deletingOllamaModel = true;
    try {
        await axios.post('/api/ollama/delete', { model: modelName });
        this.showAlert('success', 'Model deleted successfully!');
        await this.loadOllamaModels();
    } catch (error) {
        this.showAlert('error', 'Failed to delete model');
    } finally {
        this.deletingOllamaModel = false;
    }
}
```

**Purpose**: Removes a model from Ollama storage after user confirmation.

**API Endpoint**: `POST /api/ollama/delete`

**Confirmation**: Uses modal dialog to prevent accidental deletion.

**Use Case**: Allows users to free disk space by removing unused models.

---

#### loadGGUFModels()

```javascript
async loadGGUFModels() {
    this.loadingGGUFModels = true;
    try {
        const response = await axios.get('/api/ollama/gguf-models');
        if (response.data.success) {
            this.ggufModels = response.data.models;
        }
    } catch (error) {
        // Silently fail - dropdown will show empty
    } finally {
        this.loadingGGUFModels = false;
    }
}
```

**Purpose**: Fetches the curated list of available models for the dropdown.

**API Endpoint**: `GET /api/ollama/gguf-models`

**Error Handling**: Fails silently to avoid disrupting the user experience.

**Use Case**: Populates the model selection dropdown with popular options.

---

#### loadUsageRanking()

```javascript
async loadUsageRanking() {
    this.loadingUsageRanking = true;
    try {
        const response = await axios.get('/api/usage/ranking');
        if (response.data.success) {
            this.usageRanking = {
                total_requests: response.data.total_requests,
                models: response.data.models || [],
                timestamp: response.data.timestamp
            };
        }
    } catch (error) {
        // Silently fail - table will show empty state
    } finally {
        this.loadingUsageRanking = false;
    }
}
```

**Purpose**: Retrieves model usage statistics from the backend.

**API Endpoint**: `GET /api/usage/ranking`

**Refresh Rate**: Every 10 seconds for responsive updates after model tests.

**Use Case**: Populates the usage ranking panel with current statistics.

---

#### resetUsageStats()

```javascript
resetUsageStats() {
    this.showConfirmModal(
        'Reset Statistics',
        'Are you sure you want to reset all usage statistics?',
        () => this.confirmResetUsageStats(),
        'Reset',
        'Cancel'
    );
}

async confirmResetUsageStats() {
    try {
        await axios.post('/api/usage/reset');
        this.usageRanking = { total_requests: 0, models: [], timestamp: null };
        this.showAlert('success', 'Usage statistics have been reset');
    } catch (error) {
        this.showAlert('error', 'Failed to reset usage statistics');
    }
}
```

**Purpose**: Clears all usage statistics after user confirmation.

**API Endpoint**: `POST /api/usage/reset`

**Use Case**: Allows administrators to start fresh with usage tracking.

---

### UI Utility Methods

#### showAlert(type, message)

```javascript
showAlert(type, message) {
    if (['success', 'error', 'info', 'warning'].includes(type)) {
        this.addToast(type, message);
    } else {
        // Backward compatibility: showAlert(message, type)
        this.addToast(message, type);
    }
}
```

**Purpose**: Displays a toast notification to the user.

**Parameters**:
- `type`: 'success', 'error', 'info', or 'warning'
- `message`: Text to display

**Backward Compatibility**: Supports both (type, message) and (message, type) argument orders.

---

#### addToast(type, message)

```javascript
addToast(type, message) {
    const id = ++this.toastIdCounter;
    const toast = { id, type, message };
    this.toasts.push(toast);
    
    setTimeout(() => {
        this.removeToast(id);
    }, 5000);
}
```

**Purpose**: Creates a new toast notification with auto-dismiss.

**Behavior**:
1. Generates unique ID
2. Adds toast to queue
3. Schedules removal after 5 seconds

---

#### removeToast(id)

```javascript
removeToast(id) {
    const index = this.toasts.findIndex(t => t.id === id);
    if (index !== -1) {
        this.toasts.splice(index, 1);
    }
}
```

**Purpose**: Removes a toast notification from the queue.

**Use Case**: Called automatically after timeout or manually when user clicks close.

---

#### showConfirmModal(title, message, onConfirm, confirmText, cancelText)

```javascript
showConfirmModal(title, message, onConfirm, confirmText = 'Delete', cancelText = 'Cancel') {
    this.confirmModal = {
        show: true,
        title,
        message,
        onConfirm,
        confirmText,
        cancelText
    };
}
```

**Purpose**: Displays a confirmation dialog for destructive actions.

**Parameters**:
- `title`: Dialog header text
- `message`: Explanation of the action
- `onConfirm`: Callback function to execute on confirmation
- `confirmText`: Text for confirm button (default: 'Delete')
- `cancelText`: Text for cancel button (default: 'Cancel')

---

#### closeConfirmModal()

```javascript
closeConfirmModal() {
    this.confirmModal.show = false;
    this.confirmModal.onConfirm = null;
}
```

**Purpose**: Hides the confirmation modal without executing the action.

---

#### executeConfirm()

```javascript
executeConfirm() {
    if (this.confirmModal.onConfirm) {
        this.confirmModal.onConfirm();
    }
    this.closeConfirmModal();
}
```

**Purpose**: Executes the stored callback and closes the modal.

---

### Helper Methods

#### formatSize(bytes)

```javascript
formatSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
```

**Purpose**: Converts byte values to human-readable format.

**Examples**:
| Input | Output |
|-------|--------|
| 1024 | 1 KB |
| 1073741824 | 1 GB |
| 3800000000 | 3.54 GB |

**Use Case**: Displays model file sizes in the models table.

---

#### estimateModelVRAM(sizeBytes)

```javascript
estimateModelVRAM(sizeBytes) {
    if (!sizeBytes) return '~0';
    const sizeGB = sizeBytes / (1024 * 1024 * 1024);
    const vramEstimate = sizeGB * 1.2;  // 20% overhead for inference
    return vramEstimate.toFixed(1);
}
```

**Purpose**: Estimates VRAM requirement based on model file size.

**Formula**: VRAM = File Size x 1.2

**Rationale**: Model inference requires approximately 20% more memory than the model file size for activation tensors and KV cache.

**Use Case**: Displays estimated VRAM in the models table.

---

#### formatDate(dateString)

```javascript
formatDate(dateString) {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleDateString();
}
```

**Purpose**: Formats ISO date strings for display.

**Use Case**: Shows when models were downloaded in the models table.

---

#### getGPURecommendations(gpuData)

```javascript
getGPURecommendations(gpuData) {
    const recommendations = [];
    const totalVram = gpuData.total_vram_gb || 0;
    const availableVram = gpuData.available_vram_gb || 0;
    
    if (totalVram > 0) {
        const availablePercent = (availableVram / totalVram * 100);
        
        if (availablePercent < 10) {
            recommendations.push('GPU memory critically low');
        } else if (availablePercent < 30) {
            recommendations.push('GPU memory is getting low');
        } else if (availablePercent > 80) {
            recommendations.push('Plenty of GPU memory available');
        }
    }
    
    return recommendations;
}
```

**Purpose**: Generates human-readable GPU usage recommendations.

**Thresholds**:
| Available % | Recommendation |
|-------------|----------------|
| < 10% | Critically low |
| < 30% | Getting low |
| > 80% | Plenty available |

---

#### getRankClass(rank)

```javascript
getRankClass(rank) {
    if (rank === 1) return 'rank-1';
    if (rank === 2) return 'rank-2';
    if (rank === 3) return 'rank-3';
    return 'rank-other';
}
```

**Purpose**: Returns CSS class for rank badge styling.

**Styling**:
| Rank | Class | Visual |
|------|-------|--------|
| 1 | rank-1 | Gold gradient |
| 2 | rank-2 | Silver gradient |
| 3 | rank-3 | Bronze gradient |
| 4+ | rank-other | Gray |

---

#### onGGUFModelSelected()

```javascript
onGGUFModelSelected() {
    if (this.selectedGGUFModel) {
        this.newOllamaModel = this.selectedGGUFModel;
        this.showAlert('info', 'Model ready to pull. Click Pull button.');
        
        setTimeout(() => {
            document.getElementById('ollama-model')?.focus();
        }, 100);
        
        this.$nextTick(() => {
            this.selectedGGUFModel = '';
        });
    }
}
```

**Purpose**: Handles model selection from the dropdown.

**Behavior**:
1. Copies selected model ID to input field
2. Shows informational toast
3. Focuses the input field
4. Resets dropdown selection

**Use Case**: Provides smooth UX for selecting models from the curated list.

---

## CSS Styling

### Color Scheme

| Element | Primary | Secondary |
|---------|---------|-----------|
| Header | #2c3e50 | #34495e |
| Success | #27ae60 | #2ecc71 |
| Error | #c0392b | #e74c3c |
| Info | #2980b9 | #3498db |
| Warning | #d35400 | #e67e22 |
| Primary Button | #667eea | #5a67d8 |

### Animations

#### slideIn (Toast Entry)

```css
@keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
```

#### slideOut (Toast Exit)

```css
@keyframes slideOut {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(100%); opacity: 0; }
}
```

#### pulse (Status Indicator)

```css
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
```

#### spin (Loading Spinner)

```css
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
```

### Responsive Breakpoints

| Breakpoint | Layout Change |
|------------|---------------|
| 1200px | Single column layout, GPU metrics 2-column |
| 768px | GPU metrics single column, stacked actions |

---

## Data Flow

### Startup Sequence

```
1. Vue app mounts
2. checkConnection() -> GET /api/health
3. If connected:
   a. loadModels() -> GET /api/models (legacy)
   b. refreshDeployments() -> GET /api/deployments
   c. refreshGpuStatus() -> GET /api/gpu/status
   d. loadOllamaModels() -> GET /api/ollama/models
   e. loadGGUFModels() -> GET /api/ollama/gguf-models
   f. loadUsageRanking() -> GET /api/usage/ranking
4. Set up refresh intervals
```

### Model Pull Flow

```
1. User selects model from dropdown
2. onGGUFModelSelected() populates input field
3. User clicks Pull button
4. pullOllamaModel():
   a. Validate input and check for duplicates
   b. POST /api/ollama/pull to start download
   c. Begin polling loop:
      i. GET /api/ollama/pull/progress/<model>
      ii. Update progress bar and status
      iii. Continue until success or error
5. On success:
   a. Show success toast
   b. Clear input field
   c. Refresh model list
```

### Model Test Flow

```
1. User clicks Test button on model row
2. testOllamaModel():
   a. Show info toast
   b. POST /api/ollama/generate with test prompt
   c. Display response in results panel
   d. Show success toast
   e. Refresh usage ranking (backend tracked usage)
```

---

## Error Handling

### Network Errors

All API calls are wrapped in try-catch blocks. On failure:
1. Error is logged to console
2. User receives error toast notification
3. Relevant loading states are reset

### Duplicate Prevention

Before pulling a model, the frontend checks if a model with the same name already exists in `ollamaModels`. This prevents unnecessary network requests and provides immediate user feedback.

### Graceful Degradation

Non-critical features fail silently:
- `loadGGUFModels()` failures show empty dropdown
- `loadUsageRanking()` failures show empty state message
- GPU status failures hide the summary bar

---

## Security Considerations

### Input Validation

Model names are URL-encoded before being used in API endpoints:

```javascript
axios.get(`/api/ollama/pull/progress/${encodeURIComponent(modelName)}`)
```

### XSS Prevention

Vue.js automatically escapes content in template interpolations (`{{ }}`), preventing script injection through user-provided data.

### CORS

The backend enables CORS to allow the frontend to make API requests. In production, CORS should be configured to allow only trusted origins.
