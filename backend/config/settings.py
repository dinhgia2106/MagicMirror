"""
Configuration settings for the Holiday API Backend.
Load settings from config.env file or environment variables.
"""

import os

# Try to load from config.env file
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.env')
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# Server settings
HOST = os.getenv('HOLIDAY_API_HOST', '0.0.0.0')
PORT = int(os.getenv('HOLIDAY_API_PORT', 8000))
DEBUG = os.getenv('HOLIDAY_API_DEBUG', 'false').lower() == 'true'

# Data file paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HOLIDAYS_FILE = os.getenv('HOLIDAYS_FILE', os.path.join(DATA_DIR, 'holidays.json'))

# CORS settings
CORS_ORIGINS_STR = os.getenv('CORS_ORIGINS', '*')
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(',')] if CORS_ORIGINS_STR != '*' else ['*']

