/* ============================================
   Daily Runsheet — App Logic
   ============================================ */

const API_BASE = window.location.origin;
let TOKEN = localStorage.getItem('runsheet_token');
let plan = null;
let longPressTimer = null;
const LONG_PRESS_MS = 500;
let modalSelected = new Set();
let currentModalItem = null;

// ---- Category icons ----
const CATEGORY_ICONS = {
  gym: '💪',
  walk: '🚶',
  meal: '🍽️',
  prep: '🔪',
  cleaning: '🧹',
  nsdr: '😌',
  'brain-building': '🧠',
  custom: '📌',
  coffee: '☕',
  shopping: '🛒',
  shower: '🚿',
  laundry: '👕'
};

// ---- Init ----
function init() {
  if (TOKEN) {
    showApp();
    loadPlan();
  } else {
    showLogin();
  }

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }

  // Auto-refresh on visibility change
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && TOKEN) loadPlan();
  });

  // Login form
  document.getElementById('loginBtn').addEventListener('click', doLogin);
  document.getElementById('tokenInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });

  // Add item
  document.getElementById('addBtn').addEventListener('click', toggleAddBar);
  document.getElementById('addItemSubmit').addEventListener('click', addItem);
  document.getElementById('addItemInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') addItem();
  });

  // Food modal close
  document.getElementById('foodModalClose').addEventListener('click', closeFoodModal);
  document.getElementById('foodModalConfirm').addEventListener('click', confirmMultiSelect);
  document.getElementById('foodModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeFoodModal();
  });

  // Check-in modal
  document.getElementById('checkinModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeCheckinModal();
  });
  buildScales();
}

// ---- Auth ----
function showLogin() {
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
}

function showApp() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
}

