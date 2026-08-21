import * as api from './api.js?v=3.4';
import { toast } from './toast.js?v=3.3';

const getTools = api.getTools;
const getToolStats = api.getToolStats;
const getToolResults = api.getToolResults;
const getCurrentJob = api.getCurrentJob;
const startJob = api.startJob;
const stopJob = api.stopJob;
const clearJobLogs = api.clearJobLogs;
const getConfigSummary = api.getConfigSummary;
const updateConfig = api.updateConfig;
const getHealth = api.getHealth;
const getHotmails =
  typeof api.getHotmails === 'function'
    ? api.getHotmails
    : async () => ({ count: 0, accounts: [], slots: 0 });
const importHotmails =
  typeof api.importHotmails === 'function'
    ? api.importHotmails
    : async () => {
        throw new Error('API Hotmail chưa sẵn sàng — restart web server');
      };

const PAGE_META = {
  '#/register': { title: 'Bảng điều khiển', eyebrow: 'Thiết lập và theo dõi các phiên đăng ký.' },
  '#/results': { title: 'Kho tài khoản', eyebrow: 'Quản lý tài khoản và trạng thái xử lý.' },
  '#/logs': { title: 'Dòng sự kiện', eyebrow: 'Theo dõi tiến trình và lỗi theo thời gian thực.' },
  '#/settings': { title: 'Thiết lập', eyebrow: 'Quản lý kết nối và hành vi mặc định của hệ thống.' },
  '#/tools': { title: 'Hệ sinh thái', eyebrow: 'Danh sách nền tảng đang kết nối với Nexus Ops.' },
};

const state = {
  tools: [],
  selectedTool: 'grok',
  form: {},
  job: null,
  logSeq: 0,
  pollTimer: null,
  autoScroll: true,
  hotmailDraft: '',
  hotmailPool: null,
};

function isHotmailMail(val) {
  const v = String(val ?? '').trim().toLowerCase();
  return v === '1' || v === 'hotmail' || v === 'outlook' || v === 'ms';
}

function isSheetOnly(id) {
  return id === 'heygen' || id === 'capcut' || id === 'zai' || id === 'canva';
}

function brandIconSrc(t) {
  if (t.brand_icon) return t.brand_icon;
  return `/static/img/brands/${t.id}.svg`;
}

function brandIconHtml(t) {
  const src = brandIconSrc(t);
  const name = t.name || t.id || '';
  return `<div class="ico brand-official" data-brand="${esc(t.id)}">
    <img src="${esc(src)}" alt="${esc(name)}" width="40" height="40"
      onerror="this.onerror=null;this.remove();this.parentElement.classList.add('is-fallback');" />
    <span class="ico-fallback">${esc(t.icon || '')}</span>
  </div>`;
}

/* ── Theme / chrome ── */
function initChrome() {
  const btn = document.getElementById('theme-toggle');
  btn?.addEventListener('click', () => {
    const root = document.documentElement;
    const sequence = Number(root.dataset.themeSequence || 0) + 1;
    root.dataset.themeSequence = String(sequence);
    root.classList.add('theme-switching');
    const dark = root.classList.toggle('dark-theme');
    localStorage.setItem('nexus-theme-v4', dark ? 'dark' : 'light');
    root.dataset.theme = dark ? 'dark' : 'light';
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (root.dataset.themeSequence === String(sequence)) {
          root.classList.remove('theme-switching');
        }
      });
    });
  });

  const menu = document.getElementById('mobile-menu');
  const sidebar = document.getElementById('sidebar');
  const scrim = document.getElementById('sidebar-scrim');
  const close = () => {
    sidebar?.classList.remove('is-open');
    scrim?.classList.remove('is-open');
  };
  menu?.addEventListener('click', () => {
    sidebar?.classList.toggle('is-open');
    scrim?.classList.toggle('is-open');
  });
  scrim?.addEventListener('click', close);
  document.querySelectorAll('.nav-item').forEach((a) => {
    a.addEventListener('click', close);
  });
}

function setActiveNav(hash) {
  document.querySelectorAll('.nav-item').forEach((a) => {
    a.classList.toggle('is-active', a.dataset.route === hash);
  });
  const meta = PAGE_META[hash] || PAGE_META['#/register'];
  const t = document.getElementById('page-title');
  const e = document.getElementById('page-eyebrow');
  if (t) t.textContent = meta.title;
  if (e) e.textContent = meta.eyebrow;
  document.title = `${meta.title} · Nexus Ops`;
}

function revealLiveLog() {
  const panel = document.querySelector('.console-card') || document.getElementById('log-box');
  if (!panel) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  panel.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  const box = document.getElementById('log-box');
  if (box) box.scrollTop = box.scrollHeight;
}

function updateRunPill(job) {
  const pill = document.getElementById('run-pill');
  const text = document.getElementById('run-pill-text');
  if (!pill || !text) return;
  const running = job && ['running', 'pending', 'stopping'].includes(job.status);
  pill.classList.toggle('is-running', !!running);
  if (!job || job.status === 'idle') text.textContent = 'Sẵn sàng';
  else text.textContent = `${job.tool_id || 'job'} · ${job.status}`;
}

function normalizedProgress(job) {
  if (!job) return null;
  const source = job.progress || {};
  const total = Math.max(0, Number(source.total ?? job.params?.count ?? 0) || 0);
  let completed = Math.max(0, Number(source.completed) || 0);
  if (job.status === 'done' && total > 0 && completed === 0) completed = total;
  completed = total > 0 ? Math.min(total, completed) : completed;
  const ok = Math.min(completed, Math.max(0, Number(source.ok) || 0));
  const failed = Math.min(completed, Math.max(0, Number(source.failed) || 0));
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : null;
  return { completed, total, ok, failed, percent, continuous: total === 0 };
}

function progressContent(job) {
  const p = normalizedProgress(job);
  if (!p) return '';
  const countText = p.continuous
    ? `${p.completed} tài khoản đã xử lý · chạy liên tục`
    : `${p.completed} / ${p.total} tài khoản`;
  const percentText = p.continuous ? 'LIVE' : `${p.percent}%`;
  const width = p.continuous ? 32 : p.percent;
  return `
    <div class="progress-meta">
      <strong>${countText}</strong>
      <span>${percentText}</span>
    </div>
    <div class="progress-track${p.continuous ? ' is-continuous' : ''}" role="progressbar"
      aria-label="Tiến trình đăng ký" aria-valuemin="0"
      ${p.continuous ? '' : `aria-valuemax="${p.total}" aria-valuenow="${p.completed}"`}>
      <i style="width:${width}%"></i>
    </div>
    <div class="progress-detail">
      <span class="progress-ok">${p.ok} thành công</span>
      <span class="progress-fail">${p.failed} thất bại</span>
    </div>`;
}

