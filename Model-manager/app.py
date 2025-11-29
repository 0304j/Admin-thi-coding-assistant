#!/usr/bin/env python3
"""
API Server for Vue.js Model Manager
Provides REST endpoints for the Vue.js frontend with live Hugging Face integration

This is the main application entry point that:
- Initializes the Flask app
- Registers all route blueprints
- Sets up middleware for logging and cleanup
- Starts the server
"""

import logging
import gc
from flask import Flask, request, send_from_directory
from flask_cors import CORS

from config import SERVER_HOST, SERVER_PORT, DEBUG_MODE, create_http_session
from k8s_client import KubernetesClient
from hf_models import HuggingFaceModels

# Import route blueprints
from routes import (
    health_bp, init_health_routes,
    models_bp,
    deployments_bp, init_deployment_routes,
    gpu_bp, init_gpu_routes,
    ollama_bp
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    """
    Application factory function.
    Creates and configures the Flask application.
    """
    app = Flask(__name__)
    CORS(app)  # Enable CORS for frontend
    
    # Create HTTP session with connection pooling
    http_session = create_http_session()
    
    # Initialize clients
    k8s_client = None
    hf_models = None
    
    try:
        k8s_client = KubernetesClient()
        hf_models = HuggingFaceModels()
        logger.info("Kubernetes and HuggingFace clients initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
    
    # Initialize routes with dependencies
    init_health_routes(k8s_client)
    init_deployment_routes(k8s_client)
    init_gpu_routes(k8s_client)
    
    # Register blueprints with /api prefix
    app.register_blueprint(health_bp, url_prefix='/api')
    app.register_blueprint(models_bp, url_prefix='/api')
    app.register_blueprint(deployments_bp, url_prefix='/api')
    app.register_blueprint(gpu_bp, url_prefix='/api')
    app.register_blueprint(ollama_bp, url_prefix='/api')
    
    # Store clients in app context for access in routes if needed
    app.k8s_client = k8s_client
    app.hf_models = hf_models
    app.http_session = http_session
    
    # Register middleware
    register_middleware(app)
    
    # Register root route
    @app.route('/')
    def index():
        """Serve the Vue.js frontend"""
        return send_from_directory('.', 'vue-model-manager.html')
    
    return app


def register_middleware(app):
    """Register request/response middleware"""
    
    @app.before_request
    def log_request():
        """Log all incoming requests"""
        logger.info(f"[REQUEST] {request.method} {request.path} from {request.remote_addr}")
        if request.method == 'OPTIONS':
            logger.debug(f"[PREFLIGHT] CORS preflight for {request.path}")
    
    @app.after_request
    def cleanup_after_request(response):
        """Cleanup memory after each request"""
        gc.collect()
        return response


def print_startup_info(k8s_connected: bool):
    """Print startup information"""
    print("\n" + "=" * 60)
    print("  Vue.js Model Manager API Server")
    print("=" * 60)
    print(f"  Frontend:    http://localhost:{SERVER_PORT}")
    print(f"  API:         http://localhost:{SERVER_PORT}/api/")
    print(f"  Kubernetes:  {'✓ Connected' if k8s_connected else '✗ Not connected'}")
    print("  Ollama:      Enabled")
    print("=" * 60 + "\n")


# Create the application
app = create_app()


if __name__ == '__main__':
    k8s_connected = app.k8s_client and app.k8s_client.connected
    print_startup_info(k8s_connected)
    
    if not k8s_connected:
        print("⚠  Kubernetes client not connected - check your kubeconfig")
    
    # Use debug=False in production to prevent Werkzeug auto-reloader 
    # from causing CrashLoopBackOff
    app.run(
        host=SERVER_HOST, 
        port=SERVER_PORT, 
        debug=DEBUG_MODE, 
        use_reloader=False
    )
