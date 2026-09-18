# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through GitHub's
"Report a vulnerability" button on the Security tab of this repository, or reach the maintainers through
the collaboration. We will acknowledge the report, work with you on a fix, and coordinate disclosure.

## Scope

The supported version is the current `main`. crossfeed pulls only from the public mGrowthDB API and
commits no pulled or collaborator data; see [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

`crossfeed gui` runs a local page for one person: it binds to 127.0.0.1 only, requires a token that is
generated per run and printed with the URL, serves no file from disk, and uploads nothing. It is not
meant to be exposed to a network, and it carries no authentication beyond that token.
