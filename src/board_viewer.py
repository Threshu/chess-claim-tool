"""
Chess Claim Tool: Board Viewer

Copyright (C) 2026 by Tomasz Delega (C) AI-assisted refactoring
"""

import chess
import chess.pgn
import chess.svg
import io

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QTextBrowser,
    QPushButton, QLineEdit, QSizePolicy,
)
from PyQt5.QtGui import QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtSvg import QSvgRenderer

from src.logging_setup import get_logger, log_exceptions

logger = get_logger("board_viewer")

# Claim types that are low-priority (shown in orange)
_ORANGE_LABELS = {"2-fold", "55 from start"}


def _scan_game_claims(game) -> list:
    """Return a list of (label, color) tuples for all claims found in the game."""
    found_labels = set()
    result = []

    total = sum(1 for _ in game.mainline_moves())
    if game.headers.get("Result") == "1/2-1/2" and total < 60:
        return [("early draw", "#bb4400")]

    board = game.board()
    ply = 0
    for move in game.mainline_moves():
        board.push(move)
        ply += 1

        if "5-fold" not in found_labels and board.is_fivefold_repetition():
            found_labels.add("5-fold")
            result.append(("5-fold", "#bb0000"))
        if "75-move" not in found_labels and board.is_seventyfive_moves():
            found_labels.add("75-move")
            result.append(("75-move", "#bb0000"))
        if "3-fold" not in found_labels and board.is_repetition(3):
            found_labels.add("3-fold")
            result.append(("3-fold", "#bb0000"))
        if "55-move" not in found_labels and board.is_fifty_moves():
            found_labels.add("55-move")
            result.append(("55-move", "#bb0000"))
        if "2-fold" not in found_labels and board.is_repetition(2):
            found_labels.add("2-fold")
            result.append(("2-fold", "#b05000"))
        if "55 from start" not in found_labels and ply == 110:
            found_labels.add("55 from start")
            result.append(("55 from start", "#b05000"))

    return result