function updateJobProgress(job) {
  const panel = document.getElementById('job-progress');
  if (!panel) return;
  panel.hidden = !job;
  panel.innerHTML = progressContent(job);
}

/* ── Helpers ── */
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function lineClass(line) {
  const l = line.toLowerCase();
  if (/error|fail|fatal|❌/.test(l)) return 'err';
  if (/success|✅|ok |done/.test(l)) return 'ok';
  if (/warn|⚠/.test(l)) return 'warn';
  if (/info|▶|===|sub2api|sso/.test(l)) return 'info';
  return '';
}

function statusTag(status, ok) {
  if (ok) return `<span class="tag tag-ok">${esc(status || 'ok')}</span>`;
  if (/pending|manual|stopped/i.test(status || '')) {
    return `<span class="tag tag-mid">${esc(status)}</span>`;
  }
  return `<span class="tag tag-fail">${esc(status || 'fail')}</span>`;
}

function toolLabel() {
  const t = (state.tools || []).find((x) => x.id === state.selectedTool);
  return t?.name || 'tool';
}

function hotmailPlanText(pool) {
  const acc = Number(pool?.count ?? 0);
  const slots = Number(pool?.slots ?? acc);
  const maxA = Number(pool?.max_aliases ?? 5);
  const name = toolLabel();
  if (!acc) return 'Pool trống — import Hotmail rồi Start.';
  if (maxA <= 1) {
    return `Sẽ reg <strong>${slots}</strong> acc ${esc(name)} từ ${acc} Hotmail (1 mail = 1 acc).`;
  }
  return `Sẽ reg <strong>${slots}</strong> acc ${esc(name)} từ ${acc} Hotmail (mỗi acc tối đa ${maxA} alias).`;
}

function syncHotmailUi(root) {
  const hotmail = isHotmailMail(state.form.mail);
  const panel = root.querySelector('#hotmail-pool');
  const countWrap = root.querySelector('[data-field-wrap="count"]');
  const plan = root.querySelector('#hotmail-plan');
  if (panel) panel.hidden = !hotmail;
  if (countWrap) countWrap.hidden = hotmail;
  if (plan) {
    plan.hidden = !hotmail;
    plan.innerHTML = hotmailPlanText(state.hotmailPool);
  }
}

function syncCanvaJobUi(root) {
  if (state.selectedTool !== 'canva') return;
  const redeem = String(state.form.job || 'reg') === 'redeem';
  const codesEl = root.querySelector('[data-field-wrap="codes"]');
  if (codesEl) codesEl.hidden = false;
  const thr = root.querySelector('[data-field-wrap="threads"]');
  if (thr) thr.hidden = !redeem;
  const panel = root.querySelector('#hotmail-pool');
  const plan = root.querySelector('#hotmail-plan');
  if (redeem) {
    if (panel) panel.hidden = true;
    if (plan) plan.hidden = true;
    const countWrap = root.querySelector('[data-field-wrap="count"]');
    if (countWrap) countWrap.hidden = true;
  }
}

function hotmailPanelHtml(pool, show) {
  const acc = pool?.accounts || [];
  const count = pool?.count ?? acc.length;
  const maxA = pool?.max_aliases ?? 5;
  const rows = acc
    .slice(0, 40)
    .map(
      (a) => `<li>
        <span class="mono">${esc(a.email)}</span>
        <span class="hm-flags">
          ${a.has_refresh ? '<span class="tag tag-ok">refresh</span>' : '<span class="tag tag-mid">no token</span>'}
          ${a.has_client_id ? '<span class="tag tag-ok">cid</span>' : ''}
        </span>
      </li>`
    )
    .join('');
  return `
    <div class="hotmail-panel" id="hotmail-pool" ${show ? '' : 'hidden'}>
      <div class="card-head" style="margin-bottom:10px">
        <div>
          <div class="card-title">Pool Hotmail</div>
          <div class="card-sub">
            ${count} Hotmail · Start sẽ reg ${pool?.slots ?? count} ${esc(toolLabel())}${maxA > 1 ? ` (×${maxA} alias)` : ''} ·
            <span class="mono">${esc(pool?.path || 'data/hotmails.txt')}</span>
          </div>
        </div>
      </div>
      <div class="field">
        <label>Dán Hotmail vào đây</label>
        <textarea id="hotmail-draft" rows="7" placeholder="email|password|refresh_token|client_id
email:password
email----password----client_id----refresh_token">${esc(state.hotmailDraft || '')}</textarea>
        <div class="hint">1 dòng = 1 acc. Nhận <span class="mono">|</span> <span class="mono">:</span> <span class="mono">----</span> <span class="mono">;</span> tab.${maxA > 1 ? ` Alias +1…+${maxA - 1} dùng ở lần Start sau (còn slot).` : ''}</div>
      </div>
      <div class="btn-row" style="margin:8px 0 12px">
        <button type="button" class="btn btn-ghost" id="btn-hotmail-browse">Browse file</button>
        <button type="button" class="btn btn-primary" id="btn-hotmail-add">Thêm vào pool</button>
        <button type="button" class="btn btn-ghost" id="btn-hotmail-replace">Ghi đè pool</button>
        <input type="file" id="hotmail-file" accept=".txt,.csv,.tsv,.log,.text,text/plain" hidden />
      </div>
      <div class="hotmail-list-wrap">
        <div class="card-sub" style="margin-bottom:6px">Đang trong pool</div>
        ${
          acc.length
            ? `<ul class="hotmail-list">${rows}${
                acc.length > 40 ? `<li class="card-sub">… +${acc.length - 40} acc nữa</li>` : ''
              }</ul>`
            : `<div class="empty" style="padding:16px">Pool trống — dán list hoặc Browse từ Explorer.</div>`
        }
      </div>
    </div>
  `;
}

