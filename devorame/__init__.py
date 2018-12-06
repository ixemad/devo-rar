#!/usr/bin/env python
# -*- coding: utf-8 -*-
__version__ = '0.1.0'

import click
import logging
import re
import bisect
import os
import os.path
import time
from multiprocessing import Pool

import math

@click.group()
@click.option('--verbose', '-v', count=True, help="Verbosity level")
@click.pass_context
def devorame(ctx, verbose):
    FORMAT = '%(asctime)-15s %(name)s - [%(levelname)s] %(message)s'
    logging.basicConfig(format=FORMAT)
    logger_name, lvl = (lambda l: (None, logging.NOTSET) if l <= 0 else ('devorame', l))(
        logging.WARN - 10 * verbose
    )
    logging.getLogger(logger_name).setLevel(lvl) 

def ignore_sigint():
    signal.signal(signal.SIGINT, signal.SIG_IGN)

import signal    

def terms_callback(ctx, param, value):
    """
    >>> terms_callback(None, None, 'STUPID   Whi$%&te  Men.')
    ['STUPID', 'Whi', 'te', 'Men']
    
    >>> terms_callback(None, None, '!"·$%&/ ()=  ')
    []
    """
    return re.findall('\w+', value, re.LOCALE)

@devorame.command(help="Check if a phrase (between quotation marks) is a palindrome.")
@click.argument('string', nargs=1)
@click.pass_context
def palindrome(ctx, string):
    logger = logging.getLogger('devorame.palindrome')

    if is_palindrome(sanitize(string)):
        print 'Great! That "%s" is a palindrome.' % string
        sys.exit(0)
    else:
        print 'That "%s" is not a palindrome. Keep trying!' % string
        sys.exit(1)

import sys

@devorame.command(name='k-complementary', help="Return the k-complementary pairs of input integers")
@click.argument('k', type=int)
@click.argument('items', nargs=-1, type=int)
@click.pass_context
def k_complementary(ctx, k, items):
    for complementaries in get_k_complementary_pairs(k, items):
        print "%s,%s" % complementaries

@devorame.command(name='tf-idf', help="TF/IDF directory agent")
@click.option('-d', '--directory', required=True, type=click.Path(exists=True, dir_okay=True))
@click.option('-n', '--n-top', required=True, type=int)
@click.option('-p', '--period', required=True, type=int)
@click.option('-t', '--terms', required=True, callback=terms_callback)
@click.pass_context
def tf_idf(ctx, directory, n_top, period, terms):
    logger = logging.getLogger('devorame.tf_idf')

    tfidf = TfIdf()
    ranking = []
    idf = None

    try:
        while True:
            new_documents_and_paths = (
                (filename, os.path.join(directory, filename))
                for filename in os.listdir(directory)
                if not tfidf.has_document(filename)
                if os.path.isfile(os.path.join(directory, filename))
            )

            for document in tfidf.add_async(new_documents_and_paths):
                logger.info('Document %s was processed', document)
                bisect.insort(ranking, (1 - tfidf.tf(document, terms), document))
                idf = None

            idf = tfidf.idf(terms) if idf is None else idf
            print "Top-%s best documents" % n_top
            for inv_score, document in ranking[:n_top]:
                print "%s %.5f" % (document, (1 - inv_score) * tfidf.idf(terms))
            print ""
            time.sleep(period)
    except KeyboardInterrupt as e:
        logger.info('Finishing TF-IDF server')

def sanitize(string):
    """
    >>> sanitize('')
    ''
    
    >>> sanitize("JOjojO")
    'jojojo'
    
    >>> sanitize("What a f#$? ¢a (b) ulous day? 101")
    'whatafabulousday101'
    """
    return ''.join(
        ch for ch in string.lower()
        if 48 <= ord(ch) <= 57 or 97 <= ord(ch) <= 122
    )

