# Standard lib imports
import logging
import os

# Third party imports
import requests

# Project level imports
from ecsminion.util.exceptions import ECSMinionException


# Suppress the insecure request warning
# https://urllib3.readthedocs.org/en/
# latest/security.html#insecurerequestwarning
requests.packages.urllib3.disable_warnings()

log = logging.getLogger(__name__)


class TokenRequest(object):
    """
    This is a helper class to fetch a new token from the ECS controller
    and return the token as well as store it locally. Prior to fetching a new
    token we check if we have a local token and if so, whether or not it is
    still valid
    """

    def __init__(self, username, password, ecs_endpoint, token_endpoint,
                 verify_ssl, token_filename, token_location, request_timeout,
                 cache_token):
        """
        Create a new TokenRequest instance

        :param username: The username to fetch a token
        :param password: The password to fetch a token
        :param ecs_endpoint: The URL where ECS is located
        :param token_endpoint: The URL where the ECS login is located
        :param verify_ssl: Verify SSL certificates
        :param token_filename: The name of the cached token filename
        :param token_location: By default this is stored in /tmp
        :param request_timeout: How long to wait for ECS to respond
        :param cache_token: Whether to cache the token, by default this is true
        you should only switch this to false when you want to directly fetch
        a token for a user
        """
        self.username = username
        self.password = password
        self.ecs_endpoint = ecs_endpoint
        self.token_endpoint = token_endpoint
        self.verify_ssl = verify_ssl
        self.token_verification_endpoint = ecs_endpoint + '/user/whoami'
        self.token_filename = token_filename
        self.token_location = token_location
        self.request_timeout = request_timeout
        self.cache_token = cache_token
        self.token_file = os.path.join(
            self.token_location, self.token_filename)
        self.session = requests.Session()

    def get_new_token(self):
        """
        Request a new authentication token from ECS and persist it
        to a file for future usage if cache_token is true

        :return: Returns a valid token, or None if failed
        """
        log.info("Getting new token")
        self.session.auth = (self.username, self.password)

        req = self.session.get(self.token_endpoint,
                               verify=self.verify_ssl,
                               headers={'Accept': 'application/json'},
                               timeout=self.request_timeout)

        if req.status_code == 401:
            msg = 'Invalid username or password'
            log.fatal(msg)
            raise ECSMinionException(
                http_status_code=req.status_code,
                ecs_message=req.text,
                message=msg)
        if req.status_code != 200:
            msg = 'Non-200 status returned ({0})'.format(req.status_code)
            log.fatal(msg)
            raise ECSMinionException(
                http_status_code=req.status_code,
                ecs_message=req.text,
                message=msg)

        token = req.headers['x-sds-auth-token']

        if self.cache_token:
            log.debug("Caching token to '{0}'".format(self.token_file))
            with open(self.token_file, 'w') as token_file:
                token_file.write(token)

        return token

    def get_token(self):
        """
        Attempt to get an existing token, if successful then ensure it
        hasn't expired yet. If its expired, fetch a new token

        :return: A token
        """
        # XXX(brett): Maybe honor `cache_token' flag here? If user sets
        # cache_token to False, he may be expecting the cache to be skipped
        # entirely.
        token = self._get_existing_token()

        if token:
            log.debug("Validating cached token")
            req = self._request(token, self.token_verification_endpoint)

            if req.status_code == requests.codes.ok:
                log.debug("Cached token is valid")
                return token

        return self.get_new_token()

    def _get_existing_token(self):
        """
        Attempt to open and read the token file if it exists

        :return: If available return the token, if not return None
        """
        if os.path.isfile(self.token_file):
            log.debug("Reading cached token at '{0}'".format(self.token_file))
            with open(self.token_file, 'r') as token_file:
                return token_file.read()
        log.debug("No cached token found")
        return None

    def _request(self, token, url):
        """
        Perform a request and place the token header inside the request header

        :param token: A valid token
        :param url:  The URL to perform a request
        :return: Request Object
        """
        headers = {'Accept': 'application/json',
                   'X-SDS-AUTH-TOKEN': token}
        try:
            return self.session.get(url, verify=self.verify_ssl,
                                    headers=headers,
                                    timeout=self.request_timeout)
        except requests.ConnectionError as conn_err:
            msg = 'Connection error: {0}'.format(conn_err.args)
            log.error(msg)
            raise ECSMinionException(message=msg)
        except requests.HTTPError as http_err:
            msg = 'HTTP error: {0}'.format(http_err.args)
            log.error(msg)
            raise ECSMinionException(message=msg)
        except requests.RequestException as req_err:
            msg = 'Request error: {0}'.format(req_err.args)
            log.error(msg)
            raise ECSMinionException(message=msg)
