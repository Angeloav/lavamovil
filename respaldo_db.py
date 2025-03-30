import os
import shutil
from datetime import datetime

def crear_respaldo():
    carpeta = "respaldos"
    os.makedirs(carpeta, exist_ok=True)
    
    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_respaldo = f"{carpeta}/respaldo_lavamovil_{fecha}.db"
    
    if os.path.exists("lavamovil.db"):
        shutil.copy("lavamovil.db", nombre_respaldo)
        print(f"✅ Respaldo guardado como: {nombre_respaldo}")
    else:
        print("⚠️ Archivo lavamovil.db no encontrado para respaldo.")
