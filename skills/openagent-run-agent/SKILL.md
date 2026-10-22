---
name: openagent-run-agent
description: Use when the user or an upstream business Skill requests execution, continuation, or stopping based on a trusted Agent and an explicit executable prompt, or when openagent-search-agent supplies trusted selection authorization. Also handle a specified agent_id, optional name, and missing business requirement handed off by openagent-guide-agent. Handle a single invocation, Sessions, stopping, insufficient balance, and delivery failures locally.
---

# OpenAgent Agent Execution


## Purpose

Execute or continue an invocation with an existing trusted Agent and an explicit business requirement, or stop execution within the user's explicit scope. Validate authoritative terminal states and deliver standard content, files, and WebUI pages. After discovery or selection without a business requirement, only ask for task input. This Skill handles execution, Sessions, insufficient balance, and delivery failures locally; it does not search again or plan tasks.

## Terminology

- **OpenAgent**: The platform and toolset used to discover, invoke, and manage Remote Agents.
- **Remote Agent**: A service provided by OpenAgent and callable through OpenAgent tools to perform a capability task. It does not automatically inherit the Host conversation or local environment.

## Language

Set `display_locale` to `zh-CN` or `en-US`: explicit user preference > trusted Host/caller locale > request/conversation language > `en-US`. Ignore code, quotes, Tool output, and fixed installation/selection prompts.

Use only the matching bilingual template; write free-form replies in `display_locale`. Keep stage names and English-only fixed copy in English; preserve Agent names, IDs, URLs, amounts, and files. `display_locale` is context, not a Tool argument.

For ordinary new invocations, use `display_locale` as the Tool `locale`. Preserve the server-bound selection locale and the original arguments of an in-flight call or transport retry, even if the user changes the display language. Use the same invocation locale for `openagent_progress` and `openagent_run`; never start another invocation solely to change its language.

## Status Update Format

When entering a workflow stage, send a standalone user-visible assistant update in Hermes in this format:

```text
OpenAgent: <stage name> — <brief action phrase>
```

- Use the exact English workflow-stage heading for `<stage name>` and a short, verb-led action phrase in the user's language. Use Agent names only from trusted metadata.
- Describe only the current action, without reasoning, results, next steps, internal identifiers, or handoff URLs; never claim success before authoritative confirmation. Deliver errors, top-up instructions, and actual results separately.
- Emit one update per stage entry, without repeating it for polling, uploads, or resuming a pending call; re-entry may emit a new update. Check for No Explicit Intent first: that branch outputs only task-input guidance, without a stage update.
- `Output` and `Next` describe internal data handoff and workflow transitions; do not display these labels to the user.

## Workflow

On an explicit OpenAgent authentication failure, follow [runtime sign-in](../openagent-login/runtime-sign-in.md) before other error, fallback, or completion rules. Otherwise keep this workflow unchanged. A user-requested retry of an unfinished sign-in goes there too.

1. In Request Validation, route by user intent: explicit stop requests enter Task Stopping; discovery or selection alone enters No Explicit Intent; only executable requirements enter Request Preparation.
2. Request Preparation reuses or obtains Agent information under the rules below, organizes requirements, then prepares parameters and required attachments according to the trusted invocation mode. Do not submit execution when required input is missing or an attachment fails.
3. Agent Execution waits for `openagent_progress` to return, then calls `openagent_run` once with the same key and locale. Execute this Run even if progress display fails.
4. Pass every returned Tool Result to Result Validation and Delivery for validation. Transport failures without a Tool Result enter Failure Handling directly. Return the complete result to the current caller and end. Do not automatically start subsequent business invocations.

### Loop Control

Transport recovery for the same call reuses the original arguments and idempotency key. A new business retry requires explicit user authorization and a new key. After obtaining an Invocation, a timeout or disconnection leaves the state unknown; do not treat it as failure and replay it. See Task Stopping for stop conditions and Failure Handling for insufficient-balance recovery conditions.

## Workflow Stages

Follow the orchestration in Workflow and transition only through each stage's `Next` contract.

### Request Validation

Input is the current user request, the full execution request from an upstream business Skill, or trusted selection authorization.

Choose the branch in this order:

