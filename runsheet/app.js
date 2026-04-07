/* Daily Runsheet - App Logic  v2026-04-07a */

const APP_VERSION = '2026-04-07a';
const API_BASE = window.location.origin;
let plan = null;
const LONG_PRESS_MS = 500;
let modalSelected = new Set();
let currentModalItem = null;
let _loadSeq = 0;  // race guard: only the latest loadPlan() renders

const CATEGORY_ICONS = {
  gym: '💪', walk: '🚶', meal: '🍽️', prep: '🔪',
  cleaning: '🧹', nsdr: '😌', 'brain-building': '🧠',
  custom: '📌', coffee: '☕', shopping: '🛒',
  shower: '🚿', laundry: '👕'
};

// choice_type -> pantry category(ies) to query
const CHOICE_CAT_MAP = {
  oatmeal_fruit:    ['fruit'],
  snack_fruit:      ['fruit'],
  preworkout_fruit: ['fruit'],
  veggie_bowl_veg:  ['vegetable'],
  snack_veg:        ['vegetable', 'fruit'],
};

function apiFetch(url, init = {}) {
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) }
  });
}

async function init() {
  // Unregister any leftover service workers
  if ('serviceWorker' in navigator) {
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const r of regs) r.unregister();
  }

  // Show version in header for debugging
  console.log('Runsheet version:', APP_VERSION);

  // Handle browser back button: close open modals instead of navigating away
  window.addEventListener('popstate', () => {
    if (document.getElementById('foodModal').classList.contains('open')) {
      closeFoodModal(false);
    } else if (document.getElementById('checkinModal').classList.contains('open')) {
      closeCheckinModal(false);
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' &&
        !document.getElementById('app').classList.contains('hidden')) {
      loadPlan();
    }
  });

  document.getElementById('loginBtn').addEventListener('click', doLogin);
  document.getElementById('passwordInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
  document.getElementById('usernameInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('passwordInput').focus();
  });

  document.getElementById('addBtn').addEventListener('click', toggleAddBar);
  document.getElementById('addItemSubmit').addEventListener('click', addItem);
  document.getElementById('addItemInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') addItem();
  });

  document.getElementById('foodModalClose').addEventListener('click', () => closeFoodModal(true));
  document.getElementById('foodModalConfirm').addEventListener('click', confirmMultiSelect);
  document.getElementById('foodModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeFoodModal(true);
  });
  document.getElementById('checkinModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeCheckinModal(true);
  });
  buildScales();

  // Check existing session
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/today');
    if (resp.status === 200) {
      plan = await resp.json();
      showApp();
      renderPlan();
      return;
    }
  } catch (e) {}
  showLogin();
}

function showLogin() {
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
  document.getElementById('itemList').innerHTML = '';
}

function showApp() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  // Show version stamp
  const vEl = document.getElementById('versionStamp');
  if (vEl) vEl.textContent = 'v' + APP_VERSION;
}

async function doLogin() {
  const username = document.getElementById('usernameInput').value.trim();
  const password = document.getElementById('passwordInput').value;
  const errEl = document.getElementById('loginError');

  if (!username || !password) {
    errEl.textContent = 'Please enter username and password';
    return;
  }

  try {
    await fetch(API_BASE + '/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password }).toString(),
      credentials: 'include',
      redirect: 'manual'
    });

    const check = await apiFetch(API_BASE + '/api/runsheet/today');
    if (check.status === 200) {
      errEl.textContent = '';
      plan = await check.json();
      showApp();
      renderPlan();
    } else {
      errEl.textContent = 'Wrong username or password';
    }
  } catch (e) {
    errEl.textContent = 'Connection failed';
  }
}

async function loadPlan() {
  const seq = ++_loadSeq;
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/today');
    if (seq !== _loadSeq) return false;
    if (resp.status === 401) { showLogin(); return false; }
    plan = await resp.json();
    renderPlan();
    return true;
  } catch (e) {
    if (seq !== _loadSeq) return false;
    document.getElementById('itemList').innerHTML =
      '<div class="loading">Could not load plan</div>';
    return false;
  }
}

