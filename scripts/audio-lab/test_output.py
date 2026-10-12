import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from experiment import normalize_extraction, save, si_sdr


class OutputTests(unittest.TestCase):
    def test_arbitrary_model_scale_survives_wav_without_clipping(self):
        t = torch.arange(16000) / 8000
        speech = (torch.sin(2 * torch.pi * 200 * t) * 0.06).unsqueeze(0)
        # Reproduce this checkpoint's very large output and DC offset.
        raw = speech * 150000 + 30
        output = normalize_extraction(raw, speech)
        self.assertAlmostEqual(output.square().mean().sqrt().item(),
                               speech.square().mean().sqrt().item(), places=6)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'output.wav'
            save(path, output, 8000)
            wav, rate = sf.read(path, dtype='float32')
            self.assertEqual(rate, 8000)
            self.assertLess(np.max(np.abs(wav)), 0.95)
            self.assertEqual(np.mean(np.abs(wav) >= 0.999), 0)
            self.assertGreater(si_sdr(torch.from_numpy(wav), speech), 60)

    def test_global_peak_guard_preserves_shape(self):
        signal = torch.tensor([[0., 2., -4., 8., -2.]])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'output.wav'
            save(path, signal, 8000)
            wav, _ = sf.read(path, dtype='float32')
            np.testing.assert_allclose(wav, signal.numpy().flatten() * (0.95 / 8), atol=3.1e-5)

    def test_silence_stays_silent_and_invalid_output_fails(self):
        self.assertTrue(torch.equal(normalize_extraction(torch.ones(1, 4000) * 10,
                                                        torch.zeros(1, 4000)), torch.zeros(1, 4000)))
        with self.assertRaises(ValueError):
            normalize_extraction(torch.tensor([[float('nan')]]), torch.ones(1, 1))


if __name__ == '__main__':
    unittest.main()
