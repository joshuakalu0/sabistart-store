import paramiko

HOST = "ssh-sabistart.alwaysdata.net"
PORT = 22
USERNAME = "sabistart"
PASSWORD = "Joshua.24-df"
REMOTE_ROOT = "/home/sabistart/www/django"

def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    return ssh

def main():
    env_content = """DJANGO_SECRET_KEY=exzqjaP8LndPkQd0HmzNhdi7PRlLeMRX-YVZuDfcoNTjDl2zyjCIP-M0is_9lQNmOXEKsjFRsIEWvBxUbkbF-A
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=sabistart.store,www.sabistart.store,.sabistart.store,ssh-sabistart.alwaysdata.net,sabistart.alwaysdata.net,.alwaysdata.net,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://sabistart.store,https://www.sabistart.store,https://*.sabistart.store,https://ssh-sabistart.alwaysdata.net,https://sabistart.alwaysdata.net
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

PLATFORM_CNAME=sabistart.store
SUBDOMAIN_SUFFIX=.sabistart.store
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

DJANGO_DEFAULT_FROM_EMAIL=no-reply@sabistart.store
DJANGO_SERVER_EMAIL=no-reply@sabistart.store
"""
    ssh = create_ssh_client()
    cmd = f'cat > {REMOTE_ROOT}/.env << \'ENVEOF\'\n{env_content}ENVEOF'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.read()
    ssh.close()
    print("Updated .env on server with production domain settings.")

if __name__ == "__main__":
    main()