1. If the user explicitly asks to stop, cancel, terminate, or interrupt, validate the scope and trusted stop targets under the Task Stopping rules. Clarify an ambiguous scope before proceeding. If trusted IDs are missing, direct the user to the progress card's stop button only when Hermes exposes a visible, usable one; otherwise explain that the target cannot be located, and end. Enter Task Stopping only with ready targets. Dissatisfaction with a result is not stop authorization.
2. If the user only asks to search, discover, recommend, view, or select an Agent, enter No Explicit Intent even if the server returns a selection action. Do not call `openagent_progress`, `openagent_file_upload`, or `openagent_run`.
3. When an executable prompt exists, choose the invocation mode below based on the trusted invocation source; do not infer the mode from returned fields.

#### No Explicit Intent

Also enter this branch when the user only requests an `agent_id` without a concrete business requirement. If a trusted name or description is missing, do not fabricate fields. Output only “你希望我让这个 Agent 做些什么？” for `display_locale=zh-CN`, or “What would you like this Agent to do?” for `display_locale=en-US`, and retain the original ID while waiting for task input. A missing name does not block subsequent execution; do not ask the user for a name or search again.

Use the following two-line template only when both a trusted name and description are available.

Select only the template matching `display_locale`. Replace `{Agent 名}` or `{agent name}` with trusted `selected_agent.name`, and `{一句话介绍}` or `{one-line description}` with the Agent Card's trusted `selected_agent.description`. Output one message containing exactly the selected two lines, then stop:

For `zh-CN`:

```markdown
**OpenAgent：{Agent 名}** {一句话介绍}
你希望我让它做些什么？
```

For `en-US`:

```markdown
**OpenAgent: {agent name}** {one-line description}
What would you like it to do?
```

Use the trusted description verbatim when it already matches `display_locale`; otherwise translate it faithfully for display only, without changing the trusted metadata. Fold line breaks into spaces. Do not append `capabilities` or other explanations; bold only the OpenAgent prefix and Agent name on the first line. When the user later supplies an explicit task, reuse the selected trusted Agent and build the ordinary invocation's `data.prompt` from that current request. Do not use a discovery-stage default task as the current prompt or replay an expired selection action.

**Output:** Stop targets, guidance for missing explicit intent, or a trusted Agent request with an executable prompt.

**Next:** Stop requests with validated targets enter `Task Stopping`; unresolved scope waits for clarification, and missing target IDs end with guidance to an available stop button or an explanation that the target cannot be located. Without explicit intent, output the applicable task-input guidance and end. Executable requests enter `Request Preparation`.

### Request Preparation

Input is a confirmed business requirement and trusted Agent satisfying Trust and Authorization.

For a normal public selection (`execution_authorization=null`, `action.type=none`), use ordinary `agent_id` and `data` mode with the explicit user task. Never call the legacy `selection_id` mode for that selection.

Emit the Request Preparation update once, then check for a usage manual:

Use only the AgentCard `manual` field. Never use `MOM` or `mom`.

In this section, a session means the current client conversation, not a Run's `agent_session_id`. `router/run` share the Card, Card lookup attempts and results, manual read attempts and results, and any loaded manual body, keyed by the original `agent_id`. Track each Agent separately and start fresh in a new conversation. Do not compare MoM versions, URL changes, or update timestamps. Preserve this information and the attempt records when compacting context. If preparation for the same Agent is in progress, other entry points must wait for and reuse its result instead of preparing in parallel.

Prepare usage information only for a target Agent with an explicit business task and execution authorization. Do not fetch a Card or read a manual merely to browse or select candidates. If a trusted `manual` URL, an explicit `manual=null`, or usable previously loaded manual content is already available, do not fetch the Card again. When only an ID or incomplete information is available, call `openagent_get_agent_card({agent_id})` once only if no Card lookup has been attempted and no manual read has been recorded. Do not pass `agent_session_id` or other arguments. Use the tool directly if it is already loaded; otherwise, look for it once. If it remains unavailable, record the Card lookup as failed. Record the attempt before calling, check `isError` first, and on success read `structuredContent.agent_card` (or `agent_card` from the same JSON in text-compatible mode). Associate the result with the originally requested Agent; do not search again or replace its ID.

