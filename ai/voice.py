"""
Voice alerts via pyttsx3 (cross-platform). No-op if voice disabled in config.
"""
def speak(text):
    """Convert text to speech and play. Returns immediately if voice disabled."""
    if not text or not text.strip():
        return
    try:
        import config
        if not getattr(config, 'VOICE_ALERTS', False):
            return
    except Exception:
        return
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text.strip())
        engine.runAndWait()
    except Exception:
        pass
