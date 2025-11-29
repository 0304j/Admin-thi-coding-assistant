"""
Kubernetes deployment routes
"""

import logging
from flask import Blueprint, jsonify, request
from utils.vram import estimate_model_vram

logger = logging.getLogger(__name__)

deployments_bp = Blueprint('deployments', __name__)

# Will be set when registering the blueprint
k8s_client = None


def init_deployment_routes(kubernetes_client):
    """Initialize the deployment routes with the Kubernetes client"""
    global k8s_client
    k8s_client = kubernetes_client


@deployments_bp.route('/deployments')
def get_deployments():
    """Get list of deployed models across all namespaces"""
    if not k8s_client or not k8s_client.connected:
        return jsonify({"error": "Kubernetes client not connected"}), 503
    
    try:
        # Get deployments from all namespaces with timeout to prevent hanging
        all_deployments = k8s_client.apps_v1.list_deployment_for_all_namespaces(_request_timeout=5)
        
        deployed_models = []
        for deployment in all_deployments.items:
            # Skip non-model deployments (like dashboards, system services)
            name = deployment.metadata.name
            namespace = deployment.metadata.namespace
            
            # Skip system deployments
            if name in ['model-manager', 'model-dashboard'] or namespace in ['kube-system', 'kube-public']:
                continue
            
            # Extract model info from environment variables
            model_id = 'Unknown'
            model_image = 'Unknown'
            containers = deployment.spec.template.spec.containers
            
            if containers:
                container = containers[0]
                # Check for TGI or model serving containers
                if 'text-generation-inference' in container.image or 'transformers' in container.image:
                    model_image = container.image
                    
                    # Extract MODEL_ID from env vars
                    if container.env:
                        for env in container.env:
                            if env.name == 'MODEL_ID':
                                model_id = env.value
                                break
                    
                    # Get status
                    status = 'Unknown'
                    ready_replicas = deployment.status.ready_replicas or 0
                    replicas = deployment.spec.replicas or 0
                    
                    if ready_replicas > 0:
                        status = 'Running'
                    elif ready_replicas == 0 and replicas > 0:
                        status = 'Starting'
                    else:
                        status = 'Failed'
                    
                    # Get resource info
                    gpu_limit = 'N/A'
                    memory_limit = 'N/A'
                    if container.resources and container.resources.limits:
                        limits = container.resources.limits
                        gpu_limit = limits.get('nvidia.com/gpu', 'N/A')
                        memory_limit = limits.get('memory', 'N/A')
                    
                    deployed_models.append({
                        'name': name,
                        'namespace': namespace,
                        'model_id': model_id,
                        'image': model_image.split('/')[-1],  # Just image name
                        'status': status,
                        'replicas': f"{ready_replicas}/{replicas}",
                        'gpu': gpu_limit,
                        'memory': memory_limit,
                        'created': deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else 'Unknown'
                    })
        
        return jsonify({
            'success': True,
            'models': deployed_models,
            'count': len(deployed_models)
        })
        
    except Exception as e:
        logger.error(f"Failed to list deployed models: {e}")
        return jsonify({"error": str(e)}), 500


@deployments_bp.route('/deploy', methods=['POST'])
def deploy_model():
    """Deploy a model with vRAM management and resource verification"""
    if not k8s_client or not k8s_client.connected:
        return jsonify({"error": "Kubernetes client not connected"}), 503
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided', 'success': False}), 400
        
        model_id = data.get('model_id')
        deployment_name = data.get('deployment_name', f"{model_id.split('/')[-1].lower().replace('_', '-')}-deploy")
        requested_memory_gb = int(data.get('memory', '8').replace('Gi', '').replace('GB', ''))
        
        logger.info(f"Deploying model {model_id} with {requested_memory_gb}GB vRAM")
        
        # 1. Estimate model vRAM requirements
        estimated_vram = estimate_model_vram(model_id)
        logger.info(f"Estimated vRAM requirement: {estimated_vram}GB")
        
        # 2. Check if requested memory is sufficient
        if estimated_vram > requested_memory_gb:
            return jsonify({
                'error': f'Model requires ~{estimated_vram}GB vRAM, but only {requested_memory_gb}GB requested',
                'success': False,
                'estimated_vram': estimated_vram,
                'requested_vram': requested_memory_gb,
                'suggestion': f'Increase memory allocation to at least {int(estimated_vram + 1)}GB'
            }), 400
        
        # 3. Check GPU vRAM availability
        gpu_info = k8s_client.check_gpu_vram_availability()
        if not gpu_info['success']:
            return jsonify({
                'error': 'Failed to check GPU availability',
                'success': False,
                'details': gpu_info.get('error', 'Unknown error')
            }), 500
        
        available_vram = gpu_info['available_vram_gb']
        total_vram = gpu_info['total_vram_gb']
        
        logger.info(f"GPU vRAM: {available_vram}GB available of {total_vram}GB total")
        
        # 4. Verify sufficient vRAM is available
        if available_vram < requested_memory_gb:
            return jsonify({
                'error': f'Insufficient vRAM available. Requested: {requested_memory_gb}GB, Available: {available_vram}GB',
                'success': False,
                'available_vram': available_vram,
                'total_vram': total_vram,
                'allocated_vram': total_vram - available_vram,
                'suggestion': f'Only {available_vram}GB available. Reduce allocation or wait for other models to finish.'
            }), 400
        
        # 5. Calculate CUDA memory fraction
        memory_fraction = min(requested_memory_gb / total_vram, 1.0)
        
        # 6. Deploy to Kubernetes with vRAM management
        result = k8s_client.deploy_model_with_vram(
            model_id=model_id,
            deployment_name=deployment_name,
            memory_gb=requested_memory_gb,
            memory_fraction=memory_fraction,
            estimated_vram=estimated_vram
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Model {model_id} deployed successfully with {requested_memory_gb}GB vRAM allocation',
                'deployment_name': deployment_name,
                'allocated_vram_gb': requested_memory_gb,
                'memory_fraction': round(memory_fraction, 3),
                'estimated_model_vram': estimated_vram,
                'remaining_vram': available_vram - requested_memory_gb
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Deployment failed: {result.get("error", "Unknown error")}'
            }), 500
            
    except Exception as e:
        logger.error(f"Error deploying model: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@deployments_bp.route('/delete', methods=['POST'])
def delete_deployment():
    """Delete a deployment"""
    if not k8s_client or not k8s_client.connected:
        return jsonify({"error": "Kubernetes client not connected"}), 503
    
    try:
        data = request.get_json()
        deployment_name = data.get('deployment_name')
        
        if not deployment_name:
            return jsonify({"error": "deployment_name is required"}), 400
        
        success = k8s_client.delete_deployment(deployment_name)
        
        if success:
            return jsonify({"message": f"Deployment {deployment_name} deleted successfully"})
        else:
            return jsonify({"error": "Failed to delete deployment"}), 500
            
    except Exception as e:
        logger.error(f"Failed to delete deployment: {e}")
        return jsonify({"error": str(e)}), 500