function bindHotmailPanel(root, toolId) {
  const panel = root.querySelector('#hotmail-pool');
  const draft = root.querySelector('#hotmail-draft');
  const fileEl = root.querySelector('#hotmail-file');
  if (!panel) return;

  const syncDraft = () => {
    if (draft) state.hotmailDraft = draft.value;
  };
  draft?.addEventListener('input', syncDraft);

  const applyPool = (pool) => {
    state.hotmailPool = pool;
    const next = hotmailPanelHtml(pool, true);
    panel.insertAdjacentHTML('afterend', next);
    panel.remove();
    bindHotmailPanel(root, toolId);
    const mailSel = root.querySelector('[data-key="mail"]');
    if (mailSel) state.form.mail = mailSel.value;
    syncHotmailUi(root);
  };

  const send = async (mode) => {
    syncDraft();
    const text = (state.hotmailDraft || '').trim();
    if (!text) {
      toast('Dán Hotmail hoặc Browse file trước', 'err');
      return;
    }
    if (mode === 'replace' && !confirm('Ghi đè toàn bộ data/hotmails.txt?')) return;
    try {
      const res = await importHotmails(toolId, text, mode);
      state.hotmailDraft = '';
      const added = res.added ?? 0;
      const skipped = res.skipped ?? 0;
      const invalid = res.invalid ?? 0;
      toast(
        mode === 'replace'
          ? `Đã ghi đè ${res.count ?? 0} acc`
          : `Thêm ${added} · bỏ trùng ${skipped}${invalid ? ` · lỗi ${invalid}` : ''}`,
        invalid && !added ? 'err' : 'ok'
      );
      applyPool(res);
    } catch (err) {
      toast(err.message || String(err), 'err');
    }
  };

  root.querySelector('#btn-hotmail-browse')?.addEventListener('click', () => fileEl?.click());
  fileEl?.addEventListener('change', async () => {
    const file = fileEl.files && fileEl.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      state.hotmailDraft = text;
      if (draft) draft.value = text;
      toast(`Đã đọc ${file.name} (${text.split(/\r?\n/).filter((l) => l.trim()).length} dòng)`, 'ok');
    } catch (err) {
      toast(err.message || 'Không đọc được file', 'err');
    }
    fileEl.value = '';
  });
  root.querySelector('#btn-hotmail-add')?.addEventListener('click', () => send('append'));
  root.querySelector('#btn-hotmail-replace')?.addEventListener('click', () => send('replace'));
}

/* ── Pages ── */
async function renderRegister(root) {
  if (!state.tools.length) {
    const data = await getTools();
    state.tools = data.tools || [];
  }
  let tool = state.tools.find((t) => t.id === state.selectedTool) || state.tools[0];
  if (!tool) {
    root.innerHTML = `<div class="empty">Không có tool</div>`;
    return;
  }
  state.selectedTool = tool.id;

  // defaults into form
  for (const f of tool.fields || []) {
    if (state.form[f.key] === undefined) state.form[f.key] = f.default;
  }

  let stats = {};
  try {
    if (tool.status === 'ready') stats = await getToolStats(tool.id);
  } catch (_) {}
  if (['grok', 'heygen', 'capcut', 'zai', 'canva'].includes(tool.id)) {
    try {
      state.hotmailPool = await getHotmails(tool.id);
    } catch (_) {
      state.hotmailPool = state.hotmailPool || { count: 0, accounts: [] };
    }
  }

  const job = state.job;
  const running = job && ['running', 'pending', 'stopping'].includes(job.status);

  root.innerHTML = `
    <div class="page">
      <div class="grid-4">
        <div class="stat-card info" title="Số email khác nhau (lấy status lần cuối)">
          <div class="stat-label">Email (unique)</div>
          <div class="stat-value">${stats.unique_emails ?? stats.total ?? '—'}</div>
          <div class="card-sub" style="margin-top:4px">${stats.attempts ?? '—'} lượt thử</div>
        </div>
        <div class="stat-card ok" title="${isSheetOnly(tool.id) ? 'Reg thành công — chỉ lên Google Sheet, không Sub2' : 'Reg xong: Sub2API + reg-only + reg OK nhưng sub2 fail'}">
          <div class="stat-label">Reg OK</div>
          <div class="stat-value">${stats.success ?? '—'}</div>
          <div class="card-sub" style="margin-top:4px">${isSheetOnly(tool.id) ? `lên sheet ${esc(tool.id)}, không Sub2` : `chỉ reg: ${stats.reg_only ?? 0} · sub2 fail: ${stats.sub2_fail ?? 0}`}</div>
        </div>
        ${isSheetOnly(tool.id) ? `
        <div class="stat-card" title="${esc(tool.name)} không import Sub2API">
          <div class="stat-label">Google Sheet</div>
          <div class="stat-value">${stats.success ?? '—'}</div>
          <div class="card-sub" style="margin-top:4px">tab ${esc(tool.id)}</div>
        </div>` : `
        <div class="stat-card" title="Đã import Sub2API (added_sub2api)">
          <div class="stat-label">Sub2API OK</div>
          <div class="stat-value">${stats.sub2api ?? '—'}</div>
          <div class="card-sub" style="margin-top:4px">trong ${stats.success ?? 0} reg OK</div>
        </div>`}
        <div class="stat-card bad" title="error* lần status cuối mỗi email">
          <div class="stat-label">Fail</div>
          <div class="stat-value">${stats.fail ?? '—'}</div>
          <div class="card-sub" style="margin-top:4px">pending: ${stats.pending ?? 0}</div>
        </div>
      </div>
      ${stats.blurb ? `<div class="card-sub" style="margin-top:-6px">${esc(stats.blurb)}</div>` : ''}

      <div class="workspace">
        <div class="card control-card">
          <div class="card-head">
            <div>
              <div class="card-title">Thiết lập phiên chạy</div>
              <div class="card-sub">Chọn nền tảng, nguồn email và thông số vận hành.</div>
            </div>
            <span class="badge badge-ready">Ready</span>
          </div>

          <div class="section-label">01 · Chọn nền tảng</div>
          <div class="tool-grid" style="margin-bottom:19px">
            ${state.tools
              .map((t) => {
                const soon = t.status === 'coming_soon';
                const sel = t.id === tool.id;
                return `<button type="button" class="tool-tile ${sel ? 'is-selected' : ''} ${soon ? 'is-soon' : ''}" data-tool="${esc(t.id)}" ${soon ? 'disabled' : ''}>
                  ${brandIconHtml(t)}
                  <strong>${esc(t.name)}</strong>
                  <p>${esc(t.description)}</p>
                  <span class="badge ${soon ? 'badge-soon' : 'badge-ready'}" style="margin-top:8px">${soon ? 'Soon' : 'Ready'}</span>
                </button>`;
              })
              .join('')}
          </div>

          <div class="section-label">02 · Thông số chạy</div>
          <div class="form-stack form-grid" id="tool-form">
            ${(tool.fields || [])
              .map((f) => {
                if (f.type === 'select') {
                  return `<div class="field" data-field-wrap="${esc(f.key)}">
                    <label>${esc(f.label)}</label>
                    <select data-key="${esc(f.key)}">
                      ${(f.options || [])
                        .map(
                          (o) =>
                            `<option value="${esc(o.value)}" ${String(state.form[f.key]) === String(o.value) ? 'selected' : ''}>${esc(o.label)}${o.hint ? ' — ' + esc(o.hint) : ''}</option>`
                        )
                        .join('')}
                    </select>
                    ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}
                  </div>`;
                }
                if (f.type === 'checkbox') {
                  const checked = state.form[f.key] === true || state.form[f.key] === 'true' || state.form[f.key] === 1;
                  return `<div class="check-row" data-field-wrap="${esc(f.key)}">
                    <input type="checkbox" data-key="${esc(f.key)}" id="f-${esc(f.key)}" ${checked ? 'checked' : ''} />
                    <label for="f-${esc(f.key)}" style="margin:0;color:var(--text-primary)">${esc(f.label)}</label>
                  </div>
                  ${f.hint ? `<div class="hint" style="margin-top:-6px">${esc(f.hint)}</div>` : ''}`;
                }
                if (f.type === 'textarea') {
                  return `<div class="field span-2 redeem-box" data-field-wrap="${esc(f.key)}">
                    <label>${esc(f.label)}</label>
                    <textarea data-key="${esc(f.key)}" rows="5" placeholder="CANVASPIDERMAN
