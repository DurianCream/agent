---
name: traffic-light
description: Show a Korean traffic-light view of tools observed in the current Codex turn when the user asks for tool activity, the tool monitor, or 도구 신호등.
---

# Traffic light

From the project root, run `python shared/skills/traffic-light/scripts/traffic_light.py` and present its Korean snapshot. A new prompt starts a turn. For a standalone monitor request or a question about what just ran, also run it with `--previous` and identify the two turns separately. The script resolves the current chat using `CODEX_THREAD_ID` and checks the matching local rollout header. If the user wants to expand the declared tools, add `--all`. For a live view, run the same command with `--watch` in a user-visible terminal, or give the terminal command with `--thread <chat-uuid>` when the terminal cannot inherit the chat ID. Ctrl+C closes the view.

Report observed calls and structured errors at the level recorded by the host. A wrapper call and its nested shell command can both appear. Green means that a tool returned a result. Yellow means that its result has yet to appear in the log. Blue counts observed tool declarations without a call in the current turn. White marks an unresolved call when a turn ends. Per-tool context costs and skill/plugin use may be unavailable. The token figure is the last model request's input count in this turn. If the local rollout is unavailable, state that limitation. Keep raw conversation text, command arguments, and tool results out of the report.

Based on [jueyi6/traffic-light (MIT-0)](https://github.com/jueyi6/traffic-light/tree/a78845c47067728c3cd03b9e109e9c33c8d6ef65). This port reads the selected Codex rollout on demand and does not install a hook.
