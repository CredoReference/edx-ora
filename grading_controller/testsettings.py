from settings import *
from logsettings import get_logger_config

import logging
south_logger=logging.getLogger('south')
south_logger.setLevel(logging.INFO)

log_dir = REPO_PATH / "log"

try:
    os.makedirs(log_dir)
except:
    pass

LOGGING = get_logger_config(log_dir,
    logging_env="test",
    debug=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME' : 'test_essaydb',
        }
}

# Nose Test Runner
INSTALLED_APPS += ('django_nose',)
NOSE_ARGS = [ '--with-xunit', '--with-coverage',
              '--cover-html-dir', 'cover',
              '--cover-package', 'controller',
              '--cover-package', 'ml_grading',
              '--cover-package', 'staff_grading',
              '--cover-package', 'peer_grading',
              '--cover-package', 'basic_check',
              ]
TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'