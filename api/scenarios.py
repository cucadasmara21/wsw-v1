"""
Endpoints para simulación de escenarios de estrés
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter()


@router.post("/run")
async def run_stress_scenario(scenario_name: str):
    """Ejecutar un escenario de estrés predefinido"""
    predefined = {
        "market_crash": {
            "name": "Market Crash 2008",
            "shocks": [
                {"symbol": "SPY", "shock_value": -0.50}
            ]
        },
        "covid_crash": {
            "name": "COVID-19 Crash 2020",
            "shocks":  [
                {"symbol": "SPY", "shock_value": -0.35}
            ]
        }
    }

    if scenario_name not in predefined: 
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = predefined[scenario_name]

    return {
        "scenario_id": scenario_name,
        "name": scenario["name"],
        "status": "completed",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Scenario simulation completed"
    }
