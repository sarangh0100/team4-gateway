# Team 4 - Inline Gateway & IDS

## Status: Week 2 - rule-based firewall engine
Pipeline order: rate_limit -> sanity_check -> resolve_route -> (Week 3: cert, decrypt, replay, authorize) -> forward -> log

### Run with Docker
    docker compose up --build
    curl http://localhost:8080/gateway/health
    curl http://localhost:8080/api/records
    curl http://localhost:8080/gateway/logs
    curl http://localhost:8080/gateway/stats

### Run tests (no Docker)
    pip install -r tests/requirements.txt
    python -m pytest -v

### Attack scripts (gateway must be running)
    python scripts/bad_requests.py
    python scripts/flood.py        # may ban your IP for ~60 s

### Tuning
All limits live in gateway-service/config/firewall.yaml.

### Structure
- gateway-service/       gateway (FastAPI reverse proxy + firewall pipeline)
- mock-records-service/  dummy protected backend
- tests/                 Week 1 + Week 2 tests
- scripts/               flood and malformed-request demos
