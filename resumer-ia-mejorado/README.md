# 🚀 Resumer IA - Versión Mejorada

Aplicación web para resumir textos usando la API de OpenAI, construida con FastAPI.

## ✨ Mejoras implementadas

### 🔒 Seguridad
- ✅ Variables de entorno para API keys
- ✅ Validación de inputs con límites
- ✅ Rate limiting (5 requests/minuto)
- ✅ CORS configurado
- ✅ Manejo robusto de errores

### 🏗️ Arquitectura
- ✅ Código modularizado (routes, services, config)
- ✅ Templates Jinja2 separados
- ✅ Archivos estáticos organizados
- ✅ Logging estructurado
- ✅ Async/await correctamente implementado

### ✨ UX/UI
- ✅ Indicador de carga al procesar
- ✅ Contador de caracteres en tiempo real
- ✅ Modo oscuro con persistencia
- ✅ Diseño responsive
- ✅ Validación en frontend y backend
- ✅ Mensajes de error claros

### ⚡ Rendimiento
- ✅ Operaciones asíncronas
- ✅ Límite de tokens en respuestas
- ✅ Auto-resize del textarea
- ✅ Health check endpoint

## 📦 Instalación

### 1. Clonar y entrar al directorio
```bash
cd resumer-ia-mejorado
```

### 2. Crear entorno virtual
```bash
python -m venv venv

# Activar (Linux/Mac)
source venv/bin/activate

# Activar (Windows)
venv\Scripts\activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno
```bash
# Copiar el archivo de ejemplo
cp .env.example .env

# Editar .env y añadir tu API key de OpenAI
# OPENAI_API_KEY=sk-...
```

## 🚀 Uso

### Modo desarrollo
```bash
# Desde el directorio raíz
python -m uvicorn app.main:app --reload

# O usando el script directo
python app/main.py
```

La aplicación estará disponible en: http://localhost:8000

### Modo producción
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📁 Estructura del proyecto

```
resumer-ia-mejorado/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app principal
│   ├── config.py            # Configuración centralizada
│   ├── routes.py            # Endpoints y validación
│   ├── services/
│   │   ├── __init__.py
│   │   └── openai_service.py  # Lógica de OpenAI
│   ├── templates/
│   │   └── index.html       # Template Jinja2
│   └── static/
│       ├── css/
│       │   └── styles.css   # Estilos
│       └── js/
│           └── app.js       # JavaScript
├── .env.example             # Ejemplo de variables de entorno
├── .gitignore              # Archivos a ignorar en git
├── requirements.txt         # Dependencias Python
└── README.md               # Este archivo
```

## 🔧 Configuración

Puedes ajustar los siguientes parámetros en `.env`:

```bash
OPENAI_API_KEY=sk-...              # Tu API key (REQUERIDO)
MAX_TEXT_LENGTH=10000              # Máx. caracteres de entrada
MAX_INSTRUCTIONS_LENGTH=200        # Máx. caracteres de instrucciones
RATE_LIMIT_PER_MINUTE=5           # Requests permitidos por minuto
DEBUG=False                        # Modo debug (True/False)
```

## 🛠️ Endpoints

- `GET /` - Página principal
- `POST /resumir` - Generar resumen
- `GET /health` - Health check

## 📊 Logging

Los logs incluyen:
- Requests recibidos con IP origen
- Longitud de textos procesados
- Tokens consumidos por OpenAI
- Errores con stack traces completos

## 🔒 Seguridad

### IMPORTANTE: Antes de subir a GitHub

1. ✅ Asegúrate de que `.env` está en `.gitignore`
2. ✅ Nunca hagas commit de tu API key
3. ✅ Revisa el historial de git antes de hacer push

### Rate Limiting

Por defecto: 5 requests por minuto por IP.
Puedes ajustarlo en `RATE_LIMIT_PER_MINUTE` en `.env`.

## 🚀 Despliegue

### Render / Railway / Fly.io

1. Sube el código a GitHub
2. Conecta tu repositorio
3. Configura las variables de entorno
4. Deploy automático

### Docker (opcional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 📝 Notas

- La versión de OpenAI debe ser >= 1.0.0 para usar `AsyncOpenAI`
- El rate limiting usa la IP del cliente (considera usar autenticación en producción)
- Los archivos estáticos se sirven desde `/static`

## 🐛 Troubleshooting

### Error: "OPENAI_API_KEY no está configurada"
- Verifica que el archivo `.env` existe
- Asegúrate de que `OPENAI_API_KEY` está definida en `.env`

### Error: "Module not found"
- Ejecuta desde el directorio raíz: `python -m uvicorn app.main:app`
- Verifica que las dependencias están instaladas: `pip install -r requirements.txt`

### Error: 429 (Rate limit de OpenAI)
- Has excedido tu cuota de OpenAI
- Verifica tu plan en https://platform.openai.com/

## 📄 Licencia

MIT License - Úsalo libremente para tus proyectos.

---

**¿Preguntas?** Abre un issue en GitHub o revisa la [documentación de FastAPI](https://fastapi.tiangolo.com/).
