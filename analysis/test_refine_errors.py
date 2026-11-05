import unittest
import refine_errors as r
import chess

class MotifChecks(unittest.TestCase):
    def test_knight_fork_wins_material_after_reply(self):
        b=chess.Board('q3k3/8/8/1N6/8/8/8/4K3 w - - 0 1')
        self.assertIn('knight_fork',r.motif_labels(b,['b5c7','e8d7','c7a8','d7d6']))

    def test_ordinary_pawn_exchange_is_not_free_piece(self):
        b=chess.Board();b.push_san('e4');b.push_san('d5')
        self.assertNotIn('free_piece_capture',r.motif_labels(b,['e4d5','d8d5']))

    def test_pinned_defender_cannot_recapture(self):
        b=chess.Board('4k3/4n3/2r5/1B6/8/8/8/4R1K1 w - - 0 1')
        labels=r.motif_labels(b,['b5c6','e8f8'])
        self.assertIn('absolute_pin',labels)
        self.assertIn('free_piece_capture',labels)

    def test_checking_king_skewer(self):
        b=chess.Board('4q3/8/8/4k3/8/8/8/R5K1 w - - 0 1')
        self.assertIn('king_skewer',r.motif_labels(b,['a1e1','e5d5','e1e8','d5d4']))

    def test_discovered_check(self):
        b=chess.Board('6k1/8/8/6N1/8/8/8/6RK w - - 0 1')
        self.assertIn('discovered_check',r.motif_labels(b,['g5e6']))

    def test_endgame_material_types(self):
        self.assertEqual(r.endgame_kind(chess.Board('4k3/8/8/8/8/8/P7/4K3 w - - 0 1')),'King and pawn')
        self.assertEqual(r.endgame_kind(chess.Board('r3k3/8/8/8/8/8/P7/R3K3 w - - 0 1')),'Single rook versus single rook')
        self.assertEqual(r.endgame_kind(chess.Board('rr2k3/8/8/8/8/8/P7/RR2K3 w - - 0 1')),'Double rook endings')

    def test_exact_mate_count(self):
        b=chess.Board('7k/5K2/6Q1/8/8/8/8/8 w - - 0 1')
        self.assertIn('g6g7',r.mating_moves(b))
        for move in r.mating_moves(b):
            after=b.copy();after.push_uci(move);self.assertTrue(after.is_checkmate())

if __name__=='__main__':unittest.main()
