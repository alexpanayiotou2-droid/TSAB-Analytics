# Git Workflow Integration
Always stage (`git add`), commit (`git commit`), and push (`git push`) your code changes to the remote Git repository.
- **CRITICAL PREFLIGHT REQUIREMENT**: Before you commit and push any code, you MUST run the local preflight script (e.g. `npm run preflight`). This ensures perfect parity with the remote CI/CD pipeline and prevents the user from having to act as a middleman for broken remote builds.
- **REMOTE PIPELINE MONITORING**: After running `git push`, you MUST run the CI monitor script (e.g. `node .agents/scripts/monitor-ci.js`) if it exists. This script will poll the remote API for the status of your push and block until the CI pipeline completes. If the script exits with an error (CI failed), you MUST review the logs, fix the bugs, and push again. You may only present the final work to the user once the monitor script completes successfully.

# Zero-Shortcut Policy (QA & Robustness)
- **NEVER Suppress Errors as a Workaround**: If a tool, script, or CI step fails, you must find and fix the *root cause* of the failure. Do not simply remove the step, suppress the error, or add a `try/catch` block that hides it.
- **Do the Hard Work**: If a feature or fix requires diving deep into a complex file, learning an API, or setting up auth, do it. Do not propose a "graceful exit" or a "workaround" that skips the intended functionality.
- **Full Parity**: Ensure your local testing environment mirrors production exactly. Do not present a "fix" to the user unless you are 100% confident it solves the root cause and passes all tests.

# MCP Tool Installation and Session Behavior
- **Tool Activation Warning**: When registering or modifying local MCP servers/tools, the current active chat session or agent will NOT have access to the new capabilities.
- **Strict User Notification**: You must explicitly instruct the user to start a new chat session (and restart the IDE/client if needed) to load the new tools. Never claim that the new capabilities are available in the current active session.
