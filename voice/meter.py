"""Live mic level + VAD meter -- dial in your gain.

  python meter.py --device 17 --channel 0     # SM57 on Scarlett XLR
  python meter.py -l                           # list input devices

Turn the interface gain until normal speech sits in the green (peak ~0.2-0.5)
without hitting CLIP. [SPEECH] lights when Silero VAD fires -- that's what the
loop needs. Captures at the device's native rate and downsamples, opening every
channel and reading --channel (Scarlett presents the mic only as stereo ch0).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import sounddevice as sd

from mic import FRAME, SAMPLE_RATE, SileroVAD, _resample


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device")
    ap.add_argument("--channel", type=int, default=0)
    ap.add_argument("-l", "--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"[{i}] {d['name']}  ch={d['max_input_channels']} "
                      f"sr={int(d['default_samplerate'])}")
        return 0

    device = int(args.device) if args.device and args.device.isdigit() else args.device
    info = sd.query_devices(device, "input")
    rate = int(info["default_samplerate"])
    nchan = max(1, int(info["max_input_channels"]))
    ch = min(args.channel, nchan - 1)
    block = round(FRAME * rate / SAMPLE_RATE)
    vad = SileroVAD()
    print(f"device={device} {info['name']!r}  {nchan}ch @ {rate}Hz  reading ch{ch}")
    print("talk -- aim peak 0.2-0.5, [SPEECH] should light. Ctrl-C to stop.\n")
    with sd.InputStream(samplerate=rate, channels=nchan, dtype="float32",
                        blocksize=block, device=device) as stream:
        try:
            while True:
                data, _ = stream.read(block)
                f = _resample(data[:, ch].copy(), FRAME)
                rms = float(np.sqrt((f ** 2).mean()))
                peak = float(np.abs(f).max())
                prob = vad(f)
                bars = int(min(peak, 1.0) * 40)
                clip = " CLIP!" if peak >= 0.99 else ""
                flag = "[SPEECH]" if prob >= 0.5 else "        "
                print(f"\r{flag} |{'#'*bars}{'.'*(40-bars)}| peak={peak:.3f} "
                      f"vad={prob:.2f}{clip}", end="", flush=True)
        except KeyboardInterrupt:
            print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
