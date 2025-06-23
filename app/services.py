from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging
from .models import *
from .database import get_collection
import asyncio

logger = logging.getLogger(__name__)

class WaterSystemService:
    """Servicio principal para la lógica del sistema de agua"""
    
    def __init__(self):
        self.status_collection = get_collection("system_status")
        self.alerts_collection = get_collection("alerts")
        self.logs_collection = get_collection("usage_logs")
        self.settings_collection = get_collection("settings")
        self.devices_collection = get_collection("device_status")
        
    async def get_current_status(self) -> Optional[SystemStatus]:
        """Obtiene el estado actual del sistema"""
        try:
            latest = self.status_collection.find_one(
                sort=[("last_updated", -1)]
            )
            if latest:
                latest.pop("_id", None)
                return SystemStatus(**latest)
            return None
        except Exception as e:
            logger.error(f"Error obteniendo estado actual: {e}")
            return None
    
    async def update_system_status(self, status: SystemStatus) -> bool:
        """Actualiza el estado del sistema y aplica lógica de control"""
        try:
            # Insertar nuevo estado
            result = self.status_collection.insert_one(status.dict())
            
            if not result.inserted_id:
                return False
            
            # Obtener configuración actual
            settings = await self.get_settings()
            if not settings:
                settings = SystemSettings()
            
            # Aplicar control automático si está habilitado
            if settings.auto_mode_enabled:
                await self._apply_automatic_control(status, settings)
            
            # Verificar y generar alertas
            await self._check_and_generate_alerts(status, settings)
            
            # Registrar actividad
            await self._log_activity("status_update", status)
            
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando estado: {e}")
            return False
    
    async def get_settings(self) -> Optional[SystemSettings]:
        """Obtiene la configuración actual del sistema"""
        try:
            settings_doc = self.settings_collection.find_one()
            if settings_doc:
                settings_doc.pop("_id", None)
                return SystemSettings(**settings_doc)
            return SystemSettings()  # Configuración por defecto
        except Exception as e:
            logger.error(f"Error obteniendo configuración: {e}")
            return None
    
    async def update_settings(self, settings: SystemSettings) -> bool:
        """Actualiza la configuración del sistema"""
        try:
            result = self.settings_collection.replace_one(
                {}, settings.dict(), upsert=True
            )
            
            # Registrar cambio de configuración
            await self.create_alert(
                "Configuración del sistema actualizada",
                AlertType.INFO,
                "sistema"
            )
            
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error actualizando configuración: {e}")
            return False
    
    async def create_alert(self, message: str, alert_type: AlertType, 
                          component: str, severity: int = 3) -> Optional[str]:
        """Crea una nueva alerta"""
        try:
            alert = Alert(
                message=message,
                alert_type=alert_type,
                component=component,
                severity_level=severity
            )
            
            result = self.alerts_collection.insert_one(alert.dict())
            
            if result.inserted_id:
                logger.info(f"Alerta creada: {message}")
                return str(result.inserted_id)
            return None
            
        except Exception as e:
            logger.error(f"Error creando alerta: {e}")
            return None
    
    async def get_alerts(self, limit: int = 50, unresolved_only: bool = False) -> List[Dict]:
        """Obtiene las alertas del sistema"""
        try:
            query = {}
            if unresolved_only:
                query["resolved"] = False
            
            cursor = self.alerts_collection.find(query).sort("timestamp", -1).limit(limit)
            alerts = []
            
            for alert in cursor:
                alert["_id"] = str(alert["_id"])
                alerts.append(alert)
            
            return alerts
        except Exception as e:
            logger.error(f"Error obteniendo alertas: {e}")
            return []
    
    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Marca una alerta como resuelta"""
        try:
            from bson import ObjectId
            result = self.alerts_collection.update_one(
                {"_id": ObjectId(alert_id)},
                {
                    "$set": {
                        "resolved": True,
                        "resolved_at": datetime.now(),
                        "resolved_by": resolved_by
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error resolviendo alerta: {e}")
            return False
    
    async def get_usage_analytics(self, days: int = 7) -> Dict[str, Any]:
        """Obtiene análisis de uso de agua"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            # Obtener logs del período
            logs_cursor = self.logs_collection.find({
                "timestamp": {"$gte": start_date}
            }).sort("timestamp", -1)
            
            logs = list(logs_cursor)
            
            # Calcular métricas
            fill_operations = [log for log in logs if log.get("action") == "fill_complete"]
            total_fills = len(fill_operations)
            
            total_water = sum([
                log.get("water_amount_liters", 0) 
                for log in fill_operations 
                if log.get("water_amount_liters")
            ])
            
            total_duration = sum([
                log.get("duration_minutes", 0) 
                for log in fill_operations 
                if log.get("duration_minutes")
            ])
            
            total_power = sum([
                log.get("power_consumed_kwh", 0) 
                for log in fill_operations 
                if log.get("power_consumed_kwh")
            ])
            
            avg_duration = total_duration / max(total_fills, 1)
            avg_efficiency = sum([
                log.get("efficiency_score", 0.8) 
                for log in fill_operations 
                if log.get("efficiency_score")
            ]) / max(total_fills, 1)
            
            return {
                "period_days": days,
                "total_fills": total_fills,
                "total_water_liters": round(total_water, 2),
                "total_duration_minutes": total_duration,
                "total_power_kwh": round(total_power, 3),
                "average_duration_minutes": round(avg_duration, 2),
                "average_efficiency": round(avg_efficiency, 2),
                "fills_per_day": round(total_fills / days, 2),
                "water_per_day": round(total_water / days, 2),
                "power_per_day": round(total_power / days, 3),
                "recent_logs": [
                    {**log, "_id": str(log["_id"])} 
                    for log in logs[:20]
                ]
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo analytics: {e}")
            return {}
    
    async def manual_pump_control(self, action: str, user: str = "manual") -> Dict[str, Any]:
        """Control manual de la bomba"""
        try:
            current_status = await self.get_current_status()
            if not current_status:
                return {"success": False, "message": "No se pudo obtener estado actual"}
            
            if action == "start":
                if current_status.bomba_status == PumpStatus.ON:
                    return {"success": False, "message": "La bomba ya está encendida"}
                
                current_status.bomba_status = PumpStatus.ON
                current_status.system_mode = SystemMode.MANUAL
                message = "Bomba encendida manualmente"
                
            elif action == "stop":
                if current_status.bomba_status == PumpStatus.OFF:
                    return {"success": False, "message": "La bomba ya está apagada"}
                
                current_status.bomba_status = PumpStatus.OFF
                current_status.system_mode = SystemMode.MANUAL
                message = "Bomba apagada manualmente"
                
            else:
                return {"success": False, "message": "Acción no válida"}
            
            # Actualizar estado
            success = await self.update_system_status(current_status)
            if success:
                await self.create_alert(message, AlertType.INFO, "bomba")
                await self._log_activity("manual_control", current_status, 
                                        action_description=f"{action} por {user}")
            
            return {
                "success": success,
                "message": message,
                "new_status": current_status.dict()
            }
            
        except Exception as e:
            logger.error(f"Error en control manual: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    async def _apply_automatic_control(self, status: SystemStatus, settings: SystemSettings):
        """Aplica la lógica de control automático"""
        try:
            current_hour = datetime.now().hour
            
            # Verificar si debe encender la bomba
            should_start_pump = (
                status.tinaco_percentage <= settings.fill_trigger_percentage and
                status.cisterna_level != TankLevel.EMPTY and
                status.bomba_status == PumpStatus.OFF and
                status.bomba_total_runtime_today < settings.max_daily_runtime_minutes
            )
            
            if should_start_pump:
                # Verificar restricciones de horario
                if settings.energy_saving_enabled:
                    if current_hour not in settings.preferred_hours:
                        await self.create_alert(
                            "Llenado pospuesto por modo ahorro energético",
                            AlertType.INFO, "sistema"
                        )
                        return
                
                if settings.avoid_peak_hours and current_hour in settings.peak_hours:
                    await self.create_alert(
                        "Llenado pospuesto por horas pico",
                        AlertType.INFO, "sistema"
                    )
                    return
                
                # Encender bomba
                status.bomba_status = PumpStatus.ON
                status.system_mode = SystemMode.AUTOMATIC
                await self.create_alert(
                    "Bomba encendida automáticamente",
                    AlertType.INFO, "bomba"
                )
                await self._log_activity("auto_start", status)
            
            # Verificar si debe apagar la bomba
            should_stop_pump = (
                status.bomba_status == PumpStatus.ON and (
                    status.tinaco_percentage >= settings.fill_stop_percentage or
                    status.cisterna_level == TankLevel.EMPTY or
                    status.bomba_runtime_minutes >= settings.max_pump_runtime_minutes
                )
            )
            
            if should_stop_pump:
                status.bomba_status = PumpStatus.OFF
                reason = "Llenado completado"
                
                if status.cisterna_level == TankLevel.EMPTY:
                    reason = "Cisterna vacía"
                elif status.bomba_runtime_minutes >= settings.max_pump_runtime_minutes:
                    reason = "Tiempo máximo alcanzado"
                
                await self.create_alert(
                    f"Bomba apagada automáticamente: {reason}",
                    AlertType.INFO, "bomba"
                )
                await self._log_activity("auto_stop", status, action_description=reason)
            
        except Exception as e:
            logger.error(f"Error en control automático: {e}")
    
    async def _check_and_generate_alerts(self, status: SystemStatus, settings: SystemSettings):
        """Verifica el estado y genera alertas necesarias"""
        try:
            alerts_to_create = []
            
            # Alerta crítica: Cisterna vacía
            if status.cisterna_level == TankLevel.EMPTY:
                alerts_to_create.append((
                    "⚠️ CRÍTICO: Cisterna vacía - Revisar suministro de agua",
                    AlertType.CRITICAL, "cisterna", 5
                ))
            
            # Alerta de bomba funcionando demasiado tiempo
            if status.bomba_runtime_minutes > settings.max_pump_runtime_minutes:
                alerts_to_create.append((
                    f"⚠️ Bomba funcionando {status.bomba_runtime_minutes} minutos - Posible fuga o obstrucción",
                    AlertType.ERROR, "bomba", 4
                ))
            
            # Alerta de tinaco bajo
            if (status.tinaco_level == TankLevel.LOW and 
                status.cisterna_level != TankLevel.EMPTY and
                status.bomba_status == PumpStatus.OFF):
                alerts_to_create.append((
                    "Nivel de tinaco bajo - Llenado requerido",
                    AlertType.WARNING, "tinaco", 3
                ))
            
            # Alerta de consumo energético alto
            if status.daily_power_consumption > 5.0:  # kWh
                alerts_to_create.append((
                    f"Consumo energético alto: {status.daily_power_consumption:.2f} kWh hoy",
                    AlertType.WARNING, "energia", 3
                ))
            
            # Alerta de flujo bajo
            if (status.bomba_status == PumpStatus.ON and 
                status.water_flow_rate < settings.flow_rate_threshold):
                alerts_to_create.append((
                    f"Flujo de agua bajo: {status.water_flow_rate:.1f} L/min",
                    AlertType.WARNING, "bomba", 3
                ))
            
            # Crear todas las alertas
            for message, alert_type, component, severity in alerts_to_create:
                await self.create_alert(message, alert_type, component, severity)
                
        except Exception as e:
            logger.error(f"Error verificando alertas: {e}")
    
    async def _log_activity(self, action: str, status: SystemStatus, 
                           duration: int = None, water_amount: float = None,
                           action_description: str = None):
        """Registra actividad del sistema"""
        try:
            # Para algunas acciones, calcular valores por defecto
            if action == "fill_complete" and not water_amount:
                # Estimar agua basada en el cambio de nivel
                water_amount = (status.tinaco_percentage - 20) * 10  # Estimación simple
            
            log = WaterUsageLog(
                action=action,
                tinaco_level_before=status.tinaco_level,
                tinaco_level_after=status.tinaco_level,
                tinaco_percentage_before=status.tinaco_percentage,
                tinaco_percentage_after=status.tinaco_percentage,
                duration_minutes=duration,
                water_amount_liters=water_amount,
                power_consumed_kwh=status.power_consumption * (duration or 1) / 60 / 1000 if duration else None,
                triggered_by="system",
                operation_mode=status.system_mode,
                notes=action_description
            )
            
            self.logs_collection.insert_one(log.dict())
            
        except Exception as e:
            logger.error(f"Error registrando actividad: {e}")

# Instancia global del servicio
water_service = WaterSystemService()