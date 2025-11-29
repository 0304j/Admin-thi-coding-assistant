"""
vRAM estimation utilities for model deployment
"""


def estimate_model_vram(model_id: str) -> float:
    """
    Estimate vRAM requirements based on model size.
    
    Args:
        model_id: The model identifier (e.g., 'mistralai/Mistral-7B')
    
    Returns:
        Estimated vRAM requirement in GB
    """
    model_lower = model_id.lower()
    
    # Parameter-based estimation
    if '70b' in model_lower or '72b' in model_lower:
        return 14.0  # Large models need most of H100
    elif '34b' in model_lower or '32b' in model_lower:
        return 10.0  
    elif '13b' in model_lower or '14b' in model_lower:
        return 8.0
    elif '7b' in model_lower or '8b' in model_lower:
        return 6.0   
    elif '3b' in model_lower:
        return 3.5   
    elif '1.5b' in model_lower:
        return 2.0   
    elif '1b' in model_lower:
        return 1.5
    elif '560m' in model_lower or '350m' in model_lower:
        return 1.0
    elif '125m' in model_lower:
        return 0.5
    
    # Quantization reduces memory by ~50-75%
    if any(q in model_lower for q in ['gptq', 'awq', 'int4', '4bit']):
        base_estimate = 4.0  # Default for unknown quantized models
        return base_estimate * 0.6  # 40% of original size
    elif any(q in model_lower for q in ['int8', '8bit']):
        base_estimate = 4.0
        return base_estimate * 0.75  # 75% of original size
    
    # Default for unknown models
    return 4.0


def get_vram_recommendations(gpu_info: dict) -> list:
    """
    Generate deployment recommendations based on vRAM availability.
    
    Args:
        gpu_info: Dictionary containing GPU information
    
    Returns:
        List of recommendation strings
    """
    if not gpu_info.get('success'):
        return ["GPU not available"]
    
    available = gpu_info.get('available_vram_gb', 0)
    total = gpu_info.get('total_vram_gb', 0)
    
    recommendations = []
    
    if available >= 12:
        recommendations.append("Can deploy large models (7B-70B)")
    elif available >= 8:
        recommendations.append("Can deploy medium models (7B-13B)")
    elif available >= 4:
        recommendations.append("Can deploy small models (1B-7B)")
    elif available >= 2:
        recommendations.append("Can deploy quantized models only")
    else:
        recommendations.append("Insufficient vRAM for new deployments")
    
    if total > 0 and available < total * 0.2:
        recommendations.append("Consider stopping unused models to free vRAM")
    
    return recommendations