Retain both successful and failed Card lookup results, and do not retry automatically; a failed lookup must not be recorded as `manual=null`. Record a manual read attempt before reading. Reuse an available body directly. If an earlier read failed or the body has been lost, continue with whatever trusted information remains; do not claim to have the body based only on a "loaded" flag, and do not automatically fetch the Card or download the manual again. Do not switch methods to retry after the user rejects a Card lookup or manual read; stop if the user cancels the task. Missing MoM, a failed Card lookup, or a failed manual read must not by itself block execution: continue with the current user request and existing trusted information, while still satisfying authentication, execution authorization, and required-input checks.

Read the original URL in the following order only if no manual read has been attempted for this Agent in the current conversation and trusted metadata provides a valid, non-empty `manual` HTTPS URL. Curl and the fallback reader together count as one loading attempt:

1. Read it with `curl` first; on Windows, explicitly use `curl.exe` to avoid the PowerShell alias. Use `--fail --location --silent --show-error --connect-timeout 10 --max-time 30 --proto '=https' --proto-redir '=https' -- <original HTTPS URL>`, passing the URL as a separate argument. If the exit code is 0 and the response body is non-empty, use that body directly without calling another reader.

   If curl fails, request one retry through Hermes's supported authorization
   mechanism for the exact same command, only when it can grant the required
   access. Do not use another client's permission parameters.

   On success, use the response; on execution failure, use the existing
   fallback. If approval is denied, continue without the manual.

   Count these steps as one loading attempt. Allow required approval prompts.

2. Only if curl is unavailable, fails, or returns an empty body, fall back to a non-browser URL content reader for the same original HTTPS URL. Do not use this fallback if the user rejects the read.

Save the body and mark it as loaded only after a successful read. If both methods fail, save the failure result for subsequent executions and router/run handoffs.

After a successful read, use the manual to organize the requirements and construct this invocation. If `manual` is missing or empty, the link is invalid, or both reading methods fail, continue the existing workflow. Do not display any additional status, links, manual content, or read errors for this step. Do not use a browser interface, or search for, guess, or rewrite the link.

Organize the request using trusted context, then complete the parameter and attachment preparation below. Manual reading and attachment uploads belong to this stage; do not emit separate completion notices for them.

All execution uses `openagent_run`. Treat the Host's current Tool schema as the runtime source of truth. Use the target Tool directly if it is already in the current Tool list; discover it once only if it is missing.

| Mode | `openagent_run` input |
| --- | --- |
| Selection Authorization | Pass only the server action's `selection_id`, bound `idempotency_key`, and bound `locale`. |
| Initial Execution | Trusted `agent_id`, a new stable `idempotency_key`, `locale=display_locale`, and `data.prompt` containing the full task; omit `agent_session_id`. |
| Continued Execution | The same `agent_id`, `agent_session_id` from the latest trusted result, a new stable `idempotency_key`, `locale=display_locale` for this new Invocation, and `data.prompt` containing the incremental task. |
| Continue After Top-Up | The original business goal, trusted Agent, and task context preserved by this Skill on insufficient balance, a new stable `idempotency_key`, and `locale=display_locale`. Include `agent_session_id` only if a trusted value already existed before the failure. |

Selection Authorization is mutually exclusive with the other modes. Put all ordinary business parameters in `data`; use only the top-level fields allowed for the selected mode. `locale` must be `zh-CN` or `en-US` and exactly match the accompanying `openagent_progress`. Do not add top-level `task`, parent/child Invocation, payer, version, or billing fields. Omit the old Session when switching Agents, starting a new task, or explicitly restarting at the user's request.

#### Request and Attachments

These rules apply to ordinary business-parameter modes. Selection Authorization uses only server-bound parameters: do not append `data`, `agent_id`, or `agent_session_id`, or upload attachments for that mode.

