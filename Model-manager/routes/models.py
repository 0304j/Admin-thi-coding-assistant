"""
HuggingFace model routes
"""

from flask import Blueprint, jsonify, request
from hf_models import HuggingFaceModels

models_bp = Blueprint('models', __name__)


@models_bp.route('/models', methods=['GET'])
def get_models():
    """Get models from Hugging Face Hub"""
    try:
        task = request.args.get('task', 'text-generation')
        limit = int(request.args.get('limit', 50))
        query = request.args.get('search', '')
        
        hf_models = HuggingFaceModels()
        
        if query:
            models = hf_models.search_models(query, task, limit)
        else:
            models = hf_models.get_models(task, limit)
        
        return jsonify({
            'success': True,
            'models': models,
            'count': len(models)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@models_bp.route('/models-list')
def get_models_list():
    """Get list of available models"""
    hf_models = HuggingFaceModels()
    models = hf_models.get_models()
    return jsonify(models)
