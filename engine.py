"""
engine.py - Local Stockfish integration and chess hint policy.
"""
from __future__ import annotations

import atexit
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import chess
import chess.engine

from config import Config


LOGGER = logging.getLogger(__name__)
DEFAULT_STOCKFISH = "stockfish-windows-x86-64-avx2.exe"


@dataclass
class MoveEvaluation:
    rank: int
    san: str
    uci: str
    from_square: str
    to_square: str
    eval_score: Optional[float]   # centipawns, from current player's POV
    win_chance: Optional[float]
    mate: Optional[int]

    @property
    def score_display(self) -> str:
        if self.mate is not None:
            return f"M{self.mate}"
        if self.eval_score is not None:
            pawns = self.eval_score / 100
            sign = "+" if pawns >= 0 else ""
            return f"{sign}{pawns:.2f}"
        return "?"


@dataclass
class FilterResult:
    moves: List[MoveEvaluation]
    suppressed: bool
    reason: str
    mate_sequence: List[Tuple[str, str]] = field(default_factory=list)


class ChessEngine:
    def __init__(self, config: Config):
        self.config = config
        self._engine = None
        self._engine_path = self._resolve_stockfish_path()
        self._analysis_cache: OrderedDict[tuple, List[MoveEvaluation]] = OrderedDict()
        self._mate_cache: OrderedDict[tuple, List[Tuple[str, str]]] = OrderedDict()
        self.last_call_had_restart = False
        self._start_engine()
        atexit.register(self.close)

    def _resolve_stockfish_path(self) -> str:
        path = getattr(self.config, "stockfish_path", DEFAULT_STOCKFISH)
        if os.path.isabs(path):
            return path
        return os.path.join(os.path.dirname(__file__), path)

    def _limit(self) -> chess.engine.Limit:
        """Use a time budget for responsive UI, with depth as a strength ceiling."""
        depth = max(1, int(getattr(self.config, "depth", 15)))
        seconds = float(getattr(self.config, "analysis_time_seconds", 0.0) or 0.0)
        if seconds > 0:
            return chess.engine.Limit(depth=depth, time=seconds)
        return chess.engine.Limit(depth=depth)

    def _cache_put(self, cache: OrderedDict, key: tuple, value):
        max_size = max(0, int(getattr(self.config, "analysis_cache_size", 128)))
        if max_size == 0:
            return

        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > max_size:
            cache.popitem(last=False)

    def _start_engine(self):
        if not os.path.isfile(self._engine_path):
            raise FileNotFoundError(
                f"Local Stockfish binary not found: {self._engine_path}"
            )
        self._engine = chess.engine.SimpleEngine.popen_uci(self._engine_path)
        LOGGER.info("Local Stockfish connected: %s", self._engine_path)

    def close(self):
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                LOGGER.exception("Error while closing Stockfish")
            self._engine = None

    def _restart_engine(self):
        self.close()
        self._start_engine()

    def get_top_moves(self, fen: str) -> List[MoveEvaluation]:
        """Return raw top N moves with caching for repeated positions."""
        self.last_call_had_restart = False
        if self._engine is None:
            return []

        board = chess.Board(fen)
        num_moves = max(1, int(getattr(self.config, "num_moves", 3)))
        key = (
            fen,
            num_moves,
            int(getattr(self.config, "depth", 15)),
            float(getattr(self.config, "analysis_time_seconds", 0.0) or 0.0),
        )
        if key in self._analysis_cache:
            self._analysis_cache.move_to_end(key)
            return self._analysis_cache[key]

        for attempt in range(2):
            try:
                info_list = self._engine.analyse(
                    board,
                    self._limit(),
                    multipv=num_moves,
                )
                if isinstance(info_list, dict):
                    info_list = [info_list]

                results: List[MoveEvaluation] = []
                for rank, info in enumerate(info_list, start=1):
                    pv = info.get("pv") or []
                    if not pv:
                        continue
                    move = pv[0]
                    score = info["score"].pov(board.turn)
                    mate = score.mate()
                    eval_score = score.score(mate_score=100000)
                    results.append(MoveEvaluation(
                        rank=rank,
                        san=board.san(move),
                        uci=move.uci(),
                        from_square=chess.square_name(move.from_square),
                        to_square=chess.square_name(move.to_square),
                        eval_score=float(eval_score) if eval_score is not None else None,
                        win_chance=None,
                        mate=int(mate) if mate is not None else None,
                    ))
                self._cache_put(self._analysis_cache, key, results)
                return results

            except Exception as exc:
                LOGGER.warning("Local Stockfish error: %s", exc)
                if attempt == 0:
                    try:
                        LOGGER.info("Restarting local Stockfish and retrying once")
                        self._restart_engine()
                        self.last_call_had_restart = True
                    except Exception:
                        LOGGER.exception("Stockfish restart failed")
                        return []
                else:
                    LOGGER.error("Stockfish still failing after restart")
                    return []

        return []

    def get_mate_sequence(self, fen: str) -> List[Tuple[str, str]]:
        """Return a principal variation for mate positions."""
        if self._engine is None:
            return []

        key = (
            "mate",
            fen,
            int(getattr(self.config, "depth", 15)),
            float(getattr(self.config, "analysis_time_seconds", 0.0) or 0.0),
        )
        if key in self._mate_cache:
            self._mate_cache.move_to_end(key)
            return self._mate_cache[key]

        try:
            board = chess.Board(fen)
            info = self._engine.analyse(board, self._limit(), multipv=1)
            if isinstance(info, list):
                info = info[0]
            score = info["score"].pov(board.turn)
            if score.mate() is None:
                return []
            sequence = [
                (chess.square_name(move.from_square), chess.square_name(move.to_square))
                for move in info.get("pv", [])
            ]
            self._cache_put(self._mate_cache, key, sequence)
            return sequence
        except Exception:
            LOGGER.exception("Mate sequence fetch failed")
            return []

    def get_smart_moves(self, fen: str) -> FilterResult:
        moves = self.get_top_moves(fen)
        if not moves:
            return FilterResult(moves=[], suppressed=False, reason="No moves")

        smart_mode = getattr(self.config, "smart_mode", True)
        if not smart_mode:
            return FilterResult(moves=moves, suppressed=False, reason="Smart mode off")

        winning_threshold = getattr(self.config, "winning_threshold", 250)
        critical_gap = getattr(self.config, "critical_gap", 20)
        best = moves[0]
        best_cp = best.eval_score or 0

        board = chess.Board(fen)
        turn = board.turn
        viable_moves = self._viable_moves(moves)

        if board.is_check():
            if best.mate is not None:
                return self._mate_result(fen, viable_moves, best.mate)
            return FilterResult(
                moves=viable_moves,
                suppressed=False,
                reason="In check - find the escape",
            )

        if best.mate is not None:
            return self._mate_result(fen, viable_moves, best.mate)

        threat_reason = self._direct_threat_reason(board, turn)
        if threat_reason:
            best_move = chess.Move.from_uci(best.uci)
            if best_move in board.legal_moves:
                return FilterResult(
                    moves=viable_moves,
                    suppressed=False,
                    reason=threat_reason,
                )

        gap = 0
        if len(moves) >= 2:
            second_cp = moves[1].eval_score or 0
            gap = best_cp - second_cp

        if gap >= critical_gap:
            return FilterResult(
                moves=viable_moves,
                suppressed=False,
                reason=f"Critical only-move moment (gap +{gap/100:.1f})",
            )

        if best_cp >= winning_threshold:
            return FilterResult(
                moves=[],
                suppressed=True,
                reason=f"Winning (+{best_cp/100:.1f}) - play freely",
            )

        return FilterResult(
            moves=[],
            suppressed=True,
            reason=f"Many safe moves (gap {gap/100:.1f}) - play freely",
        )

    def _viable_moves(self, moves: List[MoveEvaluation]) -> List[MoveEvaluation]:
        best = moves[0]
        best_cp = best.eval_score or 0
        viable_moves = []
        for move in moves:
            if best.mate is not None:
                if move.mate is not None:
                    viable_moves.append(move)
            else:
                move_cp = move.eval_score or -99999
                if (best_cp - move_cp) <= 100:
                    viable_moves.append(move)
        return viable_moves

    def _mate_result(
        self,
        fen: str,
        moves: List[MoveEvaluation],
        mate: int,
    ) -> FilterResult:
        label = "for you" if mate > 0 else "against you - defend"
        return FilterResult(
            moves=moves,
            suppressed=False,
            reason=f"Mate in {abs(mate)} {label}",
            mate_sequence=self.get_mate_sequence(fen),
        )

    def _direct_threat_reason(self, board: chess.Board, turn: bool) -> str:
        piece_values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
            chess.KING: 100,
        }

        for square, piece in board.piece_map().items():
            if piece.color != turn or piece.piece_type == chess.KING:
                continue

            attackers = board.attackers(not turn, square)
            if not attackers:
                continue

            defenders = board.attackers(turn, square)
            piece_val = piece_values.get(piece.piece_type, 0)
            min_atk_val = min(
                piece_values.get(board.piece_at(sq).piece_type, 0)
                for sq in attackers
            )
            piece_name = chess.piece_name(piece.piece_type).title()

            if min_atk_val < piece_val:
                return f"{piece_name} is under attack"
            if not defenders:
                return f"Hanging {piece_name}"

        return ""
