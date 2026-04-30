"""
engine.py — Local Stockfish Integration
============================================================
Smart filtering logic to avoid always playing the best move:

  - Suppress suggestion if you're clearly winning (eval > winning_threshold)
  - Only show a move if move #1 is dramatically better than move #2
    (gap >= critical_gap). These are "only move" tactical moments.
  - Always show if there's a mate sequence on either side.
"""
from __future__ import annotations

import atexit
import os
from dataclasses import dataclass
from typing import List, Optional

import chess
import chess.engine

from config import Config

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
    moves: List[MoveEvaluation]   # moves to show (empty = play freely)
    suppressed: bool              # True = filter decided to hide suggestion
    reason: str                   # shown in the overlay panel


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

    # ── Raw analysis ──────────────────────────────────────────────────────

    def get_top_moves(self, fen: str) -> List[MoveEvaluation]:
        """Return raw top N moves with no filtering."""
        self.last_call_had_restart = False
        if self._engine is None:
            return []

        board = chess.Board(fen)
        num_moves = getattr(self.config, "num_moves", 3)

        for attempt in range(2):
            try:
                info_list = self._engine.analyse(
                    board,
                    chess.engine.Limit(depth=self.config.depth),
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
                return results

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
                    print("[Engine] Stockfish still crashing. May be incompatible with this CPU.")
                    return []

        return []

    # ── Smart filtering ───────────────────────────────────────────────────
    def get_smart_moves(self, fen: str) -> FilterResult:
        moves = self.get_top_moves(fen)
        if not moves:
            return FilterResult(moves=[], suppressed=False, reason="No moves")

        smart_mode = getattr(self.config, "smart_mode", True)
        if not smart_mode:
            return FilterResult(moves=moves, suppressed=False, reason="Smart mode off")

        winning_threshold = getattr(self.config, "winning_threshold", 200)
        critical_gap      = getattr(self.config, "critical_gap",      80)

        best = moves[0]
        best_cp = best.eval_score or 0

        board = chess.Board(fen)
        turn  = board.turn

        # ── VIABLE MOVES FILTER ───────────────────────────────────────────
        # Only keep moves within 100cp of best, or all mate moves if mate exists
        viable_moves = []
        for m in moves:
            if best.mate is not None:
                if m.mate is not None:
                    viable_moves.append(m)
            else:
                m_cp = m.eval_score or -99999
                if (best_cp - m_cp) <= 100:
                    viable_moves.append(m)

        # ── 1. CHECK / MATE ───────────────────────────────────────────────
        # Handle check FIRST — overrides everything else.
        # If in check, the threat scanner must not run (moves are forced).
        if board.is_check():
            if best.mate is not None:
                # Checkmate unavoidable
                label = "for you" if best.mate > 0 else "against you — defend!"
                return FilterResult(
                    moves=viable_moves,
                    suppressed=False,
                    reason=f"⚠ Mate in {abs(best.mate)} {label}",
                )
            # In check but not mate — must escape, always show the move
            return FilterResult(
                moves=viable_moves,
                suppressed=False,
                reason="⚠ You're in check!",
            )

        # Not in check — safe to run mate check on best move
        if best.mate is not None:
            label = "for you" if best.mate > 0 else "against you — defend!"
            return FilterResult(
                moves=viable_moves,
                suppressed=False,
                reason=f"⚠ Mate in {abs(best.mate)} {label}",
            )

        # ── 2. DIRECT THREAT SCANNER ──────────────────────────────────────
        # Only scan YOUR pieces (turn == board.turn).
        # Skip kings — check is already handled above.
        # Also verify the suggested escape move is legal before firing.
        piece_values = {
            chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
            chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100
        }

        under_severe_threat = False
        threat_reason = ""

        for square, piece in board.piece_map().items():
            # Only care about our own pieces, skip king (handled by check logic)
            if piece.color != turn:
                continue
            if piece.piece_type == chess.KING:
                continue

            attackers = board.attackers(not turn, square)
            if not attackers:
                continue

            defenders  = board.attackers(turn, square)
            piece_val  = piece_values.get(piece.piece_type, 0)
            min_atk_val = min(
                piece_values.get(board.piece_at(sq).piece_type, 0)
                for sq in attackers
            )
            piece_name = chess.piece_name(piece.piece_type).title()

            # Attacked by a cheaper piece — clearly losing the trade
            if min_atk_val < piece_val:
                under_severe_threat = True
                threat_reason = f"⚠ {piece_name} under attack!"
                break

            # Completely undefended and attacked
            if not defenders:
                under_severe_threat = True
                threat_reason = f"⚠ Hanging {piece_name}!"
                break

        if under_severe_threat:
            # Sanity check: make sure the best suggested move is actually legal
            # (edge case: threat detected but only legal moves don't address it)
            best_move = chess.Move.from_uci(best.uci)
            if best_move in board.legal_moves:
                return FilterResult(
                    moves=viable_moves,
                    suppressed=False,
                    reason=threat_reason,
                )
            # Best move is somehow illegal — fall through to gap check

        # ── 3. TACTICAL GAP CHECK ─────────────────────────────────────────
        gap = 0
        if len(moves) >= 2:
            second_cp = moves[1].eval_score or 0
            gap = best_cp - second_cp

        if gap >= critical_gap:
            return FilterResult(
                moves=viable_moves,
                suppressed=False,
                reason=f"⚡ Critical! Only move (gap +{gap/100:.1f})",
            )

        # ── 4. WINNING THRESHOLD ──────────────────────────────────────────
        if best_cp >= winning_threshold:
            return FilterResult(
                moves=[],
                suppressed=True,
                reason=f"You're winning (+{best_cp/100:.1f}) — play freely ✓",
            )

        # ── 5. EVEN GAME ──────────────────────────────────────────────────
        return FilterResult(
            moves=[],
            suppressed=True,
            reason=f"Many safe moves (gap {gap/100:.1f}) — play freely ✓",
        )