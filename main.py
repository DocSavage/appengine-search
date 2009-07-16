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

"""A super simple Google App Engine text posting app.

Logged in visitors can add some test and search for keywords across all 
added pages.  It demos a simple full text search module.
"""
__author__ = 'William T. Katz'

import cgi
import logging

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

# The following are necessary for full-text search demo
import search
INDEXING_URL = '/tasks/searchindexing'

class Page(search.Searchable, db.Model):
    user = db.UserProperty()
    title = db.StringProperty()
    content = db.TextProperty()
    created = db.DateTimeProperty(auto_now=True)
    INDEX_TITLE_FROM_PROP = 'title'
    # INDEX_USES_MULTI_ENTITIES = False

class SimplePage(webapp.RequestHandler):
    def render(self, html):
        user = users.get_current_user()
        page = '<html><body><div style="display:inline"><a href="/">Add Page</a> | '
        if user:
            page += 'Logged in as %s ' % (user.nickname())
            logout_url = users.create_logout_url(self.request.uri)
            page += '| <a href="%s">Logout</a>' % (logout_url)
        else:
            login_url = users.create_login_url(self.request.uri)
            page += '<a href="%s">Google login</a>' % (login_url)
        page += """</div>
        <hr>
        <h3>Full Text Search Test</h3>
        <p>This app tests a full text search module for Google App Engine.
        Once you are logged in, you can add text pages that will be indexed via
        Task Queue API tasks.  The search indices are efficiently stored using
        "Relation Index" entities as described in 
        <a href="http://code.google.com/events/io/sessions/BuildingScalableComplexApps.html">
        this Google I/O talk.</a></p>
        <p>My blog has an
        <a href="http://www.billkatz.com/2009/6/Simple-Full-Text-Search-for-App-Engine">
        article on this appengine-search module</a>.  You can download the code from the
        <a href="http://github.com/DocSavage/appengine-search">appengine-search
        github repository</a> under a liberal open source (MIT) license.</p>
        <form action="/search" method="get">
            Search for phrase (e.g., 'lorem ipsum'):
        """
        page += '<input name="phrase"'
        phrase = self.request.get('phrase')
        if phrase:
            page += ' value="%s">' % (phrase)
        page += '<input type="submit" name="submitbtn" value="Return Pages">'
        page += '<input type="submit" name="submitbtn" value="Return Keys Only">'
        page += """
        <p><strong>Return Pages</strong> retrieves the entire Page entities.<br />
           <strong>Return Keys Only</strong> retrieves just the keys but uses
           intelligent key naming to transmit "Title" data via the key names.</p>
        """
        page += '</form>'
        page += html
        page += '</body></html>'
        self.response.out.write(page)

class MainPage(SimplePage):
    def get(self):
        user = users.get_current_user()
        if not user:
            html = '<h4>Please login to add a page.</h4>'
        else:
            import time
            time_string = time.strftime('Page submitted %X on %x')
            html = """
            <h4>Add a text page below:</h4>
            <form action="/" method="post">
                <div>Title: <input type="text" size="40" name="title" 
            """
            html += 'value="' + time_string + '" />'
            html += """
                <em>This data will be encoded in the key names of index entities.</em></div>
                <div><textarea name="content" rows="10" cols="60"></textarea></div>
                <div><input type="submit" value="Add Page" /></div>
            </form>
            """
        self.render(html)

    def post(self):
        user = users.get_current_user()
        content = self.request.get('content')
        title = self.request.get('title')
        if not user:
            self.redirect('/?msg=You+must+be+logged+in')
        elif not content:
            self.redirect('/')
        else:
            page = Page(content=content, title=title, user=user)
            page.put()
            page.enqueue_indexing(url=INDEXING_URL)
            html = "<div>Thanks for entering the following text:</div>"
            html += "<pre>%s</pre>" % (cgi.escape(content))
            self.render(html)

class SearchPage(SimplePage):
    def get(self):
        submitbtn = self.request.get('submitbtn')
        phrase = self.request.get('phrase')
        html = "<h4>'" + phrase + "' was found on these pages:</h4>"
        if submitbtn == 'Return Keys Only':
            key_list = Page.search(phrase, keys_only=True)
            for key_and_title in key_list:
                html += "<div><p>Title: %s</p></div>" % key_and_title[1]
        else:
            pages = Page.search(phrase)
            for page in pages:
                html += "<div><p>Title: %s</p><p>User: %s, Created: %s</p><pre>%s</pre></div>" \
                        % (page.title, str(page.user), str(page.created), cgi.escape(page.content))
        self.render(html)

application = webapp.WSGIApplication([
        ('/', MainPage),
        ('/search', SearchPage),
        (INDEXING_URL, search.SearchIndexing)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
  main()
