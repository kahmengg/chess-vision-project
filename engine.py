"""
engine.py — Local Stockfish Integration
============================================================
Sends a FEN to a local Stockfish binary and gets back the best move.

Free and unlimited, as long as the Stockfish executable is present.
"""
from __future__ import annotations

import atexit
import os
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import List, Optional

import chess
import chess.engine

from config import Config

DEFAULT_STOCKFISH = "stockfish-windows-x86-64-avx2.exe"


@dataclass
class MoveEvaluation:
    rank: int
    san: str           # e.g. "e4"
    uci: str           # e.g. "e2e4"
    from_square: str   # e.g. "e2"
    to_square: str     # e.g. "e4"
    eval_score: Optional[float]
    win_chance: Optional[float]
    mate: Optional[int]

    @property
    def score_display(self) -> str:
        if self.mate is not None:
            return f"M{self.mate}"
        if self.eval_score is not None:
            sign = "+" if self.eval_score >= 0 else ""
            return f"{sign}{self.eval_score:.2f}"
        return "?"


class ChessEngine:
    def __init__(self, config: Config):
        self.config = config
        self._engine = None
        self._engine_path = self._resolve_stockfish_path()
        self.last_call_had_restart = False
        self._start_engine()
        atexit.register(self.close)

    def _resolve_stockfish_path(self) -> str:
        path = getattr(self.config, "stockfish_path", DEFAULT_STOCKFISH)
        if os.path.isabs(path):
            return path
        return os.path.join(os.path.dirname(__file__), path)

    def _start_engine(self):
        if not os.path.isfile(self._engine_path):
            raise FileNotFoundError(
                f"Local Stockfish binary not found: {self._engine_path}"
            )

        self._engine = chess.engine.SimpleEngine.popen_uci(self._engine_path)
        print(f"[Engine] Local Stockfish connected OK: {self._engine_path}")

    def close(self):
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    def _restart_engine(self):
        self.close()
        self._start_engine()

    def get_top_moves(self, fen: str) -> List[MoveEvaluation]:
        """
        Analyse the FEN locally and return the best move.
        """
        self.last_call_had_restart = False
        if self._engine is None:
            return []

        board = chess.Board(fen)

        for attempt in range(2):
            try:
                info = self._engine.analyse(board, chess.engine.Limit(depth=self.config.depth))
                pv = info.get("pv") or []
                if not pv:
                    return []

                move = pv[0]
                score = info["score"].pov(board.turn)
                mate = score.mate()
                eval_score = score.score(mate_score=100000)

                return [MoveEvaluation(
                    rank=1,
                    san=board.san(move),
                    uci=move.uci(),
                    from_square=chess.square_name(move.from_square),
                    to_square=chess.square_name(move.to_square),
                    eval_score=float(eval_score) if eval_score is not None else None,
                    win_chance=None,
                    mate=int(mate) if mate is not None else None,
                )]
            except Exception as e:
                print(f"[Engine] Local Stockfish error: {e}")
                if attempt == 0:
                    print("[Engine] Restarting local Stockfish and retrying once...")
                    try:
                        self._restart_engine()
                        self.last_call_had_restart = True
                    except Exception as restart_error:
                        print(f"[Engine] Stockfish restart failed: {restart_error}")
                        return []
                else:
                    print("[Engine] Stockfish still crashing. The executable may be incompatible with this CPU.")
                    return []

        return []

    def _parse_post_payload(self, data) -> List[MoveEvaluation]:
        # Response can be a single dict or a list of dicts (one per variant)
        if isinstance(data, dict):
            data = [data]

        moves: List[MoveEvaluation] = []
        for rank, item in enumerate(data, start=1):
            if item.get("type") not in ("move", "bestmove", None):
                continue
            mv = self._item_to_move(item, rank)
            if mv:
                moves.append(mv)

        return moves

    def _item_to_move(self, item: dict, rank: int) -> Optional[MoveEvaluation]:
        from_sq = item.get("from", "")
        to_sq = item.get("to", "")
        san = item.get("san", item.get("move", "?"))
        uci = item.get("lan", item.get("move", ""))
        ev = item.get("eval")
        wc = item.get("winChance")
        mate = item.get("mate")

        if not from_sq or not to_sq:
            return None

        return MoveEvaluation(
            rank=rank,
            san=san,
            uci=uci,
            from_square=from_sq,
            to_square=to_sq,
            eval_score=float(ev) if ev is not None else None,
            win_chance=float(wc) if wc is not None else None,
            mate=int(mate) if mate is not None else None,
        )

    def _post(self, payload: dict) -> any:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())