1. Preserve the object structure of `data` supplied by the current caller, including a non-empty `prompt` carrying the complete task. If it is missing, do not call `openagent_progress` or `openagent_run`.
2. For each readable local file, call `openagent_file_upload` with a separate stable `idempotency_key`, actual basename as `file_name`, MIME as `mime_type`, and byte count as `size_bytes`; send no file bytes, paths, or Base64. Retain the original `resource_id` and `structuredContent.attachment`.
3. Require `isError=false` and valid `structuredContent`. Reuse `status=ready` without uploading. For `status=pending`, save only `structuredContent` in a private temporary grant file: POSIX mode 0600; on Windows, create it in the current user's temporary directory and inherit that directory's permissions, without a separate ACL check. Reject other statuses; never expose COS credentials in output, logs, command arguments, or prompts.
4. For `pending`, run `node <installed openagent-run-agent Skill>/scripts/cos_upload.cjs --file <absolute local file> --grant-file <private temporary file>`. Require successful exit, `upload_returned=true`, and the original `resource_id`. Do not poll for `ready`, wait for the Resource worker, or call `openagent_file_upload` again after SDK success.
5. Put each original `structuredContent.attachment` object unchanged into `data.attachments[]` in user input order after SDK success or trusted `ready` reuse. Pass files only through this array; add no separate `resource_id` field. Use a different stable Run key; do not put COS credentials, local paths, Base64, or storage URLs in Run data.

**Local execution:** Use Node.js 20+ and the bundled `scripts/cos_sdk.cjs.gz` directly. When an upload needs the SDK, the helper verifies the compressed bundle, then automatically decompresses it to the writable `scripts/.cos-sdk/node_modules/<archive-sha256>/cos_sdk.cjs`. Later processes verify and reuse that file; a missing or damaged cache is rebuilt, and an updated bundle uses a new directory. The cache is retained after exit. Do not manually extract it, probe SDK/environments, install packages, or use a Base64 fallback. The COS Node.js SDK's `uploadFile` can resume parts and complete multipart. The helper consumes the grant, rejects non-regular files and symbolic links, checks ownership and mode on POSIX, and saves a credential-free SHA-256 source checkpoint. On Windows it does not inspect the owner or ACL and does not invoke PowerShell. For every script command, including recovery/cleanup, use the Host's normal authorization flow for the same command; do not alter the environment or permissions to bypass it. Use only the authorization mechanism actually supported by Hermes; do not pass another client's sandbox parameters or assume that changing execution settings grants permission. Authorization denial/unavailability or local execution/dependency failure stops upload and Run; cleanup remains best-effort.

**Recovery:** `COS_UPLOAD_SOURCE_CHANGED` stops Run and reuse of that key, even if the server reports ready. Only interrupted/unknown SDK outcomes permit at most one automatic recovery: call `openagent_file_upload` with exactly the same four arguments and upload key, require `isError=false` and the original resource ID and attachment metadata, then reuse ready or rerun once with a fresh private pending grant and unchanged file. Require the same success checks; otherwise stop. No new keys or repeated status checks. Run attachment rejection enters Failure Handling without automatic polling, reupload, or resubmission.

**Sequential orchestration:** For each file, use Hermes's available MCP, file-writing, and terminal tools to sequentially await grant preparation, private saving, authorized upload, and success checks; expose only attachment metadata/internal resource handles. Continue a pending call only through Hermes's supported continuation mechanism, without reissuing it. Recovery remains bounded as above. Pseudocode helpers represent Host Tools, not installed APIs:

```text
prepared = await openagent_file_upload(metadata)
grant = validate_upload_result(prepared)
if grant.status == "pending":
    private_file = await save_private(grant)
    uploaded = await authorized_upload(local_file, private_file)
    require_sdk_success(uploaded, grant.resource_id)
return original_attachment_and_resource_id(grant)
```

**Output:** Complete invocation parameters with all required attachments uploaded or reused ready.

**Next:** Enter Agent Execution on success; missing prompt returns to the caller, and attachment failure enters Failure Handling without progress or Run.

### Agent Execution

Input is the complete parameters from Request Preparation. Emit the Agent Execution update before calling the progress and execution tools; describe the current invocation action without claiming that submission has completed. The stable `idempotency_key` must be valid and non-placeholder, and reused for the corresponding `openagent_progress` and `openagent_run`.

When Hermes renders the progress card, it displays the exact `data.prompt` and `data.attachments` submitted to `openagent_run`. If card rendering is unavailable, use only the brief stage update. Do not send a separate prompt preview, fenced code block, or duplicate invocation data in the conversation.

