"""
Cliente Supabase -- usado pelo bot para inserir e consultar trades.
Utiliza a anon key (SUPABASE_KEY).
"""

from src.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client
import logging
from dotenv import load_dotenv

load_dotenv()


log = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
