from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class TankLevel(str, Enum):
    EMPTY = "empty"          # 0-10%
    LOW = "low"              # 10-30%
    MEDIUM = "medium"        # 30-70%
    HIGH = "high"            # 70-90%
    FULL = "full"            # 90-100%

class AlertType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class PumpStatus(str, Enum):
    OFF = "off"
    ON = "on"
    MAINTENANCE = "maintenance"
    ERROR = "error"

class SystemMode(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    MAINTENANCE = "maintenance"

class SystemStatus(BaseModel):
    # Niveles de tanques
    tinaco_level: TankLevel
    tinaco_percentage: float = Field(ge=0, le=100, description="Porcentaje exacto del tinaco")
    cisterna_level: TankLevel
    cisterna_percentage: float = Field(ge=0, le=100, description="Porcentaje exacto de la cisterna")
    
    # Estado de la bomba
    bomba_status: PumpStatus
    bomba_runtime_minutes: int = Field(default=0, description="Tiempo funcionando en la sesión actual")
    bomba_total_runtime_today: int = Field(default=0, description="Tiempo total funcionando hoy")
    
    # Métricas de flujo y consumo
    water_flow_rate: float = Field(default=0.0, description="Litros por minuto")
    power_consumption: float = Field(default=0.0, description="Consumo actual en watts")
    daily_power_consumption: float = Field(default=0.0, description="Consumo total del día en kWh")
    
    # Datos ambientales
    water_temperature: Optional[float] = Field(default=None, description="Temperatura del agua en °C")
    ambient_temperature: Optional[float] = Field(default=None, description="Temperatura ambiente en °C")
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.now)
    system_mode: SystemMode = Field(default=SystemMode.AUTOMATIC)
    
    class Config:
        use_enum_values = True

class Alert(BaseModel):
    message: str
    alert_type: AlertType
    component: str = Field(description="bomba, tinaco, cisterna, sistema, sensor")
    severity_level: int = Field(ge=1, le=5, default=3, description="Nivel de severidad 1-5")
    timestamp: datetime = Field(default_factory=datetime.now)
    resolved: bool = Field(default=False)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    auto_generated: bool = Field(default=True)
    requires_action: bool = Field(default=False)
    
    class Config:
        use_enum_values = True

class SystemSettings(BaseModel):
    # Configuración básica
    system_name: str = Field(default="SmartWater System")
    auto_mode_enabled: bool = Field(default=True)
    
    # Niveles de control
    fill_trigger_level: TankLevel = Field(default=TankLevel.LOW)
    fill_stop_level: TankLevel = Field(default=TankLevel.FULL)
    fill_trigger_percentage: float = Field(default=25.0, ge=0, le=100)
    fill_stop_percentage: float = Field(default=90.0, ge=0, le=100)
    
    # Seguridad y límites
    max_pump_runtime_minutes: int = Field(default=60, description="Tiempo máximo continuo de bomba")
    max_daily_runtime_minutes: int = Field(default=240, description="Tiempo máximo diario de bomba")
    min_cisterna_level_to_start: TankLevel = Field(default=TankLevel.LOW)
    
    # Configuración energética
    energy_saving_enabled: bool = Field(default=False)
    preferred_hours: List[int] = Field(
        default=[22, 23, 0, 1, 2, 3, 4, 5], 
        description="Horas preferidas para operar (0-23)"
    )
    avoid_peak_hours: bool = Field(default=True)
    peak_hours: List[int] = Field(default=[18, 19, 20, 21], description="Horas pico a evitar")
    
    # Notificaciones
    notifications_enabled: bool = Field(default=True)
    email_notifications: bool = Field(default=False)
    notification_email: Optional[str] = None
    critical_alerts_only: bool = Field(default=False)
    
    # Mantenimiento
    maintenance_reminder_days: int = Field(default=30, description="Días para recordatorio de mantenimiento")
    last_maintenance_date: Optional[datetime] = None
    
    # Configuración avanzada
    flow_rate_threshold: float = Field(default=10.0, description="Flujo mínimo esperado L/min")
    pressure_monitoring: bool = Field(default=False)
    leak_detection_sensitivity: float = Field(default=0.8, ge=0.1, le=1.0)
    
    class Config:
        use_enum_values = True

