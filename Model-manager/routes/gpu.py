"""
GPU status routes
"""

import logging
from flask import Blueprint, jsonify, current_app
from utils.vram import get_vram_recommendations

logger = logging.getLogger(__name__)

gpu_bp = Blueprint('gpu', __name__)

# Will be set when registering the blueprint
k8s_client = None


def init_gpu_routes(kubernetes_client):
    """Initialize the GPU routes with the Kubernetes client"""
    global k8s_client
    k8s_client = kubernetes_client


@gpu_bp.route('/gpu/status', methods=['GET'])
def get_gpu_status():
    """Get detailed GPU and vRAM status"""
    if not k8s_client or not k8s_client.connected:
        return jsonify({"error": "Kubernetes client not connected"}), 503
    
    try:
        gpu_info = k8s_client.check_gpu_vram_availability()
        
        if gpu_info['success']:
            total_vram = gpu_info.get('total_vram_gb', 0)
            available_vram = gpu_info.get('available_vram_gb', 0)
            used_vram = total_vram - available_vram
            usage_percent = (used_vram / total_vram * 100) if total_vram > 0 else 0
            
            return jsonify({
                'success': True,
                'total_vram_gb': total_vram,
                'used_vram_gb': used_vram,
                'available_vram_gb': available_vram,
                'usage_percent': round(usage_percent, 2),
                'gpu_count': gpu_info.get('gpu_count', 0),
                'gpu_devices': gpu_info.get('gpu_devices', []),
                'gpu_info': gpu_info,
                'recommendations': get_vram_recommendations(gpu_info)
            })
        else:
            return jsonify({
                'success': False,
                'error': gpu_info.get('error', 'Unknown error'),
                'total_vram_gb': 0,
                'used_vram_gb': 0,
                'available_vram_gb': 0,
                'usage_percent': 0
            }), 500
            
    except Exception as e:
        logger.error(f"Error getting GPU status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
