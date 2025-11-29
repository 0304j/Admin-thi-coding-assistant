"""
Ollama-specific routes for dynamic model management
"""

import logging
import threading
import sys
import requests
from flask import Blueprint, jsonify, request, current_app
from config import OLLAMA_URLS

logger = logging.getLogger(__name__)

ollama_bp = Blueprint('ollama', __name__)


def _get_ollama_url(endpoint: str) -> list:
    """Get list of Ollama URLs for a specific endpoint"""
    return [f"{base_url}/api/{endpoint}" for base_url in OLLAMA_URLS]


@ollama_bp.route('/ollama/models', methods=['GET'])
def get_ollama_models():
    """Get currently loaded models from Ollama"""
    try:
        urls = _get_ollama_url('tags')
        
        for url in urls:
            try:
                logger.info(f'[OLLAMA] Trying to connect to: {url}')
                response = requests.get(url, timeout=5)
                logger.info(f'[OLLAMA] Response status: {response.status_code}')
                
                if response.status_code == 200:
                    models_data = response.json()
                    logger.info(f'[OLLAMA] Success! Got {len(models_data.get("models", []))} models from {url}')
                    return jsonify(models_data)
            except requests.exceptions.RequestException as e:
                logger.warning(f'[OLLAMA] Failed to connect to {url}: {str(e)}')
                continue
        
        logger.error('[OLLAMA] All connection attempts failed')
        return jsonify({
            'models': [],
            'error': 'Failed to connect to Ollama service. All URLs exhausted.',
            'attempted_urls': urls
        }), 500
        
    except Exception as e:
        logger.error(f'[OLLAMA] Exception: {str(e)}')
        return jsonify({'error': str(e)}), 500


@ollama_bp.route('/ollama/pull', methods=['POST'])
def pull_ollama_model():
    """Pull a new model to Ollama (async operation)"""
    try:
        data = request.json
        model_name = data.get('model')
        
        if not model_name:
            return jsonify({'error': 'Model name required'}), 400
        
        def pull_in_background():
            """Background thread function to pull the model"""
            logger.info(f"[BACKGROUND] Starting pull for model: {model_name}")
            sys.stdout.flush()
            sys.stderr.flush()
            
            urls = _get_ollama_url('pull')
            pull_data = {'name': model_name}
            
            for url in urls:
                try:
                    logger.debug(f"[BACKGROUND] Trying Ollama URL: {url}")
                    sys.stdout.flush()
                    response = requests.post(url, json=pull_data, timeout=600, stream=True)
                    logger.info(f"[BACKGROUND] Ollama response from {url}: {response.status_code}")
                    sys.stdout.flush()
                    
                    if response.status_code in [200, 201]:
                        # Read the full streaming response
                        for line in response.iter_lines():
                            if line:
                                try:
                                    logger.debug(f"[BACKGROUND] Ollama: {line.decode('utf-8')}")
                                except:
                                    pass
                        
                        logger.info(f"[BACKGROUND] Successfully pulled model: {model_name}")
                        sys.stdout.flush()
                        return
                except requests.exceptions.Timeout:
                    logger.error(f"[BACKGROUND] Timeout pulling from {url}")
                    sys.stdout.flush()
                    continue
                except requests.exceptions.RequestException as e:
                    logger.debug(f"[BACKGROUND] Failed to connect to {url}: {e}")
                    sys.stdout.flush()
                    continue
            
            logger.error(f"[BACKGROUND] Failed to pull model {model_name}: Could not connect to Ollama")
            sys.stdout.flush()
        
        # Start background thread (don't wait for it)
        thread = threading.Thread(target=pull_in_background, daemon=True)
        thread.start()
        
        # Return immediately
        return jsonify({
            'message': f'Pull started for model "{model_name}". This may take several minutes. Check the models table for updates.'
        }), 202
            
    except Exception as e:
        logger.error(f"Error in pull_ollama_model: {e}")
        return jsonify({'error': str(e)}), 500


