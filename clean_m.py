import os
import shutil

def cleanup_project():
    base_dir = os.getcwd()
    # ADDED: Folders to strictly ignore
    ignored_folders = {'.venv', 'venv', 'env', '.git', '.idea', '.vscode'}

    print(f"Starting cleanup in: {base_dir}")

    for root, dirs, files in os.walk(base_dir):
        # MODIFIED: Skip the entire directory tree if it's in an ignored folder
        dirs[:] = [d for d in dirs if d not in ignored_folders]

        # 1. Delete all __pycache__ directories (Only in your app folders now)
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            print(f"Removing: {pycache_path}")
            shutil.rmtree(pycache_path)

        # 2. Delete migration files (Only in your app folders now)
        if os.path.basename(root) == 'migrations':
            for file in files:
                if file != '__init__.py' and file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    print(f"Deleting migration: {file_path}")
                    os.remove(file_path)

        # 3. Delete standalone .pyc files
        for file in files:
            if file.endswith('.pyc'):
                os.remove(os.path.join(root, file))

    print("\nCleanup Complete. Environment folders were protected.")

if __name__ == "__main__":
    cleanup_project()