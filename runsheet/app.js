/* Daily Runsheet - App Logic */

const API_BASE = window.location.origin;
let plan = null;
const LONG_PRESS_MS = 500;
let modalSelected = new Set();
let currentModalItem = null;

const CATEGORY_ICONS = {
  gym: '💪', walk: '🚶', meal: '🍽️', prep: '🔪',
  cleaning: '🧹', nsdr: '😌', 'brain-building': '🧠',
  custom: '📌', coffee: '☕', shopping: '🛒',
  shower: '🚿', laundry: '👕'
};

// Fetch wrapper: always sends session cookie
function apiFetch(url, init = {}) {
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) }
  });
}

async function init() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});

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

  document.getElementById('foodModalClose').addEventListener('click', closeFoodModal);
  document.getElementById('foodModalConfirm').addEventListener('click', confirmMultiSelect);
  document.getElementById('foodModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeFoodModal();
  });
  document.getElementById('checkinModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeCheckinModal();
  });
  buildScales();

  // Check if already authenticated (handles back-nav from pantry without re-login)
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

    // Verify the session was set by hitting a protected endpoint
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
  try {
    const resp = await apiFetch(API_BASE + '/api/runsheet/today');
    if (resp.status === 401) { showLogin(); return false; }
    plan = await resp.json();
    renderPlan();
    return true;
  } catch (e) {
    document.getElementById('itemList').innerHTML =
      '<div class="loading">Could not load plan</div>';
    return false;
  }
}

