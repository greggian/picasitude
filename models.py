from google.appengine.ext import db

class OAuthPair(db.Model):
    """Model for Authorized oauth accounts"""
    token = db.StringProperty(required=True)
    secret = db.StringProperty(required=True)
    verified = db.BooleanProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
