"""Dummy protected internal service. Stands in for the real backend until other teams deliver."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock Protected Records Service")

RECORDS = {
    1: {"id": 1, "patient": "Alice", "diagnosis": "Flu", "classification": "Restricted"},
    2: {"id": 2, "patient": "Bob", "diagnosis": "Fracture", "classification": "Confidential"},
}


class RecordIn(BaseModel):
    patient: str
    diagnosis: str
    classification: str = "Public"


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-records-service"}


@app.get("/api/records")
def list_records():
    return list(RECORDS.values())


@app.get("/api/records/{record_id}")
def get_record(record_id: int):
    if record_id not in RECORDS:
        raise HTTPException(404, "Record not found")
    return RECORDS[record_id]


@app.post("/api/records", status_code=201)
def create_record(rec: RecordIn):
    new_id = max(RECORDS) + 1
    RECORDS[new_id] = {"id": new_id, **rec.model_dump()}
    return RECORDS[new_id]


@app.put("/api/records/{record_id}")
def update_record(record_id: int, rec: RecordIn):
    if record_id not in RECORDS:
        raise HTTPException(404, "Record not found")
    RECORDS[record_id] = {"id": record_id, **rec.model_dump()}
    return RECORDS[record_id]


@app.delete("/api/records/{record_id}")
def delete_record(record_id: int):
    if RECORDS.pop(record_id, None) is None:
        raise HTTPException(404, "Record not found")
    return {"deleted": record_id}
