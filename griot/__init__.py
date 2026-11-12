"""griot: an engine-neutral text-to-speech gateway.

One small HTTP service owns the contract clients speak (`POST /speak`); each
TTS engine sits behind an adapter in `griot.engines`. The gateway itself has no
third-party dependencies, so it runs anywhere Python does -- with a neural
engine on a GPU box, or with nothing but espeak on a small one.
"""
