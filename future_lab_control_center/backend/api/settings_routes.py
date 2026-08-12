# ============================================================
# settings_routes.py — API Router para Configurações de Rede
# ============================================================
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.config.settings import get_settings, update_env_file

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

class SettingsUpdateSchema(BaseModel):
    HOST_PC_IP: Optional[str] = None
    JETSON_NANO_IP: Optional[str] = None
    TURTLEBOT_IP: Optional[str] = None
    CAMERA_STREAM_URL: Optional[str] = None
    DEFAULT_COOLDOWN_SEC: Optional[float] = None
    DEFAULT_YOLO_CONF: Optional[float] = None
    DEFAULT_VELOCITY_SCALING: Optional[float] = None

@router.get("/")
def get_current_settings():
    """Retorna as configurações atuais ativas de rede e parâmetros."""
    settings = get_settings()
    return settings.model_dump()

@router.put("/")
def update_settings(payload: SettingsUpdateSchema):
    """Atualiza as configurações no arquivo .env dinamicamente."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum parâmetro fornecido para atualização.")
    
    success = update_env_file(update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Falha ao escrever configurações no arquivo .env.")
    
    return {
        "status": "success",
        "message": "Configurações salvas no .env com sucesso!",
        "updated": update_data
    }
