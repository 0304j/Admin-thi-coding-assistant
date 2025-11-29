"""
Routes package for Model Manager API
"""

from .health import health_bp, init_health_routes
from .models import models_bp
from .deployments import deployments_bp, init_deployment_routes
from .gpu import gpu_bp, init_gpu_routes
from .ollama import ollama_bp

__all__ = [
    'health_bp',
    'init_health_routes',
    'models_bp',
    'deployments_bp',
    'init_deployment_routes',
    'gpu_bp',
    'init_gpu_routes',
    'ollama_bp',
]
