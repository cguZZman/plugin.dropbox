#-------------------------------------------------------------------------------
# Copyright (C) 2017 Carlos Guzman (cguZZman) carlosguzmang@protonmail.com
# 
# This file is part of Dropbox for Kodi
# 
# Dropbox for Kodi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Cloud Drive Common Module for Kodi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------

import datetime
import urllib

from clouddrive.common.cache.simplecache import SimpleCache
from clouddrive.common.ui.addon import CloudDriveAddon
from clouddrive.common.utils import Utils
from resources.lib.provider.dropbox import Dropbox
import json
from clouddrive.common.ui.logger import Logger


class DropboxAddon(CloudDriveAddon):
    _provider = Dropbox()
    _headers = {'content-type': 'application/json'}
    _parameters = {'include_media_info' : True}
    _cache = None
    _child_count_supported = False
    _change_token = None
    def __init__(self):
        self._cache = SimpleCache()
        super(DropboxAddon, self).__init__()
        
    def get_provider(self):
        return self._provider
    
    def get_my_files_menu_name(self):
        return self._addon.getLocalizedString(32013)
    
    def get_custom_drive_folders(self, driveid):
        drive_folders = []
        drive_folders.append({'name' : self._common_addon.getLocalizedString(32058), 'path' : 'sharedWithMe'})
        return drive_folders

    def new_change_token_slideshow(self, change_token, driveid, item_driveid=None, item_id=None, path=None):
        self._provider.configure(self._account_manager, driveid)
        if not change_token:
            response = self._provider.get('/changes/startPageToken', parameters = self._parameters)
            self._change_token = Utils.get_safe_value(response, 'startPageToken')
            change_token = 1
        else:
            page_token = self._change_token
            while page_token:
                self._parameters['pageToken'] = page_token
                self._parameters['fields'] = 'nextPageToken,newStartPageToken,changes(file(id,name,parents))'
                response = self._provider.get('/changes', parameters = self._parameters)
                if self.cancel_operation():
                    return
                self._change_token = Utils.get_safe_value(response, 'newStartPageToken', self._change_token)
                changes = Utils.get_safe_value(response, 'changes', [])
                for change in changes:
                    f = Utils.get_safe_value(change, 'file', {})
                    parents = Utils.get_safe_value(f, 'parents', [])
                    parents.append(f['id'])
                    if item_id in parents:
                        return change_token + 1
                page_token = Utils.get_safe_value(response, 'nextPageToken')
        return change_token
    
    def get_folder_items(self, driveid, item_driveid=None, item_id=None, path=None, on_items_page_completed=None):
        self._provider.configure(self._account_manager, driveid)
        item_driveid = Utils.default(item_driveid, driveid)
        url = '/files/list_folder'
        continue_url = '/list_folder/continue'
        if item_id:
            self._parameters['path'] = item_id
        elif path == 'sharedWithMe':
            continue_url = url = '/sharing/list_shared_links'
            del self._parameters['include_media_info']
        elif path == '/':
            self._parameters['path'] = ''
        files = self._provider.post(url, parameters = self._parameters, headers=self._headers)
        if self.cancel_operation():
            return
        return self.process_files(driveid, files, continue_url, on_items_page_completed)
    
    def search(self, query, driveid, item_driveid=None, item_id=None, on_items_page_completed=None):
        self._provider.configure(self._account_manager, driveid)
        item_driveid = Utils.default(item_driveid, driveid)
        self._parameters['fields'] = 'files(%s)' % self._file_fileds
        query = 'fullText contains \'%s\'' % query
        if item_id:
            query += ' and \'%s\' in parents' % item_id
        self._parameters['q'] = query
        files = self._provider.post('/files', parameters = self._parameters, headers=self._headers)
        if self.cancel_operation():
            return
        return self.process_files(driveid, files, on_items_page_completed)
    
    def process_files(self, driveid, files, continue_url, on_items_page_completed=None):
        items = []
        if 'links' in files:
            file_list = files['links']
        else:
            file_list = files['entries']
        for f in file_list:
            item = self._extract_item(f, driveid)
            cache_key = self._addonid+'-drive-'+driveid+'-item_driveid-'+item['drive_id']+'-item_id-'+item['id']+'-path-None'
            self._cache.set(cache_key, f, expiration=datetime.timedelta(minutes=1))
            items.append(item)
        if on_items_page_completed:
            on_items_page_completed(items)
        if 'has_more' in files and files['has_more']:
            next_files = self._provider.post(continue_url, parameters = {'cursor': files['cursor']}, headers=self._headers )
            if self.cancel_operation():
                return
            items.extend(self.process_files(driveid, next_files, continue_url, on_items_page_completed))
        return items
    
    def _extract_item(self, f, driveid, include_download_info=False):
        size = long('%s' % Utils.get_safe_value(f, 'size', 0))
        item = {
            'id': f['id'],
            'name': f['name'],
            'name_extension' : Utils.get_extension(f['name']),
            'drive_id' : driveid,
            'path_lower' : f['path_lower'],
            'last_modified_date' : Utils.get_safe_value(f,'client_modified'),
            'size': size
        }
        if f['.tag'] == 'folder':
            item['folder'] = {'child_count' : 0}
        metadata = Utils.get_safe_value(Utils.get_safe_value(f,'media_info',{}), 'metadata', {})
        tag = Utils.get_safe_value(metadata, '.tag', '')
        if tag == 'video':
            video = metadata['video']
            dimensions = Utils.get_safe_value(video, 'dimensions', {})
            item['video'] = {
                'width' : long('%s' % Utils.get_safe_value(dimensions, 'width', 0)),
                'height' : long('%s' % Utils.get_safe_value(dimensions, 'height', 0)),
                'duration' : long('%s' % Utils.get_safe_value(video, 'duration', 0)) / 1000
            }
        elif tag == 'photo':
            item['image'] = {'size' : size}
        if include_download_info:
            parameters = {
                'arg' : json.dumps({'path': item['id']}),
                'authorization' : 'Bearer %s' % self._provider.get_access_tokens()['access_token']
            }
            url = self._provider._get_content_url() + '/files/download'
            item['download_info'] =  {
                'url' : url + '?%s' % urllib.urlencode(parameters)
            }
        return item
    
    def get_item(self, driveid, item_driveid=None, item_id=None, path=None, find_subtitles=False, include_download_info=False):
        self._provider.configure(self._account_manager, driveid)
        item_driveid = Utils.default(item_driveid, driveid)
        cache_key = self._addonid+'-drive-'+driveid+'-item_driveid-'+Utils.str(item_driveid)+'-item_id-'+Utils.str(item_id)+'-path-'+Utils.str(path)
        f = self._cache.get(cache_key)
        if not f :
            if item_id:
                path = item_id
            elif path == '/':
                path = ''
            self._parameters['path'] = path
            f = self._provider.post('/files/get_metadata', parameters = self._parameters, headers=self._headers)
            self._cache.set(cache_key, f, expiration=datetime.timedelta(seconds=59))
        item = self._extract_item(f, driveid, include_download_info)
        if find_subtitles:
            subtitles = []
            parent_path = Utils.get_parent_path(item['path_lower'])
            if parent_path == '/':
                parent_path = ''
            self._parameters['path'] = parent_path
            self._parameters['query'] = urllib.quote(Utils.remove_extension(item['name']))
            self._parameters['mode'] = 'filename'
            del self._parameters['include_media_info']
            files = self._provider.post('/files/search', parameters = self._parameters, headers=self._headers)
            for f in files['matches']:
                subtitle = self._extract_item(f['metadata'], driveid, include_download_info)
                if subtitle['name_extension'] == 'srt' or subtitle['name_extension'] == 'sub' or subtitle['name_extension'] == 'sbv':
                    subtitles.append(subtitle)
            if subtitles:
                item['subtitles'] = subtitles
        Logger.notice(item)
        return item
    
if __name__ == '__main__':
    DropboxAddon().route()

