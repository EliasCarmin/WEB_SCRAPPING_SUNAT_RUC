# WEB_SCRAPPING_SUNAT_RUC

API REST para consultar información de RUCs en SUNAT usando web scraping con Selenium.

## Despliegue en Cloud Run

### Prerrequisitos

- Cuenta de Google Cloud Platform
- Google Cloud SDK instalado
- Docker (opcional, para pruebas locales)

### Pasos para desplegar

1. **Autenticarse en Google Cloud:**

```bash
gcloud auth login
gcloud config set project TU_PROJECT_ID
```

2. **Habilitar APIs necesarias:**

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

3. **Construir y desplegar:**

```bash
gcloud builds submit --tag gcr.io/TU_PROJECT_ID/consulta-ruc-sunat
gcloud run deploy consulta-ruc-sunat \
  --image gcr.io/TU_PROJECT_ID/consulta-ruc-sunat \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300
```

### Configuración recomendada

- **Memoria:** 2GB mínimo (Selenium requiere recursos)
- **Timeout:** 300 segundos (las consultas pueden tardar)
- **CPU:** 1-2 vCPUs
- **Concurrencia:** 1-5 (depende del uso)

## Obtener la URL de tu servicio

Después de desplegar, obtén la URL con:

```bash
gcloud run services describe consulta-ruc-sunat --region us-central1 --format 'value(status.url)'
```

O búscala en la consola de Google Cloud.

## Uso de la API

### Endpoints disponibles

- `GET /` - Información de la API
- `GET /health` - Health check
- `POST /consulta-ruc` - Consultar un RUC individual
- `GET /docs` - Documentación interactiva (Swagger UI)

### Ejemplos de uso

#### Consultar un RUC desde terminal:

```bash
curl -X POST "https://TU_URL/consulta-ruc" \
  -H "Content-Type: application/json" \
  -d '{"ruc": "10754034420"}'
```

## Estructura del proyecto

```
.
├── main.py              # Código principal de la API
├── requirements.txt     # Dependencias Python
├── Dockerfile          # Configuración del contenedor
├── .dockerignore       # Archivos a ignorar en el build
└── README.md           # Este archivo
```

## Notas importantes

- La API usa Chrome en modo headless para el web scraping
- Las consultas pueden tardar varios segundos por RUC
- El servicio está optimizado para Cloud Run pero puede ejecutarse localmente con Docker
