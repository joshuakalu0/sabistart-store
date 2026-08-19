import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('ssh-sabistart.alwaysdata.net', port=22, username='sabistart', password='Joshua.24-df')

# 1. Update .env to use sabistart.store as primary domain
env_content = """DJANGO_SECRET_KEY=exzqjaP8LndPkQd0HmzNhdi7PRlLeMRX-YVZuDfcoNTjDl2zyjCIP-M0is_9lQNmOXEKsjFRsIEWvBxUbkbF-A
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=sabistart.store,www.sabistart.store,.sabistart.store,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://sabistart.store,https://www.sabistart.store,https://*.sabistart.store
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

stdin, stdout, stderr = ssh.exec_command(f'cat > /home/sabistart/www/django/.env << \'ENVEOF\'\n{env_content}ENVEOF')
stdout.read()
print("Updated .env with sabistart.store")

# 2. Update domains in database - activate sabistart.alwaysdata.net and www.sabistart.store
db_url = "postgresql://neondb_owner:npg_sDiORl2UK3Bj@ep-fancy-hat-apy67q1y-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

sql = f"""
-- Activate the existing alwaysdata domain and add www variant
UPDATE dashboard_domain_customdomain 
SET status = 'active', updated_at = NOW()
WHERE domain = 'sabistart.alwaysdata.net';

-- Add www variant if tenant 'sho' exists
INSERT INTO dashboard_domain_customdomain (domain, tenant_id, status, created_at, updated_at)
SELECT 'www.sabistart.store', t.id, 'active', NOW(), NOW()
FROM core_shop t
WHERE t.schema_name = 'sho'
ON CONFLICT (domain) DO NOTHING;

-- Add root sabistart.store domain
INSERT INTO dashboard_domain_customdomain (domain, tenant_id, status, created_at, updated_at)
SELECT 'sabistart.store', t.id, 'active', NOW(), NOW()
FROM core_shop t
WHERE t.schema_name = 'sho'
ON CONFLICT (domain) DO NOTHING;

-- Clear old resolution cache
DELETE FROM dashboard_domain_domainresolutioncache;

-- Show results
SELECT id, domain, tenant_id, status FROM dashboard_domain_customdomain ORDER BY id;
"""

stdin, stdout, stderr = ssh.exec_command(f'PGPASSWORD=npg_sDiORl2UK3Bj psql -h ep-fancy-hat-apy67q1y-pooler.c-7.us-east-1.aws.neon.tech -U neondb_owner -d neondb -c "{sql}"')
out = stdout.read().decode()
err = stderr.read().decode()
print("DB update result:")
print(out[:2000])
if err.strip(): print('ERR:', err.strip()[:500])

ssh.close()
