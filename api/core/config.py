import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings using Pydantic Settings"""
    
    # Database settings
    db_path: str = Field(default="/mnt/efs/cocktaildb.db", description="Path to SQLite database")
    
    # AWS settings
    aws_region: str = Field(default="us-east-1", description="AWS region")
    user_pool_id: str = Field(default="", description="Cognito User Pool ID")
    app_client_id: str = Field(default="", description="Cognito App Client ID")
    
    # API settings
    api_title: str = Field(default="Cocktail DB API", description="API title")
    api_version: str = Field(default="1.0.0", description="API version")
    api_description: str = Field(default="API for managing cocktail recipes and ingredients")
    
    # CORS settings
    cors_origins: list[str] = Field(default=["*"], description="CORS allowed origins")
    cors_credentials: bool = Field(default=True, description="CORS allow credentials")
    cors_methods: list[str] = Field(default=["*"], description="CORS allowed methods")
    cors_headers: list[str] = Field(default=["*"], description="CORS allowed headers")
    
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
        
        # Try to get Cognito config from CloudFormation if not provided
        if not self.user_pool_id or not self.app_client_id:
            self._load_cognito_config_from_cfn()
    
    def _load_cognito_config_from_cfn(self):
        """Load Cognito configuration from CloudFormation stack outputs"""
        try:
            import boto3
            import logging
            
            logger = logging.getLogger(__name__)
            
            cfn = boto3.client("cloudformation", region_name=self.aws_region)
            stack_name = os.environ.get(
                "AWS_SAM_STACK_NAME",
                os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").rsplit("-", 1)[0],
            )
            
            if stack_name:
                response = cfn.describe_stacks(StackName=stack_name)
                if (
                    "Stacks" in response
                    and response["Stacks"]
                    and "Outputs" in response["Stacks"][0]
                ):
                    outputs = response["Stacks"][0]["Outputs"]
                    for output in outputs:
                        if "OutputKey" in output and "OutputValue" in output:
                            if output["OutputKey"] == "UserPoolId" and not self.user_pool_id:
                                self.user_pool_id = output["OutputValue"]
                            elif output["OutputKey"] == "UserPoolClientId" and not self.app_client_id:
                                self.app_client_id = output["OutputValue"]
                                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to retrieve Cognito config from CloudFormation: {str(e)}")


# Global settings instance
settings = Settings()