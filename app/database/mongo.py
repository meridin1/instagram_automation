from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_db():
    global _client, _database
    _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    await _client.admin.command("ping")
    _database = _client[settings.mongodb_db]


async def close_db():
    global _client, _database
    if _client:
        _client.close()
    _client = None
    _database = None


def db() -> AsyncIOMotorDatabase:
    if _database is None:
        raise RuntimeError("Database is not connected")
    return _database


async def ensure_indexes():
    database = db()
    # This is a shared-platform-key architecture: remove legacy per-client LLM keys.
    await database.clients.update_many({}, {"$unset": {"llm_api_key_encrypted": "", "llm_api_key": ""}})
    await database.clients.create_index("instagram_username", unique=True, sparse=True)
    await database.users.create_index("email", unique=True)
    # MongoDB partial indexes do not support $ne. Remove legacy empty-string values first,
    # then enforce uniqueness only when sku is actually a string.
    await database.products.update_many({"sku": ""}, {"$unset": {"sku": ""}})
    await database.messages.update_many({"external_message_id": ""}, {"$unset": {"external_message_id": ""}})
    await database.products.create_index([("client_id", 1), ("sku", 1)], unique=True, partialFilterExpression={"sku": {"$type": "string"}}, name="client_sku_unique")
    await database.products.create_index([("client_id", 1), ("active", 1)])
    await database.products.create_index([("client_id", 1), ("category", 1)])
    await database.products.create_index([("client_id", 1), ("name", 1)])
    # Encrypt any legacy Instagram tokens that were stored in plaintext by older builds.
    from app.services.secret_service import encrypt_secret
    legacy_tokens = database.instagram_accounts.find({"access_token": {"$type": "string", "$ne": ""}, "access_token_encrypted": {"$exists": False}})
    async for account in legacy_tokens:
        await database.instagram_accounts.update_one({"_id": account["_id"]}, {"$set": {"access_token_encrypted": encrypt_secret(account["access_token"])}, "$unset": {"access_token": ""}})
    await database.instagram_accounts.create_index("instagram_user_id", unique=True, name="instagram_account_global_unique")
    await database.conversations.create_index([("client_id", 1), ("sender_id", 1)], unique=True)
    await database.messages.create_index([("client_id", 1), ("conversation_id", 1), ("created_at", -1)])
    await database.messages.create_index([("client_id", 1), ("external_message_id", 1)], unique=True, partialFilterExpression={"external_message_id": {"$type": "string"}}, name="client_external_message_unique")
    await database.product_mappings.create_index([("client_id", 1), ("instagram_media_id", 1)], unique=True)
    await database.business_settings.create_index("client_id", unique=True)
    await database.automation_settings.create_index("client_id", unique=True)
    await database.client_usage.create_index([("client_id", 1), ("month", 1)], unique=True)
    await database.client_usage_totals.create_index("client_id", unique=True)
    await database.client_rate_windows.create_index([("client_id", 1), ("window", 1)], unique=True)
    await database.client_rate_windows.create_index("created_at", expireAfterSeconds=7200)
    await database.llm_usage_events.create_index([("client_id", 1), ("created_at", -1)])