1. Then call `openagent_progress` with trusted `agent_id` and `agent_name`, and the same `idempotency_key` and `locale` as the Run. Optional display fields must come only from trusted Agent metadata. When only an ID is available without a trusted name, use the original `agent_id` as the display identifier in `agent_name`, without claiming it is the Agent's actual name. Keep the same original ID in `openagent_run.agent_id`.
2. Wait for the Host MCP Tool Result of `openagent_progress`. On an authentication failure, follow Runtime Sign-in and stop here. Otherwise call `openagent_run` once with the same `idempotency_key` and `locale`. Failure or timeout of `openagent_progress` affects only progress display unless authentication failed; still perform this one Run.
3. `openagent_run` is the sole source of truth for Invocation state and business results. A progress-card failure does not change the Run, trigger a business retry, or cancel, roll back, or duplicate the Run.
4. If the execution request is rejected before creating or recovering an Invocation, preserve the trusted rejection for result validation and failure handling. Do not call Run again in this turn.
5. After the single `openagent_run` call completes, perform checkpoint cleanup before Result Validation and Delivery, preserving its original Tool Result. Only after this Run returns `isError=false` and `status=completed`, best-effort run `node <installed openagent-run-agent Skill>/scripts/cos_upload.cjs --forget-resource-id <resource_id>` for each local-file resource prepared in this request, using the authorization rules above. Keep the checkpoint when Run fails or its outcome remains unknown. Cleanup failure must not change the upload or Run result or trigger another grant request or upload; a missing checkpoint is not a reason to reupload. Then enter Result Validation and Delivery. Host pseudocode (expand helpers into authorized Tool calls):

   ```text
   result = await openagent_run(run_args)
   if result.isError == false and result.structuredContent.status == "completed":
       await best_effort_authorized_cleanup(local_upload_resource_ids)
   return result
   ```

**Output:** The authoritative `openagent_run` Tool Result, or an execution state that remains unconfirmed.

**Next:** Every returned Tool Result enters `Result Validation and Delivery`; transport failures without a Tool Result enter `Failure Handling`. Do not duplicate execution because of progress-card failure or disconnection.

### Result Validation and Delivery

Input is the authoritative Tool Result for the current Invocation. Selection Authorization uses this stage as well. Emit the Result Validation and Delivery update before validation; it does not assert successful execution or usable delivery.

#### Parsing Order

After `openagent_run` returns, process it in this order:

1. Check `isError` first, before business content.
2. Save trusted `invocation_id` and optional `agent_session_id` for stopping or continuation with the same Agent. Do not show either handle to the user by default.
3. For `isError=true`, enter Failure Handling without delivering successful content or automatically retrying. A non-completed or unknown status also enters Failure Handling; do not treat it as successful delivery. Invocation failure semantics come from `structuredContent.error.code` when present; `content[]` is only model-visible compatibility text and must not be parsed for error codes or top-up URLs.
4. For `isError=false`, require `status=completed`, then deliver `content` in its original array order.
5. Process optional `structuredContent.views`.

#### Content Delivery

- `text`: Preserve the Agent's business content; do not replace it with a model summary. Translate natural-language text faithfully into `display_locale` when needed, unless the user requests another output language or the original wording. Preserve facts, numbers, citations, code, identifiers, and URLs; do not modify the original Tool Result or files. If it contains a delivery-count table, extract only the actual counts by category and the total, and express them in one ordinary sentence. Do not display that table or change the numbers; preserve all other business content. If the text repeats delivery metadata already represented by content blocks or `views`, such as MIME, byte counts, `defaultOpen`, or raw JSON, omit only that duplicated technical information.
- `resource_link`: First obtain the HTTPS URL from `uri` and complete the download under ResourceLink File Delivery below, then show the file. Use only the file title or name for the user; do not show the raw URI, MIME, byte count, temporary authentication notes, or resource field names.

##### ResourceLink File Delivery

