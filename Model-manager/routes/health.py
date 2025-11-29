"""
Health check routes
"""

from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)

# These will be set when registering the blueprint
k8s_client = None


def init_health_routes(kubernetes_client):
    """Initialize the health routes with the Kubernetes client"""
    global k8s_client
    k8s_client = kubernetes_client


@health_bp.route('/health')
def health():
    """Health check endpoint"""
    if k8s_client and k8s_client.connected:
        return jsonify({
            "status": "healthy",
            "kubernetes": "connected",
            "huggingface": "available"
        })
    else:
        return jsonify({
            "status": "unhealthy",
            "kubernetes": "disconnected",
            "huggingface": "unknown"
        }), 503
