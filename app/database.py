from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.collections = {}
        self._connect()
        self._setup_collections()
        self._create_indexes()
    
    def _connect(self):
        """Establece conexión con MongoDB"""
        try:
            mongo_uri = os.getenv("MONGO_URI")
            if not mongo_uri:
                raise ValueError("MONGO_URI no encontrada en variables de entorno")
            
            self.client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,  # 5 segundos timeout
                connectTimeoutMS=10000,         # 10 segundos para conectar
                socketTimeoutMS=20000,          # 20 segundos para operaciones
                maxPoolSize=10,                 # Máximo 10 conexiones
                retryWrites=True
            )
            
            # Verificar conexión
            self.client.admin.command('ping')
            self.db = self.client["smartwater_system"]
            logger.info("✅ Conexión exitosa a MongoDB")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"❌ Error conectando a MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado en conexión: {e}")
            raise
    
    def _setup_collections(self):
        """Configura las colecciones de la base de datos"""
        collection_names = [
            "system_status",
            "alerts", 
            "usage_logs",
            "settings",
            "device_status",
            "maintenance_records",
            "water_quality",
            "user_preferences",
            "system_health"
        ]
        
        for name in collection_names:
            self.collections[name] = self.db[name]
        
        logger.info(f"✅ Colecciones configuradas: {collection_names}")
    
    def _create_indexes(self):
        """Crea índices para optimizar consultas"""
        try:
            # Índices para system_status
            self.collections["system_status"].create_index([
                ("last_updated", DESCENDING)
            ])
            
            # Índices para alerts
            self.collections["alerts"].create_index([
                ("timestamp", DESCENDING),
                ("resolved", ASCENDING)
            ])
            self.collections["alerts"].create_index([
                ("alert_type", ASCENDING),
                ("component", ASCENDING)
            ])
            
            # Índices para usage_logs
            self.collections["usage_logs"].create_index([
                ("timestamp", DESCENDING)
            ])
            self.collections["usage_logs"].create_index([
                ("action", ASCENDING),
                ("timestamp", DESCENDING)
            ])
            
            # Índices para device_status
            self.collections["device_status"].create_index([
                ("device_id", ASCENDING),
                ("last_seen", DESCENDING)
            ])
            
            # Índices para maintenance_records
            self.collections["maintenance_records"].create_index([
                ("date", DESCENDING)
            ])
            
            # Índices para water_quality
            self.collections["water_quality"].create_index([
                ("timestamp", DESCENDING)
            ])
            
            logger.info("✅ Índices creados exitosamente")
            
        except Exception as e:
            logger.error(f"❌ Error creando índices: {e}")
    
    def get_collection(self, name: str):
        """Obtiene una colección específica"""
        if name not in self.collections:
            raise ValueError(f"Colección '{name}' no existe")
        return self.collections[name]
    
    def health_check(self):
        """Verifica el estado de la conexión"""
        try:
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"❌ Health check fallido: {e}")
            return False
    
    def get_database_stats(self):
        """Obtiene estadísticas de la base de datos"""
        try:
            db_stats = self.db.command("dbstats")
            collection_stats = {}
            
            for name, collection in self.collections.items():
                try:
                    stats = self.db.command("collstats", name)
                    collection_stats[name] = {
                        "count": stats.get("count", 0),
                        "size": stats.get("size", 0),
                        "avgObjSize": stats.get("avgObjSize", 0)
                    }
                except:
                    collection_stats[name] = {"count": 0, "size": 0, "avgObjSize": 0}
            
            return {
                "database": {
                    "collections": db_stats.get("collections", 0),
                    "dataSize": db_stats.get("dataSize", 0),
                    "storageSize": db_stats.get("storageSize", 0),
                    "indexes": db_stats.get("indexes", 0)
                },
                "collections": collection_stats
            }
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return None
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Limpia datos antiguos para mantener la base de datos eficiente"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Limpiar logs antiguos
            result_logs = self.collections["usage_logs"].delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            # Limpiar alertas resueltas antiguas
            result_alerts = self.collections["alerts"].delete_many({
                "timestamp": {"$lt": cutoff_date},
                "resolved": True
            })
            
            # Limpiar datos de calidad de agua antiguos
            result_quality = self.collections["water_quality"].delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            logger.info(f"✅ Limpieza completada: {result_logs.deleted_count} logs, "
                       f"{result_alerts.deleted_count} alertas, "
                       f"{result_quality.deleted_count} registros de calidad eliminados")
            
            return {
                "logs_deleted": result_logs.deleted_count,
                "alerts_deleted": result_alerts.deleted_count,
                "quality_deleted": result_quality.deleted_count
            }
            
        except Exception as e:
            logger.error(f"❌ Error en limpieza: {e}")
            return None
    
    def backup_collection(self, collection_name: str, backup_path: str = None):
        """Crea un respaldo de una colección específica"""
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Colección '{collection_name}' no existe")
            
            collection = self.collections[collection_name]
            data = list(collection.find())
            
            if backup_path:
                import json
                with open(backup_path, 'w') as f:
                    json.dump(data, f, default=str, indent=2)
                logger.info(f"✅ Respaldo de '{collection_name}' guardado en {backup_path}")
            
            return data
            
        except Exception as e:
            logger.error(f"❌ Error creando respaldo: {e}")
            return None
    
    def close_connection(self):
        """Cierra la conexión a la base de datos"""
        if self.client:
            self.client.close()
            logger.info("✅ Conexión cerrada")

# Instancia global del manager
db_manager = DatabaseManager()

# Funciones de conveniencia para usar en otros módulos
def get_collection(name: str):
    return db_manager.get_collection(name)

def health_check():
    return db_manager.health_check()

def get_stats():
    return db_manager.get_database_stats()

def cleanup_old_data(days: int = 30):
    return db_manager.cleanup_old_data(days)