from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings
import logging

logger = logging.getLogger(__name__)

class DatabaseConnection:
    client: AsyncIOMotorClient = None
    db = None

db_conn = DatabaseConnection()

async def connect_to_mongo():
    logger.info("Connecting to MongoDB Atlas...")
    try:
        db_conn.client = AsyncIOMotorClient(
            settings.mongodb_uri,
            # Set a connection timeout to fail-fast if Atlas is unreachable
            serverSelectionTimeoutMS=5000
        )
        db_conn.db = db_conn.client[settings.mongodb_database]
        # Force a connection check
        await db_conn.client.server_info()
        logger.info("Successfully connected to MongoDB Atlas.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        # Raise connection error; do not fall back to in-memory state
        raise e

async def close_mongo_connection():
    logger.info("Closing MongoDB Atlas connection...")
    if db_conn.client:
        db_conn.client.close()
        logger.info("MongoDB connection closed.")

def get_database():
    if db_conn.db is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo was executed.")
    return db_conn.db
