import time
import redis

class TokenBucketLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        
        # 這是我們寫給 Redis 保鏢的 Lua 腳本
        # KEYS[1]: 限流的 Key (例如 limiter:185.220.101.5)
        # ARGV[1]: 桶子最大容量 (max_tokens)
        # ARGV[2]: 補水速率 (refill_rate, 每秒補多少 token)
        # ARGV[3]: 本次請求消耗的 token 數 (通常是 1)
        # ARGV[4]: 當前的 Unix 時間戳記 (秒)
        self.lua_script = """
        local key = KEYS[1]
        local max_tokens = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local req_tokens = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        -- 1. 取得該 IP 目前的狀態 (賸餘 Token 數, 上次更新時間)
        local state = redis.call('HMGET', key, 'tokens', 'last_updated')
        local tokens = tonumber(state[1])
        local last_updated = tonumber(state[2])

        if not tokens then
            -- 第一次來，把桶子裝滿
            tokens = max_tokens
            last_updated = now
        else
            -- 2. 惰性填充 (Lazy Refill)：計算時間差，並補上對應的 Token
            local elapsed = now - last_updated
            if elapsed > 0 then
                tokens = math.min(max_tokens, tokens + (elapsed * refill_rate))
                last_updated = now
            end
        end

        -- 3. 判斷 Token 是否夠用
        if tokens >= req_tokens then
            tokens = tokens - req_tokens
            -- 更新 Redis 中的狀態
            redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
            -- 設定 1 小時過期時間，防止沒再造訪的 IP 佔用 Redis 記憶體 (Memory Leak)
            redis.call('EXPIRE', key, 3600)
            return 1 -- 🟢 允許放行 (Allowed)
        else
            -- Token 不夠，拒絕請求，但依然更新時間戳記防止時間漂移
            redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
            redis.call('EXPIRE', key, 3600)
            return 0 -- 🔴 攔截並限流 (Rate Limited)
        end
        """
        # 註冊 Lua 腳本到 Redis，提升執行效率
        self.lua_trigger = self.redis.register_script(self.lua_script)

    def is_allowed(self, ip_address: str, max_tokens: int, refill_rate: float, cost: int = 1) -> bool:
        """
        判斷該 IP 是否允許通過
        """
        key = f"limiter:{ip_address}"
        now = time.time()
        
        # 呼叫 Lua 腳本，保證操作的原子性 (Atomicity)
        result = self.lua_trigger(
            keys=[key],
            args=[max_tokens, refill_rate, cost, now]
        )
        return result == 1
    



if __name__ == "__main__":
    # 連線到本地運行的 Redis Container
    r_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    limiter = TokenBucketLimiter(r_client)
    
    test_ip = "192.168.1.100"
    
    # 清除舊的測試資料
    r_client.delete(f"limiter:{test_ip}")
    
    # 配置：桶子容量 5 個 Token，每秒補 1 個 Token (Refill Rate = 1.0)
    max_cap = 5
    refill_r = 1.0
    
    print("🔥 --- 模擬高併發 Brute-force 攻擊（瞬間打入 8 次請求） ---")
    for i in range(1, 9):
        allowed = limiter.is_allowed(test_ip, max_cap, refill_r)
        status = "🟢 ALLOW" if allowed else "🔴 RATE_LIMITED (HTTP 429)"
        print(f"Request {i}: {status}")
        
    print("\n😴 --- 暫停 2.5 秒，等待 Token 慢慢補回 ---")
    time.sleep(2.5)
    
    print("\n⚡ --- 再次發動第二波請求 ---")
    for i in range(1, 4):
        allowed = limiter.is_allowed(test_ip, max_cap, refill_r)
        status = "🟢 ALLOW" if allowed else "🔴 RATE_LIMITED (HTTP 429)"
        print(f"Request {i}: {status}")