function renderPlan() {
  if (!plan) return;

  const d = new Date(plan.date + 'T12:00:00');
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  document.getElementById('dayLabel').textContent = days[d.getDay()] + ' — ' + (plan.day_type || '');

  // Sort by scheduled order
  const items = (plan.items || []).slice().sort((a, b) => a.order - b.order);
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;
  const pct = total ? Math.round(done / total * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = done + ' / ' + total;

  const currentIdx = items.findIndex(i => i.status === 'pending');
  buildInsertOptions(items);

  const list = document.getElementById('itemList');
  list.innerHTML = '';

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
    const dragHandle = item.status === 'pending'
      ? '<div class="drag-handle" title="Drag to reorder">⠿</div>' : '';

    card.innerHTML =
      dragHandle +
      '<div class="item-icon">' + icon + '</div>' +
      '<div class="item-content"><div class="item-label">' + item.label + '</div>' + metaHtml + '</div>' +
      '<div class="item-status-icon">' + statusIcon + '</div>';

    if (item.status === 'pending') {
      let pressStart = 0, pressTimeout = null, didLongPress = false;
      card.addEventListener('pointerdown', e => {
        if (e.target.closest('.drag-handle')) return; // drag handle owns this event
        pressStart = Date.now(); didLongPress = false;
        pressTimeout = setTimeout(() => {
          didLongPress = true; skipItem(item.id);
          card.style.transform = 'scale(0.97)';
          setTimeout(() => card.style.transform = '', 150);
        }, LONG_PRESS_MS);
      });
      card.addEventListener('pointerup', e => {
        if (e.target.closest('.drag-handle')) return;
        clearTimeout(pressTimeout);
        if (!didLongPress && Date.now() - pressStart < LONG_PRESS_MS) handleItemTap(item);
      });
      card.addEventListener('pointerleave', () => clearTimeout(pressTimeout));
    } else if (item.status === 'done') {
      // Tap a done item to reopen it
      card.style.cursor = 'pointer';
      card.addEventListener('click', () => resetItem(item.id));
    }

    list.appendChild(card);
  });

  initDrag(list);

  if (currentIdx >= 0) {
    setTimeout(() => {
      const cards = list.querySelectorAll('.item-card');
      if (cards[currentIdx]) cards[currentIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }
}

// ---- Drag-to-reorder ----

function initDrag(list) {
  let ghost = null;
  let placeholder = null;
  let offsetY = 0;

  function onMove(e) {
    if (!ghost) return;
    e.preventDefault();
    ghost.style.top = (e.clientY - offsetY) + 'px';

    const ghostMid = parseFloat(ghost.style.top) + ghost.offsetHeight / 2;
    const cards = [...list.querySelectorAll('.item-card:not(.dragging)')];
    let placed = false;
    for (const card of cards) {
      const r = card.getBoundingClientRect();
      if (ghostMid < r.top + r.height / 2) {
        if (placeholder.nextSibling !== card) list.insertBefore(placeholder, card);
        placed = true;
        break;
      }
    }
    if (!placed && list.lastChild !== placeholder) list.appendChild(placeholder);
  }

  async function onUp() {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    if (!ghost) return;

    ghost.classList.remove('dragging');
    ghost.style.cssText = '';
    list.insertBefore(ghost, placeholder);
    placeholder.remove();
    placeholder = null;

    const newOrder = [...list.querySelectorAll('.item-card[data-id]')]
      .map(c => parseInt(c.dataset.id));
    ghost = null;

    try {
      await apiFetch(API_BASE + '/api/runsheet/edit', {
        method: 'POST',
        body: JSON.stringify([{ action: 'reorder', new_order: newOrder }])
      });
      loadPlan();
    } catch (err) {
      showToast('Reorder failed', true);
      loadPlan();
    }
  }

  function onCancel() {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    if (!ghost) return;
    ghost.classList.remove('dragging');
    ghost.style.cssText = '';
    if (placeholder) { list.insertBefore(ghost, placeholder); placeholder.remove(); placeholder = null; }
    ghost = null;
    loadPlan();
  }

  list.addEventListener('pointerdown', e => {
    const handle = e.target.closest('.drag-handle');
    if (!handle) return;
    const card = handle.closest('.item-card');
    if (!card) return;
    e.preventDefault();

    const rect = card.getBoundingClientRect();
    offsetY = e.clientY - rect.top;

    placeholder = document.createElement('div');
    placeholder.className = 'drag-placeholder';
    placeholder.style.height = rect.height + 'px';
    list.insertBefore(placeholder, card);

    ghost = card;
    ghost.classList.add('dragging');
    ghost.style.position = 'fixed';
    ghost.style.width = rect.width + 'px';
    ghost.style.left = rect.left + 'px';
    ghost.style.top = (e.clientY - offsetY) + 'px';
    ghost.style.zIndex = '500';
    ghost.style.margin = '0';
    ghost.style.pointerEvents = 'none';

    window.addEventListener('pointermove', onMove, { passive: false });
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
  });
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
    await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/complete', { method: 'POST' });
    showToast('Done ✓'); loadPlan();
  } catch (e) { showToast('Failed to update', true); }
}

async function skipItem(itemId) {
  try {
    await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/skip', { method: 'POST' });
    showToast('Skipped'); loadPlan();
  } catch (e) { showToast('Failed to update', true); }
}

async function resetItem(itemId) {
  try {
    await apiFetch(API_BASE + '/api/runsheet/item/' + itemId + '/reset', { method: 'POST' });
    showToast('Reopened'); loadPlan();
  } catch (e) { showToast('Failed to update', true); }
}

// ---- Food Choice Modal ----

function openFoodModal(item) {
  currentModalItem = item; modalSelected = new Set();
  document.getElementById('foodModalTitle').textContent = item.label;
  const ct = item.food_choice.choice_type;
  const isMulti = item.food_choice.options && item.food_choice.options.multi_select;
  const names = {
    oatmeal_fruit: 'Pick a fruit for your oatmeal',
    veggie_bowl_veg: 'Pick vegetables for your bowl',
    snack_veg: 'Pick your veggies for ranch plate',
    snack_fruit: 'Pick a snack fruit',
    preworkout_fruit: 'Pick a pre-workout fruit'
  };
  document.getElementById('foodModalSubtitle').textContent =
    (names[ct] || 'What are you having?') + (isMulti ? ' (tap all that apply)' : '');
  const confirmBtn = document.getElementById('foodModalConfirm');
  confirmBtn.classList.toggle('hidden', !isMulti); confirmBtn.disabled = true;
  loadFoodOptions(item, ct, document.getElementById('foodChoiceGrid'), isMulti);
  document.getElementById('foodModal').classList.add('open');
}

async function loadFoodOptions(item, ct, grid, isMulti) {
  grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Loading...</div>';
  const catMap = { oatmeal_fruit:'fruit', snack_fruit:'fruit', preworkout_fruit:'fruit', veggie_bowl_veg:'vegetable', snack_veg:'vegetable' };
  const category = catMap[ct] || 'fruit';
  try {
    const resp = await apiFetch(API_BASE + '/api/pantry?category=' + category + '&stocked_only=true');
    const its = await resp.json();
    if (!its.length) {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">No ' +
        category + 's stocked — open the pantry and mark what you have</div>';
      return;
    }
    grid.innerHTML = '';
    its.forEach(pi => {
      const btn = document.createElement('button');
      btn.className = 'choice-btn'; btn.textContent = pi.name;
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
  closeFoodModal();
  try {
    await apiFetch(API_BASE + '/api/runsheet/food-choice', { method: 'POST', body: JSON.stringify({ plan_item_id: item.id, choice_type: ct, selected }) });
    await apiFetch(API_BASE + '/api/runsheet/item/' + item.id + '/complete', { method: 'POST' });
    showToast(selected + ' — done ✓'); loadPlan();
  } catch (e) { showToast('Failed to save', true); }
}

async function confirmMultiSelect() {
  if (!modalSelected.size || !currentModalItem) return;
  const sel = [...modalSelected].join(', '); closeFoodModal();
  try {
    await apiFetch(API_BASE + '/api/runsheet/food-choice', { method: 'POST', body: JSON.stringify({ plan_item_id: currentModalItem.id, choice_type: currentModalItem.food_choice.choice_type, selected: sel }) });
    await apiFetch(API_BASE + '/api/runsheet/item/' + currentModalItem.id + '/complete', { method: 'POST' });
    showToast([...modalSelected].join(' + ') + ' — done ✓'); loadPlan();
  } catch (e) { showToast('Failed to save', true); }
}

function closeFoodModal() { document.getElementById('foodModal').classList.remove('open'); }

// ---- Check-in Modal ----

let checkinValues = { energy: null, mood: null };

function buildScales() {
  [['energyScale', ['😴','😐','🙂','😊','⚡'], 'energy'],
   ['moodScale',   ['😞','😕','😐','🙂','😄'], 'mood']
  ].forEach(([rowId, emojis, key]) => {
    const row = document.getElementById(rowId);
    [1,2,3,4,5].forEach(n => {
      const btn = document.createElement('button');
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
  document.getElementById('checkinModal').classList.add('open');
}

function closeCheckinModal() { document.getElementById('checkinModal').classList.remove('open'); }

async function submitCheckin() {
  closeCheckinModal();
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
  setTimeout(() => t.className = 'toast', 2000);
}

document.addEventListener('DOMContentLoaded', init);
