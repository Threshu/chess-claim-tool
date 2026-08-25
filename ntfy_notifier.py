import json
import logging
import os
import urllib.request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "serverUrl": "https://ntfy.sh",
    "topic": "lazyarbiter-mc",
    "token": "",
    "enabled": True,
    "notifications": {
        "3fr": {
            "code": "3FR",
            "name": "3-Fold Repetition (Trzykrotne powtórzenie)",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "5fr": {
            "code": "5FR",
            "name": "5-Fold Repetition (5-krotne powtórzenie - Auto Remis)",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "50m": {
            "code": "50M",
            "name": "50-Move Rule (Reguła 50 posunięć)",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "75m": {
            "code": "75M",
            "name": "75-Move Rule (Reguła 75 posunięć - Auto Remis)",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "55m": {
            "code": "55M",
            "name": "55 Moves from start (55 posunięć od początku)",
            "enabled": True,
            "priority": 3,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "insm": {
            "code": "INSM",
            "name": "Niewystarczający materiał (Insufficient Material)",
            "enabled": True,
            "priority": 3,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "agr": {
            "code": "AGR",
            "name": "Zgoda na remis (Draw Agreement)",
            "enabled": False,
            "priority": 2,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "time": {
            "code": "TIME",
            "name": "Przekroczenie czasu (Timeout / Flag)",
            "enabled": True,
            "priority": 5,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "arbiter": {
            "code": "ARBITER",
            "name": "Wezwanie sędziego na stół",
            "enabled": True,
            "priority": 5,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "err_pgn": {
            "code": "ERR_PGN",
            "name": "Błąd pobierania PGN / Rozłączenie",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
        "err_dgt": {
            "code": "ERR_DGT",
            "name": "Błąd połączenia z deską DGT",
            "enabled": True,
            "priority": 4,
            "titleTemplate": "{code} #{board}",
            "bodyTemplate": "{white} - {black}",
            "tags": "",
            "sound": "default",
        },
    },
}


def _header_value(text: str) -> str:
    """ HTTP headers are latin-1; encode non-ASCII titles for ntfy. """
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        import base64
        return "=?utf-8?b?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="


class NtfyNotifier:
    """ Sends claim notifications to ntfy. Text only — no tag/emoji icons. """

    def __init__(self, config_file="ntfy_config.json"):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    logger.info("Wczytano konfigurację z pliku: %s", self.config_file)
                    return json.load(f)
            except Exception as e:
                logger.error("Błąd pliku %s: %s. Używam konfiguracji domyślnej.",
                             self.config_file, e)
        else:
            logger.info("Brak pliku %s. Używam konfiguracji wygenerowanej z panelu.",
                        self.config_file)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def reload_config(self):
        self.config = self.load_config()

    def save_config(self, path=None):
        target = path or self.config_file
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def send_claim_notification(self, claim_code, board_num, white_player="",
                                black_player="", extra_data=None):
        if not self.config.get("enabled", True):
            return False

        notifications = self.config.get("notifications", {})
        notif_cfg = None
        for item in notifications.values():
            if item.get("code") == claim_code:
                notif_cfg = item
                break

        if not notif_cfg or not notif_cfg.get("enabled", True):
            return False

        server_url = self.config.get("serverUrl", "https://ntfy.sh").rstrip("/")
        topic = self.config.get("topic", "")
        if not topic:
            return False

        url = f"{server_url}/{topic}"

        replacements = {
            "{board}": str(board_num),
            "{code}": str(claim_code),
            "{white}": str(white_player),
            "{black}": str(black_player),
            "{name}": str(notif_cfg.get("name", "")),
        }
        if extra_data and isinstance(extra_data, dict):
            for k, v in extra_data.items():
                replacements[f"{{{k}}}"] = str(v)

        title = notif_cfg.get("titleTemplate", "{code} #{board}")
        body = notif_cfg.get("bodyTemplate", "{white} - {black}")
        for k, v in replacements.items():
            title = title.replace(k, v)
            body = body.replace(k, v)

        headers = {
            "Title": _header_value(title),
            "Priority": str(notif_cfg.get("priority", 3)),
        }
        token = self.config.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            from src.DownloadPgn import get_ssl_context
            request = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5, context=get_ssl_context()) as response:
                if 200 <= response.status < 300:
                    logger.info("Ntfy success: %s | %s", title, body)
                    return True
                logger.error("Ntfy error %s", response.status)
                return False
        except HTTPError as e:
            logger.error("Ntfy error %s: %s", e.code, e.reason)
            return False
        except URLError as e:
            logger.error("Ntfy connection error: %s", e.reason)
            return False
        except Exception as e:
            logger.error("Ntfy connection error: %s", e)
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notifier = NtfyNotifier()
    notifier.send_claim_notification("3FR", 6, "Nowak", "Kowalski")
