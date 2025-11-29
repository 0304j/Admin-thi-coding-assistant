"""
Hugging Face model repository integration with live API
"""
import logging
import requests
from typing import List, Dict, Optional
import os

logger = logging.getLogger(__name__)

class HuggingFaceModels:
    """Manages Hugging Face models with live API integration"""
    
    def __init__(self):
        """Initialize with Hugging Face API"""
        self.api_url = "https://huggingface.co/api"
        self.token = os.getenv('HUGGING_FACE_HUB_TOKEN')
        self.headers = {}
        if self.token:
            self.headers['Authorization'] = f'Bearer {self.token}'
    
    def search_models(self, query: str = "", filter_type: str = "text-generation", limit: int = 20) -> List[Dict]:
        """Search models on Hugging Face Hub"""
        try:
            params = {
                'search': query,
                'filter': filter_type,
                'sort': 'downloads',
                'direction': -1,
                'limit': limit
            }
            
            response = requests.get(
                f"{self.api_url}/models",
                params=params,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                models = response.json()
                return self._format_models(models)
            else:
                logger.error(f"HF API error: {response.status_code}")
                return self._get_fallback_models()
                
        except Exception as e:
            logger.error(f"Error fetching from HF API: {e}")
            return self._get_fallback_models()
    
    def get_popular_models(self) -> List[Dict]:
        """Get popular text generation models"""
        return self.search_models("", "text-generation", 30)
    
    def get_models(self, task: str = "text-generation", limit: int = 50) -> List[Dict]:
        """Get models - main method for API compatibility"""
        return self.search_models("", task, limit)
    
    def get_code_models(self) -> List[Dict]:
        """Get code generation models"""
        return self.search_models("code", "text-generation", 20)
    
    def get_gptq_models(self) -> List[Dict]:
        """Get GPTQ quantized models"""
        return self.search_models("GPTQ", "text-generation", 20)
    
    def _format_models(self, models: List[Dict]) -> List[Dict]:
        """Format HF API response to our format"""
        formatted = []
        
        for model in models:
            model_id = model.get('id', '')
            model_name = model_id.split('/')[-1] if '/' in model_id else model_id
            
            # Extract size from model name
            size = "Unknown"
            if any(s in model_name.lower() for s in ['7b', '7-b']):
                size = "7B"
            elif any(s in model_name.lower() for s in ['13b', '13-b']):
                size = "13B"
            elif any(s in model_name.lower() for s in ['3b', '3-b']):
                size = "3B"
            elif any(s in model_name.lower() for s in ['1b', '1-b']):
                size = "1B"
            elif 'small' in model_name.lower():
                size = "Small"
            elif 'large' in model_name.lower():
                size = "Large"
            
            # Detect quantization
            quantization = None
            if 'gptq' in model_name.lower():
                quantization = 'GPTQ'
            elif 'awq' in model_name.lower():
                quantization = 'AWQ'
            elif 'gguf' in model_name.lower():
                quantization = 'GGUF'
            
            # Get tags for additional info
            tags = model.get('tags', [])
            pipeline_tag = model.get('pipeline_tag', 'text-generation')
            
            # Description
            description = f"{pipeline_tag.replace('-', ' ').title()} model"
            if quantization:
                description += f" with {quantization} quantization"
            
            formatted.append({
                'id': model_id,
                'name': model_name.replace('-', ' ').title(),
                'size': size,
                'type': pipeline_tag.replace('-', ' ').title(),
                'quantization': quantization,
                'description': description,
                'downloads': model.get('downloads', 0),
                'likes': model.get('likes', 0),
                'tags': tags[:5],  # First 5 tags only
                'updated': model.get('lastModified', ''),
                'author': model_id.split('/')[0] if '/' in model_id else 'Unknown'
            })
        
        return formatted
    
    def _get_fallback_models(self) -> List[Dict]:
        """Fallback models when API is not available"""
        return [
            {
                'id': 'TheBloke/starcoder2-7b-GPTQ',
                'name': 'StarCoder2 7B GPTQ',
                'size': '7B',
                'type': 'Code Generation',
                'quantization': 'GPTQ',
                'description': 'Code generation model with GPTQ quantization',
                'downloads': 50000,
                'likes': 100,
                'tags': ['code', 'gptq'],
                'updated': '2024-01-01',
                'author': 'TheBloke'
            },
            {
                'id': 'TheBloke/CodeLlama-7B-GPTQ',
                'name': 'Code Llama 7B GPTQ',
                'size': '7B',
                'type': 'Code Generation',
                'quantization': 'GPTQ',
                'description': 'Meta\'s code generation model with GPTQ quantization',
                'downloads': 75000,
                'likes': 150,
                'tags': ['code', 'llama', 'gptq'],
                'updated': '2024-01-01',
                'author': 'TheBloke'
            },
            {
                'id': 'microsoft/DialoGPT-small',
                'name': 'DialoGPT Small',
                'size': 'Small',
                'type': 'Conversational',
                'quantization': None,
                'description': 'Conversational AI model',
                'downloads': 100000,
                'likes': 200,
                'tags': ['conversational'],
                'updated': '2023-12-01',
                'author': 'Microsoft'
            }
        ]
    
    def get_model_by_id(self, model_id: str) -> Optional[Dict]:
        """Get specific model info by ID"""
        try:
            response = requests.get(
                f"{self.api_url}/models/{model_id}",
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                model = response.json()
                return self._format_models([model])[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error fetching model {model_id}: {e}")
            return None
    
    def generate_deployment_name(self, model_id: str) -> str:
        """Generate a deployment name from model ID"""
        name_part = model_id.split('/')[-1].lower()
        name_part = name_part.replace('-gptq', '').replace('-awq', '').replace('-gguf', '')
        name_part = ''.join(c if c.isalnum() else '-' for c in name_part)
        name_part = name_part.strip('-')
        return f"{name_part}-deploy"
