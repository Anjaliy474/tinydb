"""List the Gemini models this key can use, and try one tiny call on each model in .autose.yml.

Run by hand from the Actions tab ("AutoSE check models") before the first run, since free-tier
models change often.
"""
import os
import sys

from . import config as cfg


def main() -> int:
    from google import genai
    client = genai.Client()
    print("Models with generateContent:")
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" in actions:
            print(f"  {model.name.removeprefix('models/')}")
    conf = cfg.load()
    ok = True
    to_try = [(role, m) for role in conf["models"] for m in conf.models(role)]
    extra = [m.strip() for m in os.environ.get("EXTRA_MODELS", "").split(",") if m.strip()]
    to_try += [("extra", m) for m in extra]
    print("\nTrying the configured models (and any extra ones given):")
    for role, name in to_try:
        if not name.startswith("gemini"):
            print(f"  {role:9s} {name}: not a Gemini model, skipped")
            continue
        try:
            reply = client.models.generate_content(model=name, contents="Reply with the word ok.")
            print(f"  {role:9s} {name}: works ({(reply.text or '').strip()[:20]!r})")
        except Exception as exc:
            if role != "extra":  # a failing extra model doesn't fail the check
                ok = False
            print(f"  {role:9s} {name}: FAILED {getattr(exc, 'code', '')} {str(exc)[:200]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
