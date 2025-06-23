from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Optional, List
import os
import asyncio
from enum import Enum

app = FastAPI(title="SmartWater System", description="Sistema inteligente de llenado de agua")

# Configuración CORS para la app móvil
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["water_system"]
status_collection = db["status"]
alerts_collection = db["alerts"]
logs_collection = db["logs"]
settings_collection = db["settings"]

# Enums y modelos
class TankLevel(str, Enum):
    EMPTY = "empty"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FULL = "full"

class AlertType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class SystemStatus(BaseModel):
    tinaco_level: TankLevel
    cisterna_level: TankLevel
    bomba_active: bool
    bomba_runtime: int = Field(default=0, description="Tiempo en minutos que lleva funcionando la bomba")
    water_flow_rate: float = Field(default=0.0, description="Litros por minuto")
    power_consumption: float = Field(default=0.0, description="Consumo en watts")
    temperature: Optional[float] = Field(default=None, description="Temperatura del agua")
    timestamp: datetime = Field(default_factory=datetime.now)

class Alert(BaseModel):
    message: str
    alert_type: AlertType
    component: str = Field(description="Componente que generó la alerta (bomba, tinaco, cisterna, sistema)")
    timestamp: datetime = Field(default_factory=datetime.now)
    resolved: bool = Field(default=False)

class SystemSettings(BaseModel):
    auto_mode: bool = Field(default=True)
    fill_start_level: TankLevel = Field(default=TankLevel.LOW)
    fill_stop_level: TankLevel = Field(default=TankLevel.FULL)
    max_pump_runtime: int = Field(default=60, description="Tiempo máximo de funcionamiento en minutos")
    energy_saving_mode: bool = Field(default=False)
    preferred_fill_hours: List[int] = Field(default=[22, 23, 0, 1, 2, 3, 4, 5], description="Horas preferidas para llenar (tarifa nocturna)")
    notification_enabled: bool = Field(default=True)

