from system.account.models import PlatformUser

try:
    import psycopg
except ImportError:  # pragma: no cover - compatibility helper
    import psycopg2 as psycopg

conn = psycopg.connect(
    dbname='sabistore',
    user='sabistore',
    password='sabistore',
    host='localhost',
    port='5432'
)
conn.autocommit = True
cursor = conn.cursor()

print("Dropping public schema...")
cursor.execute("DROP SCHEMA public CASCADE;")
print("Creating public schema...")
cursor.execute("CREATE SCHEMA public;")
cursor.execute("GRANT ALL ON SCHEMA public TO sabistore;")
cursor.execute("GRANT ALL ON SCHEMA public TO public;")

print("Database reset complete!")
cursor.close()
conn.close()
