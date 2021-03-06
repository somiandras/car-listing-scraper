#!/usr/bin/env python
# -*- coding: utf8 -*-

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import logging


class BasePage:
    '''
    Provide download method and db connection for webpages.
    '''

    _html = None
    status = None
    BASE_URL = 'https://www.hasznaltauto.hu/szemelyauto'
    HEADERS = {
        'User-Agent': ' '.join([
            'Mozilla/5.0',
            '(Macintosh; Intel Mac OS X 10_12_5)',
            'AppleWebKit/537.36 (KHTML, like Gecko)',
            'Chrome/59.0.3071.115 Safari/537.36'
        ])
    }

    def __init__(self, url, brand, model):
        self.url = url
        self.brand = brand
        self.model = model
        self.logger = logging.getLogger(self._classname())

    def download(self):
        self.logger.debug('Downloading {}'.format(self.url))
        r = requests.get(self.url, headers=self.HEADERS)
        self.status = r.status_code
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self.logger.error(e)
        else:
            self._html = r.text
        
        return self

    @classmethod
    def _classname(cls):
        return cls.__name__


class AdPage(BasePage):
    '''
    Class for interacting with a single car ad page.
    '''

    _data = None

    def __init__(self, url, brand, model):
        super().__init__(url, brand, model)
        
    def parse(self):
        data = {}
        data['details'] = {}
        data['features'] = {}
        data['other'] = {}
        
        self.logger.debug('Parsing {}'.format(self.url))
        
        if self._html is None:
            self.download()

        if self._html is not None:
            soup = BeautifulSoup(self._html, 'lxml')
            data['title'] = soup.find('div', class_='adatlap-cim').text.strip()

            data_table = soup.find('table', class_='hirdetesadatok')
            cells = data_table.find_all('td')

            for cell_index in range(0, len(cells), 2):
                key = cells[cell_index].text.strip()
                value = cells[cell_index + 1].text.strip()
                new_key, new_value = self._clean_key_value(key, value)
                data['details'][new_key] = new_value

            feature_set = soup.find('div', class_='felszereltseg')
            if feature_set:
                for feature in feature_set.find_all('li'):
                    key = feature.text.strip()
                    data['features'][key] = True

            description = soup.find('div', class_='leiras')
            if description:
                data['description'] = description.find('div').text.strip()

            other_features = soup.find('div', class_='egyebinformacio')
            if other_features:                
                for feature in other_features.find_all('li'):
                    key = feature.text.strip()
                    data['other'][key] = True

            data['brand'] = self.brand
            data['model'] = self.model            
            data['url'] = self.url
            data['scraped'] = datetime.today().isoformat()

            self._data = data

        return self

    def _clean_key_value(self, key, value):
        '''
        Clean key-value pair
        '''

        new_key = key[:-1]
        new_value = value

        # Try to extract numerical values
        value_match = re.match(r'''
            ^[^/]*?
            [\s\xa0]?
            ((?:[\s\xa0]?[0-9]{1,3})+)
            [\s\xa0]?
            ([^0-9\s\xa0]*)$
        ''', value, re.VERBOSE)

        if value_match:
            # Numerical value found, update key and value
            extracted_value = value_match.group(1).strip()
            new_value = int(re.sub(r'\s|\xa0', '', extracted_value))
            unit = value_match.group(2)
            if unit:
                # Add unit to key
                new_key = '{} ({})'.format(new_key, unit)
        else:
            new_value = new_value.replace('\xa0', ' ')
        
        return (new_key, new_value)

    @property
    def data(self):
        if self._data is None:
            self.parse()

        return self._data

class ResultsPage(BasePage):
    '''
    Class for interacting a single search results page.
    '''

    _links = None

    def __init__(self, url, brand, model):
        super().__init__(url, brand, model)

    def parse(self):
        if self._html is None:
            self.download()

        self.logger.debug('Parsing {}'.format(self.url))
        
        if self._html is not None:
            soup = BeautifulSoup(self._html, 'lxml')
            result_items = soup.find_all('div', class_='cim-kontener')
            self._links = [item.find('a').get('href') for item in result_items]
        return self

    @property
    def ads(self):
        '''
        Generator yielding AdPage instances for each ad link on the
        result page.
        '''

        if self._links is None:
            self.parse()

        if self._links is not None:
            for url in self._links:
                yield AdPage(url, self.brand, self.model)
        else:
            return list()


class ModelSearch(BasePage):
    '''
    Search page for given brand and model.
    '''

    _page_count = None

    def __init__(self, url, brand, model):
        super().__init__(url, brand, model)
        if self.url is None:
            self.url = '{0}/{1}/{2}'.format(self.BASE_URL, self.brand, self.model)

    def parse(self):
        if self._html is None:
            self.download()
        
        self.logger.debug('Parsing {}'.format(self.url))

        if self._html is not None:
            try:
                soup = BeautifulSoup(self._html, 'lxml')
                last_page = int(soup.find('li', class_='last').text)
            except AttributeError as e:
                self.logger.error(e)
                self.logger.error(self.url)
            except TypeError as e:
                self.logger.error(e)
                self.logger.error('self._html: {}'.format(self._html))
            else:
                self._page_count = last_page

        return self

    @property
    def page_count(self):
        '''
        Download initial page of results list and parse the
        number of pages.
        '''

        if self._page_count is None:
            self.parse()

        return self._page_count

    @property
    def pages(self):
        '''
        Generator yielding result pages of the search for the given
        brand and model.
        '''
        if self.page_count is not None:
            for page in range(1, self.page_count + 1):
                url = '{}/page{}'.format(self.url, page)
                yield ResultsPage(url, self.brand, self.model)
        else:
            return list()
