import os

# This setup is necessary to prevent exception from being thrown by users API.
# Eventually, it should be incorporated into NoseGAE plugin.
def setup():
    os.environ['AUTH_DOMAIN'] = 'example.org'
    os.environ['USER_EMAIL'] = ''

def teardown():
    pass

from google.appengine.api import apiproxy_stub_map
from google.appengine.api import datastore_file_stub

def clear_datastore():
    """Clear datastore.  Can be used between tests to insure empty datastore.
    
    See code.google.com/p/nose-gae/issues/detail?id=16
    Note: the appid passed to DatastoreFileStub should match the app id in your app.yaml.
    """
    apiproxy_stub_map.apiproxy = apiproxy_stub_map.APIProxyStubMap()
    stub = datastore_file_stub.DatastoreFileStub('billkatz-test', '/dev/null', '/dev/null')
    apiproxy_stub_map.apiproxy.RegisterStub('datastore_v3', stub)