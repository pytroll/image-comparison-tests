import os
import getpass

class Config:
    DEBUG = False  # set to False for production environment, True for debugging
    USER_NAME = os.getenv('USER_NAME', getpass.getuser())
    CLONE_DIR_BASE = os.getenv('CLONE_DIR_BASE', f'/home/{USER_NAME}')
    PROJECT_PATH = os.getenv('PROJECT_PATH', f'{CLONE_DIR_BASE}/pytroll-image-comparison-tests')
    TEST_RESULTS_BASE_PATH = os.getenv('TEST_RESULTS_BASE_PATH', f'{PROJECT_PATH}/data/test_results')
    SERVER_LOGIC_PATH = os.getenv('SERVER_LOGIC_PATH', f'{PROJECT_PATH}/serverLogic')
    HOST_URL = os.getenv('HOST_URL', 'https://image-test.int-pytroll-development.s.ewcloud.host')
    BEHAVE_DIR = os.getenv('BEHAVE_DIR', f'/satpy/tests/behave')
