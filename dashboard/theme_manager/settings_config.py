# Add these settings to your settings.py file

import os

# Theme System Settings
THEMES_ROOT = os.path.join(MEDIA_ROOT, 'themes')

# Ensure themes directories exist
os.makedirs(os.path.join(THEMES_ROOT, 'marketplace'), exist_ok=True)
os.makedirs(os.path.join(THEMES_ROOT, 'shops'), exist_ok=True)

# Add 'themes' to INSTALLED_APPS
INSTALLED_APPS = [
    # ... your existing apps
    'themes',
    # ... rest of your apps
]

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Theme file extensions allowed
THEME_ALLOWED_EXTENSIONS = ['.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg']

# Maximum theme zip file size (in bytes)
THEME_MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50MB