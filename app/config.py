import os
from pathlib import Path
from functools import lru_cache
import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nvidia_api_key: str = "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"
    nim_model: str = "nvidia/nemotron-3-nano-30b-a3b"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    nim_reasoning_budget: int = 4096  # tokens for nemotron thinking

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_yaml_config() -> dict:
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f)
    return {}


def cfg(key_path: str, default=None):
    """Dot-path accessor for config.yaml, e.g. cfg('ttl.alerts_sec')."""
    parts = key_path.split(".")
    node = get_yaml_config()
    for part in parts:
        if not isinstance(node, dict):
            return default
        node = node.get(part, default)
    return node
