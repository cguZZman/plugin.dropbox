import json
import unittest
import urllib.parse
from unittest import mock

import stubs  # noqa: F401
import kodistubs
from resources.lib.provider.dropbox import Dropbox

kodistubs.use_temp_profile()


def entry(item_id, name, path, tag='file'):
    return {'.tag': tag, 'id': item_id, 'name': name, 'path_lower': path, 'server_modified': '2026-10-01T10:00:00Z', 'size': 10}


MOVIES = [entry('id:m', 'Movie.mkv', '/movies/movie.mkv'), entry('id:s', 'Movie.en.srt', '/movies/movie.en.srt'),
          entry('id:t', 'Movie.srt', '/movies/movie.srt'), entry('id:o', 'Movie2.srt', '/movies/movie2.srt')]


class FakeDropbox(Dropbox):
    def __init__(self, responses):
        super(FakeDropbox, self).__init__()
        self.responses = responses
        self.calls = []
        self.cancelled = False

    def _rpc(self, path, args=None, request_params=None, access_tokens=None):
        self.calls.append((path, args))
        key = args.get('path', args.get('cursor', args.get('query'))) if args else None
        return self.responses[(path, key)]

    def cancel_operation(self):
        return self.cancelled


class DropboxProviderTest(unittest.TestCase):
    def test_pages_are_joined_and_deleted_entries_skipped(self):
        d = FakeDropbox({
            ('/files/list_folder', ''): {'entries': [entry('id:a', 'Movies', '/movies', 'folder'), {'.tag': 'deleted', 'name': 'x'}], 'cursor': 'c1', 'has_more': True},
            ('/files/list_folder/continue', 'c1'): {'entries': [entry('id:b', 'song.mp3', '/song.mp3')], 'cursor': 'c2', 'has_more': False}})
        items = d.get_folder_items(path='/')
        self.assertEqual([i['name'] for i in items], ['Movies', 'song.mp3'])
        self.assertIn('folder', items[0])

    def test_children_listed_by_id_get_that_id_as_parent(self):
        d = FakeDropbox({('/files/list_folder', 'id:a'): {'entries': MOVIES, 'cursor': 'c', 'has_more': False}})
        self.assertEqual({i['parent'] for i in d.get_folder_items(item_id='id:a')}, {'id:a'})

    def test_download_goes_through_the_api_with_the_file_id(self):
        d = FakeDropbox({('/files/list_folder', 'id:a'): {'entries': MOVIES[:1], 'cursor': 'c', 'has_more': False}})
        url = d.get_folder_items(item_id='id:a', include_download_info=True)[0]['download_info']['url']
        self.assertTrue(url.startswith('https://content.dropboxapi.com/2/files/download?arg='))
        self.assertEqual(json.loads(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['arg'][0]), {'path': 'id:m'})
        self.assertTrue(d.download_requires_auth)

    def test_subtitles_are_named_after_the_video(self):
        d = FakeDropbox({('/files/list_folder', '/movies'): {'entries': MOVIES, 'cursor': 'c', 'has_more': False}})
        self.assertEqual([s['name'] for s in d.get_subtitles('/movies', 'Movie.mkv')], ['Movie.en.srt', 'Movie.srt'])
        d.cancelled = True
        self.assertEqual(d.get_subtitles('/movies', 'Movie.mkv'), [])

    def test_search_stops_after_the_page_limit(self):
        match = {'matches': [{'metadata': {'.tag': 'metadata', 'metadata': MOVIES[0]}}], 'has_more': True, 'cursor': 'c'}
        d = FakeDropbox({('/files/search_v2', 'movie'): match, ('/files/search/continue_v2', 'c'): match})
        self.assertEqual(len(d.search('movie')), Dropbox._MAX_SEARCH_PAGES)

    def test_root_has_no_metadata_call(self):
        d = FakeDropbox({})
        self.assertIn('folder', d.get_item(path='/'))
        self.assertEqual(d.calls, [])

    def test_calls_without_arguments_send_null(self):
        d = Dropbox()
        d.get_access_tokens = lambda: {'access_token': 'AT', 'refresh_token': 'RT', 'expires_in': 14400, 'date': 9e12}
        with mock.patch('clouddrive.common.remote.request.Request.request_json', lambda request: (request.data, request.headers)):
            self.assertEqual(d._rpc('/users/get_current_account')[0], b'null')
            data, headers = d._rpc('/files/list_folder', {'path': ''})
            self.assertEqual(json.loads(data), {'path': ''})
            self.assertEqual(headers['content-type'], 'application/json')


if __name__ == '__main__':
    unittest.main()


class RecursiveDropbox(FakeDropbox):
    def _rpc(self, path, args=None, request_params=None, access_tokens=None):
        self.calls.append((path, args))
        key = 'recursive' if args and args.get('recursive') else (args.get('path', args.get('cursor')) if args else None)
        return self.responses[(path, key)]


TREE = [entry('id:a', 'Movies', '/movies', 'folder'), entry('id:m', 'Movie.mkv', '/movies/movie.mkv'),
        entry('id:k', 'Kids', '/movies/kids', 'folder'), entry('id:c', 'Cartoon.mp4', '/movies/kids/cartoon.mp4')]


class SubtreeTest(unittest.TestCase):
    def test_one_recursive_listing_gives_every_folder(self):
        d = RecursiveDropbox({
            ('/files/list_folder', 'recursive'): {'entries': TREE[:2], 'cursor': 'c1', 'has_more': True},
            ('/files/list_folder/continue', 'c1'): {'entries': TREE[2:] + [{'.tag': 'deleted', 'name': 'x', 'path_lower': '/movies/x'}], 'cursor': 'c2', 'has_more': False}})
        tree = d.list_subtree(None, 'id:a')
        self.assertEqual({k: [i['id'] for i in v] for k, v in tree.items()}, {'id:a': ['id:m', 'id:k'], 'id:k': ['id:c']})
        self.assertEqual({i['parent'] for i in tree['id:k']}, {'id:k'})
        self.assertIn('download_info', tree['id:a'][0])
        d.calls = []
        for folder in ('id:a', 'id:k'):
            d.get_export_folder_items(None, folder)
        self.assertEqual([c[0] for c in d.calls], ['/files/list_folder', '/files/list_folder/continue'], 'exports reuse the listing')

    def test_the_folder_path_is_looked_up_when_the_listing_omits_it(self):
        d = RecursiveDropbox({
            ('/files/list_folder', 'recursive'): {'entries': TREE[1:], 'cursor': 'c', 'has_more': False},
            ('/files/get_metadata', 'id:a'): entry('id:a', 'Movies', '/movies', 'folder')})
        self.assertEqual([i['id'] for i in d.list_subtree(None, 'id:a')['id:a']], ['id:m', 'id:k'])

    def test_the_dropbox_root(self):
        d = RecursiveDropbox({('/files/list_folder', 'recursive'): {'entries': TREE, 'cursor': 'c', 'has_more': False}})
        tree = d.list_subtree(None, '')
        self.assertEqual([i['id'] for i in tree['']], ['id:a'])
        self.assertEqual([i['id'] for i in tree['id:k']], ['id:c'])

    def test_cancel(self):
        d = RecursiveDropbox({('/files/list_folder', 'recursive'): {'entries': TREE, 'cursor': 'c', 'has_more': False}})
        d.cancelled = True
        self.assertIsNone(d.list_subtree(None, 'id:a'))
