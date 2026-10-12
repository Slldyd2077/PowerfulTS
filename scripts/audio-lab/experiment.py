"""Offline speech enhancement / reference-conditioned extraction experiments.

No changes to live calls. Models and WAV artifacts stay in the local lab folder.
"""
import argparse
import importlib.util
import json
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as audio_functional

from paths import ROOT
SOURCE_REV = '6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61'
MODEL_REV = '2b99a144297ac4d074bb9dcc4ce9734a7e8924fd'


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f'Downloading {path.name}', flush=True)
        temporary = path.with_suffix(path.suffix + '.part')
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as out:
            while data := response.read(1024 * 1024):
                out.write(data)
        temporary.replace(path)
    return path


def read_audio(path, rate):
    data, original_rate = sf.read(path, dtype='float32', always_2d=True)
    data = torch.from_numpy(data.mean(axis=1)).unsqueeze(0)
    if original_rate != rate:
        data = audio_functional.resample(data, original_rate, rate)
    if not torch.isfinite(data).all() or data.shape[-1] < rate * 0.5:
        raise ValueError('Audio must contain at least 0.5 seconds of finite samples')
    return data


class Engines:
    def __init__(self, device='cpu'):
        self.device = torch.device(device)
        torch.set_num_threads(4)
        self.deep = None
        self.spex = None

    def deepfilter(self, samples):
        from df.enhance import enhance, init_df
        if self.deep is None:
            self.deep = init_df(model_base_dir='DeepFilterNet3')[:2]
            self.deep[0].to(self.device)
        model, state = self.deep
        # enhance() manages STFT/model state and compensates algorithmic delay.
        with torch.inference_mode():
            return enhance(model, state, samples, pad=True).cpu()

    def extract(self, samples, reference):
        if self.spex is None:
            source = download(
                f'https://raw.githubusercontent.com/modelscope/ClearerVoice-Studio/{SOURCE_REV}/'
                'train/target_speaker_extraction/models/SpEx_plus/SpEx_plus.py',
                ROOT / 'models' / 'SpEx_plus.py')
            checkpoint = download(
                f'https://huggingface.co/alibabasglab/log_wsj0-2mix_speech_SpEx-plus_2spk/resolve/{MODEL_REV}/'
                'checkpoints/log_wsj0-2mix_speech_SpEx-plus_2spk/last_best_checkpoint.pt',
                ROOT / 'models' / 'spex-best.pt')
            spec = importlib.util.spec_from_file_location('spex_upstream', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            args = SimpleNamespace(causal=False, network_audio=SimpleNamespace(
                L=20, N=256, X=8, R=4, B=256, H=512, P=3,
                norm='gLN', non_linear='relu', speakers=101))
            self.spex = module.SpEx_plus(args)
            weights = torch.load(checkpoint, map_location='cpu', weights_only=True)
            print('Checkpoint fields:', list(weights)[:8], flush=True)
            weights = weights.get('model', weights.get('model_state_dict', weights))
            weights = {k.removeprefix('module.').removeprefix('sep_network.'): v for k, v in weights.items()}
            self.spex.load_state_dict(weights, strict=True)
            self.spex.to(self.device).eval()
        with torch.inference_mode():
            result = self.spex(samples.to(self.device), reference.to(self.device),
                               torch.tensor([reference.shape[-1]], device=self.device))[0]
        # The SI-SDR-trained checkpoint has an arbitrary output scale. Upstream
        # evaluation peak-normalizes its estimate before perceptual evaluation.
        # Restore a bounded listening level BEFORE PCM serialization, without
        # clipping individual samples or changing the waveform's dynamics.
        return normalize_extraction(result.cpu(), samples)


def normalize_extraction(result, mixture):
    if not torch.isfinite(result).all() or not torch.isfinite(mixture).all():
        raise ValueError('Model produced non-finite audio')
    result = result - result.mean(dim=-1, keepdim=True)
    input_rms = mixture.square().mean().sqrt().item()
    output_rms = result.square().mean().sqrt().item()
    if input_rms < 1e-5 or output_rms < 1e-12:
        return torch.zeros_like(result)
    # Keep a conservative reference level; do not make a quiet input louder.
    target_rms = min(0.08, input_rms)
    gain = min(target_rms / output_rms, 0.95 / result.abs().max().item())
    return result * gain


def si_sdr(estimate, target):
    x = estimate.flatten().numpy().astype(np.float64)
    y = target.flatten().numpy().astype(np.float64)
    length = min(len(x), len(y))
    x, y = x[:length], y[:length]
    x, y = x - x.mean(), y - y.mean()
    projection = np.dot(x, y) / (np.dot(y, y) + 1e-12) * y
    return float(10 * np.log10((np.dot(projection, projection) + 1e-12) /
                              (np.sum((x - projection) ** 2) + 1e-12)))


def save(path, samples, rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = samples.squeeze().numpy()
    if not np.isfinite(data).all():
        raise ValueError('Cannot save non-finite audio')
    peak = float(np.max(np.abs(data)))
    # A single global attenuation preserves shape. Hard clipping would destroy
    # a high-gain model output while scale-invariant metrics still look good.
    if peak > 0.95:
        data = data * (0.95 / peak)
    sf.write(path, data, rate, subtype='PCM_16')


def saved_stats(path, target):
    data, rate = sf.read(path, dtype='float32')
    return {'sample_rate': rate, 'peak': float(np.max(np.abs(data))),
            'rms': float(np.sqrt(np.mean(data ** 2))),
            'clipped_fraction': float(np.mean(np.abs(data) >= 0.999)),
            'saved_si_sdr_db': si_sdr(torch.from_numpy(data), target)}


def demo(engines):
    sample_root = ROOT / 'samples'
    samples = {}
    for name in ['spk1_snt1', 'spk1_snt2', 'spk2_snt1', 'spk2_snt2']:
        samples[name] = download(
            f'https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/{name}.wav',
            sample_root / f'{name}.wav')
    target = read_audio(samples['spk1_snt1'], 48000)
    interferer = read_audio(samples['spk2_snt1'], 48000)
    duration = min(target.shape[-1], interferer.shape[-1], 48000 * 10)
    target = target[:, :duration]
    interferer = interferer[:, :duration]
    target = target * (0.08 / target.square().mean().sqrt())
    interferer = interferer * (0.08 / interferer.square().mean().sqrt())
    rng = np.random.default_rng(42)
    noise = torch.from_numpy(rng.normal(0, 0.04, target.shape).astype('float32'))
    noisy = target + noise
    mixture = target + interferer
    save(sample_root / 'clean-target.wav', target, 48000)
    save(sample_root / 'noise-input.wav', noisy, 48000)
    save(sample_root / 'two-speakers-input.wav', mixture, 48000)
    # Warm-up includes loading/downloads; timing excludes initialization.
    engines.deepfilter(noisy)
    started = time.perf_counter()
    enhanced = engines.deepfilter(noisy)
    df_seconds = time.perf_counter() - started
    save(sample_root / 'deepfilter-output.wav', enhanced, 48000)
    mix8 = audio_functional.resample(mixture, 48000, 8000)
    target8 = audio_functional.resample(target, 48000, 8000)
    other8 = audio_functional.resample(interferer, 48000, 8000)
    ref = read_audio(samples['spk1_snt2'], 8000)
    ref_other = read_audio(samples['spk2_snt2'], 8000)
    engines.extract(mix8, ref)
    started = time.perf_counter()
    extracted = engines.extract(mix8, ref)
    spex_seconds = time.perf_counter() - started
    extracted_other = engines.extract(mix8, ref_other)
    save(sample_root / 'spex-target-output.wav', extracted, 8000)
    save(sample_root / 'spex-other-output.wav', extracted_other, 8000)
    report = {
        'device': str(engines.device), 'torch': torch.__version__,
        'audio_seconds': duration / 48000,
        'deepfilter': {'inference_seconds': df_seconds, 'rtf': df_seconds / (duration / 48000),
                       'input_si_sdr_db': si_sdr(noisy, target), 'output_si_sdr_db': si_sdr(enhanced, target)},
        'spex': {'inference_seconds': spex_seconds, 'rtf': spex_seconds / (duration / 48000),
                 'sample_rate': 8000, 'causal': False,
                 'input_si_sdr_db': si_sdr(mix8, target8), 'target_si_sdr_db': si_sdr(extracted, target8),
                 'other_reference_si_sdr_db': si_sdr(extracted_other, other8)},
        'limits': 'Public short English recordings + synthetic noise. Not a live latency/Chinese/mobile benchmark.'}
    report['saved_wav'] = {
        'deepfilter': saved_stats(sample_root / 'deepfilter-output.wav', target),
        'spex_target': saved_stats(sample_root / 'spex-target-output.wav', target8),
        'spex_other': saved_stats(sample_root / 'spex-other-output.wav', other8)}
    (ROOT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['demo', 'deepfilter', 'spex'])
    parser.add_argument('--input', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'output.wav')
    parser.add_argument('--device', default='cpu', choices=['cpu', 'cuda'])
    args = parser.parse_args()
    engines = Engines(args.device)
    if args.mode == 'demo':
        demo(engines)
        return
    if not args.input or (args.mode == 'spex' and not args.reference):
        parser.error('--input is required; spex also needs --reference')
    rate = 48000 if args.mode == 'deepfilter' else 8000
    samples = read_audio(args.input, rate)
    result = engines.deepfilter(samples) if args.mode == 'deepfilter' else engines.extract(
        samples, read_audio(args.reference, rate))
    save(args.output, result, rate)
    print(args.output)


if __name__ == '__main__':
    main()
