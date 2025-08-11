---
id: architecture
title: Architecture
---

# Architecture

The Frigate Hotreload system monitors your Frigate configuration directory and applies changes to the running process via Frigate’s API. It consists of the following components:

- **File watcher:** Watches configuration files for changes.
- **Reload controller:** Sends reload commands to the Frigate API.
- **Notification system:** Provides feedback on successful reloads or errors.

Below is a high-level overview of the workflow:

1. The file watcher detects a change in the configuration.
2. The reload controller sends a request to the Frigate API to reload the configuration.
3. Frigate applies the new configuration without requiring a restart.
