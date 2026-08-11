# Security Policy

## Reporting a vulnerability

Please report security issues privately through the GitHub maintainer's private communication channel. Do not open a public Issue for a vulnerability. This project currently does not publish a dedicated security email address.

When reporting an issue, include the affected version, operating system, a short reproduction, and the smallest safe proof of impact. Please allow reasonable time for investigation before public disclosure.

## Sensitive information

Never paste the following into Issues, pull requests, screenshots, or public logs:

- Cookies, session data, or browser profiles
- Agent tokens or pairing codes
- Account passwords or private URLs
- Complete local file paths when they reveal personal information
- Personal data, downloaded media, or private platform content

Please sanitize logs and replace sensitive values with placeholders.

## Local Agent and LAN boundary

The Local Agent performs parsing, downloading, media conversion, and file saving on the device where it runs. LAN mode is intended for a trusted private network. Anyone who obtains a valid pairing token may be able to control supported Agent operations, including access to the configured download directory and local conversion workflow.

Do not expose the Agent port directly to the public Internet. Use the pairing flow only on a trusted network and stop the Agent when it is not needed.

## Out of scope

This project does not accept security research or feature requests intended to bypass DRM, paywalls, CAPTCHAs, forced login, platform access controls, watermark removal, attribution removal, or copyright information removal.

