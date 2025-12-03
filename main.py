from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import pandas as pd
import time
from typing import Optional, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import traceback
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API de Consulta RUC SUNAT",
    description="API para consultar información de RUCs en SUNAT usando web scraping",
    version="1.0.0"
)

# Configurar CORS para permitir peticiones desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los headers
)

def config_driver():
    """Configura el WebDriver de Chrome para Cloud Run (modo headless).
    
    Optimizado para ejecutarse en contenedores sin interfaz gráfica.
    """
    chrome_options = ChromeOptions()
    
    # Opciones esenciales para Cloud Run
    chrome_options.add_argument('--headless=new')  # Usar nuevo modo headless
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--single-process')  # Importante para Cloud Run
    chrome_options.add_argument('--remote-debugging-port=9222')
    
    # User-Agent realista para evitar bloqueos
    user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    chrome_options.add_argument(f'user-agent={user_agent}')
    
    # Headers adicionales para parecer un navegador real
    chrome_options.add_argument('--accept-language=es-PE,es;q=0.9,en;q=0.8')
    chrome_options.add_argument('--accept-encoding=gzip, deflate, br')
    
    # Configuraciones experimentales
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option("detach", True)
    
    # Preferencias para mejorar compatibilidad y seguridad
    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2
        },
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    try:
        # Intentar usar Chrome desde la ubicación estándar
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome WebDriver iniciado correctamente")
        
        # Ejecutar script para ocultar que es WebDriver
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": user_agent
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    except WebDriverException as e:
        logger.error(f"Error al iniciar Chrome WebDriver: {e}")
        logger.error(traceback.format_exc())
        # Intentar con ruta explícita de Chrome
        try:
            chrome_options.binary_location = "/usr/bin/google-chrome"
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("Chrome WebDriver iniciado con ruta explícita")
            
            # Ejecutar script para ocultar que es WebDriver
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
        except Exception as e2:
            logger.error(f"Error al iniciar Chrome con ruta explícita: {e2}")
            logger.error(traceback.format_exc())
            raise
    
    wait = WebDriverWait(driver, 20)  # Aumentar timeout a 20 segundos
    return driver, wait

