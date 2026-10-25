# Release process

Releases are created by pushing a version tag such as `v0.1.0`. The GitHub
Actions release workflow runs tests, builds the wheel and source distribution,
generates a build provenance attestation, attaches the distributions to a
GitHub Release, and publishes the package to PyPI.

Before the first PyPI release, configure PyPI Trusted Publishing for this
GitHub repository and the `pypi` GitHub Actions environment. The workflow uses
OIDC and does not require a long-lived PyPI API token. Do not create a release
tag until the package name, version, and publisher configuration are ready.

Users can verify a downloaded artifact's provenance with GitHub CLI:

```bash
gh attestation verify openstudio_etl-0.1.0-py3-none-any.whl --repo zitouthani/OpenStudio
```

Provenance confirms the artifact's build origin; it does not replace tests,
dependency review, vulnerability analysis, or review of the source code.

## Pipeline expectations

- Run all automated tests before publishing a release candidate.
- Validate the packaging flow for the target OS.
- Publish the SBOM and third-party notices.
- Provide installation instructions and a known-good configuration matrix.

## Pre-release checklist

- Confirm security review.
- Review license obligations.
- Validate packaging and update instructions.
- Check compatibility with the expected Python environment.
