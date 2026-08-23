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

import urllib.request
from urllib.error import HTTPError, URLError
import certifi

from src.logging_setup import get_logger

logger = get_logger("download")


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
        ret_code = urllib.request.urlopen(url, timeout=timeout, cafile=certifi.where()).getcode()
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
        response = urllib.request.urlopen(url, timeout=timeout, cafile=certifi.where())
        return response.read()
    except (HTTPError, URLError):
        return bytes()
    except Exception:
        logger.warning("download of %s failed", url, exc_info=True)
        return bytes()
