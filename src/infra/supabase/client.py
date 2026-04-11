"""
Cliente Supabase -- usado pelo bot para inserir e consultar trades.
Utiliza a anon key (SUPABASE_KEY).
"""

from src.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client
from dotenv import load_dotenv
from src.infra import setup_logging

load_dotenv()


log = setup_logging()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
