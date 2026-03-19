MODELS = {
    # OpenAI
    "gpt-5.2": {
        "provider": "openai",
        "price_in": 1.75,   
        "price_out": 14.00,  
        "description": "modelo de vanguardia; mayor razonamiento y contexto grande"
    },

    "gpt-4o-mini": {
        "provider": "openai",
        "price_in": 0.15,   
        "price_out": 0.60,  
        "description": "rápido y económico; ideal para extracción"
    },

    "gpt-4o": {
        "provider": "openai",
        "price_in": 2.50,  
        "price_out": 10.00,  
        "description": "más calidad, mayor costo"
    },

    # Gemini
    "gemini-2.5-flash": {
        "provider": "gemini",
        "price_in": 0.30,
        "price_out": 2.50,
        "description": "Gemini 2.5 Flash (disponible en la API de Google)"
    },
    "gemini-3-flash-preview": {
        "provider": "gemini",
        "price_in": 0.50,
        "price_out": 3.00,
        "description": "Gemini 3 Flash Preview (inteligencia máxima, velocidad, búsqueda y grounding)"
    },
    "gemini-3.1-flash-lite-preview": {
        "provider": "gemini",
        "price_in": 0.25,
        "price_out": 1.50,
        "description": "Gemini 3 Flash Preview (inteligencia máxima, velocidad, búsqueda y grounding)"
    },
    "glm-5": {
        "provider": "glm",
        "price_in": 0.50,
        "price_out": 2.00,
        "description": "GLM-5 (Zhipu AI, fuerte en razonamiento y chino/inglés)"
    }

}

# Defaults por agente
DEFAULT_OLIVAR_MODEL = "gpt-5.2"

