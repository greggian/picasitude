Picasitude
==========
Picasitude is a sync tool between Google's Picasa Web Albums and Google's Latitude Geolocation service  

Why?
----
There are lots of photos that are instantly geo-tagged when taken by a smartphone or similar geo-aware device. This is great because you can come back to a picture and know exactly when and **where** it was taken. That kind of geo-tagging should be available for all of your photos, even if they were taken by a point-and-shoot or dslr. If you use latitude, the data is available and ready to use.

How?
----
Just head over to [Picasitude](http://picasatude.appspot.com). Follow the instructions that walk you through the process. (Coming soon?!)  

The process is pretty straightforward:

*  Give Picasitude access to your Picasa Web and Latitude information. We use oauth so Picasitude will never have your access credentials, that's between you and Google.  
*  Picasitude will grab a list of your albums so you can tell us which album you would like to geotag.  
*  We run through the photos in the album and find the best position from latitude. Updating Picasa as we go!  


Caveats
-------
*  You must opt-in to Latitude's location history feature. Otherwise Latitude only knows/provides your last available location.
*  History data must be available for the time when the photo was taken (+/- an hour or so). We recommend Google Latitude for your mobile phone to keep your locations current, at least while shooting.
*  Timezone support is not yet added so your camera's date and time must be set correctly for your current timezone.