MOI_MA_KHAC">${esc(state.form[f.key] ?? f.default ?? '')}</textarea>
                    ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}
                  </div>`;
                }
                return `<div class="field" data-field-wrap="${esc(f.key)}" ${f.key === 'count' && isHotmailMail(state.form.mail) ? 'hidden' : ''}>
                  <label>${esc(f.label)}</label>
                  <input type="${f.type === 'number' ? 'number' : 'text'}" data-key="${esc(f.key)}"
                    value="${esc(state.form[f.key] ?? f.default)}"
                    ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} />
                  ${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}
                </div>`;
              })
              .join('')}
          </div>

          ${['grok', 'heygen', 'capcut', 'zai', 'canva'].includes(tool.id) ? hotmailPanelHtml(state.hotmailPool, isHotmailMail(state.form.mail)) : ''}
          ${
            ['grok', 'heygen', 'capcut', 'zai', 'canva'].includes(tool.id)
              ? `<div class="hotmail-plan" id="hotmail-plan" ${isHotmailMail(state.form.mail) ? '' : 'hidden'}>${hotmailPlanText(state.hotmailPool)}</div>`
              : ''
          }

          ${!isSheetOnly(tool.id) && stats.next_name ? `<div class="card-sub" style="margin-top:12px">Next Sub2API name: <span class="mono">${esc(stats.next_name)}</span> · Hotmail pool: ${stats.hotmails ?? 0}</div>` : ''}

          <div class="btn-row action-row">
            <button class="btn btn-primary" id="btn-start" ${running || tool.status !== 'ready' ? 'disabled' : ''}>Start</button>
            ${tool.id === 'canva' ? `<button class="btn btn-ghost" id="btn-start-redeem" ${running || tool.status !== 'ready' ? 'disabled' : ''}>Start redeem</button>` : ''}
            <button class="btn btn-danger" id="btn-stop" ${!running ? 'disabled' : ''}>Stop</button>
            <button class="btn btn-ghost" id="btn-refresh-stats">Stats</button>
          </div>
        </div>

        <div class="card console-card">
          <div class="log-head">
            <div style="display:flex;align-items:center;gap:10px;min-width:0">
              <span class="term-dots" aria-hidden="true"><i></i><i></i><i></i></span>
              <div>
              <div class="card-title">Live activity</div>
              <div class="card-sub" id="job-status-line">${job ? `${esc(job.tool_id)} · ${esc(job.status)}` : 'Đang chờ phiên chạy mới'}</div>
              </div>
            </div>
            <div class="log-actions">
              <label class="check-row" style="padding:6px 10px;margin:0">
                <input type="checkbox" id="auto-scroll" ${state.autoScroll ? 'checked' : ''} />
                <span style="font-size:12px">Auto-scroll</span>
              </label>
              <button class="btn btn-ghost" id="btn-copy-log" type="button">Copy log</button>
              <button class="btn btn-danger" id="btn-clear-log" type="button" title="Xoá log của phiên hiện tại">Xoá log</button>
            </div>
          </div>
          <div class="job-progress" id="job-progress" ${job ? '' : 'hidden'}>${progressContent(job)}</div>
          <div class="log-console" id="log-box"></div>
        </div>
      </div>
    </div>
  `;

  const liveBox = document.getElementById('log-box');
  bindLogBox(liveBox);
  paintLogs(liveBox, job?.logs || []);

  root.querySelectorAll('[data-tool]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      state.selectedTool = btn.dataset.tool;
      state.form = {};
      await renderRegister(root);
    });
  });

  root.querySelectorAll('[data-key]').forEach((el) => {
    const key = el.dataset.key;
    const sync = () => {
      if (el.type === 'checkbox') state.form[key] = el.checked;
      else if (el.type === 'number') state.form[key] = el.value === '' ? 0 : Number(el.value);
      else state.form[key] = el.value;
      if (key === 'mail') syncHotmailUi(root);
      if (key === 'job') syncCanvaJobUi(root);
    };
    el.addEventListener('change', sync);
    el.addEventListener('input', sync);
  });
  bindHotmailPanel(root, tool.id);
  syncHotmailUi(root);
  syncCanvaJobUi(root);

  document.getElementById('auto-scroll')?.addEventListener('change', (e) => {
    setAutoScroll(e.target.checked, { scrollBox: document.getElementById('log-box') });
  });
  document.getElementById('btn-copy-log')?.addEventListener('click', async () => {
    try {
      await copyLogBox(document.getElementById('log-box'));
    } catch {
      toast('Copy thất bại', 'err');
    }
  });
  bindClearLogButton();

  document.getElementById('btn-start-redeem')?.addEventListener('click', () => {
    const sel = root.querySelector('[data-key="job"]');
    if (sel) sel.value = 'redeem';
    state.form.job = 'redeem';
    document.getElementById('btn-start')?.click();
  });

  document.getElementById('btn-start')?.addEventListener('click', async () => {
    try {
      // collect form
      root.querySelectorAll('[data-key]').forEach((el) => {
        const key = el.dataset.key;
        if (el.type === 'checkbox') state.form[key] = el.checked;
        else if (el.type === 'number') state.form[key] = Number(el.value);
        else state.form[key] = el.value;
      });
      if (state.form.job === 'redeem') {
        const raw = String(state.form.codes || '').trim();
        if (!raw) {
          toast('Dán mã redeem vào ô Mã redeem (mỗi dòng 1 mã)', 'err');
          return;
        }
      } else if (isHotmailMail(state.form.mail)) {
        try {
          state.hotmailPool = await getHotmails(state.selectedTool);
        } catch (_) {}
        const n = Number(state.hotmailPool?.slots || state.hotmailPool?.count || 0);
        if (!n) {
          toast('Pool Hotmail trống / hết slot — import acc rồi Start', 'err');
          return;
        }
        state.form.count = n;
        syncHotmailUi(root);
      }
      const res = await startJob(state.selectedTool, { ...state.form });
      state.job = res.job;
      state.logSeq = 0;
      toast('Đã Start job', 'ok');
      updateRunPill(state.job);
      await renderRegister(root);
      revealLiveLog();
    } catch (err) {
      toast(err.message || String(err), 'err');
    }
  });

  document.getElementById('btn-stop')?.addEventListener('click', async () => {
    try {
      const res = await stopJob(state.job?.id || null);
      toast(res.message || 'Đang dừng…', 'ok');
      revealLiveLog();
    } catch (err) {
      toast(err.message || String(err), 'err');
    }
  });

  document.getElementById('btn-refresh-stats')?.addEventListener('click', async () => {
    await renderRegister(root);
    toast('Đã refresh stats', 'ok');
    revealLiveLog();
  });
}

