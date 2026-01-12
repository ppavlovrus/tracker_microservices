from fastapi import FastAPI, HTTPException, Depends
from dto import Record, Response, RecordListResponse
from super_service import TestService
from repository_impl import ModelRepository  # реализация репозитория
from pool import get_pool, lifespan

# Инициализация приложения
app = FastAPI(
    title="Test Service",
    description="Тестовый сервис с чистой архитектурой",
    lifespan=lifespan
)

# Зависимость: создаём сервис с инъекцией репозитория
def get_service():
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not ready")
    repository = ModelRepository(pool)
    return TestService(repository)

@app.post("/records", response_model=Response)
async def create_record(
    record: Record,
    service: TestService = Depends(get_service)
):
    try:
        saved_dto = await service.create_record(record)
        return Response(
            status="success",
            message="Record created successfully",
            record=saved_dto
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.get("/records/{record_id}", response_model=Response)
async def get_record(
    record_id: int,
    service: TestService = Depends(get_service)
):
    try:
        record = await service.get_record_by_id(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")
        return Response(
            status="success",
            message="Record retrieved",
            record=record
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.get("/records", response_model=RecordListResponse)
async def get_all_records(
    service: TestService = Depends(get_service)
):
    try:
        records = await service.get_all_records()
        return RecordListResponse(
            status="success",
            message="Records retrieved",
            records=records
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.get("/health")
async def health():
    return {"status": "ok"}