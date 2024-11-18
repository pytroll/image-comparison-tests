import os
import subprocess
import shutil
import logging
from api_utils import post_github_comment
from config import Config


# configure the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
HOST_URL = Config.HOST_URL
BEHAVE_DIR = Config.BEHAVE_DIR

def remove_existing_container(container_name):
    try:
        subprocess.check_call(['docker', 'rm', '-f', container_name])
        print(f"Existing Container {container_name} removed successfully.")
    except subprocess.CalledProcessError:
        print(f"No existing Container with name {container_name} found.")

def clear_directory(directory):
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            print(f"Directory {directory} successfully emptied.")
        os.makedirs(directory)
        print(f"Directory {directory} newly created.")
    except Exception as e:
        print(f"Error when emptying directory {directory}: {str(e)}")


def check_container(name):
    """Check if a Docker container is running."""
    try:
        # Check if the Container is running
        result = subprocess.check_output(['docker', 'ps', '--filter', f'name={name}', '--filter', 'status=running', '--format', '{{.Names}}'])
        # Check if the Container is included in the output
        if name in result.decode('utf-8').strip():
            return True
        else:
            return False
    except subprocess.CalledProcessError:
        # If an error occurs, we assume that the Container is not running
        return False

def mask_sensitive_data(output, sensitive_data):
    """Replaces sensitive data by wildcard."""
    return output.replace(sensitive_data, "[REDACTED]")

def clone_and_test_pull_request(repo_full_name, pull_number, clone_url, branch_name, clone_dir, ext_data_dir, user, github_token):
    """Clone a specific branch from a Git repository, uninstall satpy and reinstall the new pull_branch version, then run tests."""
    try:
        app_dir = '/app'
        data_dir = os.path.join(app_dir, "ext_data")
        repo_dir = os.path.join(app_dir, "repository")
        app_log_file = os.path.join(app_dir, "output.log")

        clear_directory(clone_dir)

        # Add the GitHub token to the clone URL
        auth_clone_url = clone_url.replace("https://", f"https://{github_token}@")

        logger.debug(f"Cloning repository {clone_url} branch {branch_name} into {repo_dir}")


        # Run all commands in a single docker run invocation
        full_cmd = (
            f"touch {app_log_file} && "
            f"apt-get update >> {app_log_file} 2>&1 && "
            f"apt-get install -y git libgl1-mesa-glx libglib2.0-0 python3-venv >> {app_log_file} 2>&1 && "
            f"python3 -m venv /app/venv >> {app_log_file} 2>&1 && "
            f"/app/venv/bin/pip install behave Pillow pytest numpy opencv-python dask netcdf4 h5netcdf >> {app_log_file} 2>&1 && "
            f"git clone {auth_clone_url} --branch {branch_name} {repo_dir} >> {app_log_file} 2>&1 && "
            f"source /app/venv/bin/activate && pip install -e {repo_dir} >> {app_log_file} 2>&1 && "
            f"source /app/venv/bin/activate && cd {repo_dir}{BEHAVE_DIR} && behave >> {app_log_file} 2>&1 || true && "
            f"chown -R 1004:1004 /app >> {app_log_file} 2>&1" #1004 is the user id of bildabgleich since else the file system belongs to root, causing issues
        )

        subprocess.check_call([
            'docker', 'run', '--name', 'clone-repo-image',
            '-v', f"{clone_dir}:/app",
            '-v', f"{ext_data_dir}:{data_dir}",
            'python:3.10-slim', 'bash', '-c', full_cmd
        ])

        print("Container successfully started, directory cleared, repository cloned, dependencies installed, Satpy installed, and tests executed.")
        post_github_comment(repo_full_name, pull_number, f"The testing process was executed successfully. See the test results for this pull request [here]({HOST_URL})!", github_token)

    except subprocess.CalledProcessError as e:
        error_message = mask_sensitive_data(f"Error while cloning the repository: {e}", github_token)
        print(error_message)
        logger.error(error_message)

        try:
            logs = subprocess.check_output(['docker', 'logs', 'clone-repo-image'])
            print(f"Logs for clone-repo-image:\n{logs.decode('utf-8')}")
            error_message += mask_sensitive_data(f"\nLogs for clone-repo-image:\n{logs.decode('utf-8')}", github_token)
        except subprocess.CalledProcessError as log_error:
            log_error_message = mask_sensitive_data(f"Error while retrieving the container logs: {log_error}", github_token)
            print(log_error_message)
            error_message += f"\n{log_error_message}"

        try:
            subprocess.check_call([
                'docker', 'cp', 'clone-repo-image:/app/output.log', f"{clone_dir}/output.log"
            ])
            with open(f"{clone_dir}/output.log", 'r') as log_file:
                output_log_content = log_file.read()
                print(output_log_content)
                error_message += f"\nOutput Log:\n{output_log_content}"
        except Exception as copy_error:
            copy_error_message = mask_sensitive_data(f"Error while retrieving the output log file: {copy_error}", github_token)
            print(copy_error_message)
            error_message += f"\n{copy_error_message}"

        post_github_comment(repo_full_name, pull_number, f"An error occurred during the process.", github_token)
        raise Exception(mask_sensitive_data(f"Error while cloning the repository: {e}", github_token))

    finally:
        try:
            subprocess.check_call(['docker', 'stop', 'clone-repo-image'])
            subprocess.check_call(['docker', 'rm', 'clone-repo-image'])
            print("Container successfully stopped and removed.")
        except subprocess.CalledProcessError as cleanup_error:
            cleanup_error_message = mask_sensitive_data(f"Error while stopping or removing the container: {cleanup_error}", github_token)
            print(cleanup_error_message)
            logger.error(cleanup_error_message)
            post_github_comment(repo_full_name, pull_number, f"An error occurred during the process.", github_token)
