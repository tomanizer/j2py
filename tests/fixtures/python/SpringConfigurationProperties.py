from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    datasource_url: str = "jdbc:h2:mem:testdb"
    max_connections: int = 10

    model_config = SettingsConfigDict(env_prefix="APP_")


class ValueConsumer:
    def __init__(self) -> None:
        # TODO(j2py): @Value injection is hard to lower statically
        # @Value("${app.cache-seconds:512}") -> cacheSeconds
        # Replace with: cache_seconds: int = settings.cache_seconds
        self.cache_seconds: int = 512
        # TODO(j2py): @Value injection is hard to lower statically
        # @Value("${app.welcome-message:Welcome}") -> welcomeMessage
        # Replace with: welcome_message: str = settings.welcome_message
        self.welcome_message: str = "Welcome"
