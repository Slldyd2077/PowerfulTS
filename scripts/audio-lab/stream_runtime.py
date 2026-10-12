"""Official v0.5.6 LADSPA runtime. One process per call owns all DSP state.

The plugin starts a native worker thread; process isolation also guarantees that
disconnect releases that thread and its model memory (not just the LADSPA handle).
Wire format: 960 mono PCM16LE samples per 20 ms, stdin -> stdout.
"""
import ctypes as C
import os
import sys
import time
from pathlib import Path

import numpy as np
from paths import ROOT

U = C.c_ulong
P = C.c_void_p
F = C.POINTER(C.c_float)
Instantiate = C.CFUNCTYPE(P, P, U)
Connect = C.CFUNCTYPE(None, P, U, F)
Run = C.CFUNCTYPE(None, P, U)
Action = C.CFUNCTYPE(None, P)


class Descriptor(C.Structure):
    _fields_ = [('id', U), ('label', C.c_char_p), ('properties', C.c_int),
                ('name', C.c_char_p), ('maker', C.c_char_p), ('copyright', C.c_char_p),
                ('count', U), ('ports', P), ('names', C.POINTER(C.c_char_p)),
                ('hints', P), ('implementation', P), ('instantiate', Instantiate),
                ('connect', Connect), ('activate', Action), ('run', Run),
                ('run_adding', P), ('gain', P), ('deactivate', Action), ('cleanup', Action)]


def main():
    os.environ['RAYON_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    # Rust sleeps for ~2 ms while awaiting its native worker. Windows' default
    # 15.6 ms timer otherwise triggers spurious underruns and growing buffers.
    C.WinDLL('winmm').timeBeginPeriod(1)
    root = ROOT
    dll = C.CDLL(str(root / 'deep_filter.dll'))
    dll.ladspa_descriptor.argtypes = [U]
    dll.ladspa_descriptor.restype = C.POINTER(Descriptor)
    pointer = dll.ladspa_descriptor(0)
    descriptor = pointer.contents
    handle = descriptor.instantiate(pointer, 48000)
    if not handle or descriptor.count != 8:
        raise RuntimeError('Unsupported DeepFilter LADSPA descriptor')
    input_pcm = np.zeros(960, dtype=np.float32)
    output_pcm = np.zeros(960, dtype=np.float32)
    descriptor.connect(handle, 0, input_pcm.ctypes.data_as(F))
    descriptor.connect(handle, 1, output_pcm.ctypes.data_as(F))
    # Unlimited suppression, official inference thresholds, one processing frame.
    controls = [C.c_float(v) for v in (100, -15, 35, 35, 2, 0)]
    for index, value in enumerate(controls, 2):
        descriptor.connect(handle, index, C.pointer(value))
    if descriptor.activate:
        descriptor.activate(handle)
    # Warm native kernels and settle asynchronous controls before accepting speech.
    for _ in range(20):
        descriptor.run(handle, 960)
        time.sleep(.02)
    sys.stdout.buffer.write(b'READY\n')
    sys.stdout.buffer.flush()
    while True:
        raw = sys.stdin.buffer.read(1920)
        if not raw:
            break
        if len(raw) != 1920:
            raise ValueError('Truncated PCM frame')
        input_pcm[:] = np.frombuffer(raw, dtype='<i2') / 32768.0
        descriptor.run(handle, 960)
        if not np.isfinite(output_pcm).all():
            raise ValueError('Non-finite model output')
        pcm = (np.clip(output_pcm, -.999, .999) * 32767).astype('<i2')
        sys.stdout.buffer.write(pcm.tobytes())
        sys.stdout.buffer.flush()
    # Native worker has no join API in this release. Exit tears down the process.
    os._exit(0)


if __name__ == '__main__':
    main()
