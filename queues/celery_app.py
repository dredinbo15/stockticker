"""
Celery configuration for the queue system.
"""

from celery import Celery
from config.credentials import get_credentials_manager

creds = get_credentials_manager()
redis_url = creds.get_credential('REDIS_URL', 'REDIS_URL', 'redis://localhost:6379/0')

app = Celery('stock_tracker',
             broker=redis_url,
             backend=redis_url,
             include=['queues.tasks'])

# Optional configuration
app.conf.update(
    result_expires=3600,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

if __name__ == '__main__':
    app.start()