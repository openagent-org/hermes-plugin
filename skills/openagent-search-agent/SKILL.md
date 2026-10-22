---
name: openagent-search-agent
description: Use when the user asks to find, recommend, or select Agents with an explicit query, browse available Agents without a query, or an upstream business Skill requests headless capability discovery. Perform one discovery and selection protocol only; do not plan tasks, search again, or call execution tools.
---

# OpenAgent Agent Discovery

## Purpose

Complete a single OpenAgent discovery request. Direct user searches open a confirmed user-visible Hermes browser or provide the selection-page link, then wait for a trusted user selection, with or without an explicit query. Background searches return complete candidates to the caller. This Skill does not plan business tasks, automatically search again, or call Agent execution tools.

## Terminology

- **OpenAgent**: The platform and tools for discovering, invoking, and managing Remote Agents.
- **Remote Agent**: A remote service callable through OpenAgent; it does not automatically inherit the Host conversation or local environment.

## Status Update Format

When entering a workflow stage, send a standalone user-visible assistant update in Hermes in this format:

```text
OpenAgent: <stage name> — <brief action phrase>
```

- Use the exact English workflow-stage heading for `<stage name>` and a short, verb-led action phrase in the user's language. Describe only the current action, without reasoning, results, next steps, candidate counts, internal identifiers, or handoff URLs; never claim success before authoritative confirmation.
- Emit one update on stage entry. Do not repeat it for tool polling, candidate-by-candidate checks, or resuming a pending call; re-entry may emit a new update.
- Deliver actual results separately. `Output` and `Next` describe internal data handoff and workflow transitions; do not display these labels to the user.
- For an upstream `presentation_mode=headless` request, suppress all user-facing stage updates, candidate-check notices, and UI; return data only to the caller, which owns progress reporting. On cancellation, go directly to Failure Handling and output only its fixed terminal reply, without another stage update.

## Workflow

On an explicit OpenAgent authentication failure, follow [runtime sign-in](../openagent-login/runtime-sign-in.md) before other error, fallback, or completion rules. Otherwise keep this workflow unchanged. A user-requested retry of an unfinished sign-in goes there too.

1. Run `Agent Search` once. Every direct user search uses browser presentation, with or without an explicit query; an upstream headless request uses headless presentation.
2. Pass a browser handoff result to `Browser Handoff` for validation and opening. Pass headless results to `Result Validation and Delivery`.
3. After `Browser Handoff` opens, recovers, or links the page, immediately enter `Agent Selection` in the same Turn. Use the shared Wait and Close Orchestration for every wait. On `more_requested`, return to `Browser Handoff` with the new URL, then resume selection on the same session.
4. Pass a successful selection to `Result Validation and Delivery` in the same Turn for authorization validation and handoff to `openagent-run-agent`. Handle cancellation, timeout, invalid results, or other failures in `Failure Handling` and end locally.

### Loop Control

Call the search tool only once per discovery request. For `more_requested`, use only the new handoff URL returned by the wait result and continue waiting on the same selection session; do not start a new search. The caller decides whether to search again. Keep only one active wait per selection session at a time.

## Workflow Stages

Follow the orchestration in Workflow and transition only through each stage's `Next` contract.

### Agent Search

Input is an explicit query with constraints, a general browsing intent, or a headless request from an upstream business Skill. Emit the stage update before searching, except in headless mode.

1. For every direct user search, with or without an explicit query, call `openagent_search(presentation_mode=browser)` once with `locale=zh-CN|en-US` matching the current user's language and a new stable `idempotency_key`. Pass explicit search terms as `q` (1–200 Unicode characters) to prefill and search the page, preserving names and constraints. Otherwise omit `q`; never invent terms. Do not pass other search filters. Retain the original request for post-selection handoff. Do not call `openagent_user_guide`.
2. For an upstream headless request, call `openagent_search` once with the supplied query, `presentation_mode=headless`, and the same locale rule; preserve the caller's query and constraints. In this mode, pass category, tags, sort, and pagination only when explicitly requested. Pass `category` only when the caller explicitly supplies a server-recognized category ID; never put natural-language search terms directly in that field.
3. Preserve the returned candidates and metadata without selecting, reordering, or inventing Agents. Do not open a browser or call `openagent_wait_for_selection` in this stage.

