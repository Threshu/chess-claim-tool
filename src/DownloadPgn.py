"""
Chess Claim Tool: DownloadPgn

Copyright (C) 2019 Serntedakis Athanasios <thanasis@brainfriz.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import ssl
import urllib.request
from urllib.error import HTTPError, URLError
import certifi

from src.logging_setup import get_logger

logger = get_logger("download")

_ssl_context = None


def get_ssl_context():
    """ The certifi CA bundle as an SSLContext, built once and reused.

    urlopen's cafile argument was deprecated in Python 3.6 and removed in 3.13,
    where passing it raises TypeError; context is the replacement. Building the
    context parses the whole CA bundle, so it is cached - the download workers
    poll every couple of seconds for hours on end.
    """
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = ssl.create_default_context(cafile=certifi.where())
    return _ssl_context


def check_download(url: str, timeout=4) -> bool:
    """ Checks if the url points to an existing pgn file.
    Args:
        timeout:
        url(str): The location of the file to check.
    Returns:
        True if successful, False otherwise.
    """
    if not (url.endswith(".pgn")):
        return False

    try:
        ret_code = urllib.request.urlopen(url, timeout=timeout, context=get_ssl_context()).getcode()
    except (HTTPError, URLError, ValueError):
        return False
    except OSError:
        logger.warning("check_download failed for %s", url, exc_info=True)
        return False
    return ret_code == 200


def download_pgn(url: str, timeout=10) -> bytes:
    """ Download a pgn, returning empty bytes on any failure.

    Every error must be contained here. This runs inside DownloadGames.run(), and
    an exception escaping a QThread's run() is fatal: PyQt aborts the process with
    no dialog and no traceback once the app is packaged without a console.
    HTTPError/URLError alone are not enough - a connection reset, a read timeout or
    a truncated response raises socket.timeout, ConnectionResetError or
    http.client.IncompleteRead straight out of response.read().
    """
    try:
        response = urllib.request.urlopen(url, timeout=timeout, context=get_ssl_context())
        return response.read()
    except (HTTPError, URLError):
        return bytes()
    except Exception:
        logger.warning("download of %s failed", url, exc_info=True)
        return bytes()
