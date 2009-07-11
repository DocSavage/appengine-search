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

"""A simple full-text search system

This module lets you designate particular entities for full text search
indexing.  It uses the Task Queue API to schedule search indexing and
relation index entities (as described in Brett Slatkin's 'Building Scalable,
Complex Apps on App Engine' talk at Google I/O, 2009).

The keyword extraction code was slightly modified from Ryan Barrett's
SearchableModel implementation.
"""
__author__ = 'William T. Katz'

import logging
import re
import string
import sys

from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.ext import db
from google.appengine.ext import webapp

# TODO -- This will eventually be moved out of labs namespace
from google.appengine.api.labs import taskqueue

# Use python port of Porter2 stemmer.
from search.pyporter2 import Stemmer

# Following module-level constants are cached in instance

MAX_KEYWORDS_PER_ENTITY = datastore._MAX_INDEXED_PROPERTIES - 50

FULL_TEXT_MIN_LENGTH = 4

FULL_TEXT_STOP_WORDS = frozenset([
 'a', 'about', 'according', 'accordingly', 'affected', 'affecting', 'after',
 'again', 'against', 'all', 'almost', 'already', 'also', 'although',
 'always', 'am', 'among', 'an', 'and', 'any', 'anyone', 'apparently', 'are',
 'arise', 'as', 'aside', 'at', 'away', 'be', 'became', 'because', 'become',
 'becomes', 'been', 'before', 'being', 'between', 'both', 'briefly', 'but',
 'by', 'came', 'can', 'cannot', 'certain', 'certainly', 'could', 'did', 'do',
 'does', 'done', 'during', 'each', 'either', 'else', 'etc', 'ever', 'every',
 'following', 'for', 'found', 'from', 'further', 'gave', 'gets', 'give',
 'given', 'giving', 'gone', 'got', 'had', 'hardly', 'has', 'have', 'having',
 'here', 'how', 'however', 'i', 'if', 'in', 'into', 'is', 'it', 'itself',
 'just', 'keep', 'kept', 'knowledge', 'largely', 'like', 'made', 'mainly',
 'make', 'many', 'might', 'more', 'most', 'mostly', 'much', 'must', 'nearly',
 'necessarily', 'neither', 'next', 'no', 'none', 'nor', 'normally', 'not',
 'noted', 'now', 'obtain', 'obtained', 'of', 'often', 'on', 'only', 'or',
 'other', 'our', 'out', 'owing', 'particularly', 'past', 'perhaps', 'please',
 'poorly', 'possible', 'possibly', 'potentially', 'predominantly', 'present',
 'previously', 'primarily', 'probably', 'prompt', 'promptly', 'put',
 'quickly', 'quite', 'rather', 'readily', 'really', 'recently', 'regarding',
 'regardless', 'relatively', 'respectively', 'resulted', 'resulting',
 'results', 'said', 'same', 'seem', 'seen', 'several', 'shall', 'should',
 'show', 'showed', 'shown', 'shows', 'significantly', 'similar', 'similarly',
 'since', 'slightly', 'so', 'some', 'sometime', 'somewhat', 'soon',
 'specifically', 'state', 'states', 'strongly', 'substantially',
 'successfully', 'such', 'sufficiently', 'than', 'that', 'the', 'their',
 'theirs', 'them', 'then', 'there', 'therefore', 'these', 'they', 'this',
 'those', 'though', 'through', 'throughout', 'to', 'too', 'toward', 'under',
 'unless', 'until', 'up', 'upon', 'use', 'used', 'usefully', 'usefulness',
 'using', 'usually', 'various', 'very', 'was', 'we', 'were', 'what', 'when',
 'where', 'whether', 'which', 'while', 'who', 'whose', 'why', 'widely',
 'will', 'with', 'within', 'without', 'would', 'yet', 'you'])

PUNCTUATION_REGEX = re.compile('[' + re.escape(string.punctuation) + ']')

class SearchIndex(db.Model):
    """A relation index that holds full text indexing on an entity.
    
    This model is used by the Searchable mix-in to hold full text
    indexes of a parent entity.
    """
    parent_kind = db.StringProperty(required=True)
    keywords = db.StringListProperty(required=True)

class StemIndex(db.Model):
    """A relation index that holds full text stem indexing on an entity.
    
    StemIndex should be used for full text indexing with stemming.
    """
    parent_kind = db.StringProperty(required=True)
    keywords = db.StringListProperty(required=True)