| Request source | `presentation_mode` | Result handling |
| --- | --- | --- |
| An upstream business Skill requests background capability discovery | `headless` | Do not display a Widget or the available Hermes browser; return structured candidates only to the current caller |
| The user searches or browses available Agents, with or without an explicit query | `browser` | Do not show the Search Agents Widget; pass the returned handoff result to Browser Handoff, open the available Hermes browser, and wait for selection |

“Find a PPT Agent”, “Find a stock analysis Agent”, “What is available in OpenAgent?”, and “Browse available Agents” all use `presentation_mode=browser` and hand off the discovery page through the available browser or its link.

**Output:** One unchanged search Tool Result, including candidates and any presentation or selection metadata.

**Next:** Browser results enter `Browser Handoff`; headless results enter `Result Validation and Delivery`; errors or inconsistent presentation metadata enter `Failure Handling`.

### Browser Handoff

Input is the browser result from Agent Search or a trusted `more_requested` result from Agent Selection. This stage opens the page; it does not search or wait for selection.

1. For an initial browser result, require `presentation_mode=browser`, `browser_handoff=true`, `status=pending`, non-empty `selection_id` and `handoff_url`, and no Search Agents Widget binding. For `more_requested`, require the same trusted selection session and a new non-empty `handoff_url` from its wait result. Reject invalid handoffs before opening a page.
2. Use only the exact `handoff_url` and trusted `selection_id` from that Tool Result. This URL points to the `/openagent/agents` discovery list page. Use the original absolute HTTPS URL only as a navigation argument or the target of this flow's “打开 OpenAgent 选择页”/“Open OpenAgent selection page” link. Do not compose, rewrite, separately output, log, or reuse the full URL or its short-lived token.
3. Emit the Browser Handoff update. If Hermes exposes a confirmed user-visible browser-opening tool, open the original URL once using its actual schema and keep the tab open. Retain trusted handles for tabs created by this flow. If that capability or its visibility is unconfirmed, provide the localized selection-page link instead. A successful opening response or link delivery completes the handoff; do not wait for full page load, poll continuously, or perform extra visual checks to prove it opened.
4. Apply Browser Display Boundary for one bounded recovery check after an opening failure or call timeout. Reuse a unique matching already-open tab when confirmed; otherwise provide the original selection-page link without opening another tab.
5. For `more_requested`, after successfully opening or linking the new handoff page, close this workflow's superseded handoff tab once only when Hermes exposes closing and the tab has a trusted owned handle, without closing the new one. Carry the current owned handles forward for terminal cleanup; leave closure unconfirmed when the capability or ownership is missing.

**Output:** The same trusted selection session and the opened, recovered, or linked handoff page, or an invalid handoff.

**Next:** Immediately enter `Agent Selection` in the same Turn after opening, recovery, or link delivery. Page load state must not be a prerequisite for listening or handling a terminal selection state. Invalid handoffs enter `Failure Handling`.

### Agent Selection

Input is a successfully opened, recovered, or linked Browser Handoff with a non-empty `selection_id` for the same session. Headless results and results without a selection handle must not enter this stage.

1. The discovery page is already opened, recovered, or linked. Regardless of whether the original request was to search, recommend, view, select, or find and run, emit the Agent Selection update and immediately use `selection_id` to call `openagent_wait_for_selection` through Wait and Close Orchestration in the same Turn. Do not deliver candidates first, end the Turn to await a new user message, or open the available Hermes browser again.
2. Allow only one active wait call per `selection_id` at a time. The selection-wait update replaces the opening status; do not append another guidance message or repeat the update when resuming a pending orchestration call.
3. On `more_requested`, retain the same selection session and pass only the newly returned `handoff_url` to Browser Handoff. Do not search again or start a second simultaneous wait.
4. On `selected`, `cancelled`, or `timed_out`, Wait and Close Orchestration attempts terminal cleanup once before returning the original result. Do not close again in subsequent stages. This stage does not validate execution authorization or invoke an Agent.

