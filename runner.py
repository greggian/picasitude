import logging
import sys, urllib
from datetime import datetime, timedelta
import time
from itertools import groupby
import bisect
from operator import itemgetter

import oauth2 as oauth
import simplejson as json

from google.appengine.ext import deferred
from google.appengine.api.channel import channel

sys.path.append('gdata.zip')
import gdata.photos, gdata.photos.service, gdata.auth
import gdata.alt.appengine

import models
import config


class MidnightRunner(object):

    #def __init__(self):

    def run(self, auth_pair, photos, locs=None):
        if not photos or not len(photos):
            return

        photoGroup = photos[0]

        if not locs:
            locs = self.getGroupLocs(auth_pair, photoGroup)
            # this took some time, schedule it for new run
            deferred.defer(self.run, auth_pair, photos, locs)
            return

        photo = photoGroup[0]
        loc = self.getClosestLoc(locs, photo.exif.time.text)
        if loc :
            #logging.info("updating photo: "+photo.title.text)
            self.updatePhoto(auth_pair, photo, loc)
            msg = {
                    'title': photo.title.text,
                    'thumbnail': photo.media.thumbnail[0].url,
                    'lat':loc['latitude'],
                    'lng': loc['longitude']
            };
            channel.send_message(auth_pair.token, json.dumps(msg))

        photoGroup.pop(0)
        if len(photoGroup) == 0:
            photos.pop(0)
            locs = None

        if not len(photos) == 0:
            deferred.defer(self.run, auth_pair, photos, locs)


    def getClosestLoc(self, locs, time):
        loc_dates = [loc['timestampMs'] for loc in locs]
        idx = bisect.bisect_left(loc_dates, time)
        if idx :
           return locs[idx]
        return None


    def getGroupLocs(self, auth_pair, photoGroup):
        firstTime = photoGroup[0].exif.time.text
        lastTime = photoGroup[-1].exif.time.text

        dt = datetime.fromtimestamp(int(firstTime)/1000)
        mindt = datetime.combine(dt, datetime.min.time())
        maxdt = mindt + timedelta(days=1)

        minMs = time.mktime(mindt.timetuple()) * 1000
        maxMs = time.mktime(maxdt.timetuple()) * 1000

        minMs = int(minMs)
        maxMs = int(maxMs)

        locs = self.fetchLocations(auth_pair, minMs, maxMs)
        #locs.sort(key=lambda loc: loc['timestampMs'])
        locs.sort(key=itemgetter('timestampMs'))
        return locs

    def updatePhoto(self, auth_pair, photo, loc):
        lat = loc['latitude']
        lon = loc['longitude']

        if not photo.geo:
            photo.geo = gdata.geo.Where()
        if not photo.geo.Point:
            photo.geo.Point = gdata.geo.Point()
        photo.geo.Point.pos = gdata.geo.Pos(text='%s %s' % (lat, lon))

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

        #try:
        photo = pws.UpdatePhotoMetadata(photo)
        #except gdata.photos.service.GooglePhotosException, err:
        #    logging.error("Error updating photo: %s %s" % (err.error_code, err.reason))

    def fetchLocations(self, auth_pair, minTime, maxTime):
        params = {}
        params['key'] = config.latitude_access_key
        params['min-time'] = minTime
        params['max-time'] = maxTime
        params['max-results'] = 1000

        qs_params = urllib.urlencode(params)
        url = "https://www.googleapis.com/latitude/v1/location?%s" % qs_params

        token = oauth.Token(auth_pair.token, auth_pair.secret)
        consumer = oauth.Consumer(config.consumer_key, config.consumer_secret)
        client = oauth.Client(consumer, token)
        resp, content = client.request(url, "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s : %s" % (resp, content) )
        json_content = json.loads(content)
        locations = json_content['data']['items']
        #logging.info( "location count: %d" % len(locations) )
        #logging.info( [datetime.fromtimestamp(int(entry['timestampMs'])/1000) for entry in locations ] )
        return locations

