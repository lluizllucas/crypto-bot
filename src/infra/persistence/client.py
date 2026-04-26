"""
Cliente Supabase -- usado pelo bot para inserir e consultar trades.
Utiliza a anon key (SUPABASE_KEY).
"""

from src.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
log = logging.getLogger("bot")

load_dotenv()


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