async function doLogin() {
  const token = document.getElementById('tokenInput').value.trim();
  const errEl = document.getElementById('loginError');
  if (!token) { errEl.textContent = 'Please enter a token'; return; }

  try {
    const resp = await fetch(`${API_BASE}/api/runsheet/today`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (resp.ok) {
      TOKEN = token;
      localStorage.setItem('runsheet_token', token);
      errEl.textContent = '';
      showApp();
      plan = await resp.json();
      renderPlan();
    } else {
      errEl.textContent = 'Invalid token';
    }
  } catch (e) {
    errEl.textContent = 'Connection failed';
  }
}

function headers() {
  return {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json'
  };
}

// ---- Load Plan ----
async function loadPlan() {
  try {
    const resp = await fetch(`${API_BASE}/api/runsheet/today`, { headers: headers() });
    if (resp.status === 401) {
      localStorage.removeItem('runsheet_token');
      TOKEN = null;
      showLogin();
      return;
    }
    plan = await resp.json();
    renderPlan();
  } catch (e) {
    document.getElementById('itemList').innerHTML =
      '<div class="loading">Could not load plan</div>';
  }
}

// ---- Render ----
function renderPlan() {
  if (!plan) return;

  // Day label
  const dayLabel = document.getElementById('dayLabel');
  const d = new Date(plan.date + 'T12:00:00');
  const dayNames = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  dayLabel.textContent = `${dayNames[d.getDay()]} — ${plan.day_type || ''}`;

  const items = plan.items || [];
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;

  // Progress
  const pct = total ? Math.round((done / total) * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = `${done} / ${total}`;

  // Find first pending item (the "current" one)
  const currentIdx = items.findIndex(i => i.status === 'pending');

  // Build insert position options
  buildInsertOptions(items);

  // Render items
  const list = document.getElementById('itemList');
  list.innerHTML = '';

  items.forEach((item, idx) => {
    const card = document.createElement('div');
    card.className = 'item-card';
    if (item.status === 'done') card.classList.add('done');
    else if (item.status === 'skipped') card.classList.add('skipped');
    else if (idx === currentIdx) card.classList.add('current');

    const icon = CATEGORY_ICONS[item.category] || '📋';
    const statusIcon = item.status === 'done' ? '✓'
      : item.status === 'skipped' ? '—'
      : '';

    let metaHtml = '';
    if (item.food_choice && item.food_choice.selected) {
      metaHtml = `<div class="item-meta">→ ${item.food_choice.selected}</div>`;
    }

    // Prep block: show dinner info
    let prepHtml = '';
    if (item.category === 'prep' && item.label) {
      // Extract dinner info from label — the backend embeds it
      const dinnerMatch = item.label.match(/(?:dinner|prep)[:\s]*(.+)/i);
      if (dinnerMatch) {
        prepHtml = `<div class="prep-details"><strong>${dinnerMatch[1]}</strong></div>`;
      }
    }

    card.innerHTML = `
      <div class="item-icon">${icon}</div>
      <div class="item-content">
        <div class="item-label">${item.label}</div>
        ${metaHtml}
        ${prepHtml}
      </div>
      <div class="item-status-icon">${statusIcon}</div>
    `;

    // Tap to complete (with food choice handling)
    if (item.status === 'pending') {
      let pressStart = 0;
      let pressTimeout = null;
      let didLongPress = false;

      card.addEventListener('pointerdown', e => {
        pressStart = Date.now();
        didLongPress = false;
        pressTimeout = setTimeout(() => {
          didLongPress = true;
          skipItem(item.id);
          card.style.transform = 'scale(0.97)';
          setTimeout(() => card.style.transform = '', 150);
        }, LONG_PRESS_MS);
      });

      card.addEventListener('pointerup', e => {
        clearTimeout(pressTimeout);
        if (didLongPress) return;
        if (Date.now() - pressStart < LONG_PRESS_MS) {
          handleItemTap(item);
        }
      });

      card.addEventListener('pointerleave', () => {
        clearTimeout(pressTimeout);
      });
    }

    list.appendChild(card);
  });

  // Auto-scroll to current item
  if (currentIdx >= 0) {
    setTimeout(() => {
      const cards = list.querySelectorAll('.item-card');
      if (cards[currentIdx]) {
        cards[currentIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  }
}

// ---- Item Actions ----
function handleItemTap(item) {
  // If it's a meal item with a food_choice_type, show choice modal
  if (item.category === 'meal' && item.food_choice && !item.food_choice.selected) {
    openFoodModal(item);
    return;
  }

  // Otherwise just complete it
  completeItem(item.id);

  // If it's a gym item, show check-in after completion
  if (item.category === 'gym') {
    setTimeout(() => openCheckinModal(), 600);
  }
}

async function completeItem(itemId) {
  try {
    await fetch(`${API_BASE}/api/runsheet/item/${itemId}/complete`, {
      method: 'POST',
      headers: headers()
    });
    showToast('Done ✓');
    loadPlan();
  } catch (e) {
    showToast('Failed to update', true);
  }
}

async function skipItem(itemId) {
  try {
    await fetch(`${API_BASE}/api/runsheet/item/${itemId}/skip`, {
      method: 'POST',
      headers: headers()
    });
    showToast('Skipped');
    loadPlan();
  } catch (e) {
    showToast('Failed to update', true);
  }
}

// ---- Food Choice Modal ----
function openFoodModal(item) {
  const modal = document.getElementById('foodModal');
  const title = document.getElementById('foodModalTitle');
  const subtitle = document.getElementById('foodModalSubtitle');
  const grid = document.getElementById('foodChoiceGrid');
  const confirmBtn = document.getElementById('foodModalConfirm');

  currentModalItem = item;
  modalSelected = new Set();

  title.textContent = item.label;

  const choiceType = item.food_choice.choice_type;
  const isMulti = item.food_choice.options && item.food_choice.options.multi_select;

  const friendlyNames = {
    oatmeal_fruit: 'Pick a fruit for your oatmeal',
    veggie_bowl_veg: 'Pick vegetables for your bowl',
    snack_veg: 'Pick your veggies for ranch plate',
    snack_fruit: 'Pick a snack fruit',
    preworkout_fruit: 'Pick a pre-workout fruit'
  };
  subtitle.textContent = friendlyNames[choiceType] || 'What are you having?';
  if (isMulti) subtitle.textContent += ' (tap all that apply)';

  // Show/hide confirm button
  confirmBtn.classList.toggle('hidden', !isMulti);
  confirmBtn.disabled = true;

  // Load stocked pantry items for this choice type
  loadFoodOptions(item, choiceType, grid, isMulti);
  modal.classList.add('open');
}

async function loadFoodOptions(item, choiceType, grid, isMulti) {
  grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Loading...</div>';

  const catMap = {
    oatmeal_fruit: 'fruit',
    snack_fruit: 'fruit',
    preworkout_fruit: 'fruit',
    veggie_bowl_veg: 'vegetable',
    snack_veg: 'vegetable'
  };
  const pantryCategory = catMap[choiceType] || 'fruit';

  try {
    const resp = await fetch(
      `${API_BASE}/api/pantry?category=${pantryCategory}&stocked_only=true`,
      { headers: headers() }
    );
    const items = await resp.json();

    if (!items.length) {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Nothing stocked — update your pantry first</div>';
      return;
    }

    grid.innerHTML = '';
    items.forEach(pantryItem => {
      const btn = document.createElement('button');
      btn.className = 'choice-btn';
      btn.textContent = pantryItem.name;

      if (isMulti) {
        btn.addEventListener('click', () => {
          if (modalSelected.has(pantryItem.name)) {
            modalSelected.delete(pantryItem.name);
            btn.classList.remove('selected');
          } else {
            modalSelected.add(pantryItem.name);
            btn.classList.add('selected');
          }
          document.getElementById('foodModalConfirm').disabled = modalSelected.size === 0;
        });
      } else {
        btn.addEventListener('click', () => selectFoodChoice(item, choiceType, pantryItem.name));
      }

      grid.appendChild(btn);
    });
  } catch (e) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-dim);padding:20px">Could not load options</div>';
  }
}

async function selectFoodChoice(item, choiceType, selected) {
  closeFoodModal();
  try {
    await fetch(`${API_BASE}/api/runsheet/food-choice`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        plan_item_id: item.id,
        choice_type: choiceType,
        selected: selected
      })
    });
    // Also mark the item as done
    await fetch(`${API_BASE}/api/runsheet/item/${item.id}/complete`, {
      method: 'POST',
      headers: headers()
    });
    showToast(`${selected} — done ✓`);
    loadPlan();
  } catch (e) {
    showToast('Failed to save', true);
  }
}

async function confirmMultiSelect() {
  if (modalSelected.size === 0 || !currentModalItem) return;
  const selected = [...modalSelected].join(', ');
  closeFoodModal();
  try {
    await fetch(`${API_BASE}/api/runsheet/food-choice`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        plan_item_id: currentModalItem.id,
        choice_type: currentModalItem.food_choice.choice_type,
        selected: selected
      })
    });
    await fetch(`${API_BASE}/api/runsheet/item/${currentModalItem.id}/complete`, {
      method: 'POST',
      headers: headers()
    });
    showToast(`${[...modalSelected].join(' + ')} — done ✓`);
    loadPlan();
  } catch (e) {
    showToast('Failed to save', true);
  }
}

