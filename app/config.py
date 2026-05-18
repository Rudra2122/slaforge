from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str = "HS256"
    small_model_id: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    large_model_id: str = "garage-bAInd/Platypus2-70B-instruct"
    use_mock_models: bool = True
    small_model_cost_per_1k: float = 0.0002
    large_model_cost_per_1k: float = 0.0008

    class Config:
        env_file = ".env"

settings = Settings()