class WaterUsageLog(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    action: str = Field(description="fill_start, fill_complete, alert_generated, etc.")
    tinaco_level_before: TankLevel
    tinaco_level_after: TankLevel
    duration_minutes: Optional[int] = None
    water_amount_liters: Optional[float] = None

# Variables globales para simulación
current_status = SystemStatus(
    tinaco_level=TankLevel.MEDIUM,
    cisterna_level=TankLevel.HIGH,
    bomba_active=False
)

system_settings = SystemSettings()

@app.get("/")
def root():
    return {
        "message": "SmartWater System - Sistema de llenado automático activo",
        "version": "2.0",
        "features": ["Monitoreo automático", "Alertas inteligentes", "Optimización energética", "Registro de uso"]
    }

@app.get("/status")
def get_current_status():
    """Obtiene el estado actual del sistema"""
    try:
        # Buscar el estado más reciente
        latest_status = status_collection.find_one(sort=[("timestamp", -1)])
        if latest_status:
            latest_status["_id"] = str(latest_status["_id"])
            return latest_status
        else:
            # Si no hay registros, devolver estado por defecto
            return current_status.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")

@app.post("/status/update")
def update_status(status: SystemStatus):
    """Actualiza el estado del sistema (usado por sensores IoT)"""
    try:
        # Insertar nuevo estado
        result = status_collection.insert_one(status.dict())
        
        # Aplicar lógica de control automático
        if system_settings.auto_mode:
            control_decision = _apply_automatic_control(status)
            if control_decision:
                create_log("automatic_control", status.tinaco_level, status.tinaco_level, 
                          action_description=control_decision)
        
        # Verificar si necesita generar alertas
        _check_and_generate_alerts(status)
        
        return {"inserted_id": str(result.inserted_id), "auto_control_applied": system_settings.auto_mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar estado: {str(e)}")

@app.get("/settings")
def get_settings():
    """Obtiene la configuración del sistema"""
    try:
        settings = settings_collection.find_one()
        if settings:
            settings["_id"] = str(settings["_id"])
            return settings
        return system_settings.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener configuración: {str(e)}")

@app.post("/settings/update")
def update_settings(settings: SystemSettings):
    """Actualiza la configuración del sistema"""
    try:
        global system_settings
        system_settings = settings
        
        # Guardar en base de datos
        settings_collection.replace_one({}, settings.dict(), upsert=True)
        
        create_alert("Configuración actualizada", AlertType.INFO, "sistema")
        return {"message": "Configuración actualizada exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar configuración: {str(e)}")

@app.get("/alerts")
def get_alerts(limit: int = 50, unresolved_only: bool = False):
    """Obtiene las alertas del sistema"""
    try:
        query = {}
        if unresolved_only:
            query["resolved"] = False
            
        alerts = list(alerts_collection.find(query).sort("timestamp", -1).limit(limit))
        for alert in alerts:
            alert["_id"] = str(alert["_id"])
        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener alertas: {str(e)}")

@app.post("/alerts/create")
def create_alert(message: str, alert_type: AlertType, component: str):
    """Crea una nueva alerta"""
    try:
        alert = Alert(message=message, alert_type=alert_type, component=component)
        result = alerts_collection.insert_one(alert.dict())
        return {"inserted_id": str(result.inserted_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear alerta: {str(e)}")

@app.patch("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str):
    """Marca una alerta como resuelta"""
    try:
        from bson import ObjectId
        result = alerts_collection.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"resolved": True}}
        )
        if result.modified_count > 0:
            return {"message": "Alerta marcada como resuelta"}
        else:
            raise HTTPException(status_code=404, detail="Alerta no encontrada")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al resolver alerta: {str(e)}")

@app.get("/analytics/usage")
def get_usage_analytics(days: int = 7):
    """Obtiene análisis de uso de agua de los últimos días"""
    try:
        start_date = datetime.now() - timedelta(days=days)
        
        logs = list(logs_collection.find({
            "timestamp": {"$gte": start_date}
        }).sort("timestamp", -1))
        
        # Calcular estadísticas
        total_fills = len([log for log in logs if log.get("action") == "fill_complete"])
        total_water_used = sum([log.get("water_amount_liters", 0) for log in logs if log.get("water_amount_liters")])
        avg_fill_duration = sum([log.get("duration_minutes", 0) for log in logs if log.get("duration_minutes")]) / max(total_fills, 1)
        
        return {
            "period_days": days,
            "total_fills": total_fills,
            "total_water_liters": total_water_used,
            "average_fill_duration_minutes": round(avg_fill_duration, 2),
            "fills_per_day": round(total_fills / days, 2),
            "logs": [dict(log, _id=str(log["_id"])) for log in logs]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener analytics: {str(e)}")

@app.post("/control/manual")
def manual_control(action: str):
    """Control manual de la bomba"""
    try:
        if action not in ["start_pump", "stop_pump"]:
            raise HTTPException(status_code=400, detail="Acción no válida")
        
        # Simular control de bomba
        global current_status
        if action == "start_pump":
            current_status.bomba_active = True
            message = "Bomba encendida manualmente"
        else:
            current_status.bomba_active = False
            message = "Bomba apagada manualmente"
        
        # Actualizar en base de datos
        status_collection.insert_one(current_status.dict())
        create_alert(message, AlertType.INFO, "bomba")
        
        return {"message": message, "status": current_status.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en control manual: {str(e)}")

@app.post("/simulate/scenario")
def simulate_scenario(scenario: str):
    """Simula diferentes escenarios para pruebas"""
    try:
        global current_status
        
        scenarios = {
            "low_water": SystemStatus(
                tinaco_level=TankLevel.LOW,
                cisterna_level=TankLevel.HIGH,
                bomba_active=False
            ),
            "empty_cisterna": SystemStatus(
                tinaco_level=TankLevel.LOW,
                cisterna_level=TankLevel.EMPTY,
                bomba_active=False
            ),
            "pump_malfunction": SystemStatus(
                tinaco_level=TankLevel.LOW,
                cisterna_level=TankLevel.HIGH,
                bomba_active=True,
                bomba_runtime=65  # Más del límite
            ),
            "normal_operation": SystemStatus(
                tinaco_level=TankLevel.HIGH,
                cisterna_level=TankLevel.HIGH,
                bomba_active=False
            )
        }
        
        if scenario not in scenarios:
            raise HTTPException(status_code=400, detail="Escenario no válido")
        
        current_status = scenarios[scenario]
        status_collection.insert_one(current_status.dict())
        
        # Generar alertas apropiadas
        _check_and_generate_alerts(current_status)
        
        return {"message": f"Escenario '{scenario}' simulado", "status": current_status.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al simular escenario: {str(e)}")

# Funciones auxiliares
def _apply_automatic_control(status: SystemStatus) -> Optional[str]:
    """Aplica la lógica de control automático"""
    if not system_settings.auto_mode:
        return None
        
    current_hour = datetime.now().hour
    
    # Verificar si debe encender la bomba
    if (status.tinaco_level == system_settings.fill_start_level and 
        status.cisterna_level != TankLevel.EMPTY and 
        not status.bomba_active):
        
        # Verificar horario preferido si está en modo ahorro de energía
        if system_settings.energy_saving_mode:
            if current_hour not in system_settings.preferred_fill_hours:
                return "Llenado pospuesto por modo ahorro energético"
        
        # Simular encendido de bomba
        status.bomba_active = True
        return "Bomba encendida automáticamente"
    
    # Verificar si debe apagar la bomba
    elif (status.tinaco_level == system_settings.fill_stop_level or
          status.cisterna_level == TankLevel.EMPTY or
          status.bomba_runtime > system_settings.max_pump_runtime):
        
        if status.bomba_active:
            status.bomba_active = False
            return "Bomba apagada automáticamente"
    
    return None

def _check_and_generate_alerts(status: SystemStatus):
    """Verifica el estado y genera alertas si es necesario"""
    alerts_to_create = []
    
    # Alerta de cisterna vacía
    if status.cisterna_level == TankLevel.EMPTY:
        alerts_to_create.append(("Cisterna vacía - Revisar suministro", AlertType.CRITICAL, "cisterna"))
    
    # Alerta de bomba funcionando demasiado tiempo
    if status.bomba_runtime > system_settings.max_pump_runtime:
        alerts_to_create.append(("Bomba funcionando más tiempo del normal - Posible fuga", AlertType.ERROR, "bomba"))
    
    # Alerta de tinaco bajo
    if status.tinaco_level == TankLevel.LOW and status.cisterna_level != TankLevel.EMPTY:
        alerts_to_create.append(("Nivel de tinaco bajo", AlertType.WARNING, "tinaco"))
    
    # Crear alertas
    for message, alert_type, component in alerts_to_create:
        create_alert(message, alert_type, component)

def create_log(action: str, level_before: TankLevel, level_after: TankLevel, 
               duration_minutes: Optional[int] = None, water_amount: Optional[float] = None,
               action_description: Optional[str] = None):
    """Crea un log de actividad"""
    try:
        log = WaterUsageLog(
            action=action,
            tinaco_level_before=level_before,
            tinaco_level_after=level_after,
            duration_minutes=duration_minutes,
            water_amount_liters=water_amount
        )
        logs_collection.insert_one(log.dict())
    except Exception as e:
        print(f"Error al crear log: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)