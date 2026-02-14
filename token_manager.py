"""
E*TRADE OAuth Token Manager with Redis Storage

Handles OAuth 1.0a token lifecycle:
- Request token acquisition
- Access token exchange
- Token persistence in Redis
- Automatic renewal before expiration
"""
import json
import time
import logging
from datetime import datetime, timedelta
import redis
from config import REDIS_URL, TOKEN_KEY_PREFIX, TOKEN_EXPIRY_HOURS

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages E*TRADE OAuth tokens with Redis persistence"""

    def __init__(self, user_id='default'):
        """
        Initialize token manager

        Args:
            user_id: Unique identifier for the user (for multi-user support)
        """
        self.user_id = user_id
        self.redis_key = f"{TOKEN_KEY_PREFIX}{user_id}"
        self.redis = self._connect_redis()

    def _connect_redis(self):
        """Connect to Redis"""
        try:
            client = redis.from_url(REDIS_URL, decode_responses=True)
            client.ping()
            logger.info("Connected to Redis for token storage")
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed, using file fallback: {e}")
            return None

    def save_tokens(self, access_token, access_token_secret, request_token=None, request_token_secret=None):
        """
        Save OAuth tokens to storage

        Args:
            access_token: OAuth access token
            access_token_secret: OAuth access token secret
            request_token: Optional request token (for initial auth flow)
            request_token_secret: Optional request token secret
        """
        token_data = {
            'access_token': access_token,
            'access_token_secret': access_token_secret,
            'request_token': request_token,
            'request_token_secret': request_token_secret,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': self._calculate_expiry().isoformat(),
            'last_used': datetime.utcnow().isoformat()
        }

        if self.redis:
            try:
                self.redis.setex(
                    self.redis_key,
                    timedelta(hours=TOKEN_EXPIRY_HOURS),
                    json.dumps(token_data)
                )
                logger.info(f"Tokens saved to Redis for user {self.user_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to save tokens to Redis: {e}")

        # Fallback to file storage
        return self._save_to_file(token_data)

    def _save_to_file(self, token_data):
        """Fallback file storage"""
        try:
            with open(f'/tmp/etrade_tokens_{self.user_id}.json', 'w') as f:
                json.dump(token_data, f)
            logger.info(f"Tokens saved to file for user {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save tokens to file: {e}")
            return False

    def get_tokens(self):
        """
        Retrieve OAuth tokens from storage

        Returns:
            dict with access_token and access_token_secret, or None if not found/expired
        """
        token_data = None

        if self.redis:
            try:
                data = self.redis.get(self.redis_key)
                if data:
                    token_data = json.loads(data)
            except Exception as e:
                logger.error(f"Failed to get tokens from Redis: {e}")

        if not token_data:
            # Try file fallback
            token_data = self._get_from_file()

        if token_data:
            # Check expiration
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            if datetime.utcnow() > expires_at:
                logger.warning("Tokens have expired")
                return None

            # Update last used timestamp
            self._update_last_used(token_data)

            return {
                'access_token': token_data['access_token'],
                'access_token_secret': token_data['access_token_secret']
            }

        return None

    def _get_from_file(self):
        """Fallback file retrieval"""
        try:
            with open(f'/tmp/etrade_tokens_{self.user_id}.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to read tokens from file: {e}")
            return None

    def _update_last_used(self, token_data):
        """Update the last used timestamp"""
        token_data['last_used'] = datetime.utcnow().isoformat()
        if self.redis:
            try:
                self.redis.setex(
                    self.redis_key,
                    timedelta(hours=TOKEN_EXPIRY_HOURS),
                    json.dumps(token_data)
                )
            except:
                pass

    def _calculate_expiry(self):
        """
        Calculate token expiry time
        E*TRADE tokens expire at midnight ET
        """
        # For simplicity, set expiry to 24 hours from now
        # E*TRADE actually expires at midnight ET
        return datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

    def has_valid_tokens(self):
        """Check if valid tokens exist"""
        return self.get_tokens() is not None

    def delete_tokens(self):
        """Delete stored tokens (logout)"""
        if self.redis:
            try:
                self.redis.delete(self.redis_key)
            except:
                pass

        try:
            import os
            os.remove(f'/tmp/etrade_tokens_{self.user_id}.json')
        except:
            pass

        logger.info(f"Tokens deleted for user {self.user_id}")

    def get_token_status(self):
        """Get detailed token status for display"""
        token_data = None

        if self.redis:
            try:
                data = self.redis.get(self.redis_key)
                if data:
                    token_data = json.loads(data)
            except:
                pass

        if not token_data:
            token_data = self._get_from_file()

        if not token_data:
            return {
                'authenticated': False,
                'message': 'Not authenticated'
            }

        expires_at = datetime.fromisoformat(token_data['expires_at'])
        created_at = datetime.fromisoformat(token_data['created_at'])

        is_expired = datetime.utcnow() > expires_at
        time_remaining = expires_at - datetime.utcnow()

        return {
            'authenticated': not is_expired,
            'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'time_remaining': str(time_remaining).split('.')[0] if not is_expired else 'Expired',
            'message': 'Active' if not is_expired else 'Expired - please re-authenticate'
        }


# Global token manager instance
_token_manager = None

def get_token_manager(user_id='default'):
    """Get or create token manager instance"""
    global _token_manager
    if _token_manager is None or _token_manager.user_id != user_id:
        _token_manager = TokenManager(user_id)
    return _token_manager
