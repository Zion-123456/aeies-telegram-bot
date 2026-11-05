"""Lazy Supabase client; importing this module performs no network operations."""
from supabase import Client, create_client

from aeies.config import Settings


def create_database_client(settings: Settings) -> Client:
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("Set SUPABASE_URL and SUPABASE_KEY before using the database")
    return create_client(settings.supabase_url, settings.supabase_key)
