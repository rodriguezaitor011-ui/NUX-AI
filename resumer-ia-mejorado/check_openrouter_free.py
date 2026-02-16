import requests
import json

def get_openrouter_models():
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": "Bearer TU_API_KEY_AQUI", # Sustituye por tu API Key
        "HTTP-Referer": "http://localhost:3000", # Requerido por OpenRouter
        "X-Title": "StudIA_Project"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = data.get('data', [])
        
        print(f"{'MODEL ID':<50} | {'CONTEXT':<10} | {'PRECIO (IN/OUT)'}")
        print("-" * 85)
        
        free_models = []
        for model in models:
            pricing = model.get('pricing', {})
            # Verificamos si es gratis (precio 0)
            if float(pricing.get('prompt', 0)) == 0 and float(pricing.get('completion', 0)) == 0:
                model_id = model.get('id')
                context = model.get('context_length')
                p_in = pricing.get('prompt')
                p_out = pricing.get('completion')
                
                print(f"{model_id:<50} | {context:<10} | FREE")
                free_models.append(model)
        
        print("-" * 85)
        print(f"Total de modelos gratuitos encontrados: {len(free_models)}")

    except Exception as e:
        print(f"Error al conectar con OpenRouter: {e}")

if __name__ == "__main__":
    get_openrouter_models()