def consultar_ruc_sunat(ruc: str) -> Optional[Dict]:
    """Consulta un único RUC en SUNAT y devuelve un diccionario con los datos.

    Args:
        ruc: Número de RUC a consultar (11 dígitos)

    Returns:
        Dict con los datos del RUC, o None si no se pudo obtener información.
        
    Ejemplo:
        datos = consultar_ruc_sunat("20606333227")
    """
    driver, wait = config_driver()
    try:
        logger.info(f"Intentando acceder a SUNAT para RUC: {ruc}")
        
        # Intentar cargar la página con retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver.get('https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp')
                logger.info(f"Página cargada exitosamente (intento {attempt + 1})")
                break
            except WebDriverException as e:
                if "ERR_CONNECTION_RESET" in str(e) or "ERR_CONNECTION_REFUSED" in str(e):
                    logger.warning(f"Intento {attempt + 1}/{max_retries} falló: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Backoff exponencial: 1s, 2s, 4s
                        continue
                raise
        
        # Pequeña pausa para que la página cargue completamente
        time.sleep(2)
        input_ruc = driver.find_element(By.XPATH, "//input[@placeholder='Ingrese RUC']")
        btn_buscar = driver.find_element(By.ID, 'btnAceptar')

        input_ruc.clear()
        input_ruc.send_keys(ruc)
        btn_buscar.click()

        # Esperar bloque de resultado
        wait.until(EC.visibility_of_element_located(
            (By.XPATH, "//h4[contains(text(), 'Número de RUC:')]")
        ))

        # Número de RUC y nombre
        ruc_text_el = driver.find_element(
            By.XPATH,
            "//div[contains(@class, 'list-group-item')]/div/div[h4[contains(text(), 'Número de RUC:')]]/following-sibling::div/h4"
        )
        numero_ruc, nombre = ruc_text_el.text.split(' - ', 1)
        detalle = {
            'Número de RUC': numero_ruc.strip(),
            'Nombre': nombre.strip()
        }

        # Otros campos
        mapeo = {
            "Nombre Comercial": "//h4[contains(text(), 'Nombre Comercial')]/../following-sibling::div/p",
            "Tipo Contribuyente": "//h4[contains(text(), 'Tipo Contribuyente')]/../following-sibling::div/p",
            "Estado del Contribuyente": "//h4[contains(text(), 'Estado del Contribuyente')]/../following-sibling::div/p",
            "Condición del Contribuyente": "//h4[contains(text(), 'Condición del Contribuyente')]/../following-sibling::div/p",
            "Domicilio Fiscal": "//h4[contains(text(), 'Domicilio Fiscal')]/../following-sibling::div/p",
        }
        for campo, xpath in mapeo.items():
            try:
                detalle[campo] = wait.until(
                    EC.visibility_of_element_located((By.XPATH, xpath))
                ).text.strip()
            except (TimeoutException, NoSuchElementException):
                detalle[campo] = None

        # Actividades económicas (todas las filas)
        try:
            actividades_rows = driver.find_elements(
                By.XPATH,
                "//h4[contains(text(), 'Actividad(es) Económica(s)')]/../following-sibling::div//table//tr"
            )
            actividades_list = []
            for row in actividades_rows:
                celdas = row.find_elements(By.TAG_NAME, "td")
                if len(celdas) > 0:
                    actividad = " - ".join([celda.text.strip() for celda in celdas if celda.text.strip()])
                    if actividad:
                        actividades_list.append(actividad)
            detalle["Actividades Economicas"] = "; ".join(actividades_list) if actividades_list else None
        except (TimeoutException, NoSuchElementException):
            detalle["Actividades Economicas"] = None

        return detalle
    except Exception as e:
        error_msg = f"Error en consulta RUC {ruc}: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        print(f"❌ {error_msg}")
        print(f"Traceback: {error_trace}")
        return None
    finally:
        try:
            driver.quit()
        except Exception as e:
            logger.warning(f"Error al cerrar driver: {e}")

# Modelos Pydantic para la API
class ConsultaRUCRequest(BaseModel):
    ruc: str

class ConsultaMultipleRUCRequest(BaseModel):
    rucs: List[str]
    guardar_excel: bool = False

# Endpoints de la API
@app.get("/")
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "message": "API de Consulta RUC SUNAT",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check",
            "/consulta-ruc": "Consultar un RUC individual (POST)",
            "/consulta-multiple": "Consultar múltiples RUCs (POST)",
            "/docs": "Documentación interactiva (Swagger UI)"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint para Cloud Run."""
    return {"status": "healthy", "service": "consulta-ruc-sunat"}

@app.get("/test-chrome")
async def test_chrome():
    """Endpoint de diagnóstico para verificar que Chrome funciona correctamente."""
    try:
        logger.info("Iniciando test de Chrome...")
        driver, wait = config_driver()
        
        try:
            # Intentar navegar a una página simple
            logger.info("Navegando a Google...")
            driver.get("https://www.google.com")
            title = driver.title
            logger.info(f"Título de la página: {title}")
            
            # Intentar navegar a SUNAT
            logger.info("Navegando a SUNAT...")
            driver.get('https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp')
            sunat_title = driver.title
            logger.info(f"Título de SUNAT: {sunat_title}")
            
            # Verificar que existan los elementos necesarios
            input_ruc = driver.find_element(By.XPATH, "//input[@placeholder='Ingrese RUC']")
            btn_buscar = driver.find_element(By.ID, 'btnAceptar')
            
            return {
                "status": "success",
                "chrome_working": True,
                "google_title": title,
                "sunat_title": sunat_title,
                "sunat_input_found": input_ruc is not None,
                "sunat_button_found": btn_buscar is not None,
                "message": "Chrome está funcionando correctamente"
            }
        finally:
            driver.quit()
            
    except WebDriverException as e:
        error_msg = f"Error de WebDriver: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "chrome_working": False,
            "error": error_msg,
            "error_type": "WebDriverException",
            "message": "Chrome no pudo iniciarse o navegar correctamente"
        }
    except Exception as e:
        error_msg = f"Error general: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "chrome_working": False,
            "error": error_msg,
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }

@app.post("/consulta-ruc")
async def consultar_ruc_endpoint(request: ConsultaRUCRequest):
    """
    Consulta un único RUC en SUNAT.
    
    Args:
        request: Objeto con el RUC a consultar
        
    Returns:
        Diccionario con los datos del RUC consultado
    """
    try:
        logger.info(f"Iniciando consulta para RUC: {request.ruc}")
        resultado = consultar_ruc_sunat(ruc=request.ruc)
        
        if resultado is None:
            logger.warning(f"No se pudo obtener información para RUC {request.ruc}")
            raise HTTPException(
                status_code=404,
                detail=f"No se pudo obtener información para el RUC {request.ruc}. Verifica que el RUC sea válido y que el servicio de SUNAT esté disponible."
            )
        
        logger.info(f"Consulta exitosa para RUC: {request.ruc}")
        return JSONResponse(content=resultado)
    except HTTPException:
        raise
    except Exception as e:
        error_detail = f"Error al consultar RUC {request.ruc}: {str(e)}"
        logger.error(error_detail)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1",port='5000')