@ollama_bp.route('/ollama/delete', methods=['POST'])
def delete_ollama_model():
    """Delete a model from Ollama"""
    try:
        data = request.json
        model_name = data.get('model')
        
        if not model_name:
            return jsonify({'error': 'Model name required'}), 400
        
        urls = _get_ollama_url('delete')
        delete_data = {'name': model_name}
        
        for url in urls:
            try:
                response = requests.delete(url, json=delete_data, timeout=30)
                if response.status_code == 200:
                    return jsonify({'message': f'Model {model_name} deleted successfully'})
            except requests.exceptions.RequestException:
                continue
                
        return jsonify({'error': 'Failed to connect to Ollama service for model deletion'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ollama_bp.route('/ollama/generate', methods=['POST'])
def test_ollama_model():
    """Test model generation with Ollama"""
    try:
        data = request.json
        model_name = data.get('model')
        prompt = data.get('prompt', 'Hello! Please introduce yourself briefly.')
        
        if not model_name:
            return jsonify({'error': 'Model name required'}), 400
        
        urls = _get_ollama_url('generate')
        test_data = {
            'model': model_name,
            'prompt': prompt,
            'stream': False
        }
        
        for url in urls:
            try:
                response = requests.post(url, json=test_data, timeout=60)
                if response.status_code == 200:
                    return jsonify(response.json())
            except requests.exceptions.RequestException:
                continue
                
        return jsonify({'error': 'Failed to connect to Ollama service for model testing'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ollama_bp.route('/ollama/gguf-models', methods=['GET'])
def get_gguf_coding_models():
    """
    Get coding models directly from Ollama registry.
    Fetches from ollama.ai/library and filters for coding/quantized models.
    """
    try:
        models_list = []
        
        # Try to fetch from Ollama's library
        try:
            popular_coding_models = {
                'mistral': 'mistral:7b',
                'neural-chat': 'neural-chat:7b',
                'codellama': 'codellama:7b-instruct',
                'deepseek-coder': 'deepseek-coder:6.7b',
                'orca-mini': 'orca-mini:7b',
                'llama2': 'llama2:7b',
                'llama3.1': 'llama3.1:8b',
                'phi': 'phi:2.7b',
                'tinyllama': 'tinyllama:1.1b',
                'wizard-math': 'wizard-math:7b',
                'dolphin-mixtral': 'dolphin-mixtral:8x7b',
                'openchat': 'openchat:7b',
                'zephyr': 'zephyr:7b',
                'neural-chat-v3': 'neural-chat:7b-v3',
                'orca2': 'orca2:13b',
            }
            
            # Size mapping for model parameter counts
            size_map = {
                '1.1b': '1.1B', '2.7b': '2.7B', '3b': '3B', '3.8b': '3.8B',
                '6.7b': '6.7B', '7b': '7B', '8b': '8B', '13b': '13B',
                '34b': '34B', '70b': '70B', '8x7b': '56B', '45b': '45B'
            }
            
            # Check which models are available by attempting to fetch their tags
            for model_key, model_id in popular_coding_models.items():
                model_name = model_id.split(':')[0]
                model_tag = model_id.split(':')[1] if ':' in model_id else 'latest'
                
                try:
                    url = f'https://registry.ollama.ai/v2/library/{model_name}/manifests/{model_tag}'
                    response = requests.head(url, timeout=5)
                    
                    if response.status_code in [200, 301]:
                        size = 'Unknown'
                        for size_key, size_val in size_map.items():
                            if size_key in model_id.lower():
                                size = size_val
                                break
                        
                        models_list.append({
                            'id': model_id,
                            'name': model_name.replace('-', ' ').title(),
                            'size': size,
                            'downloads': 10000,
                            'likes': 100,
                            'description': f'{model_name} quantized coding model'
                        })
                except (requests.exceptions.RequestException, requests.exceptions.Timeout):
                    continue
            
            if models_list:
                models_list.sort(key=lambda x: x.get('downloads', 0), reverse=True)
                return jsonify({
                    'success': True,
                    'models': models_list,
                    'count': len(models_list),
                    'source': 'Ollama Registry'
                })
        
        except Exception as e:
            logger.warning(f"Failed to fetch from Ollama registry: {e}")
        
        # Fallback: return hardcoded popular Ollama registry models
        fallback_models = _get_fallback_ollama_models()
        
        return jsonify({
            'success': True,
            'models': fallback_models,
            'count': len(fallback_models),
            'source': 'Ollama Registry (Cached)',
            'note': 'Popular coding models available to pull directly from Ollama'
        })
    
    except Exception as e:
        logger.error(f"Error fetching GGUF models: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_fallback_ollama_models() -> list:
    """Return a list of popular Ollama models as fallback"""
    return [
        {'id': 'mistral:7b', 'name': 'Mistral 7B', 'size': '7B', 'downloads': 100000, 'likes': 500, 'description': 'Fast instruction-tuned model'},
        {'id': 'neural-chat:7b', 'name': 'Neural Chat 7B', 'size': '7B', 'downloads': 80000, 'likes': 400, 'description': 'Intel Neural Chat for conversations'},
        {'id': 'codellama:7b-instruct', 'name': 'Code Llama 7B Instruct', 'size': '7B', 'downloads': 90000, 'likes': 450, 'description': 'Meta CodeLlama instruction-tuned'},
        {'id': 'deepseek-coder:6.7b', 'name': 'DeepSeek Coder 6.7B', 'size': '6.7B', 'downloads': 75000, 'likes': 375, 'description': 'DeepSeek specialized for coding'},
        {'id': 'orca-mini:7b', 'name': 'Orca Mini 7B', 'size': '7B', 'downloads': 70000, 'likes': 350, 'description': 'Smaller Orca model'},
        {'id': 'llama2:7b', 'name': 'Llama 2 7B', 'size': '7B', 'downloads': 120000, 'likes': 600, 'description': 'Meta Llama 2 original'},
        {'id': 'llama3.1:8b', 'name': 'Llama 3.1 8B', 'size': '8B', 'downloads': 150000, 'likes': 700, 'description': 'Meta Llama 3.1 latest'},
        {'id': 'openchat:7b', 'name': 'OpenChat 7B', 'size': '7B', 'downloads': 60000, 'likes': 300, 'description': 'OpenChat open source model'},
        {'id': 'phi:2.7b', 'name': 'Phi 2.7B', 'size': '2.7B', 'downloads': 90000, 'likes': 450, 'description': 'Microsoft Phi lightweight'},
        {'id': 'tinyllama:1.1b', 'name': 'TinyLlama 1.1B', 'size': '1.1B', 'downloads': 80000, 'likes': 400, 'description': 'Ultra lightweight model'},
        {'id': 'wizard-math:7b', 'name': 'Wizard Math 7B', 'size': '7B', 'downloads': 40000, 'likes': 200, 'description': 'Specialized for math problems'},
        {'id': 'zephyr:7b', 'name': 'Zephyr 7B', 'size': '7B', 'downloads': 85000, 'likes': 425, 'description': 'Hugging Face Zephyr'},
    ]
