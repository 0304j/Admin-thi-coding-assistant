"""
Configuration and logging setup for the Model Manager API
"""

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_http_session():
    """
    Create a requests session with connection pooling and retry strategy.
    This prevents connection leaks and reduces memory usage.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# Ollama service URLs to try (in order of preference)
OLLAMA_URLS = [
    'http://ollama-service:11434',
    'http://ollama-service.model-hosting:11434',
    'http://ollama-service.model-hosting.svc.cluster.local:11434',
    'http://localhost:11434',
    'http://127.0.0.1:11434',
]

# Server configuration
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 8080
DEBUG_MODE = False
