import logging
import os
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
import requests

LOG = logging.getLogger(__name__)
API = 'https://api.unsplash.com/search/photos'


def referral(url):
    if not url or not url.startswith('https://unsplash.com/'):
        return None
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query))
    query.update(utm_source='aerolink', utm_medium='referral')
    return urlunparse(parts._replace(query=urlencode(query)))


def find_destination_photo(destination):
    """Return image URL + credit; None on missing key, no results or network failure."""
    key = os.getenv('UNSPLASH_ACCESS_KEY', '').strip()
    if not key:
        return None
    headers = {'Authorization': f'Client-ID {key}', 'Accept-Version': 'v1'}
    try:
        response = requests.get(API, headers=headers, params={
            'query': f'{destination} travel city landmark',
            'orientation': 'landscape', 'content_filter': 'high', 'per_page': 5,
        }, timeout=7)
        response.raise_for_status()
        for photo in response.json().get('results', []):
            image_url = (photo.get('urls') or {}).get('regular')
            user = photo.get('user') or {}
            name = user.get('name')
            profile = referral((user.get('links') or {}).get('html'))
            download = (photo.get('links') or {}).get('download_location')
            if not (image_url and name and profile and download):
                continue
            # Assigning a cover is a download-like event under Unsplash API guidelines.
            if urlparse(download).hostname != 'api.unsplash.com' or not download.startswith('https://'):
                continue
            try:
                tracked = requests.get(download, headers=headers, timeout=5)
                tracked.raise_for_status()
            except requests.RequestException:
                LOG.warning('Unsplash cover selection tracking failed; skipping photo')
                continue
            return {'image_url': image_url, 'image_credit': {
                'photographer': name, 'photographer_url': profile,
                'unsplash_url': 'https://unsplash.com/?utm_source=aerolink&utm_medium=referral',
            }}
    except (requests.RequestException, ValueError, TypeError):
        LOG.warning('Unsplash photo search failed', exc_info=True)
    return None
