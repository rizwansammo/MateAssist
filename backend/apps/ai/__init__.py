"""AI engines and the credential vault.

Implemented in Phase 4:
  vault.py    AES-256-GCM envelope encryption for provider credentials (D-071)
  models.py   ProviderKey, ModelPrice
  engines/    TextEngine (DeepSeek) and VisionEngine (Gemini), D-040/D-041
  router.py   key pool and the only metered path to either engine

The engine contract lives in engines/: images reach Gemini and stop there, and
only the text it returns continues to DeepSeek (D-042).
"""