def is_palindrome(string):
    """
    >>> is_palindrome("")
    True
    
    >>> is_palindrome("x")
    True
    
    >>> is_palindrome("xX")
    False
    
    >>> is_palindrome("amanaplanacanalpanama")
    True
    
    >>> is_palindrome(sanitize("Was it a car or a cat I saw?"))
    True
    """
    forward_idx = 0
    backward_idx = len(string) - 1

    while (forward_idx < backward_idx):
        if string[forward_idx] != string[backward_idx]:
            return False
        forward_idx += 1
        backward_idx -= 1
    return True

def get_k_complementary_pairs(k, items):
    """
    >>> list(get_k_complementary_pairs(3, [1, 2])) == list(get_k_complementary_pairs(3, [2, 1]))
    True
    
    >>> list(get_k_complementary_pairs(6, [1, 2, 3, 4, 5]))
    [(3, 3), (2, 4), (1, 5)]
    
    >>> list(get_k_complementary_pairs(6, [5, 1, 2, 3, 4]))
    [(1, 5), (3, 3), (2, 4)]
    """

    spotted = {}
    for item in items:
        if item in spotted: continue
        spotted[item] = None
        k_complementary = k - item
        if k_complementary in spotted:
            yield min(k_complementary, item), max(k_complementary, item)

def collect_frequencies(document_and_path):
    try:
        logger = logging.getLogger('devorame.tf_idf')
        document, path = document_and_path
        logger.debug('Collecting frequencies of document %s at %s', document, path)

        frequencies = {}
        with open(path, 'r') as file:
            for line in file:
                for term in re.findall('\w+', line.lower(), re.LOCALE):
                    frequencies.update({term: frequencies.get(term, 0) + 1})

        logger.debug('Frequencies at %s: %s', document, frequencies)

        return document, frequencies
    except KeyboardInterrupt:
        return document, {}

class TfIdf(object):
    def __init__(self):
        self.documents = {}
        self.terms = {}
    
    def add(self, document, path):
        logger = logging.getLogger('devorame.tf_idf')
    
        logger.debug('Adding %s at %s', document, path)
        _, frequencies = collect_frequencies((document, path))     
        logger.debug('%s frequencies: %s', document, frequencies)
    
        for term, frequency in frequencies.iteritems():
            self._update_term_frequency(term, document, frequency)
    
    def add_async(self, documents_and_paths):
        logger = logging.getLogger('devorame.tf_idf')
    
        logger.debug('Processing a stream of input documents')
    
        pool = Pool(None, ignore_sigint)
        try:
            documents_and_frequencies = pool.imap_unordered(
                collect_frequencies, documents_and_paths
            )
    
            logger.debug('Gathering document frequencies')
            for document, frequencies in documents_and_frequencies:
                for term, frequency in frequencies.iteritems():
                    self._update_term_frequency(term, document, frequency)
                yield document
        except KeyboardInterrupt:
            logger.info("TF-IDF loop finished")
            pool.terminate()
            pool.join()
        except Exception:
            logger.info("TF-IDF loop finished")
            pool.terminate()
            pool.join()
            return
    
    def tf(self, document, terms):
        if not terms: return 0.0
    
        terms_in_document = float(self.documents.get(document, 0))
        if not terms_in_document: return 0.0
    
        result = sum(
            self.terms.get(term, {}).get(document, 0)
            for term in terms
        ) / terms_in_document
    
        return result
    
    def idf(self, terms):
        n_documents = float(len(self.documents))
        if not n_documents: return 0.0
        if not terms: return 0.0
    
        logger = logging.getLogger('devorame.tfidf')
        def _idf(term):
            n_term = len(self.terms.get(term, {}))
            result = math.log(n_documents / n_term)
            logger.debug('log(%s/%s)= %s', n_documents, n_term, result)
            return result
    
        return sum(_idf(term) for term in terms) / len(terms)
    
    def has_document(self, document):
        return document in self.documents
    
    def _update_term_frequency(self, term, document, frequency):
        self.terms.update({
            term: dict( self.terms.get(term, {}),
                        **{ document: self.terms.get(
                            term, {}).get(
                                document, 0) + frequency})})
        self.documents.update({
            document: self.documents.get(document, 0) + frequency })

if __name__ == '__main__':
    sys.exit(devorame.main(standalone_mode=False))
