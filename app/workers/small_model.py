import time
import asyncio
from app.config import settings

# ── Mock mode (for local dev without downloading models) ──────────────────────
class MockSmallModel:
    async def generate(self, prompt: str, max_tokens: int) -> dict:
        return {
            "text": f"[SmallModel mock response to: {prompt[:40]}...]",
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": max_tokens // 4,
            "latency_ms": 5.0,
            "model": "small",
        }

# ── Real AirLLM mode ──────────────────────────────────────────────────────────
class RealSmallModel:
    def __init__(self):
        from airllm import AutoModel
        self.model = AutoModel.from_pretrained(settings.small_model_id)

    async def generate(self, prompt: str, max_tokens: int) -> dict:
        start = time.time()
        loop = asyncio.get_event_loop()

        def _infer():
            tokens = self.model.tokenizer(
                [prompt],
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=False,
            )
            out = self.model.generate(
                tokens["input_ids"],
                max_new_tokens=max_tokens,
                use_cache=True,
                return_dict_in_generate=True,
            )
            return self.model.tokenizer.decode(out.sequences[0])

        result_text = await loop.run_in_executor(None, _infer)
        latency = (time.time() - start) * 1000

        return {
            "text": result_text,
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": max_tokens,
            "latency_ms": latency,
            "model": "small",
        }

# Factory
def get_small_model():
    if settings.use_mock_models:
        return MockSmallModel()
    return RealSmallModel()

small_model = get_small_model()