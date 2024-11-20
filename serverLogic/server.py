import logging
import os
from glob import glob
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
import json
from api_utils import verify_signature, extract_pull_request_info, post_github_comment, validate_timestamp_path_component, validate_safe_path, shall_process_event
from container_utils import clone_and_test_pull_request, check_container
from werkzeug.exceptions import HTTPException
from config import Config
import threading
import sys

# Import secrets
from secret import GITHUB_TOKEN, WEBHOOK_SECRET

container_lock = threading.Lock()

# configure the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load Config
DEBUG = Config.DEBUG
USER_NAME = Config.USER_NAME
TEST_RESULTS_BASE_PATH = Config.TEST_RESULTS_BASE_PATH
CLONE_DIR_BASE = Config.CLONE_DIR_BASE


def create_app():
    app = Flask(__name__)
    @app.route('/webhook', methods=['POST'])
    def github_webhook():
        try:
            if not request.is_json:
                logger.error("Request does not contain JSON.")
                return jsonify({'error': 'Request does not contain JSON'}), 400

            data = request.get_json()
            headers = dict(request.headers)

            # Extract the signature from headers
            signature_header = headers.get('X-Hub-Signature-256')

            # Verify the signature
            try:
                verify_signature(data, WEBHOOK_SECRET, signature_header)
            except HTTPException as e:
                logger.error("Signature verification failed.")
                return jsonify({'error': str(e)}), e.get_response().status_code

            # Handling GitHub ping event
            if 'hook' in data and 'zen' in data:
                logger.debug("Received GitHub ping event")
                return jsonify({'message': 'Ping received successfully'}), 200

            # Process the pull request event
            if shall_process_event(data, GITHUB_TOKEN):
                repo_full_name, clone_url, branch_name, pull_number = extract_pull_request_info(data)

                def process_pull_request():
                    with container_lock:
                        try:
                            clone_dir = f"{CLONE_DIR_BASE}/pull_request_{branch_name}"
                            data_dir = f"{CLONE_DIR_BASE}/pytroll-image-comparison-tests/data"

                            # Check if the container is already running
                            if check_container('clone-repo-image'):
                                message = "A job is already running for this repository. Please wait for the current job to finish."
                                logger.info(message)
                                post_github_comment(repo_full_name, pull_number, message, GITHUB_TOKEN)
                                return

                            message = f"Starting to clone and test the repository {repo_full_name}"
                            logger.info(message)
                            post_github_comment(repo_full_name, pull_number, message, GITHUB_TOKEN)

                            # Proceed with the cloning and testing
                            clone_and_test_pull_request(repo_full_name, pull_number, clone_url, branch_name, clone_dir, data_dir, USER_NAME, GITHUB_TOKEN)

                            if app.debug:
                                file_name = 'webhook_data.json'
                                with open(file_name, 'w') as json_file:
                                    json.dump({
                                        'headers': headers,
                                        'body': data
                                    }, json_file, indent=4)

                                logger.info(f"The webhook data was successfully written to '{file_name}'.")

                        except Exception as e:
                            error_message = f"Error while cloning the repository: {str(e)}"
                            logger.error(error_message)
                            post_github_comment(repo_full_name, pull_number, error_message, GITHUB_TOKEN)

                # Start processing the pull request in a new thread
                threading.Thread(target=process_pull_request).start()
                return jsonify({'message': 'Processing started'}), 200

            return jsonify({'message': 'Daten erfolgreich empfangen'}), 200

        except HTTPException as e:
            logger.error(f"HTTP Exception: {str(e)}")
            return jsonify({'error': str(e)}), e.get_response().status_code
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500


    @app.route('/<timestamp>', methods=['GET'])
    def display_test_results(timestamp):
        # Validating of the timestamp
        validate_timestamp_path_component(timestamp)

        test_dir = os.path.join(TEST_RESULTS_BASE_PATH, 'image_comparison', timestamp)

        if not os.path.exists(test_dir):
            return "No test results found.", 404

        results_file = os.path.join(test_dir, 'test_results.txt')
        try:
            with open(results_file, 'r') as file:
                results = file.read()
        except FileNotFoundError:
            results = "No test results found."

        # Find all difference images in the directory
        diff_image_paths = sorted(glob(os.path.join(test_dir, 'difference', 'diff_*.png')), key=os.path.getmtime, reverse=True)
        diff_image_paths = [{'path': '/test_results/image_comparison/' + os.path.basename(test_dir.rstrip('/')) + '/difference/' + os.path.basename(image_path), 'name': os.path.basename(image_path)} for image_path in diff_image_paths]

        # Find all generated images in the directory
        generated_image_paths = sorted(glob(os.path.join(test_dir, 'generated', 'generated_*.png')), key=os.path.getmtime, reverse=True)
        generated_image_paths = [{'path': '/test_results/image_comparison/' + os.path.basename(test_dir.rstrip('/')) + '/generated/' + os.path.basename(image_path), 'name': os.path.basename(image_path)} for image_path in generated_image_paths]

        return render_template('test_results.html', results=results, generated_image_paths=generated_image_paths, diff_image_paths=diff_image_paths, test_dir=os.path.basename(test_dir.rstrip('/')))


    @app.route('/more_results', methods=['GET'])
    def more_results():
        # Find all test results directories
        test_results_dirs = sorted(glob(os.path.join(TEST_RESULTS_BASE_PATH, 'image_comparison', '*/')), key=os.path.getmtime, reverse=True)
        test_results_list = [{'timestamp': os.path.basename(test_dir.rstrip('/'))} for test_dir in test_results_dirs]

        return render_template('more_results.html', test_results_list=test_results_list)


    @app.route('/', methods=['GET'])
    def display_latest_results():
        # Find the latest test results directory
        test_results_dirs = sorted(glob(os.path.join(TEST_RESULTS_BASE_PATH, 'image_comparison', '*/')), key=os.path.getmtime, reverse=True)

        if not test_results_dirs:
            return "No test results found.", 404

        latest_test_dir = test_results_dirs[0]

        results_file = os.path.join(latest_test_dir, 'test_results.txt')
        try:
            with open(results_file, 'r') as file:
                results = file.read()
        except FileNotFoundError:
            results = "Keine Testergebnisse gefunden."

        # Find all difference images in the directory
        image_paths = sorted(glob(os.path.join(latest_test_dir, 'difference', 'diff_*.png')), key=os.path.getmtime,
                             reverse=True)
        image_paths = [{'path': '/test_results/image_comparison/' + os.path.basename(
            latest_test_dir.rstrip('/')) + '/difference/' + os.path.basename(image_path),
                        'name': os.path.basename(image_path)} for image_path in image_paths]


        return render_template('latest_results.html', results=results, image_paths=image_paths,
                                      test_dir=os.path.basename(latest_test_dir.rstrip('/')))


    @app.route('/test_results/', defaults={'path': ''})
    @app.route('/test_results/<path:path>')
    def serve_test_results(path):
        # Validating of the path
        validate_safe_path(path)

        base_dir = TEST_RESULTS_BASE_PATH
        full_path = os.path.normpath(os.path.join(base_dir, path))

        # Make sure the resulting path lies within base_dir
        if not full_path.startswith(base_dir):
            abort(403)

        if os.path.isdir(full_path):
            # If it's a directory, list its contents
            items = os.listdir(full_path)
            items = [item + '/' if os.path.isdir(os.path.join(full_path, item)) else item for item in items]
            return render_template('test_results_images.html', path=path, items=items)

        elif os.path.isfile(full_path):
            # If it's a file, serve it
            return send_from_directory(base_dir, path)
        else:
            abort(404)

    return app

if __name__ == '__main__':
    app = create_app()

    if DEBUG:
        # start in developer mode
        app.run(debug=True, use_reloader=True, port=8080, host='0.0.0.0')
    else:
        # start in production mode
        from gunicorn.app.base import BaseApplication

        class GunicornApp(BaseApplication):
            def __init__(self, app):
                self.application = app
                super().__init__()

            def load_config(self):
                self.cfg.set('bind', '0.0.0.0:8080')
                self.cfg.set('workers', 4)

            def load(self):
                return self.application

        GunicornApp(app).run()
