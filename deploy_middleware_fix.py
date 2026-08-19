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
    # Upload fixed middleware
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()
    sftp.put('dashboard/domain/middleware.py', f'{REMOTE_ROOT}/dashboard/domain/middleware.py')
    sftp.close()
    ssh.close()
    print("Uploaded fixed middleware.py")

    # Clear __pycache__ to ensure fresh import
    run(
        f'find {REMOTE_ROOT} -type d -name __pycache__ -exec rm -rf {{}} + 2>/dev/null; echo done',
        "Clearing __pycache__"
    )

    print("\nFix deployed. Restart the app in alwaysdata admin panel.")

if __name__ == "__main__":
    main()
