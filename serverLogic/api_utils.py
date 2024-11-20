import os
import hmac
import hashlib
import json
import requests
from werkzeug.exceptions import BadRequest, Forbidden
import logging
import re

# Configure the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def post_github_comment(repo_full_name, pull_number, comment, github_token):
    url = f"https://api.github.com/repos/{repo_full_name}/issues/{pull_number}/comments"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"body": comment}
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def verify_signature(payload_body, secret_token, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256."""
    if not signature_header:
        raise BadRequest(description="x-hub-signature-256 header is missing!")

    if isinstance(payload_body, dict):
        payload_body = json.dumps(payload_body, separators=(',', ':')).encode('utf-8')

    hash_object = hmac.new(secret_token.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise Forbidden(description="Request signatures didn't match!")

def extract_pull_request_info(data):
    """Extract necessary information from the pull request payload."""
    repo_full_name = data['repository']['full_name']
    clone_url = data["pull_request"]["head"]["repo"]["clone_url"]
    branch_name = data['pull_request']['head']['ref']
    pull_number = data['pull_request']['number']
    return repo_full_name, clone_url, branch_name, pull_number

def validate_safe_path(path):
    # Prevent that '..' occurs in the path, to avoid Directory Traversal
    if '..' in path or path.startswith('/'):
        raise BadRequest("Invalid path format.")

    # Optional additional check: make sure that the path contains no dangerous
    # characters
    if not re.match(r'^[a-zA-Z0-9_\-/.]+$', path):
        raise BadRequest("Invalid path format.")

def validate_timestamp_path_component(component):
    # RegEx for the Format XXXX-XX-XX-XX-XX-XX
    if not re.match(r'^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$', component):
        raise BadRequest(f"Invalid timestamp format: {component}")

def validate_user(data, github_token):
    """True if we can confirm that user is a member of org."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token:s}"}
    org = data["organization"]["login"]
    user = data["sender"]["login"]
    url = f"https://api.github.com/orgs/{org:s}/members/{user:s}"
    return bool(requests.get(url, headers=headers))

def shall_process_event(data, github_token):
    """True if PR shall be processed."""
    return (data['action'] == 'submitted' and
            'review' in data and
            'body' in data['review'] and
            data['review']['body'].strip().lower() == 'start behave test' and
            'pull_request' in data and
            validate_user(data, github_token))
