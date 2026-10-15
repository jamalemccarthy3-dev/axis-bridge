# Code of Conduct

NEXXUS is a small project with a public beta community. These rules keep it a place where people can test, build and disagree honestly.

## For people

* Be respectful. Disagree with ideas, not with the person.
* No harassment, discrimination, threats, doxxing, or sharing other people's private information.
* Keep reviews and builder logs honest. Say what worked and what broke; do not post fake reviews or vote-manipulate.
* Keep secrets out of public posts: keys, tokens, passwords and private file paths.
* Do not use NEXXUS, the sandbox page or the relay to attack, spam or probe other people's systems.

Reports of unacceptable behaviour go to the maintainer through the repository's private channels (see [SECURITY.md](SECURITY.md) for private reporting). They are read in confidence. Depending on severity the maintainer may warn, hide or delete content, or block an account from the repository.

## For the bots

NEXXUS uses automated watchers (`watchers.py`) to notice signs of malicious intent, such as floods, schema probing or repeated refused requests. Their conduct is part of this code:

1. **They observe and flag. They never kill or block.** A watcher may not end a process, stop a service, delete data or lock anyone out. It raises a notification with the evidence and a suggestion.
2. **A human decides.** Any response (Hard Lock, Quarantine, relay pause, blocking an account) is the operator's own deliberate action.
3. **They look at patterns, not people.** They keep counts and short random identifiers only: no names, IP addresses, content or device details.
4. **They are quiet and honest.** A finding fires once per cooldown, says what it saw and what it did not do, and a broken watcher never takes anything else down.
5. **This is tested.** The test suite fails if the watcher module ever gains the ability to end processes or block anyone.

## Scope and enforcement

This applies to the repository, its issues and discussions, the release downloads and the sandbox page. The maintainer applies it fairly and may update it; changes are made in the open through the repository.
