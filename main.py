import redis
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from rate_limiter import TokenBucketLimiter

app = FastAPI(title="SRE Distributed Rate Limiter Service")

# 1. 初始化 Redis 連線與我們的限流器
r_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
limiter = TokenBucketLimiter(r_client)

# 配置限流規則：每個 IP 桶子上限 10 個 Token，每秒補回 2 個 (Refill Rate = 2.0)
MAX_TOKENS = 10
REFILL_RATE = 2.0

# 2. 自訂限流中間件 (Custom Rate Limiting Middleware)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # 取得客戶端的真實 IP 地址 (Client IP Extraction)
    client_ip = request.client.host
    
    # 呼叫我們的 Redis Lua 限流器
    is_allowed = limiter.is_allowed(
        ip_address=client_ip, 
        max_tokens=MAX_TOKENS, 
        refill_rate=REFILL_RATE
    )
    
    if not is_allowed:
        # 🔴 被限流：直接就地攔截，回覆 HTTP 429，不執行任何後續路由代碼
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Too Many Requests",
                "message": "Rate limit exceeded. Please slow down.",
                "retry_after_seconds": 1 / REFILL_RATE
            }
        )
    
    # 🟢 順利通過：放行，交給後續的 API 路由處理
    response = await call_next(request)
    return response

# --- 測試用的 API 路由 ---
@app.get("/")
async def root():
    return {"status": "success", "message": "Welcome to the secure API gateway!"}

@app.get("/api/v1/resource")
async def get_resource():
    # 模擬一個需要消耗 CPU/Database 資源的昂貴操作
    return {
        "status": "success", 
        "data": "This is extremely valuable and expensive resource data."
    }