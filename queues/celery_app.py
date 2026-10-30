"""
Celery configuration for the queue system.
"""

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

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

# Periodic collection, run with: celery -A queues.celery_app beat
# Times are UTC. US markets close at 20:00/21:00 UTC depending on DST.
app.conf.beat_schedule = {
    'weather-every-3-hours': {
        'task': 'queues.tasks.collect_weather_job',
        'schedule': crontab(minute=7, hour='*/3'),
    },
    'prices-after-close': {
        'task': 'queues.tasks.collect_prices_job',
        'schedule': crontab(minute=30, hour=22, day_of_week='mon-fri'),
    },
    'news-daily': {
        'task': 'queues.tasks.collect_news_job',
        'schedule': crontab(minute=15, hour=12),
    },
    'sec-form4-daily': {
        'task': 'queues.tasks.collect_sec_form4_job',
        'schedule': crontab(minute=45, hour=23, day_of_week='mon-fri'),
    },
    'sec-8k-daily': {
        'task': 'queues.tasks.collect_sec_8k_job',
        'schedule': crontab(minute=15, hour=0, day_of_week='tue-sat'),
    },
    'train-model-daily': {
        'task': 'queues.tasks.train_model_job',
        'schedule': crontab(minute=0, hour=2, day_of_week='tue-sat'),
    },
}

if __name__ == '__main__':
    app.start()