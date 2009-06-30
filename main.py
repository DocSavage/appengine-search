#!/usr/bin/env python
#
# The MIT License
# 
# Copyright (c) 2009 William T. Katz
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
    content = db.TextProperty()
    user = db.UserProperty()
    created = db.DateTimeProperty(auto_now=True)

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
        # Add donation button so I can get chinese dinner money :)
        page += """
        <form name="_xclick" action="https://www.paypal.com/cgi-bin/webscr" method="post">
        <input type="hidden" name="cmd" value="_xclick">
        <input type="hidden" name="business" value="billkatz@gmail.com">
        <input type="hidden" name="item_name" value="Donation to help feed self-funded coder">
        <input type="hidden" name="currency_code" value="USD">
        <input type="image" src="http://www.paypal.com/en_US/i/btn/btn_donate_LG.gif" border="0" 
         name="submit" alt="Donate and help feed a programmer."
         style="position:absolute;top:2;right:65">
        <input name="amount" size="6" maxlength="6" value="2.00"
         style="position:absolute;top:3;right:10;width:50px">
        </form>
        """
        page += """</div>
        <hr>
        <h3>Full Text Search Test</h3>
        <p>This app tests a simple full text search module for Google App Engine.
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
            page += ' value="%s"' % (phrase)
        page += '><input type="submit" value="Search"><em>&nbsp;minimum 4 letters long</em></form>'
        page += html
        page += '</body></html>'
        self.response.out.write(page)

class MainPage(SimplePage):
    def get(self):
        user = users.get_current_user()
        if not user:
            html = '<h4>Please login to add a page.</h4>'
        else:
            html = """
            <h4>Add a text page below:</h4>
            <form action="/" method="post">
                <div><textarea name="content" rows="10" cols="60"></textarea></div>
                <div><input type="submit" value="Add Page"></div>
            </form>
            """
        self.render(html)

    def post(self):
        user = users.get_current_user()
        content = self.request.get('content')
        if not user:
            self.redirect('/?msg=You+must+be+logged+in')
        elif not content:
            self.redirect('/')
        else:
            page = Page(content=content, user=user)
            page.put()
            page.queue_indexing(url=INDEXING_URL, only_index=['content'])
            html = "<div>Thanks for entering the following text:</div>"
            html += "<pre>%s</pre>" % (cgi.escape(content))
            self.render(html)

class SearchPage(SimplePage):
    def get(self):
        phrase = self.request.get('phrase')
        pages = Page.search(phrase)
        html = "<h4>'" + phrase + "' was found on these pages:</h4>"
        for page in pages:
            html += "<div><p>User: %s, Created: %s</p><pre>%s</pre></div>" \
                    % (str(page.user), str(page.created), cgi.escape(page.content))
        self.render(html)

application = webapp.WSGIApplication([
        ('/', MainPage),
        ('/search', SearchPage),
        (INDEXING_URL, search.SearchIndexing)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
  main()