1. Process the Tool Result's `content[]` in its original order. For each `type=resource_link`, use only the trimmed `uri`: accept a direct `https://` URL or extract the HTTPS target inside a Markdown link's parentheses. Do not obtain or rewrite the URL from `text`, `title`, `name`, or other fields. If no HTTPS URL is available, do not read or save the resource; only explain that the file cannot currently be displayed directly.
2. Prefer the Host download Tool, passing the exact URL and a safe filename according to its runtime schema. Accept only a local file, file reference, or file content block returned by it; do not substitute a browser for downloading. If Host download is unavailable or fails, fall back only once: prefer `curl`, use `wget` if absent, and stop if neither is available. Pass the URL as a separate argument. Do not concatenate commands, use `eval`, enable shell tracing, or output the URL. Request network authorization through the Host workflow if required; stop if authorization is not granted.

   If curl fails, request one retry through Hermes's supported authorization
   mechanism for the exact same command, only when it can grant the required
   access. Do not use another client's permission parameters.

   On success, use the response; on execution failure, use the existing
   fallback. If approval is denied, continue without the manual.

   Count these steps as one loading attempt. Allow required approval prompts.


   ```bash
   curl --fail --location --silent --show-error \
     --proto '=http,https' --proto-redir '=http,https' \
     --output <destination-path> -- <exact-URL>
   ```

   Use equivalent failure-exit, HTTP(S) redirect restrictions, and destination-file arguments for `wget`.
3. When saving files yourself, use a writable directory dedicated to the current task, or create a unique subdirectory in the system temporary directory. Derive a safe basename from `title` or `name`, removing path separators and control characters. For an empty name, derive one from MIME; use a unique name on collisions. Do not write to source repositories, the user's home directory, or existing business directories, overwrite files, or follow symlinks. A CLI download succeeds only with exit code zero and a newly created regular, non-symlink target file. Require an exact match when a trusted byte count exists. Host-returned local paths must pass the same checks. Do not treat stdout, response headers, command arguments, or download URLs as file content.
4. Do not display files until all download and save attempts finish. On success, deliver in the original `content[]` order: prefer Host file content blocks or attachment artifacts that render attachment cards. If the Host lacks attachment output but supports local media rendering, use its documented media-display interface for audio, video, and images only after confirming that Hermes can access the downloaded file; do not assume that absolute-path Markdown syntax renders media cards. PDF and TXT still use file content blocks or attachment artifacts. Ordinary Markdown links cannot replace attachment cards. Do not show URI, MIME, size, path, or status. Only if all download methods fail or Hermes cannot display the downloaded file, retain a link with the title or name as its label and the HTTPS URL as its target. Do not change the Agent terminal state, repeat `openagent_run`, invoke the Agent again, or show internal errors or save paths.

##### WebUI Page Delivery

1. Process the trusted Tool Result's `structuredContent.views[]` in its original order. Accept only views with `type=webui` whose trimmed `uri` is a parseable absolute HTTPS URL. Use the original `uri` as the WebUI URL; do not obtain it elsewhere or construct it yourself.
2. Output Markdown links to those exact URLs in their original order, using a non-empty `title` or otherwise “打开页面” for `zh-CN` or “Open page” for `en-US` as the label. Only when `defaultOpen` is strictly boolean `true`, after URL validation, use a confirmed user-visible browser-opening tool exposed by the current Hermes host once for each page, following its actual schema. Open that exact URL and keep the tab open. In all other cases, including unconfirmed browser visibility, show links only. Do not open a browser early, guess another browser interface, or use a proxy URL.
3. Each browser-opening call only opens and displays the target tab. Do not combine it with reading the title or other page operations. After a call failure or timeout, inspect existing tabs only once if Hermes exposes that capability. Reuse the target page if already open; otherwise retain the link. Do not open duplicate tabs or call the upstream business Tool again.
4. Do not expose structured fields, raw JSON, opening policies, or internal errors to the user. If the browser is unavailable, navigation fails, a timeout occurs, or the page cannot display, explain only that the page cannot currently be opened and retain the result link. Do not change the Agent terminal state, repeat `openagent_run`, or invoke the Agent again.

If `status=completed` but both `content` and `views` are empty, explain only that the Invocation completed without usable business content. Do not count this as successful business delivery.

