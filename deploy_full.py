import os
import tarfile
import paramiko

HOST = "ssh-sabistart.alwaysdata.net"
PORT = 22
USERNAME = "sabistart"
PASSWORD = "Joshua.24-df"
REMOTE_ROOT = "/home/sabistart/www/django"
LOCAL_ROOT = "."
TAR_PATH = os.path.join(LOCAL_ROOT, "_sabistart_deploy.tar.gz")

EXCLUDE_DIRS = {
    '.git', '.venv', 'env', '__pycache__', 'node_modules',
    '.kilo', '.vscode', '.opencode', 'logs', 'media', 'tmp',
    'staticfiles', '.cache',
}
EXCLUDE_FILES = {
    '.env', '.env.local', 'deploy_sftp.py', 'rename_refs.py',
    'deploy_full.py', 'sync_config.jsonc',
    '_sabistart_deploy.tar.gz', 'nul',
}
EXCLUDE_EXTENSIONS = {
    '.pyc', '.pyo', '.pyd', '.sqlite3', '.sqlite3-journal',
    '.egg', '.whl', '.zip', '.tar.gz', '.gz',
}

def should_exclude(path):
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    filename = os.path.basename(path)
    if filename in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(filename)
    if ext in EXCLUDE_EXTENSIONS:
        return True
    return False

def create_tar():
    print("Creating deployment tar.gz...")
    with tarfile.open(TAR_PATH, "w:gz", compresslevel=1) as tf:
        for root, dirs, files in os.walk(LOCAL_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                local_path = os.path.join(root, file)
                if should_exclude(local_path):
                    continue
                arcname = os.path.relpath(local_path, LOCAL_ROOT)
                tf.add(local_path, arcname=arcname)
    size = os.path.getsize(TAR_PATH)
    print(f"Tar created: {TAR_PATH} ({size / 1024 / 1024:.1f} MB)")

def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    return ssh

def upload_tar():
    print("\nUploading tar.gz to server...")
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()
    remote_tar = f"{REMOTE_ROOT}/_sabistart_deploy.tar.gz"
    sftp.put(TAR_PATH, remote_tar)
    sftp.close()
    ssh.close()
    print(f"Uploaded to {remote_tar}")

def extract_and_cleanup():
    print("\nExtracting on server...")
    ssh = create_ssh_client()
    cmds = [
        f'cd {REMOTE_ROOT} && tar -xzf _sabistart_deploy.tar.gz',
        f'rm -f {REMOTE_ROOT}/_sabistart_deploy.tar.gz',
        f'mkdir -p {REMOTE_ROOT}/staticfiles {REMOTE_ROOT}/media {REMOTE_ROOT}/logs',
    ]
    for cmd in cmds:
        print(f"  Running: {cmd[:100]}...")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if out.strip(): print(f"    OUT: {out.strip()[:300]}")
        if err.strip(): print(f"    ERR: {err.strip()[:300]}")
    ssh.close()
    print("Extracted and cleaned up.")

def setup_env():
    print("\nCreating .env on server...")
    env_content = """DJANGO_SECRET_KEY=exzqjaP8LndPkQd0HmzNhdi7PRlLeMRX-YVZuDfcoNTjDl2zyjCIP-M0is_9lQNmOXEKsjFRsIEWvBxUbkbF-A
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=ssh-sabistart.alwaysdata.net,sabistart.alwaysdata.net,.alwaysdata.net,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://ssh-sabistart.alwaysdata.net,https://sabistart.alwaysdata.net
DJANGO_LANGUAGE_CODE=en-us
DJANGO_TIME_ZONE=UTC

DB_ENGINE=django_tenants.postgresql_backend
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_CONN_MAX_AGE=60
DB_SSLMODE=require

DATABASE_URL=postgresql://neondb_owner:npg_sDiORl2UK3Bj@ep-fancy-hat-apy67q1y-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
DATABASE_URL_UNPOOLED=postgresql://neondb_owner:npg_sDiORl2UK3Bj@ep-fancy-hat-apy67q1y.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

DJANGO_STATIC_ROOT=/home/sabistart/www/django/staticfiles
DJANGO_STATIC_URL=/static/
DJANGO_MEDIA_ROOT=/home/sabistart/www/django/media
DJANGO_MEDIA_URL=/media/
DJANGO_LOG_TO_FILE=True
DJANGO_LOG_DIR=/home/sabistart/www/django/logs
DJANGO_LOG_LEVEL=INFO
DJANGO_DEFAULT_FILE_STORAGE=

PLATFORM_CNAME=sabistart.alwaysdata.net
SUBDOMAIN_SUFFIX=.alwaysdata.net
SERVER_IP=127.0.0.1
DOMAIN_RESOLUTION_CACHE_TTL=300
DOMAIN_SIMULATE_INFRA=False

DJANGO_USE_X_FORWARDED_HOST=True
DJANGO_USE_X_FORWARDED_PORT=True
DJANGO_TRUST_X_FORWARDED_PROTO=True
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
DJANGO_SECURE_CONTENT_TYPE_NOSNIFF=True
DJANGO_SECURE_REFERRER_POLICY=same-origin
DJANGO_X_FRAME_OPTIONS=SAMEORIGIN

DJANGO_DEFAULT_FROM_EMAIL=no-reply@sabistart.alwaysdata.net
DJANGO_SERVER_EMAIL=no-reply@sabistart.alwaysdata.net
"""
    ssh = create_ssh_client()
    cmd = f'cat > {REMOTE_ROOT}/.env << \'ENVEOF\'\n{env_content}ENVEOF'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.read()
    ssh.close()
    print("Created .env on server.")

def install_requirements():
    print("\nInstalling requirements...")
    ssh = create_ssh_client()
    cmd = f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/pip install -r requirements.txt'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip()[-3000:])
    if err.strip(): print('ERR:', err.strip()[-3000:])
    ssh.close()

def run_migrations():
    print("\nRunning migrations...")
    ssh = create_ssh_client()
    cmd = f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/python manage.py migrate --noinput'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip()[-3000:])
    if err.strip(): print('ERR:', err.strip()[-3000:])
    ssh.close()

def collect_static():
    print("\nCollecting static files...")
    ssh = create_ssh_client()
    cmd = f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/python manage.py collectstatic --noinput'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip()[-3000:])
    if err.strip(): print('ERR:', err.strip()[-3000:])
    ssh.close()

def cleanup_local():
    if os.path.exists(TAR_PATH):
        os.remove(TAR_PATH)
        print(f"\nRemoved local tar: {TAR_PATH}")

def main():
    try:
        create_tar()
        upload_tar()
        extract_and_cleanup()
        setup_env()
        install_requirements()
        run_migrations()
        collect_static()
        print("\n" + "="*50)
        print("DEPLOYMENT COMPLETE")
        print("="*50)
        print("Restart the app in alwaysdata admin panel.")
    finally:
        cleanup_local()

if __name__ == "__main__":
    main()
