import os

class Config:
    DEBUG = False  # Setze auf False für die Produktionsumgebung, True für Debugging
    USER_NAME = os.getenv('USER_NAME', 'bildabgleich') # bildabgleich für EWC, ubuntu für Spielwiese
    CLONE_DIR_BASE = os.getenv('CLONE_DIR_BASE', f'/home/{USER_NAME}')
    PROJECT_PATH = os.getenv('PROJECT_PATH', f'{CLONE_DIR_BASE}/pytroll-image-comparison-tests')
    TEST_RESULTS_BASE_PATH = os.getenv('TEST_RESULTS_BASE_PATH', f'{PROJECT_PATH}/data/test_results')
    SERVER_LOGIC_PATH = os.getenv('SERVER_LOGIC_PATH', f'{PROJECT_PATH}/serverLogic')
    HOST_URL = os.getenv('HOST_URL', 'https://pytroll-image-test-dev.int-pytroll-development.s.ewcloud.host')
    BEHAVE_DIR = os.getenv('BEHAVE_DIR', f'/satpy/tests/behave')

