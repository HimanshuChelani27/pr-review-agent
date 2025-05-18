from celery import Celery
from config import settings
celery_app = Celery(
    'openai_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['tasks.task']
)

# Configure Celery with Windows-specific settings
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes,
    worker_pool_restarts=True,
    worker_concurrency=1,  # Reduce concurrency for Windows
    worker_pool='solo',  # Use solo pool for Windows
)