function selectionIn(el) {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return false;
  const node = sel.anchorNode;
  return !!(node && el.contains(node));
}

function parseLogLine(text) {
  const raw = String(text ?? '');
  let body = raw.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '').trimEnd();
  let time = '';
  let level = '';
  let task = '';
  let source = '';

  const outerTime = body.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*/);
  if (outerTime) {
    time = outerTime[1];
    body = body.slice(outerTime[0].length);
  }

  // Technical logger already includes its own clock. Keep only the web clock
  // so lines do not render as "[14:14:44] 14:14:44 | INFO | ...".
  const technical = body.match(/^(\d{2}:\d{2}:\d{2})\s*\|\s*([A-Z]+)\s*\|\s*/);
  if (technical) {
    if (!time) time = technical[1];
    level = technical[2];
    body = body.slice(technical[0].length);
  }

  const taskPrefix = body.match(/^(\d+)\]\s*/);
  if (taskPrefix) {
    task = taskPrefix[1];
    body = body.slice(taskPrefix[0].length);
  }

  const tagged = body.match(/^\[([^\]]+)\]\s*/);
  if (tagged) {
    source = tagged[1];
    body = body.slice(tagged[0].length);
  } else if (/^===/.test(body)) {
    source = 'JOB';
  } else if (/^CMD:/.test(body)) {
    source = 'CMD';
  }

  const sourceKey = source.toLowerCase();
  if (sourceKey === 'grok-api') source = task ? `ACC ${task}` : 'GROK';
  else if (/^sub2api/.test(sourceKey)) source = 'SUB2API';
  else if (sourceKey === 'turnstile') source = 'CAPTCHA';
  else if (sourceKey === 'delivery') source = 'SYNC';
  else if (sourceKey === 'solver') source = 'SOLVER';
  else if (source) source = source.toUpperCase();
  else if (task) source = `ACC ${task}`;
  else if (level) source = level;
  else source = 'SYSTEM';

  return { raw, time: time || '--:--:--', source, message: body.trim(), level };
}

function makeLogLine(text) {
  const parsed = parseLogLine(text);
  const div = document.createElement('div');
  div.className = `line ${lineClass(parsed.raw)}${parsed.message ? '' : ' blank'}`;
  div.dataset.raw = parsed.raw;
  if (!parsed.message) return div;

  const time = document.createElement('span');
  time.className = 'log-time';
  time.textContent = parsed.time;
  const source = document.createElement('span');
  source.className = 'log-source';
  source.textContent = parsed.source;
  const message = document.createElement('span');
  message.className = 'log-message';
  message.textContent = parsed.message;
  div.append(time, source, message);
  return div;
}

