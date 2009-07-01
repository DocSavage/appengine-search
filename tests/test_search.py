#!/usr/bin/env python
#
# The MIT License
# 
# Copyright (c) 2009 William T. Katz
# Website/Contact: http://www.billkatz.com
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to 
# deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.

import re

LOREM_IPSUM = """
Lorem ipsum dolor sit amet, consectetur adipisicing elit, 
sed do eiusmod tempor incididunt ut labore et dolore magna 
aliqua. Ut enim ad minim veniam, quis nostrud exercitation 
ullamco laboris nisi ut aliquip ex ea commodo consequat. 
Duis aute irure dolor in reprehenderit in voluptate velit 
esse cillum dolore eu fugiat nulla pariatur. Excepteur sint 
occaecat cupidatat non proident, sunt in culpa qui officia 
deserunt mollit anim id est laborum.  Encrusted.
"""

INFLECTION_TEST = """
Guido ran up slippery ruby-encrusted monoliths in search of
the serpentine mascot.  The pythonic creatures skulked away.
How quickly did they forget their master?  Guido was
challenged by the excessively poor storyline in this fictional
tale, but alas, what could he do?  He was one of many fixtures
in ornately narrated prose doomed to be read only by
computerized algorithms implementing text processing!
"""

from google.appengine.ext import db
import search

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

class Page(search.Searchable, db.Model):
    author_name = db.StringProperty()
    content = db.TextProperty()

class NoninflectedPage(search.Searchable, db.Model):
    """Used to test search without stemming, e.g. for precise, non-inflected words"""
    author_name = db.StringProperty()
    content = db.TextProperty()
    USE_STEMMING = False

class TestLoremIpsum:
    def setup(self):
        clear_datastore()
        page = NoninflectedPage(author_name='John Doe', content=LOREM_IPSUM)
        page.put()
        page.index(only_index=['content'])
        assert search.SearchIndex.all().count() == 1
        page = NoninflectedPage(author_name='Jon Favreau', 
                                content='A director that works well with writers.')
        page.put()
        page.index()
        assert search.SearchIndex.all().count() == 2

    def teardown(self):
        pass

    def test_only_index(self):
        returned_pages = NoninflectedPage.search('John')
        assert not returned_pages
        returned_pages = NoninflectedPage.search('Favreau')
        assert returned_pages

    def test_two_word_search(self):
        returned_pages = NoninflectedPage.search('LoReM IpSuM')
        assert returned_pages and len(returned_pages) == 1
        lmatch = re.search(r'lorem', returned_pages[0].content, re.IGNORECASE)
        imatch = re.search(r'ipsum', returned_pages[0].content, re.IGNORECASE)
        assert lmatch and imatch

    def test_key_only_search(self):
        keys = NoninflectedPage.search('LoReM ipsum', keys_only=True)
        assert isinstance(keys, list) and len(keys) == 1
        assert isinstance(keys[0], db.Key)
        assert NoninflectedPage.search('LoReM IpSuM')[0].key() == keys[0]

    def test_search_miss(self):
        returned_pages = NoninflectedPage.search('NowhereInDoc')
        assert not returned_pages
        returned_pages = NoninflectedPage.search('director')
        lmatch = re.search(r'lorem', returned_pages[0].content, re.IGNORECASE)
        imatch = re.search(r'ipsum', returned_pages[0].content, re.IGNORECASE)
        assert not lmatch and not imatch

    def test_not_inflected(self):
        returned_pages = NoninflectedPage.search('encrust')
        assert not returned_pages
        returned_pages = NoninflectedPage.search('encrusted')
        assert returned_pages

class TestInflection:
    def setup(self):
        clear_datastore()
        page = Page(author_name='John Doe', content=INFLECTION_TEST)
        page.put()
        page.index()
        assert search.StemIndex.all().count() == 1
        page = Page(author_name='Jon Favreau', content='A director that works well with writers.')
        page.put()
        page.index()
        assert search.StemIndex.all().count() == 2

    def teardown(self):
        pass

    def test_inflections(self):
        def check_inflection(word1, word2):
            returned_pages = Page.search(word1)
            assert returned_pages
            assert re.search(word2, returned_pages[0].content, re.IGNORECASE)
        check_inflection('algorithm', 'algorithms')
        check_inflection('python', 'pythonic')
        check_inflection('rubies', 'ruby')
        check_inflection('encrust', 'encrusted')