class WaterUsageLog(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    action: str = Field(description="fill_start, fill_complete, manual_start, manual_stop, alert_generated, etc.")
    
    # Estados antes y después
    tinaco_level_before: TankLevel
    tinaco_level_after: TankLevel
    tinaco_percentage_before: float
    tinaco_percentage_after: float
    
    # Métricas de la operación
    duration_minutes: Optional[int] = None
    water_amount_liters: Optional[float] = None
    power_consumed_kwh: Optional[float] = None
    
    # Contexto
    triggered_by: str = Field(default="system", description="system, user, schedule, alert")
    operation_mode: SystemMode
    
    # Calidad de la operación
    efficiency_score: Optional[float] = Field(default=None, ge=0, le=1, description="Eficiencia de la operación")
    notes: Optional[str] = None
    
    class Config:
        use_enum_values = True

class DeviceStatus(BaseModel):
    """Estado de los dispositivos IoT conectados"""
    device_id: str
    device_type: str = Field(description="sensor_nivel, bomba_relay, flow_sensor, etc.")
    online: bool = Field(default=True)
    last_seen: datetime = Field(default_factory=datetime.now)
    battery_level: Optional[float] = Field(default=None, ge=0, le=100)
    signal_strength: Optional[float] = Field(default=None, ge=0, le=100, description="Fuerza de señal WiFi/cellular")
    firmware_version: Optional[str] = None
    
class MaintenanceRecord(BaseModel):
    """Registro de mantenimiento del sistema"""
    date: datetime = Field(default_factory=datetime.now)
    maintenance_type: str = Field(description="preventivo, correctivo, limpieza, calibracion")
    component: str = Field(description="bomba, sensores, tuberia, electricidad")
    description: str
    performed_by: str
    cost: Optional[float] = None
    next_maintenance_due: Optional[datetime] = None
    parts_replaced: List[str] = Field(default_factory=list)
    
class WaterQuality(BaseModel):
    """Datos de calidad del agua (si se tienen sensores)"""
    timestamp: datetime = Field(default_factory=datetime.now)
    ph_level: Optional[float] = Field(default=None, ge=0, le=14)
    turbidity: Optional[float] = Field(default=None, ge=0, description="NTU")
    chlorine_level: Optional[float] = Field(default=None, ge=0, description="mg/L")
    temperature: Optional[float] = Field(default=None, description="°C")
    conductivity: Optional[float] = Field(default=None, description="µS/cm")
    
class UserPreferences(BaseModel):
    """Preferencias del usuario para la app móvil"""
    user_id: str
    language: str = Field(default="es", description="Idioma de la interfaz")
    timezone: str = Field(default="America/Mexico_City")
    notification_frequency: str = Field(default="important", description="all, important, critical, none")
    dashboard_widgets: List[str] = Field(
        default=["status", "alerts", "usage", "efficiency"],
        description="Widgets a mostrar en dashboard"
    )
    auto_refresh_seconds: int = Field(default=30, ge=5, le=300)
    dark_mode: bool = Field(default=False)
    
class APIResponse(BaseModel):
    """Respuesta estándar de la API"""
    success: bool
    message: str
    data: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
class SystemHealth(BaseModel):
    """Estado general de salud del sistema"""
    overall_status: str = Field(description="healthy, warning, critical, maintenance")
    uptime_hours: float
    last_error: Optional[str] = None
    active_alerts_count: int = Field(default=0)
    critical_alerts_count: int = Field(default=0)
    system_efficiency: float = Field(ge=0, le=1, description="Eficiencia general del sistema")
    components_status: dict = Field(default_factory=dict)
    last_health_check: datetime = Field(default_factory=datetime.now)