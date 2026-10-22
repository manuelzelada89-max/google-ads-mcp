"""Persistent, encrypted OAuth proxy storage for Cloud Run (Firestore).

Compatible with the Firestore key sanitization approach already used by
this repository's Google Ads MCP, but with independent environment variables.
"""
import os
from typing import Any


def create_client_storage() -> Any:
    storage_type = os.getenv("MEASUREMENT_MCP_STORAGE_TYPE", "firestore").lower()
    if storage_type == "memory":
        if os.getenv("K_SERVICE"):
            raise RuntimeError("Never use in-memory OAuth storage on Cloud Run")
        from key_value.aio.stores.memory import MemoryStore
        store = MemoryStore()
    elif storage_type == "firestore":
        from key_value.aio.stores.firestore import (
            FirestoreStore,
            FirestoreV1CollectionSanitizationStrategy,
            FirestoreV1KeySanitizationStrategy,
        )
        store = FirestoreStore(
            project=os.getenv("MEASUREMENT_MCP_FIRESTORE_PROJECT") or None,
            database=os.getenv("MEASUREMENT_MCP_FIRESTORE_DATABASE") or "(default)",
            key_sanitization_strategy=FirestoreV1KeySanitizationStrategy(),
            collection_sanitization_strategy=FirestoreV1CollectionSanitizationStrategy(),
        )
    else:
        raise RuntimeError("Supported OAuth storage: firestore or local memory")

    secret = (os.getenv("MEASUREMENT_MCP_STORAGE_ENCRYPTION_KEY")
              or os.getenv("MEASUREMENT_MCP_JWT_SIGNING_KEY"))
    if not secret:
        raise RuntimeError("OAuth store encryption requires JWT_SIGNING_KEY or a dedicated key")

    from cryptography.fernet import Fernet
    from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper
    from fastmcp.server.auth.oauth_proxy.proxy import derive_jwt_key

    try:
        key = Fernet(secret.encode())
    except (ValueError, TypeError):
        key = Fernet(derive_jwt_key(
            high_entropy_material=secret,
            salt="fastmcp-storage-encryption-key",
        ))
    return FernetEncryptionWrapper(
        key_value=store,
        fernet=key,
        raise_on_decryption_error=False,
    )
