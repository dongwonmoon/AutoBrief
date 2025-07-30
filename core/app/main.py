from fastapi import FastAPI
from core.api.v1 import project_groups

app = FastAPI()

app.include_router(project_groups.router, prefix="/api/v1")

@app.get("/")
def health_check():
    """기본 헬스 체크용 엔드포인트"""
    return {"message": "AutoBrief Backend is running!"}