class BoardViewerWindow(QMainWindow):
    """PGN viewer window with live PGN support and claim annotations."""

    def showEvent(self, event):
        super().showEvent(event)
        self.update_board()

    def __init__(self, pgn_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chess Claim Tool – Board Viewer")
        self.resize(1200, 640)

        self.pgn_path = pgn_path
        self.games = []           # list of (idx, game)
        self.game_claims = {}     # idx → list of (label, color)
        self.filtered_games = []
        self.current_game = None
        self.current_board = None
        self.move_list = []
        self.move_index = 0
        self.current_game_index = 0

        self._build_ui()
        self._load_games()
        self._refresh_game_list()

        if self.filtered_games:
            self.game_list.setCurrentRow(0)
            self.load_game_at_index(0)

        self.setFocusPolicy(Qt.StrongFocus)
        self.centralWidget().setFocus()
        self.pgn_view.setFocusPolicy(Qt.NoFocus)
        self.game_list.setFocusPolicy(Qt.NoFocus)
        self.search_box.setFocusPolicy(Qt.ClickFocus)

    # ------------------------------------------------------------------
    # LOAD GAME / SELECTION
    # ------------------------------------------------------------------

    def load_game_at_index(self, game_index: int):
        if not self.games or game_index < 0 or game_index >= len(self.games):
            return

        self.current_game_index = game_index
        _, game = self.games[game_index]

        self.current_game = game
        self.current_board = game.board()
        self.move_list = list(game.mainline_moves())
        self.move_index = len(self.move_list)

        if hasattr(self, "game_list"):
            self.game_list.setCurrentRow(game_index)
        self._refresh_pgn_with_highlight()
        self.update_board()

    @log_exceptions
    def on_game_selected(self, arg) -> None:
        row = arg if isinstance(arg, int) else self.game_list.row(arg)
        if row < 0 or row >= len(self.filtered_games):
            return

        index, game = self.filtered_games[row]
        self.current_game_index = index
        self.current_game = game
        self.current_board = game.board()
        self.move_list = list(game.mainline_moves())
        self.move_index = len(self.move_list)

        self._refresh_pgn_with_highlight()
        self.update_board()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # LEFT: search + game list (narrow)
        left_layout = QVBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by player name or board number...")
        self.search_box.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self.search_box)

        self.game_list = QListWidget()
        self.game_list.setMinimumWidth(200)
        self.game_list.currentRowChanged.connect(self.on_game_selected)
        left_layout.addWidget(self.game_list)
        main_layout.addLayout(left_layout, 22)

        # CENTER: board + navigation buttons
        center_layout = QVBoxLayout()

        self.board_label = QLabel()
        self.board_label.setMinimumSize(360, 360)
        self.board_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.board_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.board_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        self.btn_start = QPushButton("⏮")
        self.btn_prev  = QPushButton("◀")
        self.btn_next  = QPushButton("▶")
        self.btn_end   = QPushButton("⏭")

        NAV_STYLE = "font-size: 16pt; padding: 6px 0;"
        for btn in [self.btn_start, self.btn_prev, self.btn_next, self.btn_end]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(48)
            btn.setStyleSheet(NAV_STYLE)

        self.btn_start.clicked.connect(self.go_start)
        self.btn_prev.clicked.connect(self.go_prev)
        self.btn_next.clicked.connect(self.go_next)
        self.btn_end.clicked.connect(self.go_end)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_prev)
        btn_layout.addWidget(self.btn_next)
        btn_layout.addWidget(self.btn_end)
        center_layout.addLayout(btn_layout)
        main_layout.addLayout(center_layout, 45)

        # RIGHT: pgn view full height
        self.pgn_view = QTextBrowser()
        self.pgn_view.setOpenLinks(False)
        self.pgn_view.anchorClicked.connect(self.on_move_clicked)
        self._apply_pgn_style()
        font = self.game_list.font()
        font.setPointSize(10)
        self.pgn_view.setFont(font)
        main_layout.addWidget(self.pgn_view, 33)

    def _apply_pgn_style(self):
        self.pgn_view.document().setDefaultStyleSheet("""
            a         { text-decoration: none; color: #222; }
            a:link    { text-decoration: none; color: #222; }
            a:visited { text-decoration: none; color: #222; }
            a:hover   { text-decoration: none; color: #222; }
            a:active  { text-decoration: none; color: #222; }
        """)

    # ------------------------------------------------------------------
    # LOAD GAMES / FILTER
    # ------------------------------------------------------------------

    def _load_games(self) -> None:
        self.games.clear()
        self.game_claims.clear()
        try:
            with open(self.pgn_path, "r", encoding="utf-8") as f:
                idx = 0
                while True:
                    game = chess.pgn.read_game(f)
                    if game is None:
                        break
                    self.games.append((idx, game))
                    self.game_claims[idx] = _scan_game_claims(game)
                    idx += 1
        except Exception as e:
            logger.exception("could not load %s", self.pgn_path)
            self.game_list.addItem(f"Error loading PGN: {e}")
        self.filtered_games = list(self.games)
        logger.info("loaded %s game(s) from %s", len(self.games), self.pgn_path)

    @log_exceptions
    def _apply_filter(self) -> None:
        text = self.search_box.text().lower().strip()
        if not text:
            self.filtered_games = list(self.games)
        else:
            self.filtered_games = []
            is_num = text.isdigit()
            num_q  = int(text) if is_num else None
            for idx, game in self.games:
                white = game.headers.get("White", "").lower()
                black = game.headers.get("Black", "").lower()
                if is_num and idx == num_q:
                    self.filtered_games.append((idx, game))
                    continue
                if text in white or text in black:
                    self.filtered_games.append((idx, game))
        self._refresh_game_list()

    def _refresh_game_list(self) -> None:
        self.game_list.clear()
        for idx, game in self.filtered_games:
            white  = game.headers.get("White", "White")
            black  = game.headers.get("Black", "Black")
            result = game.headers.get("Result", "")
            result_map = {"1-0": "1-0", "0-1": "0-1",
                          "1/2-1/2": "½-½", "½-½": "½-½"}
            rt = result_map.get(result, "")

            claims = self.game_claims.get(idx, [])
            claim_text = ""
            if claims:
                claim_text = "  ·  " + ", ".join(c[0] for c in claims)

            label = f"{idx + 1}. {white} – {black}"
            if rt:
                label += f"  ({rt})"
            label += claim_text

            item = QListWidgetItem(label)

            # Colour the list item by highest severity claim
            if any(c[1] == "#bb0000" for c in claims):
                item.setForeground(QColor("#bb0000"))
            elif any(c[1] == "#b05000" for c in claims):
                item.setForeground(QColor("#b05000"))
            elif any(c[1] == "#bb4400" for c in claims):
                item.setForeground(QColor("#bb4400"))

            self.game_list.addItem(item)

    # ------------------------------------------------------------------
    # PGN HTML — columnar chess notation with claim annotations
    # ------------------------------------------------------------------

    def build_pgn_html(self, game, highlight_index=None) -> str:
        board  = game.board()
        moves  = list(game.mainline_moves())
        total  = len(moves)

        white_name = game.headers.get("White", "White")
        black_name = game.headers.get("Black", "Black")
        result     = game.headers.get("Result", "*")

        html = []
        html.append(
            f'<div style="font-size:13pt;font-weight:bold;margin-bottom:8px;">'
            f'{white_name} – {black_name}</div>'
        )

        if result == "1/2-1/2" and total < 60:
            html.append(
                f'<div style="color:#bb4400;font-weight:bold;margin-bottom:6px;">'
                f'⚠ Early draw ({total // 2} moves)</div>'
            )

        # Build list of rendered move rows: (move_num, white_html, black_html)
        rows = []
        ply = 0
        move_num = 1
        i = 0

        while i < len(moves):
            wm   = moves[i]
            wsan = board.san(wm)
            board.push(wm)
            wc   = self._get_move_claims(board, ply + 1)
            white_html = self._fmt_move(wsan, ply, wc, highlight_index)
            ply += 1
            i   += 1

            if i < len(moves):
                bm   = moves[i]
                bsan = board.san(bm)
                board.push(bm)
                bc   = self._get_move_claims(board, ply + 1)
                black_html = self._fmt_move(bsan, ply, bc, highlight_index)
                ply += 1
                i   += 1
            else:
                black_html = ""

            rows.append((move_num, white_html, black_html))
            move_num += 1

        # Split into columns of 30 move-pairs each
        CHUNK = 30
        chunks = [rows[j: j + CHUNK] for j in range(0, max(len(rows), 1), CHUNK)]

        html.append('<table style="border-collapse:collapse;width:100%;">')
        html.append('<tr style="vertical-align:top;">')

        for chunk in chunks:
            html.append('<td style="padding-right:16px;vertical-align:top;">')
            html.append(
                '<table style="border-collapse:collapse;font-size:10pt;">'
            )
            for mn, wh, bh in chunk:
                html.append('<tr>')
                html.append(
                    f'<td style="font-weight:bold;color:#555;padding:2px 6px 2px 2px;'
                    f'white-space:nowrap;width:34px;vertical-align:top;">{mn}.</td>'
                )
                html.append(
                    f'<td style="padding:2px 10px 2px 2px;white-space:nowrap;'
                    f'vertical-align:top;">{wh}</td>'
                )
                html.append(
                    f'<td style="padding:2px 2px 2px 2px;white-space:nowrap;'
                    f'vertical-align:top;">{bh}</td>'
                )
                html.append('</tr>')
            html.append('</table>')
            html.append('</td>')

        html.append('</tr>')
        html.append('</table>')
        return ''.join(html)

    def _get_move_claims(self, board, ply_count: int) -> list:
        claims = []
        if board.is_fivefold_repetition():
            claims.append(("5-fold", "#bb0000"))
        elif board.is_repetition(3):
            claims.append(("3-fold", "#bb0000"))
        elif board.is_repetition(2):
            claims.append(("2-fold", "#b05000"))

        if board.is_seventyfive_moves():
            claims.append(("75-move", "#bb0000"))
        elif board.is_fifty_moves():
            claims.append(("55-move", "#bb0000"))
        elif ply_count == 110:
            claims.append(("55 from start", "#b05000"))

        return claims

    def _fmt_move(self, san: str, ply: int, claims: list, highlight) -> str:
        is_hl = (highlight == ply)
        if is_hl:
            link = f'<a href="move_{ply}" style="color:#c03000;font-weight:bold;">{san}</a>'
            cell = f'<span style="background:#ffd080;border-radius:3px;padding:0 3px;">{link}</span>'
        else:
            cell = f'<a href="move_{ply}">{san}</a>'

        if claims:
            badges = '&nbsp;'.join(
                f'<span style="color:{color};font-weight:bold;font-size:8pt;">({label})</span>'
                for label, color in claims
            )
            cell += '&nbsp;' + badges

        return cell

    # ------------------------------------------------------------------
    # LIVE PGN RELOAD
    # ------------------------------------------------------------------

    def reload_pgn(self, pgn_path: str):
        try:
            with open(pgn_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            logger.warning("could not re-read %s", pgn_path, exc_info=True)
            return

        all_games = []
        pgn_io = io.StringIO(text)
        while True:
            try:
                game = chess.pgn.read_game(pgn_io)
            except Exception:
                """ games.pgn is rebuilt by MakePgn while we read it, so a
                half-written game here is expected rather than exceptional."""
                logger.warning("stopped parsing %s after %s game(s)",
                               pgn_path, len(all_games), exc_info=True)
                break
            if game is None:
                break
            all_games.append(game)

        self.games = [(i, g) for i, g in enumerate(all_games)]
        self.game_claims = {i: _scan_game_claims(g) for i, g in self.games}
        self.filtered_games = list(self.games)
        self._refresh_game_list()

        if 0 <= self.current_game_index < len(self.filtered_games):
            self.game_list.setCurrentRow(self.current_game_index)
            _, game = self.filtered_games[self.current_game_index]
            self.current_game = game
            self.current_board = game.board()
            self.move_list = list(game.mainline_moves())
            self.move_index = len(self.move_list)
            self._refresh_pgn_with_highlight()
            self.update_board()

    # ------------------------------------------------------------------
    # BOARD RENDERING (no border)
    # ------------------------------------------------------------------

    def update_board(self) -> None:
        if self.current_board is None:
            self.board_label.clear()
            return

        board     = self.current_board.copy()
        last_move = None
        for move in self.move_list[:self.move_index]:
            last_move = move
            board.push(move)

        svg = chess.svg.board(
            board,
            lastmove=last_move,
            colors={
                "square light lastmove": "#fff066",
                "square dark lastmove":  "#fff066",
            }
        )

        renderer   = QSvgRenderer(bytearray(svg, encoding="utf-8"))
        label_size = self.board_label.size()
        side       = max(min(label_size.width(), label_size.height()) - 4, 300)

        pixmap = QPixmap(side, side)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, side, side))
        painter.end()

        self.board_label.setPixmap(pixmap)

    # ------------------------------------------------------------------
    # KEYBOARD
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        k = event.key()
        if   k == Qt.Key_Left:  self.go_prev();  return
        elif k == Qt.Key_Right: self.go_next();  return
        elif k == Qt.Key_Home:  self.go_start(); return
        elif k == Qt.Key_End:   self.go_end();   return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # MOVE NAVIGATION
    # ------------------------------------------------------------------

    def _refresh_pgn_with_highlight(self):
        if not self.current_game:
            return
        hl = self.move_index - 1 if self.move_index > 0 else None
        self.pgn_view.setHtml(self.build_pgn_html(self.current_game, hl))
        self._apply_pgn_style()

    def go_start(self) -> None:
        self.move_index = 0
        self.update_board(); self._refresh_pgn_with_highlight()

    def go_prev(self) -> None:
        if self.move_index > 0:
            self.move_index -= 1
        self.update_board(); self._refresh_pgn_with_highlight()

    def go_next(self) -> None:
        if self.move_index < len(self.move_list):
            self.move_index += 1
        self.update_board(); self._refresh_pgn_with_highlight()

    def go_end(self) -> None:
        self.move_index = len(self.move_list)
        self.update_board(); self._refresh_pgn_with_highlight()

    @log_exceptions
    def on_move_clicked(self, url):
        ply = int(url.toString().split("_")[1])
        self.move_index = ply + 1
        self.update_board()
        self.pgn_view.setHtml(self.build_pgn_html(self.current_game, highlight_index=ply))
        self._apply_pgn_style()

    def jump_to_move(self, move_index: int):
        if not self.move_list:
            return
        self.move_index = max(0, min(move_index, len(self.move_list)))
        self.update_board(); self._refresh_pgn_with_highlight()
