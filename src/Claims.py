"""
Chess Claim Tool: Claims

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
from dataclasses import dataclass
from enum import Enum
from typing import Any

import chess.pgn
from math import ceil


def is_threefold_repetition(self) -> bool:
    """ Checks if a threefold repetition occurred in the game.
    This is an extension method of Class Board class from chess module.
    """
    transposition_key = self._transposition_key()
    repetitions = 1
    switchyard = []

    while self.move_stack and repetitions < 3:
        move = self.pop()
        switchyard.append(move)

        if self.is_irreversible(move):
            break

        if self._transposition_key() == transposition_key:
            repetitions += 1

    while switchyard:
        self.push(switchyard.pop())

    return repetitions >= 3


def is_fifty_moves(self) -> bool:
    """ Checks if the 55 Move Draw Rule occurred in the game.
    This is an extension method of Class Board class from chess module.
    """
    if self.halfmove_clock >= 110:
        if any(self.generate_legal_moves()):
            return True
    return False


chess.Board.is_threefold_repetition = is_threefold_repetition
chess.Board.is_fifty_moves = is_fifty_moves


def get_players(game: Any) -> str:
    white = game.headers["White"][:22]
    black = game.headers["Black"][:22]
    return f"{white} - {black}"


class Claims:
    """
    Attributes:
        dont_check: Players whose games should not be re-checked.
        entries: Already-emitted ClaimEntry objects (dedup).
        enabled_claims: Set of ClaimType values that are active.
    """

    def __init__(self, enabled_claims: set = None):
        self.dont_check = set()
        self.entries = set()
        self.enabled_claims = enabled_claims if enabled_claims is not None else set(ClaimType)

    def set_enabled_claims(self, enabled_claims: set) -> None:
        self.enabled_claims = enabled_claims

    def check_game(self, game: Any, game_index: int = 0) -> set:
        """ Checks the game for 3 Fold Repetitions, 5 Fold Repetitions,
        50 Move Draw Rule and for the 75 Move Draw Rule.
        Args:
            game: The game to be checked.
            game_index: 0-based index of this game in the PGN file.
        """
        move_counter = 0
        board = game.board()
        players = get_players(game)
        board_number = self.get_board_number(game)
        game_entries = set()
        all_moves_list = list(game.mainline_moves())
        total_moves_in_game = len(all_moves_list)
        last_irreversible_move = 0

        # Loop to go through of all the moves of the game.
        for move in game.mainline_moves():
            san_move = str(board.san(move))

            piece = board.piece_at(move.from_square)
            if board.is_capture(move) or (piece is not None and piece.piece_type == 1):
                last_irreversible_move = move_counter + 1

            board.push(move)
            move_counter += 1
            printable_move = self.get_move(move_counter, san_move)

            en = self.enabled_claims

            if ClaimType.EARLY_DRAW in en and game.headers["Result"] == "1/2-1/2" and total_moves_in_game < 60:
                game_entries.add(ClaimEntry(
                    ClaimType.EARLY_DRAW, board_number, players,
                    str(total_moves_in_game / 2), game_index, move_counter, 0
                ))
                break
            if ClaimType.FIVEFOLD in en and board.is_fivefold_repetition():
                game_entries.add(ClaimEntry(
                    ClaimType.FIVEFOLD, board_number, players,
                    printable_move, game_index, move_counter, last_irreversible_move
                ))
                self.dont_check.add(players)
                break
            if ClaimType.SEVENTYFIVE_MOVES in en and board.is_seventyfive_moves():
                game_entries.add(ClaimEntry(
                    ClaimType.SEVENTYFIVE_MOVES, board_number, players,
                    printable_move, game_index, move_counter, last_irreversible_move
                ))
                self.dont_check.add(players)
                break
            if ClaimType.FIFTY_MOVES_FROM_START in en and move_counter == 110:
                game_entries.add(ClaimEntry(
                    ClaimType.FIFTY_MOVES_FROM_START, board_number, players,
                    printable_move, game_index, move_counter, 0
                ))
            if ClaimType.FIFTY_MOVES in en and board.is_fifty_moves():
                game_entries.add(ClaimEntry(
                    ClaimType.FIFTY_MOVES, board_number, players,
                    printable_move, game_index, move_counter, last_irreversible_move,
                    f"First counting move: {last_irreversible_move}"
                ))
            if ClaimType.TWOFOLD in en and board.is_repetition(count=2):
                game_entries.add(ClaimEntry(
                    ClaimType.TWOFOLD, board_number, players,
                    printable_move, game_index, move_counter, last_irreversible_move
                ))
            if ClaimType.THREEFOLD in en and board.is_threefold_repetition():
                game_entries.add(ClaimEntry(
                    ClaimType.THREEFOLD, board_number, players,
                    printable_move, game_index, move_counter, last_irreversible_move
                ))

        game_entries = game_entries - self.entries
        self.entries.update(game_entries)
        return game_entries

    def empty_dont_check(self) -> None:
        self.dont_check.clear()

    def empty_entries(self) -> None:
        self.entries.clear()

    @staticmethod
    def get_move(move_counter: int, san_move: str) -> str:
        """ Returns: The move as it's been displayed in the claimsTable.
        Args:
            move_counter: The number of the moves played in the game.
            san_move: The SAN representation of the move
        """
        move_num = ceil(move_counter / 2)

        if move_counter % 2 == 0:
            move = f"{move_num}...{san_move}"
        else:
            move = f"{move_num}.{san_move}"
        return move

    @staticmethod
    def get_board_number(game: Any) -> str:
        """Return a board identifier shown in UI and used for notifications.

        Many tournament PGNs do not have a `Board` header and encode it as
        `Round` in the form `round.board` (e.g. `3.4`). In that case we show the
        board part only (`4`).
        """
        value = ""
        try:
            value = str(game.headers["Board"])
        except KeyError:
            value = str(game.headers.get("Round", ""))

        value = (value or "").strip()
        if "." in value:
            # Typical convention: ROUND.BOARD -> keep BOARD
            parts = [p for p in value.split(".") if p]
            if parts:
                return parts[-1]
        return value


class ClaimType(Enum):
    TWOFOLD = "2 Fold Repetition"
    THREEFOLD = "3 Fold Repetition"
    FIVEFOLD = "5 Fold Repetition"
    FIFTY_MOVES = "55 Moves Rule"
    SEVENTYFIVE_MOVES = "75 Moves Rule"
    FIFTY_MOVES_FROM_START = "55 Moves from Start"
    EARLY_DRAW = "Early Draw (before 30 moves)"


@dataclass(frozen=True)
class ClaimEntry:
    type: ClaimType
    board_number: str
    players: str
    move: str
    game_index: int
    move_counter: int
    start_move_counter: int
    comment: str = ""