**Output:** The unchanged trusted wait result from the same selection session, with terminal cleanup already attempted when applicable.

**Next:** `more_requested` returns to `Browser Handoff`; `selected` enters `Result Validation and Delivery` in the current Turn; cancellation, timeout, or wait failure enters `Failure Handling`. Do not end the Turn between the successful wait and authorization handoff.

### Result Validation and Delivery

Input is a complete headless search result or a trusted terminal selection state. Emit the Result Validation and Delivery update except for headless requests. Validate before delivering candidates or handing off authorization.

- If `recommended_agent_id` is non-empty, `results` must contain exactly one matching candidate with a non-empty name. On mismatch, do not recommend or execute an Agent; enter Failure Handling. For headless requests, return the current query and trusted public error; for direct requests, explain that search results are temporarily unavailable and end.
- Determine whether candidates are empty only from `results` and trusted counts, not from a missing selection handle. Headless results may contain multiple candidates without a handle. Do not show an empty card or invent Agents.
- For a direct `search_only` request, complete the browser handoff and `openagent_wait_for_selection` in the same Turn first. After successful selection, enter the No Explicit Intent branch of `openagent-run-agent`; do not end the Turn early because the original request was only to search or select.
- `find_and_run` still returns only structured discovery results. The current caller decides whether to search again or execute. For direct user requests, hand off to `openagent-run-agent` only when an explicit executable prompt and trusted authorization already exist.
- Headless search returns complete model-readable candidates only. It creates no selection session, returns no Widget binding metadata, and does not enter the human-assisted discovery chain. The current caller selects a trusted Agent.
- Return headless search results completely unchanged to the current caller. Do not rewrite candidates, reorder results, or replace the upstream decision.
- For `status=selected`, terminal cleanup has already been attempted; do not close again. Read only trusted `selected_agent`, `execution_authorization`, and `action`, preserving `selected_agent.name` and the Agent Card's `selected_agent.description`. A selection action provides server authorization only; it does not replace the user's business requirement. A general discovery request has no executable task. If the original request only searches, recommends, views, or selects an Agent, pass the trusted Agent to the No Explicit Intent branch of `openagent-run-agent` for its fixed two-line guidance. Do not use the selection action or an Agent default task to start a run; do not execute a default task.
- Normal public discovery returns `execution_authorization=null` and `action.type=none`. Validate the trusted `selected_agent` identity, then pass it with the user's original business requirement to `openagent-run-agent` using ordinary `agent_id` and `data`. If no business task was supplied, use its No Explicit Intent branch. A selected Agent is not authorization to invent a task.
- Only a legacy persisted trial selection may contain `execution_authorization.source=user_selection`, `immediate=true`, and `action.type=call_tool`. Validate its matching selection handle and bound idempotency key before handing it to the execution Skill; never reinterpret an invalid legacy authorization as an ordinary task. After validation, read the `openagent-run-agent` Skill if needed, or reuse it if already read in the current context. Immediately pass the selection result and authorization unchanged to `openagent-run-agent` in the same Turn. Do not end the Turn between `openagent_wait_for_selection` and `openagent-run-agent`.

**Output:** Complete candidate results, or validated and unchanged user selection authorization with the Selected Remote Agent.

**Next:** For headless requests, deliver results to the caller and end. With valid authorization, hand off to `openagent-run-agent` in the same Turn so it can determine whether an executable business requirement exists.

### Failure Handling

Input is a trusted failure result from search, selection waiting, handoff, or result validation. Emit the Failure Handling update except for headless requests and cancellation.

For cancellation replies, set `display_locale` to `zh-CN` or `en-US`: explicit user preference > trusted Host/caller locale > request/conversation language > `en-US`. Ignore code, quotes, Tool output, and fixed installation/selection prompts. Output only the matching single-language reply.