class Searchable(object):
    """A class that supports full text indexing and search on entities.
    
    Add this class to your model's inheritance declaration like this:
    
        class Page(Searchable, db.Model):
            author_name = db.StringProperty()
            content = db.TextProperty()
            # STEMMING = False
            # MULTI_INDEX_ENTITIES = True

    Stemming is on by default but can be toggled off by setting STEMMING
    to False in your class declaration.

    Because most keyword lists generated from an entity will be under the
    approximately 5000 indexed property limit, this module preferentially
    stores only one index entity.  You can allow larger indexes by setting
    MULTI_INDEX_ENTITIES to True.  This incurs overhead on every indexing
    operation, whether multiple index entities are writter or not, because
    we must query for all index entities and delete unused ones.  In the
    case of a single index entity, it can be simply overwritten.

    The enqueue_indexing() method should be called after your model is created or
    edited:

        myPage = Page(author_name='John Doe', content='My amazing content!')
        myPage.put()
        myPage.enqueue_indexing(url='/tasks/searchindexing')

    Note that a url must be included that corresponds with the url mapped
    to search.SearchIndexing controller.

    You can limit the properties indexed by passing in a list of 
    property names:

        myPage.enqueue_indexing(url='/foo', only_index=['content'])

    If you want to risk getting a timeout during indexing, you could
    index immediately after putting your model and forego task queueing:

        myPage.put()
        myPage.index(only_index=['content'])

    After your model has been indexed, you may use the search() method:

        Page.search('search phrase')          # -> Returns Page entities
        Page.search('stuff', keys_only=True)  # -> Returns Page keys

    You can use the full_text_search() static method to return all entities,
    not just a particular kind, that have been indexed:

        Searchable.full_text_search('stuff')  # -> Returns any entities
        Searchable.full_text_search('stuff', stemming=False)

    Because stemming can be toggled for any particular Model, only entities will
    be returned that match indexing style (i.e., stemming on or off).
    """

    STEMMING = True                 # Allow stemming to be turned off per subclass.
    MULTI_INDEX_ENTITIES = False    # If FALSE, limit keywords to < MAX_KEYWORDS_PER_ENTITY
    MULTI_WORD_LITERAL = False      # If TRUE, allow "search term" that matches phrase

    @staticmethod
    def full_text_search(phrase, 
                        limit=10, offset=0, kind=None, 
                        stemming=STEMMING):
        """Queries search indices for keywords in a phrase using a merge-join.
        
        Args:
            phrase: String.  Search phrase with space between keywords
            kind: String.  Returned keys/entities are restricted to this kind.

        Returns:
            A list of parent keys or parent entities, depending on the value
            of keys_only argument.
        """
        if stemming:
            stemmer = Stemmer.Stemmer('english')
            keywords = stemmer.stemWords(phrase.split())
            klass = StemIndex
        else:
            keywords = phrase.split()
            klass = SearchIndex

        query = klass.all(keys_only=True)
        for keyword in keywords:
            query = query.filter('keywords =', keyword.lower())
        if kind:
            query = query.filter('parent_kind =', kind)
        index_keys = query.fetch(limit=limit, offset=offset)
        return [key.parent() for key in index_keys]

    @classmethod
    def get_simple_search_phraseset(cls, text):
        """Returns a simple set of keywords from given text.

        Args:
            text: String.

        Returns:
            A set of keywords that aren't stop words and meet length requirement.

        >>> Searchable.get_simple_search_phraseset('I shall return.')
        set(['return'])
        """
        if text:
            datastore_types.ValidateString(text, 'text', max_len=sys.maxint)
            text = PUNCTUATION_REGEX.sub(' ', text)
            words = text.lower().split()
            words = set(words)
            words -= FULL_TEXT_STOP_WORDS
            for word in list(words):
                if len(word) < FULL_TEXT_MIN_LENGTH:
                    words.remove(word)
        else:
            words = set()
        return words

    @classmethod
    def get_search_phraseset(cls, text):
        """Returns set of phrases, including two and three adjacent word phrases 
           not spanning punctuation or stop words.

        Args:
            text: String with punctuation.

        Returns:
            A set of search terms that aren't stop words and meet length 
            requirement.  Set includes phrases of adjacent words that
            aren't stop words.

        >>> Searchable.get_search_phraseset('Recalling friends, past and present.')
        set(['recalling', 'recalling friends', 'friends'])
        """
        if text:
            datastore_types.ValidateString(text, 'text', max_len=sys.maxint)
            text = text.lower()
            phrases = []
            two_words = []
            three_words = []
            fragments = text.split()
            for frags in fragments:
                parts = frags.split('-')
                for part in parts:
                    if part:
                        word, replaced = PUNCTUATION_REGEX.subn('', part)
                        not_end_punctuation = (replaced > 1 or part[-1] not in string.punctuation)
                        if (replaced and not_end_punctuation) or word in FULL_TEXT_STOP_WORDS:
                            two_words = []
                            three_words = []
                        else:
                            if len(word) >= FULL_TEXT_MIN_LENGTH:
                                phrases.append(word)
                            two_words.append(word)
                            three_words.append(word)
                            if len(two_words) == 2:
                                phrases.append(' '.join(two_words))
                                del two_words[0]
                            if len(three_words) == 3:
                                phrases.append(' '.join(three_words))
                                del three_words[0]
            phrases = set(phrases)
        else:
            phrases = set()
        return phrases

    @classmethod
    def search(cls, phrase, limit=10, offset=0, keys_only=False):
        """Queries search indices for keywords in a phrase using a merge-join.
        
        Use of this class method lets you easily restrict searches to a kind
        and retrieve entities or keys.
        """
        # TODO -- Handle quoted multiword query when MULTI_WORD_LITERAL = True

        keys = Searchable.full_text_search(phrase, limit=limit, offset=offset,
                                           kind=cls.kind(),
                                           stemming=cls.STEMMING)
        if keys_only:
            return keys
        else:
            return cls.get(keys)

    def index(self, only_index=None, indexing_func=None):
        """Generates or replaces a Search Index for a Model instance.

        Args (optional):
            only_index: List of strings.  Restricts indexing to these property names.
            indexing_func: A function that returns a set of keywords or phrases.

        Note that the indexing_func can be passed in to allow more customized
        search phrase generation.  Multi-word literal search phrases (via setting
        the class MULTI_WORD_LITERAL to True) is currently experimental but
        shows how you can have different search phrase generation functions.
        """
        if not indexing_func:
            klass = self.__class__
            if klass.MULTI_WORD_LITERAL:
                indexing_func = klass.get_search_phraseset
            else:
                indexing_func = klass.get_simple_search_phraseset
        if self.STEMMING:
            stemmer = Stemmer.Stemmer('english')
        keywords = set()
        for prop_name, prop_value in self.properties().iteritems():
            if (not only_index) or (prop_name in only_index):
                values = prop_value.get_value_for_datastore(self)
                if not isinstance(values, list):
                    values = [values]
                if (isinstance(values[0], basestring) and
                        not isinstance(values[0], datastore_types.Blob)):
                    for value in values:
                        words = indexing_func(value)
                        if self.STEMMING:
                            stemmed_words = set([stemmer.stemWord(w) for w in words])
                            keywords.update(stemmed_words)
                        else:
                            keywords.update(words)
        keyword_list = list(keywords)

        key = self.key()
        klass = StemIndex if self.STEMMING else SearchIndex

        if self.__class__.MULTI_INDEX_ENTITIES:
            query = klass.all(keys_only=True).ancestor(self.key())
            previous_entity_keys = query.fetch(1000)
        num_keywords = len(keyword_list)
        logging.debug("Number of keywords for this entity: %d", num_keywords)
        start_index = 0
        entity_num = 1      # Appended to key name of index entity
        cur_entity_keys = []
        while (num_keywords > 0):
            cur_num_keywords = min(num_keywords, MAX_KEYWORDS_PER_ENTITY)
            end_index = start_index + cur_num_keywords
            num_indices = (num_keywords - 1) / MAX_KEYWORDS_PER_ENTITY + 1
            index_key_name = key.kind() + str(key.id_or_name()) + str(entity_num)
            args = {'parent': key, 'key_name': index_key_name,
                    'parent_kind': key.kind(), 
                    'keywords': keyword_list[start_index:end_index] }
            index_entity = klass(**args)
            cur_entity_keys.append(index_entity.put())
            if self.__class__.MULTI_INDEX_ENTITIES:
                start_index = end_index
                num_keywords -= cur_num_keywords
                entity_num += 1
            else:
                num_keywords = 0    # Only write one index entity
        if self.__class__.MULTI_INDEX_ENTITIES:
            delete_keys = []
            for key in previous_entity_keys:
                if key not in cur_entity_keys:
                    delete_keys.append(key)
            db.delete(delete_keys)

    def enqueue_indexing(self, url, only_index=None):
        """Adds an indexing task to the default task queue.
        
        Args:
            url: String. The url associated with SearchIndexing handler.
            only_index: List of strings.  Restricts indexing to these prop names.
        """
        if url:
            params = {'key': str(self.key())}
            if only_index:
                params['only_index'] = ' '.join(only_index)
            taskqueue.add(url=url, params=params)

class SearchIndexing(webapp.RequestHandler):
    """Handler for full text indexing task."""
    def post(self):
        key_str = self.request.get('key')
        only_index_str = self.request.get('only_index')
        if key_str:
            key = db.Key(key_str)
            entity = db.get(key)
            only_index = only_index_str.split(',') if only_index_str else None
            entity.index(only_index=only_index)

