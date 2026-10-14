# Security policy

## Supported versions

Only the latest release gets security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
**Security > Report a vulnerability** on the
[repository page](https://github.com/Ignacio-Aranda/handcue/security/advisories/new).
Do not open a public issue.

Include what an attacker can do, the steps to reproduce it and the version you tested. You
should get an answer within a week. Once a fix is released, the advisory is published and
you are credited unless you prefer not to be.

## Scope

HandCue runs as your user and can, by design, start programs, type text and run the
commands you configure. Things that are in scope include, for example:

- another local user reading or changing your settings or face data,
- a crafted model file, image or configuration making the app run code you did not configure,
- face data being written unencrypted or overwritten without your consent,
- a binding firing much more often than its cooldown allows.

Things that are expected behavior rather than vulnerabilities:

- someone in front of your camera making a gesture you configured (use *Only obey registered
  people* for sensitive bindings),
- face recognition accepting a photo of a registered person (there is no liveness check yet),
- a "Run command" binding doing what its command says.

[docs/security.md](docs/security.md) describes the threat model and how data is stored.
