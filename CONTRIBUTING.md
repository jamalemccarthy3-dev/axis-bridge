# Contributing to NEXXUS

NEXXUS is in Public Beta and the most useful contribution right now is **honest feedback**.

## The easy ways to help

- **Rate and review** the build, or **start a builder log**, from the links in the [README](README.md#community-reviews-ratings-and-builder-logs).
- **Report a bug** with the bug-report form (Issues, New issue). Say what you did, what you expected and what happened.
- **Ask or suggest** in Discussions.

## Code changes

Please open an issue or a discussion before a large change, so we agree on the direction first. This repository keeps a high bar on purpose:

1. **Evidence beats assertion.** A change ships with a test, a measurement or a log. If something is not proven, say so in the docs.
2. **Real data only.** No sample rows, mock results or placeholder code behind something that looks finished.
3. **Fail loudly and safely.** Report problems in plain words; never swallow them.
4. **Tests leave nothing behind.** Run on temp folders.
5. **No personal paths or secrets.** Use paths relative to the file or configurable ones. Never commit keys, tokens or files from the gitignored vaults.
6. **Anything that adds capability, runs outside the sandbox, captures the screen or camera, or changes a trusted file needs the owner's approval.** Say in your pull request which of these your change touches.

Before opening a pull request:

```bash
python verify_all.py
```

It should end with `ALL GREEN`. If you changed a sealed item, say so; the axis gate will report drift until the owner re-signs it.

## License

By contributing you agree that your contribution is licensed under the project's license (PolyForm Noncommercial 1.0.0, see [LICENSE](LICENSE)).

## Conduct

Be respectful; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

Do not report vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).