function closeFoodModal() {
  document.getElementById('foodModal').classList.remove('open');
}

// ---- Check-in Modal ----
let checkinValues = { energy: null, mood: null };

function buildScales() {
  const energyRow = document.getElementById('energyScale');
  const moodRow = document.getElementById('moodScale');
  const emojisEnergy = ['😴', '😐', '🙂', '😊', '⚡'];
  const emojisMood = ['😞', '😕', '😐', '🙂', '😄'];

  [1,2,3,4,5].forEach(n => {
    const eBtn = document.createElement('button');
    eBtn.className = 'scale-btn';
    eBtn.textContent = emojisEnergy[n-1];
    eBtn.dataset.value = n;
    eBtn.addEventListener('click', () => {
      checkinValues.energy = n;
      energyRow.querySelectorAll('.scale-btn').forEach(b => b.classList.remove('selected'));
      eBtn.classList.add('selected');
      updateCheckinSubmit();
    });
    energyRow.appendChild(eBtn);

    const mBtn = document.createElement('button');
    mBtn.className = 'scale-btn';
    mBtn.textContent = emojisMood[n-1];
    mBtn.dataset.value = n;
    mBtn.addEventListener('click', () => {
      checkinValues.mood = n;
      moodRow.querySelectorAll('.scale-btn').forEach(b => b.classList.remove('selected'));
      mBtn.classList.add('selected');
      updateCheckinSubmit();
    });
    moodRow.appendChild(mBtn);
  });

  document.getElementById('checkinSubmit').addEventListener('click', submitCheckin);
}

function updateCheckinSubmit() {
  document.getElementById('checkinSubmit').disabled =
    !(checkinValues.energy && checkinValues.mood);
}

function openCheckinModal() {
  checkinValues = { energy: null, mood: null };
  document.querySelectorAll('#energyScale .scale-btn, #moodScale .scale-btn')
    .forEach(b => b.classList.remove('selected'));
  document.getElementById('checkinSubmit').disabled = true;
  document.getElementById('checkinModal').classList.add('open');
}

function closeCheckinModal() {
  document.getElementById('checkinModal').classList.remove('open');
}

async function submitCheckin() {
  closeCheckinModal();
  try {
    await fetch(`${API_BASE}/api/checkin`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        energy: checkinValues.energy,
        mood: checkinValues.mood
      })
    });
    showToast('Check-in saved');
  } catch (e) {
    showToast('Check-in failed', true);
  }
}

// ---- Add Item ----
function toggleAddBar() {
  const bar = document.getElementById('addItemBar');
  const picker = document.getElementById('insertPicker');
  const isHidden = bar.classList.contains('hidden');
  bar.classList.toggle('hidden');
  picker.classList.toggle('visible', isHidden);
  if (isHidden) {
    document.getElementById('addItemInput').focus();
  }
}

function buildInsertOptions(items) {
  const sel = document.getElementById('insertPosition');
  sel.innerHTML = '<option value="end">At the end</option>';
  items.forEach(item => {
    if (item.status === 'pending') {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = `Before: ${item.label}`;
      sel.appendChild(opt);
    }
  });
}

async function addItem() {
  const input = document.getElementById('addItemInput');
  const label = input.value.trim();
  if (!label) return;

  const position = document.getElementById('insertPosition').value;

  try {
    const edits = [{ action: 'add', label: label, category: 'custom' }];

    await fetch(`${API_BASE}/api/runsheet/edit`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(edits)
    });

    input.value = '';
    toggleAddBar();
    showToast('Item added');
    loadPlan();
  } catch (e) {
    showToast('Failed to add', true);
  }
}

// ---- Toast ----
function showToast(msg, warn) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (warn ? ' warn' : '');
  setTimeout(() => t.className = 'toast', 2000);
}

// ---- Start ----
document.addEventListener('DOMContentLoaded', init);