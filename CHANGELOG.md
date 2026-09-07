# Changelog

This file follows a small Keep a Changelog-style format. It intentionally does not reconstruct historical releases that cannot be verified from the repository history.

## [Unreleased]

## [0.1.53] - 2026-09-07

### Added

- Manual update checks and build identity reporting in the local control page.
- Regression coverage for update lifecycle, task cancellation, browser polling, and local media processing.

### Fixed

- YouTube thumbnail fallback, Douyin image-post classification, and Instagram carousel post matching.
- Download output tracking and validation of empty or non-media responses.
- Download and conversion cancellation, child-process cleanup, concurrent task limits, and conversion output locking.
- Preview and format-selection resets during polling, task recovery after refresh, and mobile control layout.
- Update restart verification, stale update status handling, and code rollback after failed restart.
- Local-client verification, DELETE preflight handling, token file permissions, and Windows JSON encoding.

### Notes

- Media processing remains on the Local Agent device; production still serves static web assets and update packages.
- Update manifests are not digitally signed. Dependency installation is not transactionally rolled back with application code.
- Platform compatibility can change. Installers remain unsigned; Windows validation for this release is static rather than a clean-machine installation test.

## [0.1.52] - 2026-08-11

### Added

- OSS community documentation and templates.
- CI and focused automated tests.
- Repository architecture documentation.
- GitHub security reporting guidance.

### Security

- Safer ZIP extraction and managed-path validation.
- Basic updater rollback handling.
- Pairing-code rate limiting.
- SHA256 release consistency checks.

### Changed

- Improved repository presentation and local-first architecture documentation.

### Compliance

- Removed active watermark-URL rewriting.
- Removed the browser automation-hiding flag.
- Clarified public-content and trusted-LAN boundaries.

## Existing repository history

The repository history can be reviewed directly with `git log`. Verified recent work includes the Local Agent, local iPhone-compatible conversion, download cancellation, Instagram parsing fixes, English documentation, and local Agent version display.
