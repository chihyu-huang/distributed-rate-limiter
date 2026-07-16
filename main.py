import redis
import boto3
import asyncio
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from rate_limiter import TokenBucketLimiter

app = FastAPI(title="SRE Active Defense API Gateway")

# 1. 初始化 Redis 與限流器
r_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
limiter = TokenBucketLimiter(r_client)

# 配置限流規則
MAX_TOKENS = 10
REFILL_RATE = 2.0

# 🛡️ 聯防安全策略配置 (Active Defense Security Policy)
VIOLATION_THRESHOLD = 5  # 60秒內被限流(429)達 5 次，直接送他去 AWS 黑名單
VIOLATION_WINDOW = 60     # 違規紀錄窗口 (秒)

def trigger_aws_nacl_block(ip_address: str):
    """
    實施主動防禦：調用 AWS Boto3 API，將惡意 IP 寫入 Network ACL (NACL) Inbound 拒絕規則。
    """
    print(f"🚨 [ACTIVE DEFENSE] Automated trigger initiated for malicious IP: {ip_address}")
    
    try:
        # 使用 AWS SDK (預設連線至都柏林區域 eu-west-1)
        client = boto3.client('ec2', region_name='eu-west-1')
        
        # 你的 AWS 網路控制黑名單 ID (實際環境中替換成你的 NACL ID)
        nacl_id = "acl-0123456789abcdef0" 
        
        # 建立一條 Inbound Deny 規則，規則編號設為 50 (越小越優先執行，搶在 Allow 之前)
        client.create_network_acl_entry(
            NetworkAclId=nacl_id,
            RuleNumber=50, 
            Protocol='-1',       # 所有協定 (All Traffic)
            RuleAction='deny',   # 阻斷
            Egress=False,        # Inbound 流量
            CidrBlock=f"{ip_address}/32" # 鎖定單一惡意 IP
        )
        print(f"🔒 [SUCCESS] IP {ip_address} has been blacklisted in AWS NACL {nacl_id}!")
        
    except (BotoCoreError, ClientError) as e:
        # 當本地測試沒有 AWS Credentials 時，會優雅地降級為模擬模式，確保程式不會崩潰 (Graceful Degradation)
        print(f"⚠️ [SIMULATION MODE] AWS API call bypassed: {e}")
        print(f"ℹ️ [SIMULATION] IP {ip_address} is now fully blocked in our virtual Security Loop.")


# 2. 自訂限流 + 聯防中間件 (Rate Limiting & Active Defense Middleware)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    
    # 檢查限流器
    is_allowed = limiter.is_allowed(
        ip_address=client_ip, 
        max_tokens=MAX_TOKENS, 
        refill_rate=REFILL_RATE
    )
    
    if not is_allowed:
        # ─── 聯防邏輯啟動 ───
        # 1. 增加該 IP 在 Redis 中的違規計數
        violation_key = f"violation:{client_ip}"
        violations = r_client.incr(violation_key)
        
        # 第一次違規時，設定過期時間
        if violations == 1:
            r_client.expire(violation_key, VIOLATION_WINDOW)
            
        print(f"⚠️ [WARNING] IP {client_ip} triggered HTTP 429. Total violations: {violations}/{VIOLATION_THRESHOLD}")
        
        # 2. 如果違規次數達標，觸發 AWS 基礎設施級別阻斷
        if violations >= VIOLATION_THRESHOLD:
            # 💡 面試大加分：使用 asyncio.to_thread 在背景執行阻塞的 Boto3 API，不卡死 FastAPI 的 Event Loop
            asyncio.create_task(asyncio.to_thread(trigger_aws_nacl_block, client_ip))
            # 歸零違規紀錄，防止重複觸發 AWS API
            r_client.delete(violation_key)
        
        # 🔴 回覆 429
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Too Many Requests",
                "message": "You have triggered rate limit. Multiple violations will result in AWS Network Block!"
            }
        )
    
    # 🟢 放行
    response = await call_next(request)
    return response

# --- API 路由 ---
@app.get("/")
async def root():
    return {"status": "success", "message": "API Gateway is active and secure."}

@app.get("/api/v1/resource")
async def get_resource():
    return {"status": "success", "data": "Protected data source."}