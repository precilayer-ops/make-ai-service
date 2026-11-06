import logging
from typing import Any, Optional, Set
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import settings

logger = logging.getLogger("make_ai_service.db")


class ReadOnlySecurityViolation(Exception):
    """Raised when any code attempts an unauthorized write operation on a read-only database."""
    pass


class ReadOnlyCollectionProxy:
    """
    Hard-boundary proxy intercepting any write, update, replace, or delete operations.
    Enforces the strict rule: NO WRITE OPERATIONS ALLOWED.
    """
    FORBIDDEN_OPERATIONS: Set[str] = {
        "insert_one", "insert_many",
        "update_one", "update_many",
        "replace_one",
        "delete_one", "delete_many",
        "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
        "drop", "drop_index", "drop_indexes",
        "bulk_write", "rename", "create_index", "create_indexes",
    }

    def __init__(self, collection: Any, db_name: str):
        self._collection = collection
        self._db_name = db_name

    @property
    def name(self) -> str:
        return self._collection.name

    def __getattr__(self, name: str) -> Any:
        if name in self.FORBIDDEN_OPERATIONS:
            def forbidden_write(*args, **kwargs):
                err_msg = (
                    f"[SECURITY VIOLATION - HARD RULE ENFORCED] "
                    f"Write operation '{name}' was BLOCKED on read-only database '{self._db_name}.{self._collection.name}'. "
                    f"Only READ operations (find, find_one, aggregate, count_documents) are permitted."
                )
                logger.error(err_msg)
                raise ReadOnlySecurityViolation(err_msg)
            return forbidden_write

        return getattr(self._collection, name)

    def __getitem__(self, name: str) -> Any:
        return getattr(self._collection, name)


class ReadOnlyDatabaseProxy:
    """
    Wraps an AsyncIOMotorDatabase so that all collection accesses are automatically
    intercepted and secured by ReadOnlyCollectionProxy.
    """
    def __init__(self, database: AsyncIOMotorDatabase):
        self._database = database

    @property
    def name(self) -> str:
        return self._database.name

    def __getitem__(self, collection_name: str) -> ReadOnlyCollectionProxy:
        coll = self._database[collection_name]
        return ReadOnlyCollectionProxy(coll, self._database.name)

    def __getattr__(self, name: str) -> Any:
        if name in ("drop_collection", "create_collection"):
            def forbidden_ddl(*args, **kwargs):
                raise ReadOnlySecurityViolation(
                    f"[SECURITY VIOLATION] Database schema operation '{name}' is strictly forbidden on '{self._database.name}'."
                )
            return forbidden_ddl

        attr = getattr(self._database, name)
        # If accessing collection as an attribute (e.g. db.quotes or db.suppliers)
        if hasattr(attr, "find") and hasattr(attr, "insert_one"):
            return ReadOnlyCollectionProxy(attr, self._database.name)
        return attr


class DatabaseManager:
    def __init__(self):
        self.erp_client: Optional[AsyncIOMotorClient] = None
        self.sc_client: Optional[AsyncIOMotorClient] = None
        self.mes_client: Optional[AsyncIOMotorClient] = None
        self.ai_client: Optional[AsyncIOMotorClient] = None

        # Protected read-only proxies
        self.erp_db: Optional[ReadOnlyDatabaseProxy] = None
        self.sc_db: Optional[ReadOnlyDatabaseProxy] = None
        self.mes_db: Optional[ReadOnlyDatabaseProxy] = None

        # AI Chat Database (Read-write for chat history, messages, and uploaded context)
        self.ai_db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self):
        """Initialize connection pools to MongoDB databases."""
        try:
            # 1. ERP Database (Strictly READ-ONLY query pool)
            if settings.ERP_MONGO_URI:
                self.erp_client = AsyncIOMotorClient(
                    settings.ERP_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                try:
                    raw_erp_db = self.erp_client.get_default_database()
                except Exception:
                    default_erp = "ndcs-make-local" if "ndcs" in settings.INSTANCE_NAME.lower() else "pipl-make-local"
                    raw_erp_db = self.erp_client[default_erp]
                self.erp_db = ReadOnlyDatabaseProxy(raw_erp_db)
                logger.info(f"Connected to ERP MongoDB database: {self.erp_db.name} [STRICT READ-ONLY ENFORCED]")

            # 2. SC (Supply Chain) Database (Strictly READ-ONLY query pool for suppliers, RFQs, POs)
            if settings.SC_MONGO_URI:
                self.sc_client = AsyncIOMotorClient(
                    settings.SC_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                try:
                    raw_sc_db = self.sc_client.get_default_database()
                except Exception:
                    default_sc_name = "ndcs-sc-local" if "ndcs" in settings.INSTANCE_NAME.lower() else "pipl-sc-local"
                    raw_sc_db = self.sc_client[default_sc_name]
                self.sc_db = ReadOnlyDatabaseProxy(raw_sc_db)
                logger.info(f"Connected to SC MongoDB database: {self.sc_db.name} [STRICT READ-ONLY ENFORCED]")

            # 3. MES Database (Strictly READ-ONLY query pool)
            if settings.MES_MONGO_URI:
                self.mes_client = AsyncIOMotorClient(
                    settings.MES_MONGO_URI,
                    maxPoolSize=20,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=5000,
                )
                try:
                    raw_mes_db = self.mes_client.get_default_database()
                except Exception:
                    raw_mes_db = self.mes_client["precilayer-mes-dev"]
                self.mes_db = ReadOnlyDatabaseProxy(raw_mes_db)
                logger.info(f"Connected to MES MongoDB database: {self.mes_db.name} [STRICT READ-ONLY ENFORCED]")

            # 4. AI Service Database (For chat history, saved quotes, cache)
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
