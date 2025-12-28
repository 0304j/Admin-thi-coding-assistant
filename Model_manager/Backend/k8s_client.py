"""
Kubernetes client for GPU monitoring
"""
import logging
from typing import Dict
from kubernetes import client, config

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(self, namespace: str = "model-hosting"):
        self.namespace = namespace
        self.connected = False
        
        try:
            try:
                config.load_incluster_config()
                logger.info("Using in-cluster config")
            except Exception:
                config.load_kube_config()
                logger.info("Using local kubeconfig")
            
            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.connected = True
            logger.info(f"Connected to Kubernetes, namespace: {self.namespace}")
        except Exception as e:
            logger.error(f"Kubernetes connection failed: {e}")
            self.core_v1 = None
            self.apps_v1 = None

    def check_gpu_vram_availability(self) -> Dict:
        """Check GPU vRAM availability"""
        try:
            total_vram_gb = self._get_gpu_total_vram()
            allocated_vram = self._get_allocated_vram()
            available_vram = max(0, total_vram_gb - allocated_vram)
            utilization = round((allocated_vram / total_vram_gb) * 100, 1) if total_vram_gb > 0 else 0
            
            return {
                'success': True,
                'total_vram_gb': total_vram_gb,
                'allocated_vram_gb': allocated_vram,
                'available_vram_gb': available_vram,
                'gpu_count': 1,
                'utilization_percent': utilization
            }
        except Exception as e:
            logger.error(f"GPU check failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_vram_gb': 0,
                'allocated_vram_gb': 0,
                'available_vram_gb': 0,
                'gpu_count': 0
            }

    def _get_gpu_total_vram(self) -> float:
        """Detect total GPU vRAM from node"""
        try:
            nodes = self.core_v1.list_node()
            for node in nodes.items:
                if node.status.capacity and 'nvidia.com/gpu' in node.status.capacity:
                    gpu_count = int(node.status.capacity.get('nvidia.com/gpu', 0))
                    if gpu_count > 0:
                        labels = node.metadata.labels or {}
                        gpu_model = labels.get('nvidia.com/gpu.product', '')
                        
                        # Map GPU models to VRAM (ordered: most specific first)
                        # Use list of tuples to maintain order - check specific models before generic ones
                        gpu_vram_patterns = [
                            ('H100L-23C', 23),      # Time-sliced H100 23GB (check before H100)
                            ('H100L-15C', 15.36),   # Time-sliced H100 15GB (check before H100)
                            ('H100', 80),           # Full H100
                            ('A100', 40),
                            ('A10', 24),
                            ('V100', 16),
                            ('T4', 16),
                            ('RTX-A6000', 48),
                        ]
                        
                        for gpu_type, vram in gpu_vram_patterns:
                            if gpu_type.lower() in gpu_model.lower():
                                logger.info(f"Detected GPU: {gpu_model} with {vram}GB")
                                return vram
                        
                        # Default for time-sliced H100L
                        logger.info(f"Detected {gpu_count} virtual GPU(s), using 23GB total")
                        return 23.0
            
            logger.warning("No GPU detected, using default 23GB")
            return 23.0
        except Exception as e:
            logger.error(f"GPU detection failed: {e}")
            return 23.0

    def _get_allocated_vram(self) -> float:
        """Get vRAM allocated by Ollama deployment"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(self.namespace)
            for dep in deployments.items:
                if dep.metadata.name == 'ollama':
                    ready = dep.status.ready_replicas or 0
                    if ready > 0:
                        # Ollama uses full GPU when running
                        return self._get_gpu_total_vram()
            return 0.0
        except Exception as e:
            logger.error(f"Allocation check failed: {e}")
            return 0.0