function logBoxText(box) {
  if (!box) return '';
  return [...box.querySelectorAll('.line')].map((el) => el.dataset.raw ?? el.textContent).join('\n');
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch (_) {
    /* fall through */
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  ta.remove();
}

function isLogAtBottom(box, slop = 48) {
  if (!box) return true;
  return box.scrollHeight - box.scrollTop - box.clientHeight < slop;
}

function setAutoScroll(on, { scrollBox } = {}) {
  state.autoScroll = !!on;
  const cb = document.getElementById('auto-scroll');
  if (cb && cb.checked !== state.autoScroll) cb.checked = state.autoScroll;
  if (state.autoScroll && scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
}

function paintLogs(box, lines) {
  if (!box) return;
  const next = Array.isArray(lines) ? lines : [];
  const selecting = selectionIn(box);
  // Keep streaming while the user is selecting/copying. Only skip a full
  // rewrite — that would wipe the highlight and look like the log "stopped".
  const pin =
    !selecting &&
    !box.dataset.holdScroll &&
    (state.autoScroll || isLogAtBottom(box));
  const kids = box.children;
  const prevN = kids.length;
  const canAppend =
    prevN > 0 &&
    next.length >= prevN &&
    kids[0].dataset.raw === String(next[0] ?? '') &&
    kids[prevN - 1].dataset.raw === String(next[prevN - 1] ?? '');

  if (canAppend) {
    if (next.length === prevN) return;
    const frag = document.createDocumentFragment();
    for (let i = prevN; i < next.length; i++) frag.appendChild(makeLogLine(next[i]));
    box.appendChild(frag);
  } else {
    if (selecting) return;
    const frag = document.createDocumentFragment();
    next.forEach((l) => frag.appendChild(makeLogLine(l)));
    box.replaceChildren(frag);
  }
  if (pin) box.scrollTop = box.scrollHeight;
}

function bindLogBox(box) {
  if (!box || box.dataset.copyBound) return;
  box.dataset.copyBound = '1';
  box.setAttribute('tabindex', '0');
  box.setAttribute('role', 'log');
  box.setAttribute('aria-label', 'Live log — bôi chọn để copy');
  box.addEventListener('keydown', (e) => {
    const key = String(e.key).toLowerCase();
    if (!(e.ctrlKey || e.metaKey)) return;
    if (key === 'a') {
      e.preventDefault();
      e.stopPropagation();
      const range = document.createRange();
      range.selectNodeContents(box);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      return;
    }
    if (key === 'c') {
      // Copy only — never treat Ctrl+C in the log as Stop.
      e.stopPropagation();
      const sel = window.getSelection();
      const picked =
        sel && !sel.isCollapsed && box.contains(sel.anchorNode)
          ? sel.toString()
          : '';
      if (picked) return;
      e.preventDefault();
      copyLogBox(box).catch(() => toast('Copy thất bại', 'err'));
    }
  });
  box.addEventListener('copy', (e) => {
    e.stopPropagation();
  });
  box.addEventListener('pointerdown', (e) => {
    box.dataset.holdScroll = '1';
    try {
      box.setPointerCapture(e.pointerId);
    } catch (_) {
      /* ignore */
    }
  });
  const release = () => {
    delete box.dataset.holdScroll;
    setAutoScroll(isLogAtBottom(box));
  };
  box.addEventListener('pointerup', release);
  box.addEventListener('pointercancel', release);
  box.addEventListener(
    'wheel',
    () => {
      requestAnimationFrame(() => setAutoScroll(isLogAtBottom(box)));
    },
    { passive: true },
  );
  box.addEventListener(
    'scroll',
    () => {
      setAutoScroll(isLogAtBottom(box));
    },
    { passive: true },
  );
}

async function copyLogBox(box) {
  const text = logBoxText(box);
  await copyToClipboard(text);
  const n = text ? text.split('\n').length : 0;
  toast(n ? `Đã copy ${n} dòng log` : 'Log trống', n ? 'ok' : 'err');
}

function bindClearLogButton() {
  document.getElementById('btn-clear-log')?.addEventListener('click', async () => {
    const jobId = state.job?.id;
    if (!jobId) {
      toast('Chưa có log để xoá', 'err');
      return;
    }
    try {
      const result = await clearJobLogs(jobId);
      state.job = result.job;
      paintLogs(document.getElementById('log-box'), []);
      toast(`Đã xoá ${result.removed || 0} dòng log`, 'ok');
    } catch (e) {
      toast(e.message || 'Xoá log thất bại', 'err');
    }
  });
}

async function renderResults(root) {
  const toolId = state.selectedTool || 'grok';
  let rows = [];
  let stats = {};
  try {
    const r = await getToolResults(toolId, 150);
    rows = r.results || [];
    stats = await getToolStats(toolId);
  } catch (e) {
    root.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }

  root.innerHTML = `
    <div class="page">
      <div class="page-banner">
        <div><div class="hero-kicker"><i></i> Data vault</div><h2>Kho dữ liệu tài khoản</h2><p>Dữ liệu tài khoản và trạng thái xử lý mới nhất của ${esc(toolId)}.</p></div>
        <span class="page-banner-mark">${rows.length} RECORDS</span>
      </div>
      <div class="grid-4">
        <div class="stat-card info"><div class="stat-label">Email unique</div><div class="stat-value">${stats.unique_emails ?? stats.total ?? 0}</div>
          <div class="card-sub" style="margin-top:4px">${stats.attempts ?? 0} lượt thử</div></div>
        <div class="stat-card ok"><div class="stat-label">Reg OK</div><div class="stat-value">${stats.success ?? 0}</div>
          <div class="card-sub" style="margin-top:4px">${isSheetOnly(toolId) ? 'không Sub2 — chỉ sheet' : `reg-only ${stats.reg_only ?? 0} · sub2 fail ${stats.sub2_fail ?? 0}`}</div></div>
        <div class="stat-card"><div class="stat-label">${isSheetOnly(toolId) ? `Sheet ${esc(toolId)}` : 'Sub2API OK'}</div><div class="stat-value">${isSheetOnly(toolId) ? (stats.success ?? 0) : (stats.sub2api ?? 0)}</div></div>
        <div class="stat-card bad"><div class="stat-label">Fail</div><div class="stat-value">${stats.fail ?? 0}</div>
          <div class="card-sub" style="margin-top:4px">pending ${stats.pending ?? 0}</div></div>
      </div>
      ${stats.blurb ? `<div class="card-sub">${esc(stats.blurb)}</div>` : ''}
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">Accounts · ${esc(toolId)}</div>
            <div class="card-sub">data/accounts.txt — mỗi dòng = 1 lượt thử (email có thể lặp)</div>
          </div>
          <button class="btn btn-ghost" id="btn-copy-ok">Copy Reg OK</button>
        </div>
        <div class="table-wrap">
          <table class="results">
            <thead>
              <tr><th>Email</th><th>Password</th><th>Status</th></tr>
            </thead>
            <tbody>
              ${
                rows.length
                  ? rows
                      .map(
                        (r) => `<tr>
                  <td class="mono">${esc(r.email)}</td>
                  <td class="mono">${esc(r.password)}</td>
                  <td>${statusTag(r.status, r.ok)}</td>
                </tr>`
                      )
                      .join('')
                  : `<tr><td colspan="3" class="empty">Chưa có kết quả</td></tr>`
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById('btn-copy-ok')?.addEventListener('click', async () => {
    const text = rows
      .filter((r) => r.ok)
      .map((r) => `${r.email}|${r.password}|${r.status}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text || '');
      toast(`Đã copy ${rows.filter((r) => r.ok).length} dòng`, 'ok');
    } catch {
      toast('Copy thất bại', 'err');
    }
  });
}

