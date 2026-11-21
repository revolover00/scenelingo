from urllib.request import Request

import pytest

from yarn_clips import CLIP_ID, _parse_title, _validate_yarn_url, _YarnRedirectHandler


def test_title_requires_whole_word_in_quote():
    page = '<title>YARN | Curious? | A Movie (2020) | Video clips by quotes | ID</title>'
    assert _parse_title(page, 'curious') == ('Curious?', 'A Movie (2020)')
    assert _parse_title(page, 'curio') is None
    assert _parse_title('<title>YARN | Hello | Curious Movie | Video clips</title>', 'curious') is None


def test_search_clip_ids_only():
    page = '<a href="/yarn-clip/305c386b-5828-4421-b5ee-372687117294">x</a>'
    assert CLIP_ID.findall(page) == ['305c386b-5828-4421-b5ee-372687117294']


def test_yarn_fetch_guard_accepts_origin_and_media_subdomains():
    assert _validate_yarn_url('https://yarn.co/yarn-find') == 'https://yarn.co/yarn-find'
    assert _validate_yarn_url('https://cdn.yarn.co/clip.mp4') == 'https://cdn.yarn.co/clip.mp4'


def test_redirect_guard_accepts_same_site_and_blocks_cross_site_redirects():
    handler = _YarnRedirectHandler()
    request = Request('https://yarn.co/yarn-find')
    redirect = handler.redirect_request(request, None, 302, 'Found', {}, '/yarn-clip/id')
    assert redirect.full_url == 'https://yarn.co/yarn-clip/id'

    with pytest.raises(ValueError, match='unexpected URL'):
        handler.redirect_request(request, None, 302, 'Found', {}, 'https://attacker.example/')


@pytest.mark.parametrize(
    'url',
    [
        'file:///etc/passwd',
        'http://yarn.co/clip.mp4',
        'https://yarn.co.attacker.example/clip.mp4',
        'https://attacker-yarn.co/clip.mp4',
        'https://user@yarn.co/clip.mp4',
        'https://cdn.yarn.co:444/clip.mp4',
    ],
)
def test_yarn_fetch_guard_rejects_untrusted_origins(url):
    with pytest.raises(ValueError, match='unexpected URL'):
        _validate_yarn_url(url)
