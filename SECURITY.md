# Security policy

NEXXUS runs a local web server, background engines and an optional phone bridge on your own computer, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting: on this repository, open the **Security** tab, choose **Report a vulnerability**, and describe what you found, how to reproduce it and what you think it affects.
If that button is not available, open a public issue that says only "I have a security report, please enable private reporting" with no details, and the maintainer will arrange a private channel.

You can expect an acknowledgement within a few days. NEXXUS is a one-person project in Public Beta, so fixes are made as fast as one person can make them, and you will be credited if you want to be.

## What is in scope

- The local server (`python_server.py`) and its routes, including anything reachable from another machine or another website.
- The axis gate, signing, ticket and quarantine logic.
- The intake and tool-ingestion pipeline (anything that could run or trust outside code without the owner's approval).
- The capture module (`capture.py`): screen and camera capture must stay off by default, local-only and logged.
- Operator mode folder scope (`operator_scope.py`): access outside a granted folder must always be refused.
- The phone bridge and the update feed.

## Defaults worth knowing

- The server listens on the loopback address only unless you turn phone access on.
- The governance secret and the admin token are created on first run, kept on your machine and never committed.
- Nothing is sent out by default: no accounts, no tracking.

## Supported versions

Only the latest release and the `main` branch receive fixes.

## Please keep out of public posts

Keys, tokens, passwords, private paths and screenshots of your own dashboard that show them.
