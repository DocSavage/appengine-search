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

class Error(Exception):
    """Base search module error type."""

class IndexTitleError(Error):
    """Raised when INDEX_TITLE_FROM_PROP or title alterations are incorrect."""

# Following module-level constants are cached in instance

KEY_NAME_DELIMITER = '||'  # Used to hold arbitrary strings in key names.
                           # Should not be contained in derived class key names.

MAX_ENTITY_SEARCH_PHRASES = datastore._MAX_INDEXED_PROPERTIES - 1

SEARCH_PHRASE_MIN_LENGTH = 4

STOP_WORDS = frozenset([
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

# Rather than have an extra property name to distinguish stemmed from
# non-stemmed index entities, we use different Models that are
# identical to a base index entity.
class SearchIndex(db.Model):
    """Holds full text indexing on an entity.
    
    This model is used by the Searchable mix-in to hold full text
    indexes of a parent entity.
    """
    @staticmethod
    def get_index_key_name(parent, index_num=1):
        key = parent.key()
        title = key.kind() + ' ' + str(key.id_or_name())
        uniq_key = title + KEY_NAME_DELIMITER + str(index_num)
        if hasattr(parent, 'INDEX_TITLE_FROM_PROP'):
            logging.debug("Getting key name from property '%s'", parent.INDEX_TITLE_FROM_PROP)
            if hasattr(parent, parent.INDEX_TITLE_FROM_PROP):
                title = getattr(parent, parent.INDEX_TITLE_FROM_PROP) or title
        return uniq_key + KEY_NAME_DELIMITER + title

    @staticmethod
    def get_title(key_name=''):
        frags = key_name.split(KEY_NAME_DELIMITER)
        if len(frags) < 3:
            return 'Unknown Title'
        else:
            return frags[2]

    @staticmethod
    def get_index_num(key_name=''):
        frags = key_name.split(KEY_NAME_DELIMITER)
        if len(frags) < 2:
            return '1'
        else:
            return frags[1]

    @classmethod
    def put_index(cls, parent, phrases, index_num=1):
        parent_key = parent.key()
        args = {'key_name': cls.get_index_key_name(parent, index_num),
                'parent': parent_key, 'parent_kind': parent_key.kind(), 
                'phrases': phrases }
        return cls(**args).put()


class LiteralIndex(SearchIndex):
    """Index model for non-inflected search phrases."""
    parent_kind = db.StringProperty(required=True)
    phrases = db.StringListProperty(required=True)


class StemmedIndex(SearchIndex):
    """Index model for stemmed (inflected) search phrases."""
    parent_kind = db.StringProperty(required=True)
    phrases = db.StringListProperty(required=True)


class Searchable(object):
    """A class that supports full text indexing and search on entities.
    
    Add this class to your model's inheritance declaration like this:
    
        class Page(Searchable, db.Model):
            title = db.StringProperty()
            author_name = db.StringProperty()
            content = db.TextProperty()
            INDEX_TITLE_FROM_PROP = 'title'
            # INDEX_STEMMING = False
            # INDEX_USES_MULTI_ENTITIES = False
            # INDEX_MULTI_WORD = False
            # INDEX_ONLY = ['content']

    There are a few class variables that can be overridden by your Model.
    The settings were made class variables because their use should be
    declared at Model definition.

    You can declare a string property to be stowed in index key names by
    using the INDEX_TITLE_FROM_PROP variable.  This allows you to retrieve
    useful labels on key-only searches without doing a get() on the whole 
    entity.

    Defaults are for searches to use stemming, multiple index entities,
    and index all basestring-derived properties.  Also, two and three-word
    phrases are inserted into the index, which can be disable by setting
    INDEX_MULTI_WORD to False.

    Stemming is on by default but can be toggled off by setting INDEX_STEMMING
    to False in your class declaration.

    You can set a class variable INDEX_ONLY to a list of property names
    for indexing.  If INDEX_ONLY is not None, only those properties named
    in the list will be indexed.

    Because most search phrase lists generated from an entity will be under
    the approximately 5000 indexed property limit, you can make indexing
    more efficient by setting INDEX_USES_MULTI_ENTITIES to False if you know
    your indexed content will be relatively small (or you don't care about
    some false negatives).  When INDEX_USES_MULTI_ENTITIES is True (default),
    there is slight overhead on every indexing operation because
    we must query for all index entities and delete unused ones.  In the
    case of a single index entity, it can be simply overwritten.

    The enqueue_indexing() method should be called after your model is created or
    edited:

        myPage = Page(author_name='John Doe', content='My amazing content!')
        myPage.put()
        myPage.enqueue_indexing(url='/tasks/searchindexing')

    Note that a url must be included that corresponds with the url mapped
    to search.LiteralIndexing controller.

    You can limit the properties indexed by passing in a list of 
    property names:

        myPage.enqueue_indexing(url='/foo', only_index=['content'])

    If you want to risk getting a timeout during indexing, you could
    index immediately after putting your model and forego task queueing:

        myPage.put()
        myPage.index()

    After your model has been indexed, you may use the search() method:

        Page.search('search phrase')          # -> Returns Page entities
        Page.search('stuff', keys_only=True)  # -> Returns Page keys

    In the case of multi-word search phrases like the first example above,
    the search will first list keys that match the full phrase and then
    list keys that match the AND of individual keywords.  Note that when
    INDEX_USES_MULTI_ENTITIES is True (default), if a Page's index is spread
    over multiple index entities, the keyword AND may fail portion of the
    search may fail, i.e., there will be false negative search results.

    You can use the full_text_search() static method to return all entities,
    not just a particular kind, that have been indexed:

        Searchable.full_text_search('stuff')  # -> Returns any entities
        Searchable.full_text_search('stuff', stemming=False)

    Because stemming can be toggled for any particular Model, only entities will
    be returned that match indexing style (i.e., stemming on or off).
    """

    INDEX_ONLY = None           # Can set to list of property names to index.
    INDEX_STEMMING = True       # Allow stemming to be turned off per subclass.
    INDEX_MULTI_WORD = True     # Add two and three-word phrases to index.

    # If TRUE, incurs additional query/delete overhead on indexing but will workaround
    # indexed properties limit (MAX_ENTITY_SEARCH_PHRASES)
    INDEX_USES_MULTI_ENTITIES = True

    @staticmethod
    def full_text_search(phrase, limit=10, 
                         kind=None, 
                         stemming=INDEX_STEMMING,
                         multi_word_literal=INDEX_MULTI_WORD):
        """Queries search indices for phrases using a merge-join.
        
        Args:
            phrase: String.  Search phrase.
            kind: String.  Returned keys/entities are restricted to this kind.

        Returns:
            A list of (key, title) tuples corresponding to the indexed entities.  
            Multi-word literal matches are returned first.

        TODO -- Should provide feedback if input search phrase has stop words, etc.
        """
        index_keys = []
        keywords = PUNCTUATION_REGEX.sub(' ', phrase).lower().split()
        if stemming:
            stemmer = Stemmer.Stemmer('english')
            klass = StemmedIndex
        else:
            klass = LiteralIndex

        if len(keywords) > 1 and multi_word_literal:
            # Try to match literal multi-word phrases first
            if len(keywords) == 2:
                search_phrases = [' '.join(keywords)]
            else:
                search_phrases = []
                sub_strings = len(keywords) - 2
                keyword_not_stop_word = map(lambda x: x not in STOP_WORDS, keywords)
                for pos in xrange(0, sub_strings):
                    if keyword_not_stop_word[pos] and keyword_not_stop_word[pos+2]:
                        search_phrases.append(' '.join(keywords[pos:pos+3]))
            query = klass.all(keys_only=True)
            for phrase in search_phrases:
                if stemming:
                    phrase = stemmer.stemWord(phrase)
                query = query.filter('phrases =', phrase)
            if kind:
                query = query.filter('parent_kind =', kind)
            index_keys = query.fetch(limit=limit)

        if len(index_keys) < limit:
            new_limit = limit - len(index_keys)
            keywords = filter(lambda x: len(x) >= SEARCH_PHRASE_MIN_LENGTH, keywords)
            if stemming:
                keywords = stemmer.stemWords(keywords)
            query = klass.all(keys_only=True)
            for keyword in keywords:
                query = query.filter('phrases =', keyword)
            if kind:
                query = query.filter('parent_kind =', kind)
            single_word_matches = [key for key in query.fetch(limit=new_limit) \
                                   if key not in index_keys]
            index_keys.extend(single_word_matches)

        return [(key.parent(), SearchIndex.get_title(key.name())) for key in index_keys]

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
            words -= STOP_WORDS
            for word in list(words):
                if len(word) < SEARCH_PHRASE_MIN_LENGTH:
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
            aren't stop words.  (Stop words are allowed in middle of three-word
            phrases like "Statue of Liberty".)

        >>> Searchable.get_search_phraseset('You look through rosy-colored glasses.')
        set(['look through rosy', 'rosy colored', 'colored', 'colored glasses', 'rosy', 'rosy colored glasses', 'glasses', 'look'])
        >>> Searchable.get_search_phraseset('I saw the Statue of Liberty.')
        set(['saw the statue', 'statue of liberty', 'liberty', 'statue'])
        >>> Searchable.get_search_phraseset('Recalling friends, past and present.')
        set(['recalling', 'recalling friends', 'friends'])
        """
        if text:
            datastore_types.ValidateString(text, 'text', max_len=sys.maxint)
            text = text.lower()
            phrases = []
            two_words = []
            three_words = ['', '']
            three_words_no_stop = [False, False]
            text = text.replace('-', ' ')
            fragments = text.split()
            for frag in fragments:
                word, replaced = PUNCTUATION_REGEX.subn('', frag)
                not_end_punctuation = (replaced > 1 or frag[-1] not in string.punctuation)
                if replaced and not_end_punctuation:
                    two_words = []
                    three_words = ['', '']
                three_words.append(word)  # We allow stop words in middle
                if word in STOP_WORDS:
                    two_words = []
                    three_words_no_stop.append(False)
                else:
                    two_words.append(word)
                    three_words_no_stop.append(True)
                    if len(word) >= SEARCH_PHRASE_MIN_LENGTH:
                        phrases.append(word)
                    if len(two_words) == 2:
                        phrases.append(' '.join(two_words))
                        del two_words[0]
                    if len(three_words) == 3 and three_words_no_stop[0]:
                        phrases.append(' '.join(three_words))
                del three_words[0]
                del three_words_no_stop[0]
            phrases = set(phrases)
        else:
            phrases = set()
        return phrases

    @classmethod
    def search(cls, phrase, limit=10, keys_only=False):
        """Queries search indices for phrases using a merge-join.
        
        Use of this class method lets you easily restrict searches to a kind
        and retrieve entities or keys.

        Args:
            phrase: Search phrase (string)
            limit: Number of entities or keys to return.
            keys_only: If True, return only keys with title of parent entity.
        
        Returns:
            A list.  If keys_only is True, the list holds (key, title) tuples.
            If keys_only is False, the list holds Model instances.
        """
        key_list = Searchable.full_text_search(
                        phrase, limit=limit, kind=cls.kind(),
                        stemming=cls.INDEX_STEMMING, 
                        multi_word_literal=cls.INDEX_MULTI_WORD)
        if keys_only:
            logging.debug("key_list: %s", key_list)
            return key_list
        else:
            return [cls.get(key_and_title[0]) for key_and_title in key_list]

    def indexed_title_changed(self):
        """Renames index entities for this model to match new title."""
        klass = StemmedIndex if self.INDEX_STEMMING else LiteralIndex
        query = klass.all(keys_only=True).ancestor(self.key())
        old_index_keys = query.fetch(1000)
        if not hasattr(self, 'INDEX_TITLE_FROM_PROP'):
            raise IndexTitleError('Must declare a property name via INDEX_TITLE_FROM_PROP')
        new_keys = []
        for old_key in old_index_keys:
            old_index = db.get(old_key)
            index_num = SearchIndex.get_index_num(old_key.name())
            index_key = klass.put_index(parent=self, index_num=index_num,
                                        phrases=old_index.phrases)
            new_keys.append(index_key)
        delete_keys = filter(lambda key: key not in new_keys, old_index_keys)
        db.delete(delete_keys)

    def get_search_phrases(self, indexing_func=None):
        """Returns search phrases from properties in a given Model instance.

        Args (optional):
            only_index: List of strings.  Restricts indexing to these property names.
            indexing_func: A function that returns a set of keywords or phrases.

        Note that the indexing_func can be passed in to allow more customized
        search phrase generation.

        Two model variables influence the output of this method:
            INDEX_ONLY: If None, all indexable properties are indexed.
                If a list of property names, only those properties are indexed.
            INDEX_MULTI_WORD: Class variable that allows multi-word search
                phrases like "statue of liberty."
            INDEX_STEMMING: Returns stemmed phrases.
        """
        if not indexing_func:
            klass = self.__class__
            if klass.INDEX_MULTI_WORD:
                indexing_func = klass.get_search_phraseset
            else:
                indexing_func = klass.get_simple_search_phraseset
        if self.INDEX_STEMMING:
            stemmer = Stemmer.Stemmer('english')
        phrases = set()
        for prop_name, prop_value in self.properties().iteritems():
            if (not self.INDEX_ONLY) or (prop_name in self.INDEX_ONLY):
                values = prop_value.get_value_for_datastore(self)
                if not isinstance(values, list):
                    values = [values]
                if (isinstance(values[0], basestring) and
                        not isinstance(values[0], datastore_types.Blob)):
                    for value in values:
                        words = indexing_func(value)
                        if self.INDEX_STEMMING:
                            stemmed_words = set(stemmer.stemWords(words))
                            phrases.update(stemmed_words)
                        else:
                            phrases.update(words)
        return list(phrases)

    def index(self, indexing_func=None):
        """Generates or replaces a search entities for a Model instance.

        Args (optional):
            indexing_func: A function that returns a set of keywords or phrases.

        Note that the indexing_func can be passed in to allow more customized
        search phrase generation.
        """
        search_phrases = self.get_search_phrases(indexing_func=indexing_func)

        key = self.key()
        klass = StemmedIndex if self.INDEX_STEMMING else LiteralIndex

        if self.__class__.INDEX_USES_MULTI_ENTITIES:
            query = klass.all(keys_only=True).ancestor(key)
            previous_index_keys = query.fetch(1000)
        num_phrases = len(search_phrases)

        start_index = 0
        entity_num = 1      # Appended to key name of index entity
        index_keys = []
        while (num_phrases > 0):
            cur_num_phrases = min(num_phrases, MAX_ENTITY_SEARCH_PHRASES)
            end_index = start_index + cur_num_phrases
            num_indices = (num_phrases - 1) / MAX_ENTITY_SEARCH_PHRASES + 1
            index_key = klass.put_index(parent=self, index_num=entity_num,
                                        phrases=search_phrases[start_index:end_index])
            index_keys.append(index_key)
            if self.__class__.INDEX_USES_MULTI_ENTITIES:
                start_index = end_index
                num_phrases -= cur_num_phrases
                entity_num += 1
            else:
                num_phrases = 0    # Only write one index entity
        if self.__class__.INDEX_USES_MULTI_ENTITIES:
            delete_keys = []
            for key in previous_index_keys:
                if key not in index_keys:
                    delete_keys.append(key)
            db.delete(delete_keys)

    def enqueue_indexing(self, url, only_index=None):
        """Adds an indexing task to the default task queue.
        
        Args:
            url: String. The url associated with LiteralIndexing handler.
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
            if not entity:
                self.response.set_status(200)   # Clear task because it's a bad key
            else:
                only_index = only_index_str.split(',') if only_index_str else None
                entity.index()