**Output:** Trusted content and views delivered in the original order, or an explanation that no usable business content was returned. Return trusted handles only for internal caller use.

**Next:** On an error or non-completed state, enter `Failure Handling`. Otherwise, deliver the usable result or the no-content explanation to the current caller and end without triggering search, planning, or other business Skills.

### Task Stopping

Emit the Task Stopping update when trusted stop targets are ready and the user's stop scope is confirmed.

1. Resolve the user's explicit stop scope to `single`, `multiple`, or `all_active_in_current_task`; clarify if ambiguous. Use only trusted server-returned `invocation_id` values from the current context. Do not derive targets from Sessions, selection handles, or card text. If IDs are missing, direct the user to the progress card's stop button only when Hermes exposes a visible, usable one; otherwise explain that the target cannot be located. Do not claim that no tasks are running.
2. Call `openagent_stop_run` with a separate new idempotency key for each target. Multiple targets may run in parallel.
3. Report each target's Tool-confirmed state. On failure, explain the trusted public reason and end without automatically retrying.

**Output:** Each stop target's authoritative state or trusted public failure reason.

**Next:** Deliver each stop result and end without automatically repeating the stop.

### Failure Handling

Input is a trusted error from the current invocation or a required attachment, a public transport error, or an execution state that remains unconfirmed. Emit the Failure Handling update once, then determine and deliver the trusted public outcome. Do not claim a retry is underway without authorization.

#### Error Normalization and User Boundaries

If a trusted rejection confirms that the request was rejected before creating or recovering an Invocation, use “Failed to send task ({agent name})” as the fixed English send-failure result message, replacing the placeholder with the trusted Agent name. This is not a stage update.

1. For an `openagent_run` Tool Result, check `isError` first. For `isError=true`, read public failure semantics from `structuredContent.error.code`, `structuredContent.error.message`, and `structuredContent.error.retryable` when they are present. Treat `quota_exceeded` as insufficient balance only when `structuredContent.error.code` is exactly `quota_exceeded`; never infer it from `content[].text`, English copy, HTTP status, internal reason fields, or words such as "credit". If structured error fields are missing, use the authoritative terminal `status` and first safe `text` only as a generic public failure reason. Internal fields, handles, and raw results must not be used as the user reply.

#### Retries and Unconfirmed States

1. `retryable=false` terminates the current failed invocation. `retryable=true` only permits offering the user a retry after explaining the public failure reason and retry type. A business retry requires explicit user authorization and a new stable `idempotency_key`; only transport recovery of the same call reuses the original arguments and key.
2. If a timeout or disconnection occurs after obtaining `invocation_id`, do not treat the unknown execution state as failure and call `openagent_run` again. Explain that the result is unconfirmed and stop.

#### Continue After Insufficient Balance

1. Treat a failure as insufficient balance only when the server's stable public code is explicitly `structuredContent.error.code=quota_exceeded`. Accept a top-up link only from `structuredContent.recharge_url` when its trimmed value is a parseable absolute `https://` URL; preserve the original server value in the output. Do not read `content[].text` lines such as `recharge_url=...`, construct a billing URL from the API host, environment, or current page origin, rewrite the URL, or proactively open it. If the trusted HTTPS link is present, output only the two-line template matching `display_locale`:

   For `zh-CN`:

   ```text
   余额不足，充值后继续：{充值链接}
   充值后，想继续原任务时告诉我即可
   ```

   For `en-US`:

   ```text
   Insufficient credits. Top up to continue: {billing link}
   After topping up, let me know if you want to continue the original task.
   ```

   Replace `{充值链接}` or `{billing link}` with the trusted `structuredContent.recharge_url`. If the server provides no trusted HTTPS link, output “余额不足，请充值后重新发起。” for `zh-CN` or “Insufficient credits. Top up and submit your request again.” for `en-US`, without inventing a link.
2. Retain the original business goal, trusted Agent, task data, and any trusted Session that existed before the failure. The failed `invocation_id` stays terminal and must not be revived. Resume only when the user's message and context confirm intent to continue the original task after top-up; no fixed reply wording is required. This authorizes one new business action using only the preserved context and a new stable `idempotency_key`. Do not reuse the failed call's idempotency key or directly replay the failed Invocation.
3. Stop if the trusted goal is missing, the user's intent is ambiguous, or the new call returns `quota_exceeded` again. Do not loop. This Skill does not use `openagent-query-account` to determine the balance or proactively query the account.

