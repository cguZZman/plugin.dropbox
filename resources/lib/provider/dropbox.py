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

from clouddrive.common.remote.provider import Provider
from clouddrive.common.ui.logger import Logger


class Dropbox(Provider):
    __api_url = 'https://%s.dropboxapi.com/2'
    _user = None
    
    def __init__(self):
        super(Dropbox, self).__init__('dropbox')
    
    def fetch_tokens_info(self, pin_info, request_params={}):
        tokens_info = super(Dropbox, self).fetch_tokens_info(pin_info, request_params)
        if tokens_info:
            tokens_info['expires_in'] = 315360000
            tokens_info['refresh_token'] = '-'
        Logger.notice(tokens_info)
        return tokens_info
    
    def _get_content_url(self):
        return self.__api_url % 'content'
        
    def _get_api_url(self):
        return self.__api_url % 'api'

    def _get_request_headers(self):
        return None
    
    def get_account(self, request_params={}, access_tokens={}):
        me = self.post('/users/get_current_account', request_params=request_params, access_tokens=access_tokens, headers={'content-type': ''})
        if not me:
            raise Exception('NoAccountInfo')
        self._user = me 
        return { 'id' : self._user['account_id'], 'name' : me['name']['display_name'] }
    
    def get_drives(self, request_params={}, access_tokens={}):
        drives = [{
            'id' : self._user['account_id'],
            'name' : '',
            'type' : self._user['account_type']['.tag']
        }]
        return drives
    
    def get_drive_type_name(self, drive_type):
        if drive_type == 'basic':
            return 'Basic'
        elif drive_type == 'pro':
            return 'Pro'
        elif drive_type == 'business':
            return 'Business'
        return drive_type
    