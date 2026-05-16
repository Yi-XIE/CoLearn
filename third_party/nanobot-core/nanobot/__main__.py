"""
This vendor snapshot is kept for CoLearn runtime study and adaptation.

The upstream CLI entrypoint is intentionally disabled here because the
chat-channel, gateway, and WebUI layers are not part of the preferred
integration path inside CoLearn.
"""

if __name__ == "__main__":
    raise SystemExit(
        "This CoLearn vendor snapshot disables the upstream nanobot CLI entrypoint."
    )
