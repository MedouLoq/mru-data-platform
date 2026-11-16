from scraper import scraper_flow
from services.sync_mongo.sync import sync_flow
from services.ml_service.train import training_flow  # Import your new flow
from prefect import flow

if __name__ == "__main__":
    print("Builder: Starting master deployment registration...")

    # 1. Scraper
    scraper_flow.from_source(
        source="/code", 
        entrypoint="scraper.py:scraper_flow"
    ).deploy(
        name="Daily Data Acquisition",
        work_pool_name="default-agent-pool",
        cron="0 0 * * *",
    )

    # 2. NoSQL Sync
    sync_flow.from_source(
        source="/code", 
        entrypoint="services/sync_mongo/sync.py:sync_flow"
    ).deploy(
        name="Hourly NoSQL Sync",
        work_pool_name="default-agent-pool",
        cron="0 * * * *",
    )

    # 3. ML Training (New!)
    training_flow.from_source(
        source="/code", 
        entrypoint="services/ml_service/train.py:training_flow"
    ).deploy(
        name="Weekly ML Retraining",
        work_pool_name="default-agent-pool",
        cron="0 0 * * 0", # Runs every Sunday at midnight
    )

    print("🚀 All 3 Pipelines (Scraping, Sync, Training) are now Orchestrated!")