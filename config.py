import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "OpenAI Celery API"
    
    # OpenAI API configuration
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    
    # Redis configuration
    REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT: str = os.getenv('REDIS_PORT', '6379')
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    
    # Celery configuration
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    #Azure openai configurations
    AZURE_OPENAI_KEY: str = os.getenv('AZURE_OPENAI_KEY')
    AZURE_OPENAI_ENDPOINT: str = os.getenv('AZURE_OPENAI_ENDPOINT')
    AZURE_OPENAI_DEPLOYEMENT_NAME: str = os.getenv('AZURE_OPENAI_DEPLOYEMENT_NAME')


settings = Settings() 