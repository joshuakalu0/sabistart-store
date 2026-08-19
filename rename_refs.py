import os
import re

# Files to update - Python, shell, markdown, config files
extensions = {'.py', '.sh', '.md', '.jsonc', '.yaml', '.yml', '.ini', '.cfg', '.txt'}

# Directories to skip
skip_dirs = {'.git', '.venv', '__pycache__', 'node_modules', '.kilo', '.vscode', 'logs', 'media', 'tmp', 'staticfiles'}

replacements = 0

for root, dirs, files in os.walk('.'):
    # Skip unwanted directories
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    
    for filename in files:
        ext = os.path.splitext(filename)[1]
        if ext not in extensions:
            continue
            
        filepath = os.path.join(root, filename)
        
        # Skip binary-like files
        if filename.endswith(('.pyc', '.png', '.jpg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.pdf', '.zip', '.tar.gz')):
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Count occurrences before replacement
            count = content.count('sabistart')
            
            if count > 0:
                new_content = content.replace('sabistart', 'sabistart')
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}: {count} replacements")
                replacements += count
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

print(f"\nTotal replacements: {replacements}")
