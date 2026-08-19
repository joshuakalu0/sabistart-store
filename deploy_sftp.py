import os
import sys
import paramiko
from scp import SCPClient

HOST = "ssh-sabistart.alwaysdata.net"
PORT = 22
USERNAME = "sabistart"
PASSWORD = "Joshua.24-df"
REMOTE_PATH = "/home/sabistart/www/django"
LOCAL_PATH = "."

def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    return ssh

def upload_folder(local_path, remote_path):
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()

    for root, dirs, files in os.walk(local_path):
        rel_path = os.path.relpath(root, local_path)
        if rel_path == ".":
            rel_path = ""
        
        remote_dir = os.path.join(remote_path, rel_path).replace("\\", "/")
        try:
            sftp.mkdir(remote_dir)
        except IOError:
            pass

        for file in files:
            local_file = os.path.join(root, file)
            remote_file = os.path.join(remote_dir, file).replace("\\", "/")
            print(f"Uploading {local_file} -> {remote_file}")
            sftp.put(local_file, remote_file)

    sftp.close()
    ssh.close()
    print("Upload complete!")

if __name__ == "__main__":
    upload_folder(LOCAL_PATH, REMOTE_PATH)
