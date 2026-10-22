import { host } from '@hermes/plugin-sdk';

// 安装器仅向本次临时插件注入回调地址、目标 profile 和固定引导提示。
const config = __OPENAGENT_DESKTOP_CONFIG__;
const ACCOUNT_TOOL = 'mcp__openagent__openagent_account_credits';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const emptyArgs = value => object(value) && Object.keys(value).length === 0;

function accountSucceeded(value) {
  try {
    let data = typeof value === 'string' ? JSON.parse(value) : value;
    if (!object(data) || 'error' in data || data.isError === true) return false;
    if ('structuredContent' in data) data = data.structuredContent;
    else if ('result' in data) data = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
    return object(data) && !('error' in data) && data.isError !== true && data.success === true;
  } catch {
    return false;
  }
}

export default {
  id: config.id,
  name: 'OpenAgent 安装验收',
  defaultEnabled: true,
  register(ctx) {
    let disposed = false;
    let stopped = false;
    let checking = false;
    let submitted = false;
    let route;
    let sessionId;
    let accountId;
    let accountOk = false;
    let lastSeq = -1;
    let reports = Promise.resolve(true);
    let cancelPoll = () => {};
    let cancelDeadline = () => {};
    let unsubscribe = () => {};
    const requests = new Set();
    const previousSessions = new Set();

    const stop = () => {
      stopped = true;
      cancelPoll();
      cancelDeadline();
      unsubscribe();
    };
    ctx.onDispose(() => {
      disposed = true;
      stop();
      for (const request of requests) request.abort();
    });

    async function post(body) {
      if (disposed) return false;
      const controller = new AbortController();
      requests.add(controller);
      const cancel = ctx.setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch(config.callbackUrl, {
          method: 'POST', headers: { 'Content-Type': 'text/plain' },
          credentials: 'omit', body: JSON.stringify(body), signal: controller.signal,
        });
        return !disposed && response.ok && (await response.json()).ok === true;
      } catch {
        return false;
      } finally {
        cancel();
        requests.delete(controller);
      }
    }

    function report(body) {
      // 顺序回执；前一回执被拒绝或未知时，不重试、不继续报成功。
      reports = reports.then(ok => ok && post(body));
      return reports;
    }

    function fail(reason) {
      if (stopped || disposed) return;
      stop();
      void report({ phase: 'failed', reason, ...(sessionId ? { session_id: sessionId } : {}) });
    }

    const value = key => host.state[key].get();
    const sameRoute = () => value('profile') === route.profile
      && (value('connectionId') || 'local') === route.connectionId;
    const freshDraft = () => sameRoute() && value('gateway') === 'open'
      && !value('activeSessionId') && !value('focusedSessionId') && !value('focusedStoredSessionId');

    function eventReceived(event) {
      if (stopped || disposed || !submitted || event.replayed
          || event.profile !== route.profile || (event.connectionId || 'local') !== route.connectionId) return;
      if (!sessionId) {
        if (event.type !== 'message.start' || typeof event.session_id !== 'string'
            || !event.session_id || previousSessions.has(event.session_id)
            || !sameRoute() || value('activeSessionId') !== event.session_id
            || value('focusedSessionId') !== event.session_id) return;
        sessionId = event.session_id;
        void report({ phase: 'sent', session_id: sessionId });
      }
      if (event.session_id !== sessionId) return;
      if (!sameRoute() || value('activeSessionId') !== sessionId || value('focusedSessionId') !== sessionId) {
        fail('session_changed');
        return;
      }
      if (Number.isInteger(event.seq)) {
        if (event.seq <= lastSeq) return;
        lastSeq = event.seq;
      }
      const payload = event.payload || {};
      if (payload.name === ACCOUNT_TOOL && event.type === 'tool.start') {
        if ((accountId && accountId !== payload.tool_id) || typeof payload.tool_id !== 'string' || !payload.tool_id
            || (payload.args !== undefined && !emptyArgs(payload.args))) {
          fail('account_invalid');
          return;
        }
        accountId = payload.tool_id;
      } else if (payload.name === ACCOUNT_TOOL && event.type === 'tool.complete') {
        if (!accountId || payload.tool_id !== accountId
            || !emptyArgs(payload.args) || !accountSucceeded(payload.result)) {
          fail('account_invalid');
          return;
        }
        accountOk = true;
      } else if (event.type === 'message.complete') {
        if (payload.status !== 'complete' || payload.error || payload.error_surface || payload.failure_reason || payload.partial) {
          fail('turn_failed');
        } else if (!accountOk) {
          fail('evidence_missing');
        } else {
          stop();
          void report({ phase: 'complete', session_id: sessionId, account_success: true });
        }
      }
    }

    async function checkDraft() {
      if (checking || stopped || disposed || submitted || !freshDraft()) return;
      checking = true;
      try {
        const draft = await host.composer.getDraft('new');
        if (stopped || disposed) return;
        if (!freshDraft()) return fail('session_changed');
        if (draft === null) return;
        if (draft !== '') return fail('session_changed');
        // SDK 的外部提交会保留草稿；不预填固定提示，也不清空用户随后输入的内容。
        // true 仅说明原生可见输入框接收了提交；之后只等本次事件，绝不再次发送。
        submitted = true;
        cancelPoll();
        if (!host.composer.submit('new', config.prompt)) fail('new_chat_timeout');
      } catch {
        fail('unsupported_host');
      } finally {
        checking = false;
      }
    }

    async function start() {
      // 安装进程只接受一次 ready；热重载的新模块必须先取得本次许可。
      if (!await report({ phase: 'ready' }) || disposed) return;
      try {
        const required = ['activeSessionId', 'focusedSessionId', 'focusedStoredSessionId', 'profile', 'connectionId', 'gateway'];
        if (typeof host.newChat !== 'function' || typeof host.profileRoutes !== 'function'
            || typeof host.composer?.getDraft !== 'function'
            || typeof host.composer?.submit !== 'function'
            || required.some(key => typeof host.state?.[key]?.get !== 'function')) return fail('unsupported_host');
        const routes = (await host.profileRoutes()).filter(item => item.mode === 'local'
          && item.targetProfile === config.profile && typeof item.connectionId === 'string' && item.connectionId
          && typeof item.profile === 'string' && item.profile);
        if (stopped || disposed) return;
        if (routes.length !== 1) return fail('profile_unavailable');
        [route] = routes;
        for (const key of ['activeSessionId', 'focusedSessionId']) {
          if (value(key)) previousSessions.add(value(key));
        }
        // SDK 先向插件分发，再更新原生会话状态；微任务中核对更新后的同一会话。
        unsubscribe = ctx.onEvent('*', event => queueMicrotask(() => eventReceived(event)));
        cancelDeadline = ctx.setTimeout(() => fail(submitted ? 'timeout' : 'new_chat_timeout'), config.timeoutMs);
        host.newChat(route);
        if (stopped || disposed) return;
        cancelPoll = ctx.setInterval(() => { void checkDraft(); }, 100);
        void checkDraft();
      } catch {
        fail('unsupported_host');
      }
    }
    void start();
  },
};
