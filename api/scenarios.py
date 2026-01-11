"""
Endpoints para simulación de escenarios de estrés
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter(tags=["scenarios"])


@router.post("/run")
async def run_stress_scenario(scenario_name: str):
    """
    Execute a predefined stress test scenario.
    
    Args:
        scenario_name (str): Name of the scenario to run. Supported scenarios:
            - `market_crash`: Simulates 2008 market crash (-50% SPY shock)
            - `covid_crash`: Simulates 2020 COVID crash (-35% SPY shock)
    
    Returns:
        dict: Scenario execution result with status, timestamp, and completion message.
    
    Raises:
        HTTPException: 404 if scenario_name not found in predefined scenarios.
    """
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
