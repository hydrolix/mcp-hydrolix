"""Configuration and LLM setup."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings
from langchain_openai import ChatOpenAI


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Server Configuration
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    cors_origins: list[str] = ["*"]
    config_path: str = "./agent.local.yaml"

    # Agent Configuration
    max_iterations: int = 10
    max_retries: int = 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_llm(streaming: bool = True) -> ChatOpenAI:
    """Get configured LLM instance."""
    from hdx_agent.config import Config
    from hdx_agent.graphs.llm import create_graph_models

    conf = Config()
    assistant_model, summary_model, summarization_node, embedding_model  = create_graph_models(conf)
    return assistant_model

    # settings = get_settings()
    # return ChatOpenAI(
    #     model=settings.openai_model,
    #     temperature=settings.openai_temperature,
    #     api_key=settings.openai_api_key,
    #     streaming=streaming,
    # )
