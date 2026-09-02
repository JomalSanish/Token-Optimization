# Technical Research: Token Cost Estimator and Optimizer

## Decisions and Rationales

### 1. Asynchronous I/O Pattern (Backend)
- **Decision**: Implement a fully asynchronous backend using FastAPI, `motor` (async MongoDB client), and `httpx.AsyncClient` for provider LLM calls.
- **Rationale**: The backend is highly I/O bound. Each client request to `/extract` or `/discover-optimizations` requires calling third-party LLM APIs, which can take several seconds. Under a concurrent load of 10+ users, synchronous handlers would block worker threads, degrading performance and violating p95 latency targets (<200ms for deterministic requests). Async routes ensure that the server can handle other requests while waiting for outbound network calls.
- **Alternatives Considered**: 
  - *Standard Synchronous FastAPI + Requests*: Rejected because it requires spinning up multi-threaded workers which scale poorly and increase memory footprints.
  - *Celery Task Queues*: Rejected because the API requires immediate inline responses; adding a task queue increases architectural complexity without performance benefit.

### 2. Pure Calculation Engine Boundary
- **Decision**: Isolate all cost formulas and optimizer rules into side-effect-free, pure Python functions that receive inputs via arguments and return outputs. These functions must not import the database client or make network requests.
- **Rationale**: Isolating math from I/O ensures 100% reproducible and testable code. It allows testing calculations against fixed pricing snapshots without requiring running database instances or mocking database connection pools.
- **Alternatives Considered**: 
  - *Active Record Pattern*: Querying model prices inline within the cost formulas. Rejected because it couples calculations to database state, preventing reliable testing and auditing.

### 3. Client-Side Key Storage & Rotation
- **Decision**: Store API keys in browser `localStorage` in an array pool structure, rotating key pools sequentially on the client whenever the backend returns a `429 Too Many Requests` or authorization error.
- **Rationale**: The backend is stateless and must not store keys. Managing key rotation on the client ensures keys are rotated immediately without server-side tracking, preventing cross-user key leaking and reducing server exposure.
- **Alternatives Considered**: 
  - *Server-Side Session Store*: Storing keys in Redis sessions. Rejected because it violates the constitution's stateless requirement (Principle II) and introduces high database security risks.

### 4. Admin Security & Authentication
- **Decision**: Protect `/admin/*` routes using standard Bearer Token (JWT or API Token) authentication where the administrator secret is loaded via a backend-only environment variable (`ADMIN_API_KEY`). plaintext admin credentials will not be stored in MongoDB.
- **Rationale**: Restricting credentials to backend environment variables prevents exposure through MongoDB read dumps. It ensures that standard database user read privileges cannot read or compromise admin authentication mechanisms.
- **Alternatives Considered**: 
  - *Plaintext credentials in database*: Highly insecure and rejected.
  - *Database-backed OAuth*: Over-engineered for a catalog admin panel. Using a secure environment variable is standard, lightweight, and robust.