async function renderLogs(root) {
  const job = state.job;
  root.innerHTML = `
    <div class="page">
      <div class="page-banner">
        <div><div class="hero-kicker"><i></i> Activity stream</div><h2>Dòng sự kiện trực tiếp</h2><p>Theo dõi chi tiết tiến trình, cảnh báo và lỗi trong thời gian thực.</p></div>
        <span class="page-banner-mark">LIVE STREAM</span>
      </div>
      <div class="card">
        <div class="log-head">
          <div>
            <div class="card-title">Full log stream</div>
            <div class="card-sub" id="job-status-line">${job ? `${esc(job.tool_id)} · ${esc(job.status)} · id ${esc(job.id || '')}` : 'Idle'}</div>
          </div>
          <div class="btn-row" style="margin:0">
            <label class="check-row" style="padding:6px 10px;margin:0">
              <input type="checkbox" id="auto-scroll" ${state.autoScroll ? 'checked' : ''} />
              <span style="font-size:12px">Auto-scroll</span>
            </label>
            <button class="btn btn-danger" id="btn-stop-log">⏹ Stop</button>
            <button class="btn btn-ghost" id="btn-copy-log" type="button">Copy log</button>
            <button class="btn btn-danger" id="btn-clear-log" type="button" title="Xoá log của phiên hiện tại">Xoá log</button>
          </div>
        </div>
        <div class="job-progress" id="job-progress" ${job ? '' : 'hidden'}>${progressContent(job)}</div>
        <div class="log-console" id="log-box" style="height:calc(100vh - 220px)"></div>
      </div>
    </div>
  `;
  const fullBox = document.getElementById('log-box');
  bindLogBox(fullBox);
  paintLogs(fullBox, job?.logs || []);
  document.getElementById('auto-scroll')?.addEventListener('change', (e) => {
    setAutoScroll(e.target.checked, { scrollBox: document.getElementById('log-box') });
  });
  document.getElementById('btn-copy-log')?.addEventListener('click', async () => {
    try {
      await copyLogBox(document.getElementById('log-box'));
    } catch {
      toast('Copy thất bại', 'err');
    }
  });
  bindClearLogButton();
  document.getElementById('btn-stop-log')?.addEventListener('click', async () => {
    try {
      await stopJob();
      toast('Stop sent', 'ok');
    } catch (e) {
      toast(e.message, 'err');
    }
  });
}

async function renderSettings(root) {
  let sum = {};
  try {
    sum = await getConfigSummary();
  } catch (e) {
    root.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  const sub = sum.sub2api || {};
  const gs = sum.google_sheets || {};
  root.innerHTML = `
    <div class="page">
      <div class="page-banner">
        <div><div class="hero-kicker"><i></i> System settings</div><h2>Thiết lập hệ thống</h2><p>Tổng quan các kết nối và chính sách đang được áp dụng.</p></div>
        <span class="page-banner-mark">EDITABLE</span>
      </div>
      <form id="settings-form" class="settings-form">
        <div class="grid-2">
          <section class="card settings-card">
            <div class="card-head">
              <div><div class="card-title">Sub2API</div><div class="card-sub">Kết nối và thông tin xác thực.</div></div>
              <label class="switch"><input id="cfg-sub-enabled" type="checkbox" ${sub.enabled ? 'checked' : ''}><span></span></label>
            </div>
            <div class="form-grid">
              <div class="field"><label>Chế độ</label><select id="cfg-sub-mode">
                ${['auto', 'api', 'sso', 'browser'].map((v) => `<option value="${v}" ${sub.mode === v ? 'selected' : ''}>${v}</option>`).join('')}
              </select></div>
              <div class="field"><label>URL</label><input id="cfg-sub-url" type="text" value="${esc(sub.url)}" placeholder="http://localhost:8080"></div>
              <div class="field"><label>Group</label><input id="cfg-sub-group" type="text" value="${esc(sub.group)}"></div>
              <div class="field"><label>Name prefix</label><input id="cfg-sub-prefix" type="text" value="${esc(sub.name_prefix)}"></div>
              <div class="field span-2"><label>User</label><input id="cfg-sub-user" type="text" value="${esc(sub.user)}" autocomplete="username"></div>
              <div class="field"><label>Password</label><input id="cfg-sub-pass" type="password" value="" autocomplete="new-password" placeholder="${sub.password_set ? 'Đã cấu hình · để trống để giữ nguyên' : 'Chưa cấu hình'}"></div>
              <div class="field"><label>API token</label><input id="cfg-sub-token" type="password" value="" autocomplete="off" placeholder="${sub.api_token_set ? 'Đã cấu hình · để trống để giữ nguyên' : 'Chưa cấu hình'}"></div>
            </div>
          </section>

          <section class="card settings-card">
            <div class="card-head">
              <div><div class="card-title">Google Sheets</div><div class="card-sub">Đích xuất dữ liệu sau khi chạy.</div></div>
              <label class="switch"><input id="cfg-sheet-enabled" type="checkbox" ${gs.enabled ? 'checked' : ''}><span></span></label>
            </div>
            <div class="form-stack">
              <div class="field"><label>Spreadsheet ID</label><input id="cfg-sheet-id" type="text" value="${esc(gs.spreadsheet_id)}" placeholder="1Abc..."></div>
              <div class="field"><label>Webapp URL</label><input id="cfg-sheet-webapp" type="password" value="" autocomplete="off" placeholder="${gs.webapp_set ? 'Đã cấu hình · để trống để giữ nguyên' : 'Chưa cấu hình'}"></div>
              <div class="settings-note">Thông tin nhạy cảm không được tải ngược ra trình duyệt. Nhập giá trị mới chỉ khi muốn thay đổi.</div>
            </div>
          </section>
        </div>

        <section class="card settings-card">
          <div class="card-head"><div><div class="card-title">Phiên & bảo mật</div><div class="card-sub">Các hành vi mặc định cho phiên đăng ký mới.</div></div></div>
          <div class="settings-options">
            <label class="check-row"><input id="cfg-force-guest" type="checkbox" ${sum.force_guest_on_start ? 'checked' : ''}><span>Force guest khi bắt đầu</span></label>
            <label class="check-row"><input id="cfg-open-grok" type="checkbox" ${sum.open_grok_after_success ? 'checked' : ''}><span>Mở Grok sau khi thành công</span></label>
            <div class="field"><label>Fixed password</label><input id="cfg-fixed-pass" type="password" value="" autocomplete="new-password" placeholder="${sum.fixed_password_set ? 'Đã cấu hình · để trống để giữ nguyên' : 'Chưa cấu hình'}"></div>
          </div>
        </section>

        <div class="settings-actions">
          <div><strong>config.json</strong><span>Thay đổi áp dụng cho các job bắt đầu sau khi lưu.</span></div>
          <div class="btn-row"><button type="button" class="btn btn-ghost" id="btn-settings-reset">Hoàn tác</button><button type="submit" class="btn btn-primary" id="btn-settings-save">Lưu thiết lập</button></div>
        </div>
      </form>
    </div>
  `;

  const form = root.querySelector('#settings-form');
  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const save = root.querySelector('#btn-settings-save');
    if (save) { save.disabled = true; save.textContent = 'Đang lưu…'; }
    const val = (id) => root.querySelector(id)?.value || '';
    const checked = (id) => !!root.querySelector(id)?.checked;
    try {
      const result = await updateConfig({
        sub2api: {
          enabled: checked('#cfg-sub-enabled'), mode: val('#cfg-sub-mode'), url: val('#cfg-sub-url'),
          group: val('#cfg-sub-group'), name_prefix: val('#cfg-sub-prefix'), user: val('#cfg-sub-user'),
          password: val('#cfg-sub-pass') || null, api_token: val('#cfg-sub-token') || null,
        },
        google_sheets: {
          enabled: checked('#cfg-sheet-enabled'), spreadsheet_id: val('#cfg-sheet-id'),
          webapp_url: val('#cfg-sheet-webapp') || null,
        },
        force_guest_on_start: checked('#cfg-force-guest'),
        open_grok_after_success: checked('#cfg-open-grok'),
        fixed_password: val('#cfg-fixed-pass') || null,
      });
      toast(result.message || 'Đã lưu thiết lập', 'ok');
      await renderSettings(root);
    } catch (error) {
      toast(error.message || 'Không lưu được thiết lập', 'err');
      if (save) { save.disabled = false; save.textContent = 'Lưu thiết lập'; }
    }
  });
  root.querySelector('#btn-settings-reset')?.addEventListener('click', () => renderSettings(root));
}

