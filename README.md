# Team 4 - Inline Gateway & IDS

## Week 1 status: proxy skeleton + pipeline stubs + mock service

### Run with Docker
    docker compose up --build
    curl http://localhost:8080/gateway/health
    curl http://localhost:8080/api/records
    curl http://localhost:8080/gateway/logs

### Run tests (no Docker)
    pip install -r tests/requirements.txt
    pytest -v

### Structure
- gateway-service/    the gateway (FastAPI reverse proxy + pipeline)
- mock-records-service/ dummy protected backend
- tests/              Week 1 tests
