import re

LOREM_IPSUM = """
Lorem ipsum dolor sit amet, consectetur adipisicing elit, 
sed do eiusmod tempor incididunt ut labore et dolore magna 
aliqua. Ut enim ad minim veniam, quis nostrud exercitation 
ullamco laboris nisi ut aliquip ex ea commodo consequat. 
Duis aute irure dolor in reprehenderit in voluptate velit 
esse cillum dolore eu fugiat nulla pariatur. Excepteur sint 
occaecat cupidatat non proident, sunt in culpa qui officia 
deserunt mollit anim id est laborum.
"""

from google.appengine.ext import db
import search
class Page(search.Searchable, db.Model):
    author_name = db.StringProperty()
    content = db.TextProperty()

class TestSearchModule:
    def setup(self):
        import tests
        tests.clear_datastore()

    def teardown(self):
        pass

    def test_indexing_and_search(self):
        # Test indexing
        page = Page(author_name='John Doe', content=LOREM_IPSUM)
        page.put()
        page.index()
        assert search.SearchIndex.all().count() == 1
        page = Page(author_name='Marky Mark', content='Nothing but us rapper/actors here!')
        page.put()
        page.index()
        assert search.SearchIndex.all().count() == 2

        # Test searching
        returned_pages = Page.search('LoReM IpSuM')
        assert returned_pages and len(returned_pages) == 1
        lmatch = re.search(r'lorem', returned_pages[0].content, re.IGNORECASE)
        imatch = re.search(r'ipsum', returned_pages[0].content, re.IGNORECASE)
        assert lmatch and imatch
        keys = Page.search('LoReM ipsum', keys_only=True)
        assert isinstance(keys, list) and len(keys) == 1
        assert isinstance(keys[0], db.Key)
        assert returned_pages[0].key() == keys[0]
        returned_pages = Page.search('NowhereInDoc')
        assert not returned_pages
        returned_pages = Page.search('rapper')
        lmatch = re.search(r'lorem', returned_pages[0].content, re.IGNORECASE)
        imatch = re.search(r'ipsum', returned_pages[0].content, re.IGNORECASE)
        assert not lmatch and not imatch
    