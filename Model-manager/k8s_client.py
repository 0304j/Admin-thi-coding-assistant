"""
Kubernetes client wrapper for model management
"""
import logging
from typing import List, Dict, Optional, Tuple
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)

class KubernetesClient:
    def __init__(self, namespace: str = "default"):
        """Initialize Kubernetes client"""
        self.namespace = namespace
        self.connected = False
        
        try:
            # Try in-cluster config first, then fallback to local config
            try:
                config.load_incluster_config()
                logger.info("Using in-cluster Kubernetes configuration")
            except Exception:
                config.load_kube_config()
                logger.info("Using local Kubernetes configuration")
            
            self.apps_v1 = client.AppsV1Api()
            self.core_v1 = client.CoreV1Api()
            self.connected = True
            logger.info(f"Connected to Kubernetes cluster, using namespace: {self.namespace}")
        except Exception as e:
            logger.error(f"Failed to connect to Kubernetes: {e}")
            # Don't raise exception, allow app to start without k8s connection
            self.apps_v1 = None
            self.core_v1 = None
    
    def ensure_namespace(self) -> None:
        """Ensure the namespace exists"""
        try:
            self.core_v1.read_namespace(name=self.namespace)
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Creating namespace: {self.namespace}")
                namespace = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=self.namespace)
                )
                self.core_v1.create_namespace(body=namespace)
            else:
                raise
    
    def list_deployments(self) -> List[Dict]:
        """List all model deployments"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=self.namespace)
            result = []
            
            for deployment in deployments.items:
                if deployment.metadata.name == "model-dashboard":
                    continue
                
                # Extract model info
                model_id = "Unknown"
                containers = deployment.spec.template.spec.containers
                if containers and containers[0].env:
                    for env in containers[0].env:
                        if env.name == "MODEL_ID":
                            model_id = env.value
                            break
                
                # Get status
                ready_replicas = deployment.status.ready_replicas or 0
                desired_replicas = deployment.spec.replicas or 0
                
                result.append({
                    'name': deployment.metadata.name,
                    'model_id': model_id,
                    'ready_replicas': ready_replicas,
                    'desired_replicas': desired_replicas,
                    'status': 'Running' if ready_replicas > 0 else 'Pending'
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to list deployments: {e}")
            return []
    
    def deploy_model(self, model_id: str, deployment_name: str, memory: str = "8Gi") -> bool:
        """Deploy a model"""
        try:
            self.ensure_namespace()
            
            # Check if deployment already exists
            try:
                self.apps_v1.read_namespaced_deployment(
                    name=deployment_name, namespace=self.namespace
                )
                logger.error(f"Deployment '{deployment_name}' already exists")
                return False
            except ApiException as e:
                if e.status != 404:
                    raise
            
            # Create deployment
            deployment = self._create_deployment_spec(model_id, deployment_name, memory)
            self.apps_v1.create_namespaced_deployment(
                namespace=self.namespace, body=deployment
            )
            
            # Create service
            service = self._create_service_spec(deployment_name)
            self.core_v1.create_namespaced_service(
                namespace=self.namespace, body=service
            )
            
            logger.info(f"Successfully deployed {deployment_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deploy model: {e}")
            return False
    
    def delete_deployment(self, deployment_name: str) -> bool:
        """Delete a deployment and its service"""
        try:
            # Delete deployment
            self.apps_v1.delete_namespaced_deployment(
                name=deployment_name, namespace=self.namespace
            )
            
            # Delete service
            try:
                self.core_v1.delete_namespaced_service(
                    name=f"{deployment_name}-service", namespace=self.namespace
                )
            except ApiException:
                pass  # Service might not exist
            
            logger.info(f"Successfully deleted {deployment_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete deployment: {e}")
            return False
    
    def _create_deployment_spec(self, model_id: str, name: str, memory: str):
        """Create deployment specification"""
        # Environment variables
        env_vars = [
            client.V1EnvVar(name="MODEL_ID", value=model_id),
            client.V1EnvVar(name="PORT", value="80"),
            client.V1EnvVar(name="TRUST_REMOTE_CODE", value="true"),
            client.V1EnvVar(name="MAX_CONCURRENT_REQUESTS", value="64"),
            client.V1EnvVar(name="MAX_INPUT_LENGTH", value="4096"),
            client.V1EnvVar(name="MAX_TOTAL_TOKENS", value="8192"),
        ]
        
        # Add quantization if needed
        if 'gptq' in model_id.lower():
            env_vars.append(client.V1EnvVar(name="QUANTIZE", value="gptq"))
        elif 'awq' in model_id.lower():
            env_vars.append(client.V1EnvVar(name="QUANTIZE", value="awq"))
        
        # Add HF token if secret exists
        try:
            self.core_v1.read_namespaced_secret(
                name="huggingface-token", namespace=self.namespace
            )
            env_vars.append(client.V1EnvVar(
                name="HUGGING_FACE_HUB_TOKEN",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="huggingface-token",
                        key="token"
                    )
                )
            ))
        except ApiException:
            pass
        
        # Container spec
        container = client.V1Container(
            name="tgi-server",
            image="ghcr.io/huggingface/text-generation-inference:latest",
            ports=[client.V1ContainerPort(container_port=80)],
            env=env_vars,
            resources=client.V1ResourceRequirements(
                requests={"nvidia.com/gpu": "1", "memory": memory},
                limits={"nvidia.com/gpu": "1", "memory": memory}
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health", port=80),
                initial_delay_seconds=120,
                period_seconds=15
            )
        )
        
        # Deployment spec
        return client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self.namespace,
                labels={"managed-by": "model-manager", "model": model_id.replace("/", "-")}
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": name}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": name}),
                    spec=client.V1PodSpec(containers=[container])
                )
            )
        )
    
    def _create_service_spec(self, name: str):
        """Create service specification"""
        return client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=f"{name}-service",
                namespace=self.namespace,
                labels={"managed-by": "model-manager"}
            ),
            spec=client.V1ServiceSpec(
                selector={"app": name},
                ports=[client.V1ServicePort(port=80, target_port=80, name="http")],
                type="ClusterIP"
            )
        )

    def check_gpu_vram_availability(self) -> Dict:
        """Check GPU vRAM availability across all deployments"""
        try:
            # First, try to detect actual GPU from node capacity
            total_vram_gb = self._get_gpu_total_vram()
            
            # Get all deployments that use GPUs
            gpu_deployments = []
            all_deployments = self.apps_v1.list_deployment_for_all_namespaces()
            
            total_allocated_vram = 0.0
            
            for deployment in all_deployments.items:
                # Check if deployment uses GPU
                containers = deployment.spec.template.spec.containers
                if containers:
                    container = containers[0]
                    if (container.resources and 
                        container.resources.limits and 
                        container.resources.limits.get('nvidia.com/gpu', '0') != '0'):
                        
                        # For Ollama, assume it uses full available VRAM
                        if deployment.metadata.name == 'ollama':
                            allocated_vram = total_vram_gb
                        else:
                            # Extract allocated vRAM from labels if available
                            allocated_vram = 0.0
                            if (deployment.metadata.labels and 
                                'allocated-vram-gb' in deployment.metadata.labels):
                                try:
                                    allocated_vram = float(deployment.metadata.labels['allocated-vram-gb'])
                                except (ValueError, TypeError):
                                    allocated_vram = 8.0  # Default assumption
                            else:
                                # Estimate based on memory limits
                                memory_limit = container.resources.limits.get('memory', '8Gi')
                                if 'Gi' in memory_limit:
                                    allocated_vram = float(memory_limit.replace('Gi', '')) / 2
                                else:
                                    allocated_vram = 8.0  # Default
                        
                        # Only count running deployments
                        ready_replicas = deployment.status.ready_replicas or 0
                        if ready_replicas > 0:
                            total_allocated_vram += allocated_vram
                        
                        gpu_deployments.append({
                            'name': deployment.metadata.name,
                            'namespace': deployment.metadata.namespace,
                            'allocated_vram_gb': allocated_vram,
                            'ready_replicas': ready_replicas,
                            'desired_replicas': deployment.spec.replicas or 0
                        })
            
            available_vram_gb = max(0, total_vram_gb - total_allocated_vram)
            
            return {
                'success': True,
                'total_vram_gb': total_vram_gb,
                'allocated_vram_gb': total_allocated_vram,
                'available_vram_gb': available_vram_gb,
                'gpu_deployments': gpu_deployments,
                'gpu_count': 1,
                'utilization_percent': round((total_allocated_vram / total_vram_gb) * 100, 1) if total_vram_gb > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to check GPU vRAM availability: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_vram_gb': 0,
                'allocated_vram_gb': 0,
                'available_vram_gb': 0,
                'gpu_count': 0
            }
    
    def _get_gpu_total_vram(self) -> float:
        """Detect total GPU vRAM from node capacity"""
        try:
            nodes = self.core_v1.list_node()
            for node in nodes.items:
                # Check node capacity for nvidia.com/gpu
                if node.status.capacity and 'nvidia.com/gpu' in node.status.capacity:
                    gpu_count = int(node.status.capacity.get('nvidia.com/gpu', 0))
                    if gpu_count > 0:
                        # Try to detect from node labels or use defaults
                        labels = node.metadata.labels or {}
                        
                        # Common NVIDIA GPU labels
                        if 'nvidia.com/gpu' in labels:
                            gpu_model = labels.get('nvidia.com/gpu')
                            # Map GPU models to VRAM
                            gpu_vram_map = {
                                'H100': 80,
                                'H100L-23C': 23,
                                'H100L-15C': 15.36,
                                'A100': 40,
                                'A10': 24,
                                'V100': 16,
                                'T4': 16,
                                'RTX-A6000': 48
                            }
                            for gpu_type, vram in gpu_vram_map.items():
                                if gpu_type.lower() in gpu_model.lower():
                                    logger.info(f"Detected GPU: {gpu_model} with {vram}GB VRAM")
                                    return vram * gpu_count
                        
                        # Default to 23GB for H100L (most common in this setup)
                        logger.info(f"Detected {gpu_count} GPU(s), using default 23GB per GPU")
                        return 23.0 * gpu_count
            
            # Fallback to 23GB (H100L-23C)
            logger.warning("Could not detect GPU from nodes, using default 23GB")
            return 23.0
        except Exception as e:
            logger.error(f"Failed to detect GPU VRAM: {e}")
            return 23.0  # Default fallback

    def deploy_model_with_vram(self, model_id: str, deployment_name: str, 
                               memory_gb: float, memory_fraction: float, 
                               estimated_vram: float) -> Dict:
        """Deploy a model with vRAM management"""
        try:
            self.ensure_namespace()
            
            # Check if deployment already exists
            try:
                self.apps_v1.read_namespaced_deployment(
                    name=deployment_name, namespace=self.namespace
                )
                logger.error(f"Deployment '{deployment_name}' already exists")
                return {'success': False, 'error': f"Deployment '{deployment_name}' already exists"}
            except ApiException as e:
                if e.status != 404:
                    raise
            
            # Create deployment with vRAM management
            deployment = self._create_vram_deployment_spec(
                model_id, deployment_name, memory_gb, memory_fraction, estimated_vram
            )
            self.apps_v1.create_namespaced_deployment(
                namespace=self.namespace, body=deployment
            )
            
            # Create service
            service = self._create_service_spec(deployment_name)
            self.core_v1.create_namespaced_service(
                namespace=self.namespace, body=service
            )
            
            logger.info(f"Successfully deployed {deployment_name} with {memory_gb}GB vRAM allocation")
            return {'success': True, 'message': f"Deployed {deployment_name} successfully"}
            
        except Exception as e:
            logger.error(f"Failed to deploy model with vRAM: {e}")
            return {'success': False, 'error': str(e)}

    def _create_vram_deployment_spec(self, model_id: str, name: str, 
                                     memory_gb: float, memory_fraction: float, 
                                     estimated_vram: float):
        """Create deployment specification with vRAM management"""
        
        # Calculate token limits based on available memory
        max_batch_tokens = int(memory_gb * 800)  # ~800 tokens per GB
        max_input_length = min(int(memory_gb * 400), 4096)  # Conservative input length
        max_total_tokens = max_batch_tokens + max_input_length
        max_concurrent_requests = max(1, int(memory_gb / 2))
        
        # Environment variables with vRAM management
        env_vars = [
            client.V1EnvVar(name="MODEL_ID", value=model_id),
            client.V1EnvVar(name="PORT", value="80"),
            client.V1EnvVar(name="TRUST_REMOTE_CODE", value="true"),
            client.V1EnvVar(name="CUDA_MEM_FRACTION", value=str(memory_fraction)),
            client.V1EnvVar(name="MAX_BATCH_TOTAL_TOKENS", value=str(max_batch_tokens)),
            client.V1EnvVar(name="MAX_INPUT_LENGTH", value=str(max_input_length)),
            client.V1EnvVar(name="MAX_TOTAL_TOKENS", value=str(max_total_tokens)),
            client.V1EnvVar(name="MAX_CONCURRENT_REQUESTS", value=str(max_concurrent_requests)),
            client.V1EnvVar(name="CUDA_VISIBLE_DEVICES", value="0"),
        ]
        
        # Add quantization if needed
        if 'gptq' in model_id.lower():
            env_vars.append(client.V1EnvVar(name="QUANTIZE", value="gptq"))
        elif 'awq' in model_id.lower():
            env_vars.append(client.V1EnvVar(name="QUANTIZE", value="awq"))
        
        # Add HF token if secret exists
        try:
            self.core_v1.read_namespaced_secret(
                name="huggingface-token", namespace=self.namespace
            )
            env_vars.append(client.V1EnvVar(
                name="HUGGING_FACE_HUB_TOKEN",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="huggingface-token",
                        key="token"
                    )
                )
            ))
        except ApiException:
            pass
        
        # Container spec with vRAM-based resource limits
        container = client.V1Container(
            name="tgi-server",
            image="ghcr.io/huggingface/text-generation-inference:latest",
            ports=[client.V1ContainerPort(container_port=80)],
            env=env_vars,
            resources=client.V1ResourceRequirements(
                requests={
                    "nvidia.com/gpu": "1", 
                    "memory": f"{int(memory_gb * 2)}Gi"
                },
                limits={
                    "nvidia.com/gpu": "1", 
                    "memory": f"{int(memory_gb * 3)}Gi"
                }
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health", port=80),
                initial_delay_seconds=120,
                period_seconds=15,
                timeout_seconds=10
            ),
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health", port=80),
                initial_delay_seconds=300,
                period_seconds=60,
                timeout_seconds=10
            )
        )
        
        # Deployment spec with vRAM tracking labels
        return client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self.namespace,
                labels={
                    "managed-by": "model-manager",
                    "model": model_id.replace("/", "-"),
                    "allocated-vram-gb": str(memory_gb),
                    "estimated-vram-gb": str(estimated_vram)
                }
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": name}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={
                            "app": name,
                            "allocated-vram-gb": str(memory_gb)
                        }
                    ),
                    spec=client.V1PodSpec(containers=[container])
                )
            )
        )