function renderPlan() {
  if (!plan) return;

  const d = new Date(plan.date + 'T12:00:00');
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  document.getElementById('dayLabel').textContent = days[d.getDay()] + ' \u2014 ' + (plan.day_type || '');

  const items = (plan.items || []).slice().sort((a, b) => {
    const aInactive = a.status !== 'pending' ? 1 : 0;
    const bInactive = b.status !== 'pending' ? 1 : 0;
    if (aInactive !== bInactive) return aInactive - bInactive;
    return a.order - b.order;
  });
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;
  const pct = total ? Math.round(done / total * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = done + ' / ' + total;

  const currentIdx = items.findIndex(i => i.status === 'pending');
  buildInsertOptions(items);

  const list = document.getElementById('itemList');
  list.innerHTML = '';

  const pendingIds = items.filter(i => i.status === 'pending').map(i => i.id);

  items.forEach((item, idx) => {
    const card = document.createElement('div');
    card.className = 'item-card';
    card.dataset.id = item.id;
    if (item.status === 'done') card.classList.add('done');
    else if (item.status === 'skipped') card.classList.add('skipped');
    else if (idx === currentIdx) card.classList.add('current');

    const icon = CATEGORY_ICONS[item.category] || '📋';
    const statusIcon = item.status === 'done' ? '✓' : item.status === 'skipped' ? '—' : '';
    const metaHtml = item.food_choice && item.food_choice.selected
      ? '<div class="item-meta">→ ' + item.food_choice.selected + '</div>' : '';

    let reorderHtml = '';
    if (item.status === 'pending') {
      const pIdx = pendingIds.indexOf(item.id);
      const canUp = pIdx > 0;
      const canDown = pIdx < pendingIds.length - 1;
      reorderHtml =
        '<div class="reorder-btns">' +
        '<button type="button" class="reorder-btn up-btn" data-id="' + item.id + '"' +
          (canUp ? '' : ' disabled') + ' title="Move up">↑</button>' +
        '<button type="button" class="reorder-btn down-btn" data-id="' + item.id + '"' +
          (canDown ? '' : ' disabled') + ' title="Move down">↓</button>' +
        '</div>';
    }

    card.innerHTML =
      '<div class="item-icon">' + icon + '</div>' +
      '<div class="item-content"><div class="item-label">' + item.label + '</div>' + metaHtml + '</div>' +
      reorderHtml +
      '<div class="item-status-icon">' + statusIcon + '</div>';

    if (item.status === 'pending') {
      let pressStart = 0, pressTimeout = null, didLongPress = false;
      card.addEventListener('pointerdown', e => {
        if (e.target.closest('.reorder-btns')) return;
        pressStart = Date.now(); didLongPress = false;
        pressTimeout = setTimeout(() => {
          didLongPress = true; skipItem(item.id);
          card.style.transform = 'scale(0.97)';
          setTimeout(() => card.style.transform = '', 150);
        }, LONG_PRESS_MS);
      });
      card.addEventListener('pointerup', e => {
        if (e.target.closest('.reorder-btns')) return;
        clearTimeout(pressTimeout);
        if (!didLongPress && Date.now() - pressStart < LONG_PRESS_MS) handleItemTap(item);
      });
      card.addEventListener('pointerleave', () => clearTimeout(pressTimeout));

      card.querySelectorAll('.up-btn').forEach(btn => {
        btn.addEventListener('click', e => { e.stopPropagation(); moveItem(item.id, -1, items); });
      });
      card.querySelectorAll('.down-btn').forEach(btn => {
        btn.addEventListener('click', e => { e.stopPropagation(); moveItem(item.id, +1, items); });
      });
    } else if (item.status === 'done' || item.status === 'skipped') {
      card.style.cursor = 'pointer';
      card.addEventListener('click', () => {
        if (item.status === 'done' && item.food_choice && item.food_choice.choice_type) {
          reopenFoodModal(item);
        } else {
          resetItem(item.id);
        }
      });
    }

    list.appendChild(card);
  });

  if (currentIdx >= 0) {
    setTimeout(() => {
      const cards = list.querySelectorAll('.item-card');
      if (cards[currentIdx]) cards[currentIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }
}

// ---- Up/Down reorder ----

async function moveItem(itemId, direction, sortedItems) {
  const pending = sortedItems.filter(i => i.status === 'pending');
  const pIdx = pending.findIndex(i => i.id === itemId);
  if (pIdx < 0) return;
  const newPIdx = pIdx + direction;
  if (newPIdx < 0 || newPIdx >= pending.length) return;

  const swapped = [...pending];
  [swapped[pIdx], swapped[newPIdx]] = [swapped[newPIdx], swapped[pIdx]];

  let pCursor = 0;
  const finalOrder = sortedItems.map(i => {
    if (i.status !== 'pending') return i.id;
    return swapped[pCursor++].id;
  });

  try {
    await apiFetch(API_BASE + '/api/runsheet/edit', {
      method: 'POST',
      body: JSON.stringify([{ action: 'reorder', new_order: finalOrder }])
    });
    loadPlan();
  } catch (e) {
    showToast('Reorder failed', true);
  }
}

// ---- Item actions ----

function handleItemTap(item) {
  if (item.category === 'meal' && item.food_choice && !item.food_choice.selected) {
    openFoodModal(item); return;
  }
  completeItem(item.id);
  if (item.category === 'gym') setTimeout(() => openCheckinModal(), 600);
}

async function completeItem(itemId) {
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/complete', { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '');
      showToast('Complete err ' + resp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    showToast('Done ✓'); loadPlan();
  } catch (e) {
    showToast('Complete net err: ' + (e.message || 'unknown'), true);
  }
}

async function skipItem(itemId) {
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/skip', { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '');
      showToast('Skip err ' + resp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    showToast('Skipped'); loadPlan();
  } catch (e) {
    showToast('Skip net err: ' + (e.message || 'unknown'), true);
  }
}

async function resetItem(itemId) {
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/reset', { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '');
      showToast('Reset err ' + resp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    showToast('Reopened'); loadPlan();
  } catch (e) {
    showToast('Reset net err: ' + (e.message || 'unknown'), true);
  }
}

// ---- Food Choice Modal ----

function reopenFoodModal(item) {
  apiFetch(API_BASE + '/api/runsheet/item/' + item.id + '/reset', { method: 'POST' })
    .then(() => {
      return apiFetch(API_BASE + '/api/runsheet/today').then(r => r.json());
    })
    .then(freshPlan => {
      plan = freshPlan;
      const freshItem = (freshPlan.items || []).find(i => i.id === item.id);
      if (freshItem) openFoodModal(freshItem, item.food_choice ? item.food_choice.selected : null);
    })
    .catch(() => openFoodModal(item, item.food_choice ? item.food_choice.selected : null));
}

function openFoodModal(item, preSelected) {
  currentModalItem = item;
  modalSelected = preSelected
    ? new Set(preSelected.split(',').map(s => s.trim()).filter(Boolean))
    : new Set();
  document.getElementById('foodModalTitle').textContent = item.label;
  const ct = item.food_choice.choice_type;
  const isMulti = item.food_choice.options && item.food_choice.options.multi_select;
  const names = {
    oatmeal_fruit:    'Pick a fruit for your oatmeal',
    veggie_bowl_veg:  'Pick vegetables for your bowl',
    snack_veg:        'Pick your snacks',
    snack_fruit:      'Pick a snack fruit',
    preworkout_fruit: 'Pick a pre-workout fruit'
  };
  document.getElementById('foodModalSubtitle').textContent =
    (names[ct] || 'What are you having?') + (isMulti ? ' (tap all that apply)' : '');
  const confirmBtn = document.getElementById('foodModalConfirm');
  confirmBtn.classList.toggle('hidden', !isMulti);
  confirmBtn.disabled = modalSelected.size === 0;
  loadFoodOptions(item, ct, document.getElementById('foodChoiceGrid'), isMulti);
  history.pushState({ modal: 'food' }, '');
  document.getElementById('foodModal').classList.add('open');
}

async function loadFoodOptions(item, ct, grid, isMulti) {
  grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Loading...</div>';
  const categories = CHOICE_CAT_MAP[ct] || ['fruit'];
  try {
    const fetches = categories.map(cat =>
      apiFetch(API_BASE + '/api/pantry?category=' + cat + '&stocked_only=true').then(r => r.json())
    );
    const results = await Promise.all(fetches);
    const its = results.flat();

    if (!its.length) {
      const catLabel = categories.length > 1 ? 'fruits or vegetables' : categories[0] + 's';
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">No ' +
        catLabel + ' stocked \u2014 open the pantry and mark what you have</div>';
      return;
    }
    grid.innerHTML = '';
    its.forEach(pi => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'choice-btn'; btn.textContent = pi.name;
      if (modalSelected.has(pi.name)) btn.classList.add('selected');
      if (isMulti) {
        btn.addEventListener('click', () => {
          modalSelected.has(pi.name) ? (modalSelected.delete(pi.name), btn.classList.remove('selected'))
                                     : (modalSelected.add(pi.name),    btn.classList.add('selected'));
          document.getElementById('foodModalConfirm').disabled = modalSelected.size === 0;
        });
      } else {
        btn.addEventListener('click', () => selectFoodChoice(item, ct, pi.name));
      }
      grid.appendChild(btn);
    });
  } catch (e) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Could not load options</div>';
  }
}

async function selectFoodChoice(item, ct, selected) {
  try {
    const fcResp = await apiFetch(API_BASE + '/api/runsheet/food-choice', {
      method: 'POST',
      body: JSON.stringify({ plan_item_id: item.id, choice_type: ct, selected: selected })
    });
    if (!fcResp.ok) {
      const detail = await fcResp.text().catch(() => '');
      closeFoodModal(true);
      showToast('Food err ' + fcResp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    const compResp = await apiFetch(API_BASE + '/api/runsheet/item/' + item.id + '/complete', { method: 'POST' });
    if (!compResp.ok) {
      const detail = await compResp.text().catch(() => '');
      closeFoodModal(true);
      showToast('Done err ' + compResp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    closeFoodModal(true);
    showToast(selected + ' \u2014 done \u2713'); loadPlan();
  } catch (e) {
    closeFoodModal(true);
    showToast('Net err: ' + (e.message || 'unknown'), true);
  }
}

async function confirmMultiSelect() {
  if (!modalSelected.size || !currentModalItem) return;
  const sel = [...modalSelected].join(', ');
  try {
    const fcResp = await apiFetch(API_BASE + '/api/runsheet/food-choice', {
      method: 'POST',
      body: JSON.stringify({ plan_item_id: currentModalItem.id, choice_type: currentModalItem.food_choice.choice_type, selected: sel })
    });
    if (!fcResp.ok) {
      const detail = await fcResp.text().catch(() => '');
      closeFoodModal(true);
      showToast('Food err ' + fcResp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    const compResp = await apiFetch(API_BASE + '/api/runsheet/item/' + currentModalItem.id + '/complete', { method: 'POST' });
    if (!compResp.ok) {
      const detail = await compResp.text().catch(() => '');
      closeFoodModal(true);
      showToast('Done err ' + compResp.status + ': ' + detail.substring(0, 80), true);
      return;
    }
    closeFoodModal(true);
    showToast([...modalSelected].join(' + ') + ' \u2014 done \u2713'); loadPlan();
  } catch (e) {
    closeFoodModal(true);
    showToast('Net err: ' + (e.message || 'unknown'), true);
  }
}

function closeFoodModal(popBack) {
  document.getElementById('foodModal').classList.remove('open');
  if (popBack) history.back();
}

// ---- Check-in Modal ----

let checkinValues = { energy: null, mood: null };

function buildScales() {
  [['energyScale', ['😴','😐','🙂','😊','⚡'], 'energy'],
   ['moodScale',   ['😞','😕','😐','🙂','😄'], 'mood']
  ].forEach(([rowId, emojis, key]) => {
    const row = document.getElementById(rowId);
    [1,2,3,4,5].forEach(n => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'scale-btn'; btn.textContent = emojis[n-1]; btn.dataset.value = n;
      btn.addEventListener('click', () => {
        checkinValues[key] = n;
        row.querySelectorAll('.scale-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected'); updateCheckinSubmit();
      });
      row.appendChild(btn);
    });
  });
  document.getElementById('checkinSubmit').addEventListener('click', submitCheckin);
}

function updateCheckinSubmit() {
  document.getElementById('checkinSubmit').disabled = !(checkinValues.energy && checkinValues.mood);
}

function openCheckinModal() {
  checkinValues = { energy: null, mood: null };
  document.querySelectorAll('#energyScale .scale-btn, #moodScale .scale-btn').forEach(b => b.classList.remove('selected'));
  document.getElementById('checkinSubmit').disabled = true;
  history.pushState({ modal: 'checkin' }, '');
  document.getElementById('checkinModal').classList.add('open');
}

function closeCheckinModal(popBack) {
  document.getElementById('checkinModal').classList.remove('open');
  if (popBack) history.back();
}

async function submitCheckin() {
  closeCheckinModal(true);
  try {
    await apiFetch(API_BASE + '/api/checkin', { method: 'POST', body: JSON.stringify({ energy: checkinValues.energy, mood: checkinValues.mood }) });
    showToast('Check-in saved');
  } catch (e) { showToast('Check-in failed', true); }
}

// ---- Add Item ----

function toggleAddBar() {
  const bar = document.getElementById('addItemBar');
  const picker = document.getElementById('insertPicker');
  const isHidden = bar.classList.contains('hidden');
  bar.classList.toggle('hidden'); picker.classList.toggle('visible', isHidden);
  if (isHidden) document.getElementById('addItemInput').focus();
}

function buildInsertOptions(items) {
  const sel = document.getElementById('insertPosition');
  sel.innerHTML = '<option value="end">At the end</option>';
  items.filter(i => i.status === 'pending').forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.id; opt.textContent = 'Before: ' + item.label;
    sel.appendChild(opt);
  });
}

async function addItem() {
  const input = document.getElementById('addItemInput');
  const label = input.value.trim();
  if (!label) return;
  try {
    await apiFetch(API_BASE + '/api/runsheet/edit', { method: 'POST', body: JSON.stringify([{ action: 'add', label, category: 'custom' }]) });
    input.value = ''; toggleAddBar(); showToast('Item added'); loadPlan();
  } catch (e) { showToast('Failed to add', true); }
}

// ---- Toast ----

function showToast(msg, warn) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast show' + (warn ? ' warn' : '');
  setTimeout(() => t.className = 'toast', 4000);
}

document.addEventListener('DOMContentLoaded', init);
