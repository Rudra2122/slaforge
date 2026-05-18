from locust import HttpUser, task, between
import random

# Pre-create 3 tenants via the API and paste their keys here
TENANT_KEYS = {
    "realtime": "sf_JVVT4ufrIh9XCixaB_VcUQVfD5mZQ0UoG5tXF0n9dTk",
    "standard": "sf_cl8uRj3VCqSEDSU0dph9aK8KrWoTgPmXr35eYEIoDEk",
    "batch":    "sf_nk5D25onaYNxZdZiK43WZYyOEVK-Tcoka8-1y7QFBz4",
}

PROMPTS = [
    "Explain the concept of neural networks in simple terms.",
    "What are the key differences between REST and GraphQL?",
    "Summarize the main causes of the 2008 financial crisis.",
    "Write a Python function to check if a string is a palindrome.",
    "What is the capital of France and why is it historically significant? " * 10,  # long prompt
]

class RealtimeTenant(HttpUser):
    wait_time = between(0.1, 0.5)
    weight = 2

    @task
    def infer(self):
        self.client.post(
            "/inference/",
            json={"prompt": random.choice(PROMPTS), "max_tokens": 64},
            headers={"X-API-Key": TENANT_KEYS["realtime"]},
        )

class StandardTenant(HttpUser):
    wait_time = between(0.5, 2)
    weight = 5

    @task
    def infer(self):
        self.client.post(
            "/inference/",
            json={"prompt": random.choice(PROMPTS), "max_tokens": 128},
            headers={"X-API-Key": TENANT_KEYS["standard"]},
        )

class BatchTenant(HttpUser):
    wait_time = between(2, 5)
    weight = 3

    @task
    def infer(self):
        self.client.post(
            "/inference/",
            json={"prompt": random.choice(PROMPTS), "max_tokens": 256},
            headers={"X-API-Key": TENANT_KEYS["batch"]},
        )