**Output:** A trusted public reason and, when needed, preserved business goal, context, and continuation information.

**Next:** End handling of the current failure or unknown state. Re-enter Request Validation only for an explicitly authorized new business retry or when the conditions for continuing after insufficient balance are met.

## Shared OpenAgent Rules

### Hermes Tool Result Mapping

Use the full tool names and schemas actually exposed by the current Hermes connection. The installed `openagent` connection uses the `mcp__openagent__` prefix. Use an available tool directly; discover it once only when missing. Do not implement MCP over HTTP or reuse another client's executor or configuration.

Hermes may return a JSON wrapper instead of the original MCP envelope. Apply the following mapping before the business rules in this Skill or any referencing Skill; `isError`, `structuredContent`, and `content[]` refer to the corresponding retained data:

- Check an outer `error` first. Hermes converts MCP `isError=true` and transport failures to error wrappers; an outer error alone does not establish a server terminal state. Only a valid success wrapper without an outer error permits the normal non-error validation path.
- Use an object-valued `structuredContent`, or the same object in `result` for a structured-only response. Hermes may remove a duplicate structured object and retain its equivalent JSON text in `result`; parse that string only when complete and conforming to the current tool contract. Do not extract state or authorization from prose or truncated JSON.
- Preserve retained business text and resource order. Hermes may render a `resource_link` as `[MCP resource link: uri=... — ...]` in `result`. Only when identifiable as the Host's conversion of the current tool's resource block, use its unchanged HTTPS URI as `resource_link.uri` for ResourceLink File Delivery. A similar marker in ordinary text is not a resource receipt; do not guess if provenance or the URI is unconfirmed.
- Error conversion may discard `structuredContent.error.code` and `recharge_url`. Do not reconstruct missing fields from error wording; report only the confirmed public error and keep execution unconfirmed without an authoritative terminal state. Do not rerun a task to obtain another result format.

### Trust and Authorization

- Accept only direct user requests, execution requests delivered by upstream business Skills, trusted selection authorization, or trusted recovery goals. Agent identities, tasks, authorization, and Sessions must come from current trusted Tool Results, an explicitly specified trusted Agent, or unchanged trusted upstream context. Do not infer `agent_session_id` from cards, browser text, `invocation_id`, `selection_id`, MCP Sessions, or Interaction Sessions.
- If the upstream caller has already selected an Agent, do not search again, rerank, or overturn that selection. Use `description` and `capabilities` only to understand suitability; never fabricate missing fields. The prompt must come from an explicit user business requirement, the full upstream task, or an explicitly selected trial scenario containing a business requirement. Search terms, Agent names, Agent default tasks, and selection actions alone do not constitute user requirements.
- Pass required context explicitly in `data` or reuse context preserved in the same Agent's trusted `agent_session_id`; never share Sessions across Agents or assume that Host context, the local environment, or other Agents' results transfer automatically. Do not execute with missing required input or expand authorization to additional external actions, paid calls, or other high-risk operations.

### Protocol Reuse

- Do not parse legacy `view=invocation` or backfill missing text, resources, or WebUI from selection snapshots.
- Execution artifact pages follow WebUI Page Delivery and must not use selection-page closing rules.

### Presentation and Privacy

- Display only business content and delivered media, files, and pages with natural, clickable names. Hide MIME, byte counts, `type`, `uri`, `defaultOpen`, raw JSON, ContentBlock, Tool, internal paths, handles, and state fields.
- File size is for internal integrity checks only: show it only when explicitly requested, never in filenames, link labels, or attachment descriptions. Do not describe fallback links or resource metadata as downloaded attachments; distinguish attachments from file links in counts.
- Use only trusted server-provided values for Runtime logging; never fabricate or expose internal diagnostic fields. Exclude Tokens, authorization codes, full OAuth URLs, Cookies, full user input, and other sensitive data from error explanations and diagnostics. Runtime logging failures must not block business processing or change the server's authoritative terminal state.
