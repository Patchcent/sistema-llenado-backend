from fastapi import FastAPI, HTTPException
from models import SystemStatus, Alert, SystemSettings, WaterUsageLog, TankLevel
from services import water_service

app = FastAPI()

@app.get("/status", response_model=SystemStatus)
async def get_status():
    return await water_service.get_current_status()

@app.post("/status", response_model=SystemStatus)
async def update_status(status: SystemStatus):
    return await water_service.update_system_status(status)

@app.get("/settings", response_model=SystemSettings)
async def get_settings():
    return await water_service.get_system_settings()

@app.post("/settings", response_model=SystemSettings)
async def update_settings(settings: SystemSettings):
    return await water_service.update_system_settings(settings)

@app.get("/alerts", response_model=list[Alert])
async def get_alerts():
    return await water_service.get_alerts()

@app.post("/control/manual", response_model=SystemStatus)
async def manual_control(pump_on: bool):
    return await water_service.manual_control(pump_on)

@app.get("/analytics/usage", response_model=list[WaterUsageLog])
async def get_usage_analytics():
    return await water_service.get_usage_analytics()

@app.post("/simulate/scenario", response_model=SystemStatus)
async def simulate_scenario(tank_level: TankLevel):
    return await water_service.simulate_scenario(tank_level)
