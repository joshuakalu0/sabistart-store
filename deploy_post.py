import paramiko
import sys
import io

HOST = "ssh-sabistart.alwaysdata.net"
PORT = 22
USERNAME = "sabistart"
PASSWORD = "Joshua.24-df"
REMOTE_ROOT = "/home/sabistart/www/django"

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    return ssh

def run(cmd, description=""):
    ssh = create_ssh_client()
    print(f"\n=== {description or cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out.strip(): print(out.strip()[-4000:])
    if err.strip(): print('ERR:', err.strip()[-2000:])
    ssh.close()

def main():
    # Upload updated requirements.txt
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()
    sftp.put('requirements.txt', f'{REMOTE_ROOT}/requirements.txt')
    sftp.close()
    ssh.close()
    print("Uploaded updated requirements.txt")

    # Install dependencies
    run(
        f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/pip install -r requirements.txt',
        "Installing requirements"
    )

    # Run migrations
    run(
        f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/python manage.py migrate --noinput',
        "Running migrations"
    )

    # Collect static
    run(
        f'cd {REMOTE_ROOT} && /home/sabistart/www/django/env/bin/python manage.py collectstatic --noinput',
        "Collecting static"
    )

    print("\n" + "="*50)
    print("POST-DEPLOY COMPLETE")
    print("="*50)
    print("Restart the app in alwaysdata admin panel.")

if __name__ == "__main__":
    main()
