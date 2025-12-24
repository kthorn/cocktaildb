from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings using Pydantic Settings"""
    
    # Database settings (PostgreSQL)
    db_host: str = Field(default="localhost", description="PostgreSQL host")
    db_port: str = Field(default="5432", description="PostgreSQL port")
    db_name: str = Field(default="cocktaildb", description="PostgreSQL database name")
    db_user: str = Field(default="cocktaildb", description="PostgreSQL user")
    db_password: str = Field(default="", description="PostgreSQL password")
    
    # AWS settings
    aws_region: str = Field(default="us-east-1", description="AWS region")
    user_pool_id: str = Field(default="", description="Cognito User Pool ID", env="USER_POOL_ID")
    app_client_id: str = Field(default="", description="Cognito App Client ID", env="APP_CLIENT_ID")
    
    # API settings
    api_title: str = Field(default="Cocktail DB API", description="API title")
    api_version: str = Field(default="1.0.0", description="API version")
    api_description: str = Field(default="API for managing cocktail recipes and ingredients")
    
    # Environment
    environment: str = Field(default="dev", description="Environment (dev/prod)")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = ""
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Config initialized - user_pool_id: {self.user_pool_id[:10] + '...' if self.user_pool_id else 'MISSING'}, app_client_id: {self.app_client_id[:10] + '...' if self.app_client_id else 'MISSING'}")
        
        if not self.user_pool_id or not self.app_client_id:
            logger.warning(
                "Cognito configuration is missing; set USER_POOL_ID and APP_CLIENT_ID."
            )


# Global settings instance
settings = Settings()