async function renderTools(root) {
  if (!state.tools.length) {
    const data = await getTools();
    state.tools = data.tools || [];
  }
  root.innerHTML = `
    <div class="page">
      <div class="page-banner">
        <div><div class="hero-kicker"><i></i> Connected apps</div><h2>Hệ sinh thái Nexus</h2><p>Quản lý các nền tảng đã kết nối với Nexus Ops.</p></div>
        <span class="page-banner-mark">${state.tools.length} PLUGINS</span>
      </div>
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">Danh mục nền tảng</div>
            <div class="card-sub">Các công cụ kết nối với Nexus Core. Placeholder = sắp triển khai.</div>
          </div>
        </div>
        <div class="tool-grid">
          ${state.tools
            .map((t) => {
              const soon = t.status === 'coming_soon';
              return `<div class="tool-tile ${soon ? 'is-soon' : ''}" style="cursor:default">
                ${brandIconHtml(t)}
                <strong>${esc(t.name)}</strong>
                <p>${esc(t.description)}</p>
                <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
                  <span class="badge ${soon ? 'badge-soon' : 'badge-ready'}">${soon ? 'Coming soon' : 'Ready'}</span>
                  <span class="mono" style="font-size:11px;color:var(--text-muted)">${esc(t.id)}</span>
                </div>
              </div>`;
            })
            .join('')}
        </div>
      </div>
    </div>
  `;
}

/* ── Router ── */
async function route() {
  const hash = location.hash || '#/register';
  const known = PAGE_META[hash] ? hash : '#/register';
  if (known !== location.hash) location.hash = known;
  setActiveNav(known);
  const main = document.getElementById('main-content');
  if (!main) return;
  main.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    if (known === '#/register') await renderRegister(main);
    else if (known === '#/results') await renderResults(main);
    else if (known === '#/logs') await renderLogs(main);
    else if (known === '#/settings') await renderSettings(main);
    else if (known === '#/tools') await renderTools(main);
  } catch (e) {
    main.innerHTML = `<div class="empty">${esc(e.message || e)}</div>`;
  }
}

/* ── Poll job ── */
async function pollJob() {
  try {
    const snap = await getCurrentJob(0);
    if (snap && snap.status && snap.status !== 'idle') {
      state.job = snap;
    } else if (snap && snap.running === false && state.job && state.job.running) {
      state.job = snap;
    } else if (snap && Array.isArray(snap.logs) && snap.logs.length) {
      state.job = snap;
    }
    updateRunPill(state.job);
    updateJobProgress(state.job);

    const box = document.getElementById('log-box');
    const statusLine = document.getElementById('job-status-line');
    if (state.job) {
      if (statusLine) {
        statusLine.textContent = `${state.job.tool_id || ''} · ${state.job.status || ''}${state.job.id ? ' · ' + state.job.id : ''}`;
      }
      if (box) paintLogs(box, state.job.logs || []);

      // refresh Start/Stop disabled state on register page without full re-render
      const running = ['running', 'pending', 'stopping'].includes(state.job.status);
      const bs = document.getElementById('btn-start');
      const bt = document.getElementById('btn-stop');
      if (bs) bs.disabled = running;
      if (bt) bt.disabled = !running;
    }
  } catch (_) {
    /* ignore poll errors */
  }
}

async function boot() {
  initChrome();
  window.addEventListener('hashchange', () => route());
  try {
    await getHealth();
    const data = await getTools();
    state.tools = data.tools || [];
  } catch (e) {
    toast('API offline: ' + e.message, 'err');
  }
  await route();
  await pollJob();
  state.pollTimer = setInterval(pollJob, 900);
}

boot();
