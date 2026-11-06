import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from config import settings

logger = logging.getLogger("make_ai_service.db")

class DatabaseManager:
    def __init__(self):
        self.erp_client: Optional[AsyncIOMotorClient] = None
        self.sc_client: Optional[AsyncIOMotorClient] = None
        self.mes_client: Optional[AsyncIOMotorClient] = None
        self.ai_client: Optional[AsyncIOMotorClient] = None

        self.erp_db: Optional[AsyncIOMotorDatabase] = None
        self.sc_db: Optional[AsyncIOMotorDatabase] = None
        self.mes_db: Optional[AsyncIOMotorDatabase] = None
        self.ai_db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self):
        """Initialize connection pools to MongoDB databases."""
        try:
            # 1. ERP Database (Read-only query pool)
            if settings.ERP_MONGO_URI:
                self.erp_client = AsyncIOMotorClient(
                    settings.ERP_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                self.erp_db = self.erp_client.get_default_database()
                logger.info(f"Connected to ERP MongoDB database: {self.erp_db.name}")

            # 2. SC (Supply Chain) Database (Read-only query pool for suppliers, RFQs, POs)
            if settings.SC_MONGO_URI:
                self.sc_client = AsyncIOMotorClient(
                    settings.SC_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                try:
                    self.sc_db = self.sc_client.get_default_database()
                except Exception:
                    default_sc_name = "ndcs-sc-local" if "ndcs" in settings.INSTANCE_NAME.lower() else "pipl-sc-local"
                    self.sc_db = self.sc_client[default_sc_name]
                logger.info(f"Connected to SC MongoDB database: {self.sc_db.name}")

            # 3. MES Database (Read-only query pool)
            if settings.MES_MONGO_URI:
                self.mes_client = AsyncIOMotorClient(
                    settings.MES_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                self.mes_db = self.mes_client.get_default_database()
                logger.info(f"Connected to MES MongoDB database: {self.mes_db.name}")

            # 3. AI Service Database (For chat history, saved quotes, cache)
            if settings.AI_CHAT_MONGO_URI:
                self.ai_client = AsyncIOMotorClient(
                    settings.AI_CHAT_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                try:
                    self.ai_db = self.ai_client.get_default_database()
                except Exception:
                    default_db_name = "ndcs-ai-service-local" if "ndcs" in settings.INSTANCE_NAME.lower() else "pipl-ai-service-local"
                    self.ai_db = self.ai_client[default_db_name]
                logger.info(f"Connected to AI Chat MongoDB database: {self.ai_db.name}")

        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")

    async def disconnect(self):
        """Close all connection pools."""
        if self.erp_client:
            self.erp_client.close()
        if self.sc_client:
            self.sc_client.close()
        if self.mes_client:
            self.mes_client.close()
        if self.ai_client:
            self.ai_client.close()
        logger.info("All MongoDB connection pools closed.")

db_manager = DatabaseManager()
