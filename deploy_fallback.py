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
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()
    
    # Upload middleware fix
    sftp.put('dashboard/domain/middleware.py', f'{REMOTE_ROOT}/dashboard/domain/middleware.py')
    print("Uploaded middleware.py")
    
    # Upload settings update
    sftp.put('sabistart/settings.py', f'{REMOTE_ROOT}/sabistart/settings.py')
    print("Uploaded settings.py")
    
    sftp.close()
    ssh.close()
    
    # Clear pycache
    ssh = create_ssh_client()
    stdin, stdout, stderr = ssh.exec_command(f'find {REMOTE_ROOT} -type d -name __pycache__ -exec rm -rf {{}} + 2>/dev/null; echo done')
    stdout.read()
    ssh.close()
    print("Cleared __pycache__")
    
    print("\nDone. Restart the app in alwaysdata admin panel.")
    print("Now any domain will fall back to the 'sho' tenant.")

if __name__ == "__main__":
    main()
