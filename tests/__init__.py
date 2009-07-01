import os

# This setup is necessary to prevent exception from being thrown by users API.
# Eventually, it should be incorporated into NoseGAE plugin.
def setup():
    os.environ['AUTH_DOMAIN'] = 'example.org'
    os.environ['USER_EMAIL'] = ''

def teardown():
    pass

