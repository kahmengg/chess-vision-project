import unittest

import chess

from overlay_ui import sq_screen
from vision import VisionModule


class BoardMappingTests(unittest.TestCase):
    def setUp(self):
        # Avoid launching Chrome; these tests exercise the pure state helpers.
        self.vision = VisionModule.__new__(VisionModule)
        self.vision._last_board = None

    def test_screen_square_mapping_for_both_orientations(self):
        self.assertEqual((0, 7), sq_screen("a1", flipped=False))
        self.assertEqual((7, 0), sq_screen("a1", flipped=True))
        self.assertEqual((7, 0), sq_screen("h8", flipped=False))
        self.assertEqual((0, 7), sq_screen("h8", flipped=True))

    def test_fen_uses_detected_turn(self):
        board = [[""] * 8 for _ in range(8)]
        board[0][4] = "k"  # e8
        board[7][4] = "K"  # e1
        self.assertEqual("4k3/8/8/8/8/8/8/4K3 b - - 0 1", self.vision._to_fen(board, "b"))

    def test_page_fen_is_used_only_when_pieces_match(self):
        board = [[""] * 8 for _ in range(8)]
        board[0][4] = "k"
        board[7][4] = "K"
        matching = "4k3/8/8/8/8/8/8/4K3 b - - 12 44"
        wrong = chess.STARTING_FEN

        self.assertEqual(matching, self.vision._resolve_fen(board, "w", matching))
        self.vision._last_board = None
        self.assertEqual("4k3/8/8/8/8/8/8/4K3 w - - 0 1", self.vision._resolve_fen(board, "w", wrong))

    def test_legal_transition_preserves_real_turn_and_en_passant(self):
        before_d5 = chess.Board()
        for uci in ("e2e4", "a7a6", "e4e5"):
            before_d5.push_uci(uci)
        self.vision._last_board = before_d5
        after_d5 = before_d5.copy()
        after_d5.push_uci("d7d5")
        rows = [[""] * 8 for _ in range(8)]
        for square, piece in after_d5.piece_map().items():
            file_idx = chess.square_file(square)
            rank_idx = chess.square_rank(square)
            rows[7 - rank_idx][file_idx] = piece.symbol()

        resolved = chess.Board(self.vision._resolve_fen(rows, "w", None))
        self.assertEqual(chess.WHITE, resolved.turn)
        self.assertEqual(chess.D6, resolved.ep_square)
        self.assertTrue(resolved.has_kingside_castling_rights(chess.WHITE))


if __name__ == "__main__":
    unittest.main()
