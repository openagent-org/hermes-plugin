# OpenAgent runtime sign-in

## When to use

Use this only after an OpenAgent Tool or the Host explicitly reports missing or expired OpenAgent authentication, such as `MCP_AUTH_REQUIRED` or `MCP_TOKEN_INVALID`. A bare HTTP status, missing tool, insufficient scope, business error, or network failure is not enough. Do not check login before normal calls. Anonymous search, guide, and selection calls stay anonymous unless their supplied credentials are explicitly rejected.

This takes priority over the caller's failure, fallback, and completion rules. Headless or delegated calls return the trusted authentication failure to their caller; that caller owns the single login flow and user messages. This does not handle App-only tools.

## Flow and messages

Use `display_locale`; if unset, choose explicit preference > trusted Host locale > conversation language > `en-US`. Show only the matching column, without workflow labels.

| State | zh-CN | en-US |
| --- | --- | --- |
| Starting login | 需要登录 OpenAgent 才能继续。正在打开登录页面… | Please sign in to OpenAgent to continue. Opening the sign-in page… |
| Page opened, still waiting | 请在打开的页面中登录 OpenAgent… | Please sign in to OpenAgent in the page that opened… |
| Authorization confirmed | 已登录 OpenAgent | Signed in to OpenAgent |
| Timed out | 还未完成登录。回复“继续登录”，我会重新打开登录页面。 | Sign-in is not complete yet. Reply ‘continue sign-in’ and I will reopen the sign-in page. |

1. Use the login path below for the actual failing connection only after the user explicitly authorizes sign-in or connection recovery. A reported authentication failure alone is not authorization: Hermes login resets the connection's existing browser OAuth state and is not a read-only check. If the Host or this conversation already has a login in progress, keep its process or session handle and wait for that attempt, even if the user says “continue sign-in”; do not start another or repeat its messages. If the previous attempt's state cannot be confirmed, report that limitation without starting a new attempt.
2. Send the starting message immediately before launching login once. Keep and wait on the same process. A printed OAuth URL alone does not prove that the page opened; never reopen that URL. Show the waiting message only after confirmed opening and while authorization is still pending.
3. Confirm this attempt's authorization callback and successful token exchange, then show the success message and perform the configuration check below. Report any verification failure separately. Configuration verification is not business success.
4. Cancellation, denial, reported page closure, opening failure, login failure, or confirmed OAuth timeout ends the attempt without retry. A short tool wait, a yielded process, or no new output is not an OAuth timeout; keep waiting on the same attempt. Report the actual result; only a confirmed OAuth timeout uses the fixed timeout message. If page closure is not observable, wait for the bounded timeout instead of claiming closure. A later explicit request to continue sign-in starts one fresh attempt only after the previous process is confirmed to have ended. Do not abandon or terminate a pending attempt just to start another.

## Login

Use the native CLI from the current Hermes installation, preserving its active profile and `HERMES_HOME` on every command. In the commands below, `hermes` means that verified CLI; do not substitute a CLI from another installation or an unknown PATH entry. If unavailable, report that limitation and stop.

Check `hermes mcp list` for the existing enabled `openagent` server, `hermes config get mcp_servers.openagent.url` for its configured endpoint, and `hermes config get mcp_servers.openagent.auth` for `oauth`. Keep that endpoint and profile; do not migrate environments or read authentication storage. Then run `hermes mcp login openagent` once and wait for its callback and successful token exchange. Require the native `Authenticated` result from this attempt and successful process completion; exit code zero alone does not prove authentication. Use the Host's actual page-open and terminal results for the messages above.

For interactive first sign-in on a supported local backend, use Hermes `terminal` with `background=true`, `pty=true`, and `notify=true`, setting `timeout` in seconds to cover the configured OAuth timeout and token exchange. Retain its returned `session_id` and continue with `process_manage(action="wait", session_id=<same-session>, timeout=60)`; do not relaunch login when a wait yields.

The login command or Host owns opening the authorization page. Do not use `open`, `start`, `Start-Process`, `xdg-open`, or any browser tool to open or reopen the OAuth URL, including to check whether it opened or to move it into another browser. If opening cannot be confirmed, report the uncertainty and wait on the same attempt; do not compensate with another navigation. This restriction applies to OAuth pages, not normal business browser handoffs.

After success, repeat the same `mcp list` and narrow `config get` checks and verify the same server, endpoint, OAuth configuration, profile, and enabled state. Do not invoke an account or business tool for verification.
