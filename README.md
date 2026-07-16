# Distributed Rate Limiter & Automated Active Defense System

An enterprise-grade, high-throughput, distributed rate limiting service engineered with **FastAPI**, **Redis (Lua Scripting)**, and **AWS SDK (Boto3)**. This system features an automated **Active Defense Closed-Loop** that dynamically blocks malicious IPs at the infrastructure level (AWS Network ACL) upon detecting rate limit abuse.

---

## 🛠️ System Architecture & Workflow


1. **Client Request**: Client hits the FastAPI gateway.
2. **Edge Interception (Middleware)**: The request is intercepted at the outermost layer to protect downstream application logic.
3. **Atomic Evaluation (Redis + Lua)**: The middleware evaluates the client's quota using a **Token Bucket Algorithm** implemented via an atomic Lua script inside Redis, guaranteeing race-condition safety.
4. **Active Defense Trigger**: If a client continuously triggers `HTTP 429` beyond a defined safety threshold, an asynchronous task is dispatched to automatically update the **AWS Network ACL (NACL)**, blacklisting the malicious IP at the subnet boundary.

---

## 🚀 Key Architectural Features

| Feature | Engineering Implementation | SRE/Production Value |
| :--- | :--- | :--- |
| **Distributed Consistency** | Centralized state tracking via clustered/dockerized **Redis**. | Prevents "split-brain" quota bypass when scaling horizontally across multiple web instances. |
| **Race-Condition Immunity** | **Atomic execution** of Token Bucket logic via Redis-compiled **Lua Scripts**. | Ensures thread-safety and consistent token operations under extreme concurrent load. |
| **Fail-Fast Latency Guard** | Short-circuiting requests at the **FastAPI Middleware** level. | Eliminates unnecessary CPU/DB consumption, preserving web event-loop capacity. |
| **Active Incident Response** | Non-blocking asynchronous triggers using `asyncio.to_thread` to call **AWS Boto3**. | Mitigates brute-force/DDoS attacks at the network boundary (Layer 4) instead of the app layer (Layer 7). |

---

## 📊 Performance & Load Testing Results (Locust)

The system was subjected to high-concurrency load testing simulating a brute-force scraping attempt using **Locust** (30 concurrent users, spawn rate of 3/sec, target: `/api/v1/resource`):

* **Configured Capacity**: `MAX_TOKENS = 10`, `REFILL_RATE = 2.0/sec`
* **Observed Metrics**:
  * **Successful QPS**: Constrained strictly at **~2.0 RPS** (aligned with the configured refill rate).
  * **Blocked QPS**: Safely shed as **HTTP 429 Too Many Requests** as concurrency scaled up.
  * **System Latency**: Maintained at an ultra-low **2ms - 5ms** median, proving the efficiency of the edge-discarding middleware.
  * **Automated Block Triggered**: The malicious IP was successfully identified and flagged for AWS NACL exclusion.

---

## ⚙️ Quick Start

### 1. Run Redis Container
```bash
docker run -d --name redis-limiter -p 6379:6379 redis:alpine
```

### 2. Install Dependencies & Activate Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
### 3. Launch Web Server (FastAPI)
```bash
uvicorn main:app --reload --port 8000
```
### 4. Execute Load Test (Locust)
```bash
python -m locust -f locustfile.py
Open your browser and navigate to http://localhost:8089 to monitor real-time rate limiting telemetry and fail-fast performance charts.
```