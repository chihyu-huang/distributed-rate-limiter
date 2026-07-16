from locust import HttpUser, task, between

class APIStormUser(HttpUser):
    # 每個虛擬用戶每次請求之間，隨機停頓 0.1 到 0.5 秒 (模擬極快的點擊速度)
    wait_time = between(0.1, 0.5)

    @task
    def access_expensive_resource(self):
        # 這些虛擬用戶會瘋狂造訪我們那個昂貴的 API 路由
        self.client.get("/api/v1/resource")