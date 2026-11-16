import os
import sys
import logging
from datetime import datetime
import psycopg2
from pymongo import MongoClient
from psycopg2.extras import RealDictCursor
from prefect import flow, task

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@task(retries=2, retry_delay_seconds=30)
def fetch_from_pg():
    """Task to pull data from PostgreSQL."""
    pg_config = {
        'host': os.getenv('DB_HOST', 'db'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'currency_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD')
    }
    
    try:
        conn = psycopg2.connect(**pg_config)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT p.id, a.code as asset_code, a.name as asset_name,
                       a.category as asset_category, p.date, p.value_mru, p.source
                FROM app_price p
                JOIN app_asset a ON p.asset_id = a.id
                ORDER BY p.date DESC, a.code
            """
            cursor.execute(query)
            prices = cursor.fetchall()
            conn.close()
            logger.info(f"Fetched {len(prices)} records from PostgreSQL")
            return prices
    except Exception as e:
        logger.error(f"PostgreSQL Fetch Error: {e}")
        raise

@task
def sync_to_mongo(prices):
    """Task to push data to MongoDB."""
    if not prices:
        return 0
    
    mongo_url = os.environ['MONGO_URL']  # e.g. mongodb://user:password@mongo:27017/ (set in .env)
    client = MongoClient(mongo_url)
    db = client['currency_db']
    collection = db['prices']
    
    synced_count = 0
    for price in prices:
        try:
            doc = {
                'postgres_id': price['id'],
                'asset_code': price['asset_code'],
                'asset_name': price['asset_name'],
                'asset_category': price['asset_category'],
                'date': str(price['date']),
                'price_mru': float(price['value_mru']),
                'source': price['source'],
                'synced_at': datetime.utcnow()
            }
            collection.update_one(
                {'postgres_id': price['id']},
                {'$set': doc},
                upsert=True
            )
            synced_count += 1
        except Exception as e:
            logger.error(f"Mongo Sync Error on ID {price.get('id')}: {e}")
            
    logger.info(f"Sync complete. {synced_count} records updated in MongoDB.")
    return synced_count

@flow(name="Postgres to Mongo Sync Flow")
def sync_flow():
    """Main Orchestrator Flow for NoSQL Sync."""
    logger.info("Starting NoSQL Synchronization Pipeline...")
    data = fetch_from_pg()
    count = sync_to_mongo(data)
    return count

if __name__ == "__main__":
    # For local testing
    sync_flow()