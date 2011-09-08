from google.appengine.dist import use_library
#use_library('django', '1.2')
# must come after use_library call

import logging
from google.appengine.ext.webapp import template
import os, sys, urllib, cgi
from datetime import datetime
import bisect
from itertools import groupby

import oauth2 as oauth
import simplejson as json

from google.appengine.api import memcache, quota
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import deferred

sys.path.append('gdata.zip')
import gdata.photos, gdata.photos.service, gdata.auth
import gdata.alt.appengine

from runner import MidnightRunner
import models
import config

request_token_url = 'https://www.google.com/accounts/OAuthGetRequestToken'
#authorize_url = 'https://www.google.com/accounts/OAuthAuthorizeToken'
authorize_url = 'https://www.google.com/latitude/apps/OAuthAuthorizeToken'
access_token_url = 'https://www.google.com/accounts/OAuthGetAccessToken'

request_token_params = {
    'scope': 'https://picasaweb.google.com/data https://www.googleapis.com/auth/latitude',
    'oauth_callback': 'http://picasitude.appspot.com/auth_callback',
}

authorize_token_params = {
    'domain': 'picasitude.appspot.com',
    'granularity': 'best',
    'location': 'all'
}

class MainHandler(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates/main.html')
        template_values = {
        }
        html = template.render(path, template_values)
        self.response.out.write(html)

class AuthHandler(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates/auth.html')
        template_values = {
        }
        html = template.render(path, template_values)
        self.response.out.write(html)


class InitHandler(webapp.RequestHandler):

    def get(self):
        consumer = oauth.Consumer(config.consumer_key, config.consumer_secret)
        client = oauth.Client(consumer)

        qs_params = urllib.urlencode(request_token_params)
        resp, content = client.request(request_token_url, "POST", qs_params)
        if resp['status'] != '200':
            raise Exception("Invalid response %s : %s" % (resp['status'], content) )

        request_resp_parts = dict(cgi.parse_qsl(content))
        request_token = request_resp_parts['oauth_token']
        request_token_secret = request_resp_parts['oauth_token_secret']

        # store oauth_token and secret for use in the callback
        models.OAuthPair(token=request_token, secret=request_token_secret,
                verified=False).put()
        auth_params = authorize_token_params.copy()
        auth_params['oauth_token'] = request_token
        qs_params = urllib.urlencode(auth_params)
        redirect_url = "%s?%s" % (authorize_url, qs_params)
        self.redirect(redirect_url)


class CallbackHandler(webapp.RequestHandler):

    def get(self):
        auth_token = self.request.get("oauth_token")
        auth_verifier = self.request.get("oauth_verifier")
        # retrieve token key from the db
        auth_pair = models.OAuthPair.gql(
                        "WHERE verified = :verified and token = :token",
                        verified=False, token=auth_token).get()
        auth_token_secret = auth_pair.secret
        auth_pair.delete()

        token = oauth.Token(auth_token, auth_token_secret)
        token.set_verifier(auth_verifier)
        consumer = oauth.Consumer(config.consumer_key, config.consumer_secret)
        client = oauth.Client(consumer, token)

        resp, content = client.request(access_token_url, "POST")
        access_resp_parts = dict(cgi.parse_qsl(content))

        access_token = access_resp_parts['oauth_token']
        access_token_secret = access_resp_parts['oauth_token_secret']

        models.OAuthPair(token=access_token, secret=access_token_secret,
                verified=True).put()

        params = {
            'auth_token':access_token
        }
        qs_params = urllib.urlencode(params)
        url = "auth_complete?%s" % qs_params
        self.redirect(url)


class CompleteHandler(webapp.RequestHandler):

    def get(self):
        #logging.debug(self.request)
        auth_token = self.request.get("auth_token")
        auth_pair = models.OAuthPair.gql(
                        "WHERE verified = :verified and token = :token",
                        verified=True, token=auth_token).get()
        token = oauth.Token(auth_pair.token, auth_pair.secret)
        consumer = oauth.Consumer(config.consumer_key, config.consumer_secret)
        client = oauth.Client(consumer, token)

        username, albums = self.fetchAlbumNames(client)

        path = os.path.join(os.path.dirname(__file__), 'templates/albums.html')
        template_values = {
            'user': username,
            'albums': albums,
            'auth_token': auth_token
        }
        html = template.render(path, template_values)
        self.response.out.write(html)



    def fetchLocations(self, client):
        latitude_params = {
            'key': config.latitude_access_key
        }
        qs_params = urllib.urlencode(latitude_params)
        url = "https://www.googleapis.com/latitude/v1/location?%s" % qs_params
        resp, content = client.request(url, "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s : %s" % (resp, content) )
        json_content = json.loads(content)
        locations = json_content['data']['items']
        #logging.info( "location count: %d" % len(locations) )
        #logging.info( [datetime.fromtimestamp(int(entry['timestampMs'])/1000) for entry in locations ] )

    def fetchAlbumNames(self, client):
        #logging.debug("using new featchAlbumNames")
        pws = gdata.photos.service.PhotosService()
        gdata.alt.appengine.run_on_appengine(pws, store_tokens=False, single_user_mode=True)
        oauth_params = gdata.auth.OAuthInputParams(
                                gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
                                config.consumer_key,
                                consumer_secret=config.consumer_secret)
        oauth_token = gdata.auth.OAuthToken(
                        key=client.token.key,
                        secret=client.token.secret,
                        oauth_input_params = oauth_params)
        pws.SetOAuthToken(oauth_token)

        feed = pws.GetUserFeed()
        username = feed.title.text
        albums = [ (album.title.text, album.gphoto_id.text) for album in feed.entry ]
        return username, albums

    def fetchAlbums(self, client):
        url = "https://picasaweb.google.com/data/feed/api/user/default?alt=json&prettyprint=true"
        resp, content = client.request(url, "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s : %s" % (resp, content) )
        json_content = json.loads(content)
        albums = json_content['feed']['entry']
        #logging.info( "album count: %d" % len(albums) )
        #logging.info( [entry['title']['$t'] for entry in albums ] )

    def fetchAlbumNames2(self, client):
        url = "https://picasaweb.google.com/data/feed/api/user/default?alt=json&prettyprint=true"
        resp, content = client.request(url, "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s : %s" % (resp, content) )
        json_content = json.loads(content)
        albums = json_content['feed']['entry']
        return [entry['title']['$t'] for entry in albums ]

class SyncHandler(webapp.RequestHandler):

    def post(self):
        auth_token = self.request.get("auth_token")
        album = self.request.get("album")
        auth_pair = models.OAuthPair.gql(
                        "WHERE verified = :verified and token = :token",
                        verified=True, token=auth_token).get()

        pws = gdata.photos.service.PhotosService()
        gdata.alt.appengine.run_on_appengine(pws, store_tokens=False, single_user_mode=True)
        oauth_params = gdata.auth.OAuthInputParams(
                                gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
                                config.consumer_key,
                                consumer_secret=config.consumer_secret)
        oauth_token = gdata.auth.OAuthToken(
                        key=auth_pair.token,
                        secret=auth_pair.secret,
                        oauth_input_params = oauth_params)
        pws.SetOAuthToken(oauth_token)
        photo_feed = pws.GetFeed('/data/feed/api/user/%s/albumid/%s?kind=photo' % ("default", album))

        photos = photo_feed.entry
        photos.sort(key=lambda photo: photo.exif.time.text)
        grouped = [list(y) for x, y in groupby(photos, key= lambda photo: self.timestampToYMD(photo.exif.time.text))]
        #logging.debug([len(x) for x in grouped])



        token = oauth.Token(auth_pair.token, auth_pair.secret)
        consumer = oauth.Consumer(config.consumer_key, config.consumer_secret)
        client = oauth.Client(consumer, token)


        from google.appengine.api.channel import channel
        #using auth_token as unique client_id to gen a token
        channel_token = channel.create_channel(auth_token)

        runner = MidnightRunner()
        #passing entity to deferred, nto recommended but acceptable
        #as long as we arent updating/storing it
        deferred.defer(runner.run, auth_pair, grouped)

        #data = [ self.buildTuple(photo) for photo in photos.entry ]
        #logging.debug(data)


        path = os.path.join(os.path.dirname(__file__), 'templates/sync.html')
        template_values = {
            'channel_token': channel_token
        }
        html = template.render(path, template_values)
        self.response.out.write(html)

    def timestampToYMD(self, timestampMS):
        timestampS = int(timestampMS)/1000
        dt = datetime.fromtimestamp(timestampS)
        return dt.strftime("%Y%m%d")

    def buildTuple(self, photo):
        timestampS = int(photo.exif.time.text)/1000
        return (
                photo.geo.Point.pos.text,
                photo.title.text,
                datetime.fromtimestamp(timestampS)
                )

application = webapp.WSGIApplication(
                [
                    ('/', MainHandler),
                    ('/auth', AuthHandler),
                    ('/init_auth', InitHandler),
                    ('/auth_callback', CallbackHandler),
                    ('/auth_complete', CompleteHandler),
                    ('/sync', SyncHandler)
                ],
                 debug=True)

def main():
        run_wsgi_app(application)

if __name__ == "__main__":
        main()