- For `status=cancelled`, terminal cleanup has already been attempted by Wait and Close Orchestration. Do not close again or emit a stage update. Use only existing trusted evidence of page closure; `status=cancelled` alone does not prove that the page is closed. If closure is confirmed, output only “你已关闭 OpenAgent 发现页。” for `zh-CN` or “You have closed the OpenAgent discovery page.” for `en-US`. Otherwise, output only “OpenAgent 选择已取消。” for `zh-CN` or "OpenAgent selection cancelled." for `en-US`. End selection; do not automatically reopen the page or continue Agent execution.
- For `status=timed_out`, terminal cleanup has already been attempted by Wait and Close Orchestration. Do not close again; explain that selection timed out and end discovery. Do not automatically reopen the page.
- This Skill handles search, wait, and browser handoff failures locally; do not silently switch Agents. Use only trusted Tool Results, authoritative states, or stable public Host error codes. Without a stable public code, treat the error as unknown and do not retry automatically. Do not infer error category, authentication state, or retryability from message text.
- Headless failures must return the original search goal, constraints, trusted public reason, and all candidates already obtained to the current caller, without overwriting or fabricating results. For direct requests, show only a natural-language reason; hide raw results and internal fields.

**Output:** A caller-facing failure result preserving full context, or a trusted user-visible termination explanation.

**Next:** End the current discovery without silently searching again, reopening the page, or executing another Agent.

## Shared OpenAgent Rules

### Shared Protocol References

- Reuse [the shared rules of openagent-run-agent](../openagent-run-agent/SKILL.md#shared-openagent-rules) for post-selection execution authorization, Invocations, Sessions, attachments, and execution result delivery. Apply its [Hermes tool-result mapping](../openagent-run-agent/SKILL.md#hermes-tool-result-mapping) before validating search or wait results. Referencing a protocol does not authorize execution; hand off only after Result Validation and Delivery passes.
- This Skill owns search, candidate delivery, and UI Handoff. Callers must not independently rewrite the browser opening, waiting, or cleanup protocol.

### Result and User Boundaries

- Trust only candidates, metadata, and authorization returned by the search Tool. Return headless results completely to the current caller without fabrication, reordering, or rewriting.
- Raw Tool Results, candidate IDs, selection handles, and Widget metadata are internal only and must not enter the conversation stream. Display `handoff_url` only as the target of this flow's selection-page link; do not separately output the URL or its token.

### Browser Display Boundary

- To open a handoff page, use only a browser-opening tool actually exposed by Hermes and confirmed to be user-visible, following its current schema. Use the exact `handoff_url` returned by the Tool Result and keep the tab open. Otherwise provide the original selection-page link; do not open the same URL repeatedly.
- After opening, recovery, or link delivery, immediately start the corresponding `openagent_wait_for_selection`; the page may continue loading asynchronously. After an opening failure or call timeout, inspect existing tabs only once if Hermes supports it. Reuse a unique matching tab belonging to this selection; otherwise retain the link. Do not open a duplicate tab, call the upstream business Tool again, or start a second wait.
- After receiving `selected`, `cancelled`, or `timed_out`, attempt to close only tabs created by this flow with trusted owned handles, using Hermes's actual closing capability. Skip cleanup if no page was opened or no trusted handle or closing capability is available. Preserve pre-existing tabs and Agent result pages.
- Closing must not read page content or perform post-close state checks. If closing fails or no close receipt is available, record only the cleanup failure or unconfirmed closure. Do not switch browser interfaces, reopen the page, or claim that it was closed.

### Wait and Close Orchestration

Call the currently exposed `mcp__openagent__openagent_wait_for_selection` directly with only the original trusted `selection_id`. Keep one active call per selection session. Before waiting, retain this flow's trusted owned tab handles for terminal cleanup; do not close early or wrap the call in another client's executor.

While the wait is pending, continue only that same call through a continuation mechanism actually supported by Hermes; do not issue another wait. If continuation is unavailable, the call times out, or transport disconnects without a trusted terminal result, preserve the original selection session and report its state as unconfirmed.

After `selected`, `cancelled`, or `timed_out`, preserve the complete original result, then attempt terminal cleanup once under Browser Display Boundary before entering the next stage or handing off execution. Result Validation and Delivery and Failure Handling must not close again. On cleanup failure, record only that failure and preserve the original selection result, without retries or authorization changes. Do not close here for `more_requested`; continue the existing opening and waiting workflow.
