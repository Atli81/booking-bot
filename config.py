import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(os.getenv('ADMIN_ID'))] if os.getenv('ADMIN_ID') else []
