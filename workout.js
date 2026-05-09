'use strict';

// ══════════════════════════════════════════════════════════ CONSTANTS ══

const ARNOLD_QUOTES = [
  "The last three or four reps is what makes the muscle grow. This area of pain divides a champion from someone who is not a champion.",
  "Strength does not come from winning. Your struggles develop your strengths.",
  "The mind is the limit. As long as the mind can envision the fact that you can do something, you can do it.",
  "You can have results or excuses. Not both.",
  "For me, life is continuously being hungry. The meaning of life is not simply to exist, to survive, but to move ahead.",
  "The worst thing I can be is the same as everybody else. I hate that.",
  "I do the same exercises I did 50 years ago and they still work.",
  "If you want to turn a vision into reality, you have to give 100% and never stop believing in your dream.",
  "Just remember, you can't climb the ladder of success with your hands in your pockets.",
  "The better you get at a skill, the more you will enjoy it and want to practice it.",
  "Bodybuilding is much like any other sport. To be successful, you must dedicate yourself 100% to your training, diet and mental approach.",
  "What we face may look insurmountable. But I learned something from all those years of training. We are always stronger than we know.",
  "Go the extra mile. It's never crowded.",
  "Pain makes me grow. Growing is what I want. Therefore, for me pain is pleasure.",
  "Nobody ever got muscles by watching other people lift.",
];

const WORKOUT_LABELS = {
  chest:          'CHEST DAY',
  back:           'BACK DAY',
  legs:           'LEG DAY',
  cardio_walking: 'CARDIO — WALK',
  cardio_bag:     'CARDIO — BAG',
};

// Full exercise database — Crunch Gym equipment
// isDefault:true = shown automatically; false = available via search
const EXERCISE_DB = {
  chest: [
    { name: "Barbell Bench Press",      sets: 4, reps: "8-10",   rest: 90,  equipment: "Barbell",      isDefault: true,  tip: "Drive through your chest, keep shoulder blades pinched" },
    { name: "Incline Dumbbell Press",   sets: 3, reps: "10-12",  rest: 75,  equipment: "Dumbbell",     isDefault: true,  tip: "Keep elbows at 45° from torso" },
    { name: "Cable Chest Fly",          sets: 3, reps: "12-15",  rest: 60,  equipment: "Cable",        isDefault: true,  tip: "Slight bend in elbows, squeeze at center" },
    { name: "Push-ups",                 sets: 3, reps: "max",    rest: 60,  equipment: "Bodyweight",   isDefault: true,  tip: "Full range of motion, chest to floor" },
    { name: "Decline Bench Press",      sets: 3, reps: "8-10",   rest: 90,  equipment: "Barbell",      isDefault: false },
    { name: "Pec Deck Machine",         sets: 3, reps: "12-15",  rest: 60,  equipment: "Machine",      isDefault: false, tip: "Control the negative, don't let it snap back" },
    { name: "Chest Press Machine",      sets: 3, reps: "10-12",  rest: 75,  equipment: "Machine",      isDefault: false },
    { name: "Dumbbell Flat Press",      sets: 3, reps: "10-12",  rest: 75,  equipment: "Dumbbell",     isDefault: false },
    { name: "Incline Cable Fly",        sets: 3, reps: "12-15",  rest: 60,  equipment: "Cable",        isDefault: false },
    { name: "Low Cable Chest Fly",      sets: 3, reps: "12-15",  rest: 60,  equipment: "Cable",        isDefault: false },
    { name: "Dumbbell Pullover",        sets: 3, reps: "12",     rest: 60,  equipment: "Dumbbell",     isDefault: false, tip: "Keep slight bend in elbows throughout" },
    { name: "Smith Machine Bench",      sets: 3, reps: "10-12",  rest: 75,  equipment: "Smith Machine",isDefault: false },
    { name: "Incline Barbell Press",    sets: 3, reps: "8-10",   rest: 90,  equipment: "Barbell",      isDefault: false },
    { name: "Close-Grip Push-ups",      sets: 3, reps: "max",    rest: 60,  equipment: "Bodyweight",   isDefault: false },
    { name: "Hammer Strength Chest Press", sets: 3, reps: "10-12", rest: 75, equipment: "Machine",    isDefault: false },
  ],
  back: [
    { name: "Lat Pulldown",             sets: 4, reps: "8-10",   rest: 90,  equipment: "Cable Machine",isDefault: true,  tip: "Pull to upper chest, squeeze lats at bottom" },
    { name: "Barbell Rows",             sets: 4, reps: "8-10",   rest: 90,  equipment: "Barbell",      isDefault: true,  tip: "Hinge at hips, pull bar to lower chest" },
    { name: "Seated Cable Rows",        sets: 3, reps: "12",     rest: 75,  equipment: "Cable Machine",isDefault: true,  tip: "Sit tall, pull elbows past your back" },
    { name: "Face Pulls",               sets: 3, reps: "15",     rest: 60,  equipment: "Cable",        isDefault: true,  tip: "Pull to eye level, externally rotate at end" },
    { name: "Pull-ups",                 sets: 3, reps: "max",    rest: 90,  equipment: "Bodyweight",   isDefault: false },
    { name: "Assisted Pull-ups",        sets: 3, reps: "8-10",   rest: 90,  equipment: "Machine",      isDefault: false },
    { name: "T-Bar Rows",               sets: 3, reps: "10-12",  rest: 90,  equipment: "T-Bar",        isDefault: false },
    { name: "Single-Arm DB Row",        sets: 3, reps: "10-12",  rest: 75,  equipment: "Dumbbell",     isDefault: false, tip: "Plant knee on bench, keep back flat" },
    { name: "Straight-Arm Pulldown",    sets: 3, reps: "12-15",  rest: 60,  equipment: "Cable",        isDefault: false },
    { name: "Wide-Grip Seated Row",     sets: 3, reps: "12",     rest: 75,  equipment: "Cable Machine",isDefault: false },
    { name: "Deadlift",                 sets: 3, reps: "6-8",    rest: 120, equipment: "Barbell",      isDefault: false, tip: "Neutral spine, push the floor away" },
    { name: "Hyperextensions",          sets: 3, reps: "12-15",  rest: 60,  equipment: "Machine",      isDefault: false },
    { name: "Reverse Fly Machine",      sets: 3, reps: "12-15",  rest: 60,  equipment: "Machine",      isDefault: false },
    { name: "Hammer Strength Row",      sets: 3, reps: "10-12",  rest: 75,  equipment: "Machine",      isDefault: false },
    { name: "Close-Grip Pulldown",      sets: 3, reps: "10-12",  rest: 75,  equipment: "Cable Machine",isDefault: false },
    { name: "Chest-Supported DB Row",   sets: 3, reps: "12",     rest: 75,  equipment: "Dumbbell",     isDefault: false },
  ],
  legs: [
    { name: "Barbell Squat",            sets: 4, reps: "8-10",   rest: 120, equipment: "Barbell",      isDefault: true,  tip: "Chest up, knees track over toes, break parallel" },
    { name: "Leg Press",                sets: 3, reps: "12-15",  rest: 90,  equipment: "Machine",      isDefault: true,  tip: "Full range, don't lock knees at top" },
    { name: "Romanian Deadlift",        sets: 3, reps: "10",     rest: 90,  equipment: "Barbell",      isDefault: true,  tip: "Push hips back, feel the hamstring stretch" },
    { name: "Leg Curls",                sets: 3, reps: "12",     rest: 60,  equipment: "Machine",      isDefault: true,  tip: "Slow and controlled on the way down" },
    { name: "Calf Raises",              sets: 4, reps: "20",     rest: 45,  equipment: "Machine",      isDefault: true,  tip: "Full range — all the way up and all the way down" },
    { name: "Hack Squat",               sets: 3, reps: "10-12",  rest: 90,  equipment: "Machine",      isDefault: false },
    { name: "Bulgarian Split Squat",    sets: 3, reps: "10 each",rest: 90,  equipment: "Dumbbell",     isDefault: false, tip: "Keep front knee over toe, drive through heel" },
    { name: "Walking Lunges",           sets: 3, reps: "12 each",rest: 75,  equipment: "Dumbbell",     isDefault: false },
    { name: "Leg Extensions",           sets: 3, reps: "12-15",  rest: 60,  equipment: "Machine",      isDefault: false },
    { name: "Smith Machine Squat",      sets: 3, reps: "10-12",  rest: 90,  equipment: "Smith Machine",isDefault: false },
    { name: "Seated Calf Raises",       sets: 4, reps: "15-20",  rest: 45,  equipment: "Machine",      isDefault: false },
    { name: "Hip Abductor Machine",     sets: 3, reps: "15",     rest: 45,  equipment: "Machine",      isDefault: false },
    { name: "Hip Adductor Machine",     sets: 3, reps: "15",     rest: 45,  equipment: "Machine",      isDefault: false },
    { name: "Sumo Deadlift",            sets: 3, reps: "8-10",   rest: 90,  equipment: "Barbell",      isDefault: false },
    { name: "Glute Kickbacks",          sets: 3, reps: "15 each",rest: 45,  equipment: "Cable",        isDefault: false },
    { name: "Step-ups",                 sets: 3, reps: "12 each",rest: 60,  equipment: "Dumbbell",     isDefault: false },
    { name: "Goblet Squat",             sets: 3, reps: "12-15",  rest: 75,  equipment: "Dumbbell",     isDefault: false },
    { name: "Lying Leg Curls",          sets: 3, reps: "12",     rest: 60,  equipment: "Machine",      isDefault: false },
  ],
  cardio_walking: [
    { name: "Warm-up Walk",  type: "timed", duration: 300,  isDefault: true },
    { name: "Brisk Walk",    type: "timed", duration: 1500, isDefault: true },
    { name: "Cool-down Walk",type: "timed", duration: 300,  isDefault: true },
  ],
  cardio_bag: [
    { name: "Warm-up",          type: "timed",  duration: 120, isDefault: true },
    { name: "Rounds",           type: "rounds", work: 180, rest: 60, total_rounds: 6, isDefault: true },
    { name: "Cool-down Stretch",type: "timed",  duration: 300, isDefault: true },
  ],
};

const RING_CIRCUMFERENCE = 326.7; // 2π × 52

// ══════════════════════════════════════════════════════════════ STATE ══

const STATE = {
  screen: 'home',
  exercises: {},
  workoutType: null,
  workoutExercises: [],
  exerciseIndex: 0,
  currentSets: [],
  session: null,
  restTimerHandle: null,
  restSecondsLeft: 0,
  restTotalSeconds: 0,
  cardioTimerHandle: null,
  cardioSecondsLeft: 0,
  cardioPhase: 'work',
  cardioRound: 1,
  cardioPaused: true,
  calendarMonth: new Date(),
  foodDate: '',
  workoutLogs: [],
  selectedFood: null,
  foodSearchTimeout: null,
};

// ══════════════════════════════════════════════════════════ UTILITIES ══

const $ = id => document.getElementById(id);

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function fmtTime(secs) {
  const m = Math.floor(secs / 60);
  const s = String(secs % 60).padStart(2, '0');
  return `${m}:${s}`;
}

function fmtDuration(mins) {
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function randQuote() {
  return ARNOLD_QUOTES[Math.floor(Math.random() * ARNOLD_QUOTES.length)];
}

function typeClass(type) {
  if (type === 'chest') return 'chest';
  if (type === 'back')  return 'back';
  if (type === 'legs')  return 'legs';
  return 'cardio';
}

function fmtDateLabel(dateStr) {
  if (dateStr === todayStr()) return 'TODAY';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

function stopAllTimers() {
  clearInterval(STATE.restTimerHandle);
  clearInterval(STATE.cardioTimerHandle);
  STATE.restTimerHandle = null;
  STATE.cardioTimerHandle = null;
}

// ══════════════════════════════════════════════════════════════ API ══

async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`);
  return r.json();
}

async function apiDelete(path) {
  const r = await fetch(path, { method: 'DELETE' });
  if (!r.ok) throw new Error(`DELETE ${path} → ${r.status}`);
  return r.json();
}

async function loadExercises() {
  STATE.exercises = EXERCISE_DB;
}

async function loadWorkoutLogs() {
  try {
    STATE.workoutLogs = await apiGet('/api/workout/logs');
  } catch (e) {
    STATE.workoutLogs = [];
  }
}

async function saveWorkoutLog(session) {
  try {
    await apiPost('/api/workout/logs', session);
    await loadWorkoutLogs();
  } catch (e) {
    console.warn('Could not save workout log', e);
  }
}

async function loadFoodLog(date) {
  try {
    return await apiGet(`/api/food/logs?date=${date}`);
  } catch (e) {
    return [];
  }
}

async function saveFoodEntry(entry) {
  return apiPost('/api/food/logs', entry);
}

async function deleteFoodEntry(id, date) {
  return apiDelete(`/api/food/logs/${id}?date=${date}`);
}

async function searchFood(q) {
  const url = `https://world.openfoodfacts.org/cgi/search.pl?search_terms=${encodeURIComponent(q)}&json=1&page_size=10&fields=product_name,nutriments`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('Food API error');
  const data = await r.json();
  return (data.products || [])
    .filter(p => p.product_name && p.product_name.trim())
    .map(p => {
      const n = p.nutriments || {};
      let kcal = n['energy-kcal_100g'] || n['energy-kcal'] || 0;
      if (!kcal && n['energy_100g']) kcal = Math.round(n['energy_100g'] / 4.184);
      return {
        name: p.product_name.trim(),
        kcal_per_100g:     Math.round(parseFloat(kcal) || 0),
        protein_per_100g:  Math.round((parseFloat(n['proteins_100g'])       || 0) * 10) / 10,
        carbs_per_100g:    Math.round((parseFloat(n['carbohydrates_100g'])  || 0) * 10) / 10,
        fat_per_100g:      Math.round((parseFloat(n['fat_100g'])            || 0) * 10) / 10,
      };
    });
}

// ══════════════════════════════════════════════════════ SCREEN ROUTING ══

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = $(`screen-${name}`);
  if (target) target.classList.add('active');
  STATE.screen = name;

  // Update bottom nav highlight
  ['home', 'calendar', 'food'].forEach(n => {
    const btn = $(`nav-${n}`);
    if (btn) btn.classList.toggle('active', n === name);
  });

  if (name === 'home')            renderHome();
  if (name === 'select')          renderSelect();
  if (name === 'exercise-select') renderExerciseSelect();
  if (name === 'calendar')        renderCalendar();
  if (name === 'food')            renderFood();
  if (name === 'schedule')        renderSchedule();
}

function navTo(name) {
  // Don't interrupt an active workout
  if (STATE.screen === 'workout') return;
  showScreen(name);
}

// ══════════════════════════════════════════════════════════ HOME SCREEN ══

function renderHome() {
  // Date
  const now = new Date();
  $('home-date').textContent = now.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric'
  }).toUpperCase();

  // Arnold quote
  $('home-quote-text').textContent = randQuote();

  // Today's scheduled workout banner
  renderTodayBanner();

  // Stats
  loadTodayStats();
}

async function loadTodayStats() {
  const today = todayStr();

  // Today's calories
  try {
    const entries = await loadFoodLog(today);
    const cal = entries.reduce((s, e) => s + (e.calories || 0), 0);
    $('home-calories').textContent = cal > 0 ? Math.round(cal).toLocaleString() : '—';
  } catch (_) {
    $('home-calories').textContent = '—';
  }

  // Last workout
  if (STATE.workoutLogs.length) {
    const last = STATE.workoutLogs[STATE.workoutLogs.length - 1];
    const label = WORKOUT_LABELS[last.type] || last.type.toUpperCase();
    const d = new Date(last.date + 'T00:00:00');
    const daysAgo = Math.floor((Date.now() - d.getTime()) / 86400000);
    const when = daysAgo === 0 ? 'TODAY' : daysAgo === 1 ? 'YESTERDAY' : `${daysAgo}D AGO`;
    $('home-last-workout').textContent = `${label.split(' ')[0]} · ${when}`;
  } else {
    $('home-last-workout').textContent = 'NONE YET';
  }
}

function onStartPress() {
  const btn = $('btn-start');
  btn.style.transform = 'scale(0.88)';
  btn.style.boxShadow = '0 0 0 4px rgba(255,179,0,.2), 0 0 80px rgba(255,179,0,.6)';
  setTimeout(() => {
    btn.style.transform = '';
    btn.style.boxShadow = '';
    showScreen('select');
  }, 300);
}

// ══════════════════════════════════════════════════ WORKOUT SELECT ══

function renderSelect() {
  $('select-quote').textContent = `"${randQuote()}"`;
}

// ══════════════════════════════════════════════════════ WORKOUT FLOW ══

function startWorkout(type) {
  STATE.workoutType = type;
  const all = EXERCISE_DB[type] || [];

  // Cardio — skip picker, go straight in
  if (all.every(e => e.type === 'timed' || e.type === 'rounds')) {
    launchWorkout(type, all.map(e => ({ ...e })));
    return;
  }

  // Seed with defaults only, all pre-selected
  STATE._pendingType = type;
  STATE._pendingExercises = all
    .filter(e => e.isDefault)
    .map(e => ({ ...e, _selected: true }));
  renderExerciseSelect();
  showScreen('exercise-select');
}

function renderExerciseSelect() {
  const type = STATE._pendingType;
  $('ex-select-title').textContent = WORKOUT_LABELS[type] || type.toUpperCase();
  renderExSelectList();
}

function renderExSelectList() {
  const exs = STATE._pendingExercises;
  const rows = exs.map((ex, i) => {
    const meta = `${ex.sets} sets × ${ex.reps} reps`;
    const eq   = ex.equipment ? `<span class="eq-tag">${ex.equipment}</span>` : '';
    return `<div class="ex-select-row${ex._selected ? ' selected' : ''}" id="ex-row-${i}" onclick="toggleExercise(${i})">
      <div class="ex-check">${ex._selected ? '✓' : ''}</div>
      <div class="ex-select-info">
        <div class="ex-select-name">${ex.name}</div>
        <div class="ex-select-meta">${meta} ${eq}</div>
      </div>
    </div>`;
  }).join('');

  const search = `
    <div class="add-exercise-search">
      <input type="text" id="ex-search-input" class="food-search-input"
             placeholder="&#128269; Search exercises to add..."
             oninput="onExSearchInput(this.value)" autocomplete="off">
      <div id="ex-search-results"></div>
    </div>`;

  $('ex-select-list').innerHTML = rows + search;
}

function onExSearchInput(val) {
  const results = $('ex-search-results');
  if (!val.trim()) { results.innerHTML = ''; return; }

  const type  = STATE._pendingType;
  const added = new Set(STATE._pendingExercises.map(e => e.name));
  const query = val.toLowerCase();

  window._exSearchResults = (EXERCISE_DB[type] || []).filter(e =>
    !added.has(e.name) && e.name.toLowerCase().includes(query)
  );

  if (!window._exSearchResults.length) {
    results.innerHTML = '<div class="searching-label">No exercises found.</div>';
    return;
  }

  results.innerHTML = window._exSearchResults.map((ex, i) => `
    <div class="food-result-item" onclick="addExerciseFromSearch(${i})">
      <div class="food-result-name">${ex.name}</div>
      <div class="food-result-kcal">${ex.sets}×${ex.reps} · ${ex.equipment || ''}</div>
    </div>
  `).join('');
}

function addExerciseFromSearch(i) {
  const ex = window._exSearchResults[i];
  STATE._pendingExercises.push({ ...ex, _selected: true });
  renderExSelectList();
  // Re-focus search
  const inp = $('ex-search-input');
  if (inp) { inp.value = ''; inp.focus(); }
}

function toggleExercise(i) {
  STATE._pendingExercises[i]._selected = !STATE._pendingExercises[i]._selected;
  const row = $(`ex-row-${i}`);
  row.classList.toggle('selected', STATE._pendingExercises[i]._selected);
}

function confirmExerciseSelection() {
  const selected = STATE._pendingExercises.filter(e => e._selected);
  if (!selected.length) { alert('Select at least one exercise.'); return; }
  launchWorkout(STATE._pendingType, selected);
}

function launchWorkout(type, exercises) {
  STATE.workoutType = type;
  STATE.workoutExercises = exercises;
  STATE.exerciseIndex = 0;
  STATE.currentSets = [];
  STATE.session = {
    date: todayStr(),
    type,
    started_at: new Date().toISOString(),
    completed_at: null,
    duration_mins: 0,
    exercises: [],
  };
  showScreen('workout');
  renderWorkout();
}

function renderWorkout() {
  const total = STATE.workoutExercises.length;
  const idx = STATE.exerciseIndex;
  const ex = STATE.workoutExercises[idx];

  if (!ex) { finishWorkout(); return; }

  // Header
  $('workout-type-label').textContent = WORKOUT_LABELS[STATE.workoutType] || '';
  $('workout-progress').textContent = `${idx + 1}/${total}`;
  $('workout-progress-bar').style.width = `${((idx) / total) * 100}%`;

  // Render correct exercise type
  const isCardioType = ex.type === 'timed' || ex.type === 'rounds';
  if (isCardioType) {
    renderCardioExercise(ex);
  } else {
    renderStrengthExercise(ex, idx);
  }
}

// ── Strength exercises ───────────────────────────────────────────────────────

function renderStrengthExercise(ex) {
  const sets = STATE.currentSets;
  const targetSets = ex.sets;
  const allDone = sets.length >= targetSets;
  const currentSetNum = sets.length + 1;
  const isLast = STATE.exerciseIndex >= STATE.workoutExercises.length - 1;

  $('workout-body').innerHTML = `
    <div class="exercise-card">
      <div class="exercise-name">${ex.name}</div>
      <div class="exercise-target">${ex.sets} SETS × ${ex.reps} REPS</div>
      ${ex.tip ? `<div class="exercise-tip">${ex.tip}</div>` : ''}

      ${!allDone ? `
        <div class="set-status">SET <span>${currentSetNum}</span> OF <span>${targetSets}</span></div>
        <div class="set-inputs">
          <div class="set-input-group">
            <div class="set-input-label">WEIGHT (lbs)</div>
            <input type="number" id="inp-weight" class="set-input" value="${getLastWeight()}" min="0" max="999" inputmode="decimal">
          </div>
          <div class="set-input-group">
            <div class="set-input-label">REPS</div>
            <input type="number" id="inp-reps" class="set-input" value="${getTargetReps(ex.reps)}" min="1" max="99" inputmode="numeric">
          </div>
        </div>
        <button class="btn-log-set" onclick="logSet()">LOG SET ${currentSetNum}</button>
      ` : ''}

      <div class="set-log-list" id="set-log-list">
        ${sets.map((s, i) => `
          <div class="set-log-row">
            <div class="set-log-num">SET ${i + 1}</div>
            <div class="set-log-detail">${s.weight > 0 ? s.weight + ' lbs' : 'BW'} × ${s.reps}</div>
            <div class="set-log-check">✓</div>
          </div>
        `).join('')}
      </div>

      ${allDone ? `
        <button class="btn-next-exercise" onclick="nextExercise()">
          ${isLast ? 'FINISH WORKOUT ✓' : 'NEXT EXERCISE →'}
        </button>
      ` : ''}
    </div>
  `;
}

function getLastWeight() {
  if (STATE.currentSets.length) {
    return STATE.currentSets[STATE.currentSets.length - 1].weight;
  }
  return 0;
}

function getTargetReps(repsStr) {
  // "8-10" → 10, "max" → 10, "12" → 12
  if (repsStr === 'max') return 10;
  const parts = String(repsStr).split('-');
  return parseInt(parts[parts.length - 1], 10) || 10;
}

function logSet() {
  const weight = parseFloat($('inp-weight').value) || 0;
  const reps   = parseInt($('inp-reps').value, 10) || 0;
  if (reps <= 0) return;

  STATE.currentSets.push({ reps, weight });

  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  const allDone = STATE.currentSets.length >= ex.sets;

  renderStrengthExercise(ex);

  if (!allDone) {
    startRestTimer(ex.rest || 90);
  }
}

function nextExercise() {
  // Save completed exercise to session
  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  STATE.session.exercises.push({
    name: ex.name,
    target_sets: ex.sets,
    target_reps: ex.reps,
    sets: [...STATE.currentSets],
  });

  STATE.exerciseIndex++;
  STATE.currentSets = [];

  if (STATE.exerciseIndex >= STATE.workoutExercises.length) {
    finishWorkout();
  } else {
    renderWorkout();
  }
}

async function finishWorkout() {
  stopAllTimers();
  hideRestOverlay();

  const now = new Date();
  const startedAt = new Date(STATE.session.started_at);
  const durationMins = Math.round((now - startedAt) / 60000);

  STATE.session.completed_at = now.toISOString();
  STATE.session.duration_mins = durationMins;

  await saveWorkoutLog(STATE.session);
  renderComplete(durationMins);
  showScreen('complete');
}

function renderComplete(durationMins) {
  const s = STATE.session;
  const totalSets = s.exercises.reduce((acc, e) => acc + (e.sets ? e.sets.length : 0), 0);

  $('complete-type').textContent = WORKOUT_LABELS[s.type] || s.type.toUpperCase();
  $('complete-duration').textContent = fmtDuration(durationMins);
  $('complete-exercises').textContent = s.exercises.length;
  $('complete-sets').textContent = totalSets;
  $('complete-quote').textContent = randQuote();

  // Update progress bar to 100%
  const pb = $('workout-progress-bar');
  if (pb) pb.style.width = '100%';
}

function confirmQuitWorkout() {
  if (confirm("Quit workout? Progress won't be saved.")) {
    stopAllTimers();
    hideRestOverlay();
    STATE.session = null;
    showScreen('home');
  }
}

// ── Rest timer ───────────────────────────────────────────────────────────────

function startRestTimer(seconds) {
  clearInterval(STATE.restTimerHandle);
  STATE.restSecondsLeft = seconds;
  STATE.restTotalSeconds = seconds;

  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  const nextSetNum = STATE.currentSets.length + 1;
  const allDone = STATE.currentSets.length >= (ex ? ex.sets : 0);

  $('rest-next-label').textContent = allDone
    ? 'All sets done — ready for next exercise'
    : `Up next: Set ${nextSetNum} of ${ex ? ex.sets : ''}`;

  updateRestDisplay();
  showRestOverlay();

  STATE.restTimerHandle = setInterval(tickRest, 1000);
}

function tickRest() {
  STATE.restSecondsLeft--;
  if (STATE.restSecondsLeft <= 0) {
    skipRest();
  } else {
    updateRestDisplay();
  }
}

function updateRestDisplay() {
  $('rest-time').textContent = fmtTime(STATE.restSecondsLeft);
  const elapsed = STATE.restTotalSeconds - STATE.restSecondsLeft;
  const offset = RING_CIRCUMFERENCE * (elapsed / STATE.restTotalSeconds);
  $('rest-ring-fg').setAttribute('stroke-dashoffset', offset.toFixed(2));
}

function skipRest() {
  clearInterval(STATE.restTimerHandle);
  STATE.restTimerHandle = null;
  hideRestOverlay();

  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  if (ex && !ex.type) {
    renderStrengthExercise(ex);
  }
}

function showRestOverlay() {
  $('rest-ring-fg').setAttribute('stroke-dashoffset', '0');
  $('rest-overlay').classList.add('visible');
}

function hideRestOverlay() {
  $('rest-overlay').classList.remove('visible');
}

// ── Cardio exercises ─────────────────────────────────────────────────────────

function renderCardioExercise(ex) {
  STATE.cardioPaused = true;
  clearInterval(STATE.cardioTimerHandle);

  if (ex.type === 'timed') {
    STATE.cardioSecondsLeft = ex.duration;
    renderTimedCard(ex);
  } else if (ex.type === 'rounds') {
    STATE.cardioRound = 1;
    STATE.cardioPhase = 'work';
    STATE.cardioSecondsLeft = ex.work;
    renderRoundsCard(ex);
  }
}

function renderTimedCard(ex) {
  const isLast = STATE.exerciseIndex >= STATE.workoutExercises.length - 1;
  $('workout-body').innerHTML = `
    <div class="exercise-card cardio-card">
      <div class="cardio-phase-label">TIMED EXERCISE</div>
      <div class="cardio-exercise-name">${ex.name}</div>
      <div class="cardio-timer-display" id="cardio-timer">${fmtTime(STATE.cardioSecondsLeft)}</div>
      <div class="cardio-controls">
        <button class="btn-cardio-start" id="btn-cardio-playpause" onclick="toggleCardioTimer('timed')">START</button>
        <button class="btn-cardio-skip" onclick="skipCardioExercise()">SKIP →</button>
      </div>
    </div>
  `;
}

function renderRoundsCard(ex) {
  const isWork = STATE.cardioPhase === 'work';
  $('workout-body').innerHTML = `
    <div class="exercise-card cardio-card">
      <div class="cardio-exercise-name">${ex.name}</div>
      <div class="rounds-indicator">ROUND ${STATE.cardioRound} OF ${ex.total_rounds}</div>
      <div class="cardio-phase-badge ${STATE.cardioPhase}">${isWork ? 'WORK' : 'REST'}</div>
      <div class="cardio-timer-display" id="cardio-timer">${fmtTime(STATE.cardioSecondsLeft)}</div>
      <div class="cardio-controls">
        <button class="btn-cardio-start" id="btn-cardio-playpause" onclick="toggleCardioTimer('rounds')">START</button>
        <button class="btn-cardio-skip" onclick="skipCardioExercise()">SKIP →</button>
      </div>
    </div>
  `;
}

function toggleCardioTimer(mode) {
  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  if (STATE.cardioPaused) {
    STATE.cardioPaused = false;
    $('btn-cardio-playpause').textContent = 'PAUSE';
    STATE.cardioTimerHandle = setInterval(() => tickCardio(ex, mode), 1000);
  } else {
    STATE.cardioPaused = true;
    clearInterval(STATE.cardioTimerHandle);
    $('btn-cardio-playpause').textContent = 'RESUME';
  }
}

function tickCardio(ex, mode) {
  STATE.cardioSecondsLeft--;
  const timerEl = $('cardio-timer');
  if (timerEl) timerEl.textContent = fmtTime(STATE.cardioSecondsLeft);

  if (STATE.cardioSecondsLeft > 0) return;

  // Phase ended
  clearInterval(STATE.cardioTimerHandle);
  STATE.cardioPaused = true;

  if (mode === 'timed') {
    // Timed exercise done
    STATE.session.exercises.push({ name: ex.name, type: 'timed', duration: ex.duration });
    STATE.exerciseIndex++;
    STATE.currentSets = [];
    if (STATE.exerciseIndex >= STATE.workoutExercises.length) {
      finishWorkout();
    } else {
      renderWorkout();
    }
  } else if (mode === 'rounds') {
    if (STATE.cardioPhase === 'work') {
      // Switch to rest
      STATE.cardioPhase = 'rest';
      STATE.cardioSecondsLeft = ex.rest;
      renderRoundsCard(ex);
    } else {
      // Rest done — next round or finish
      if (STATE.cardioRound < ex.total_rounds) {
        STATE.cardioRound++;
        STATE.cardioPhase = 'work';
        STATE.cardioSecondsLeft = ex.work;
        renderRoundsCard(ex);
      } else {
        // All rounds done
        STATE.session.exercises.push({ name: ex.name, type: 'rounds', rounds: ex.total_rounds });
        STATE.exerciseIndex++;
        STATE.currentSets = [];
        if (STATE.exerciseIndex >= STATE.workoutExercises.length) {
          finishWorkout();
        } else {
          renderWorkout();
        }
      }
    }
  }
}

function skipCardioExercise() {
  clearInterval(STATE.cardioTimerHandle);
  STATE.cardioPaused = true;
  const ex = STATE.workoutExercises[STATE.exerciseIndex];
  STATE.session.exercises.push({ name: ex.name, type: ex.type, skipped: true });
  STATE.exerciseIndex++;
  STATE.currentSets = [];
  if (STATE.exerciseIndex >= STATE.workoutExercises.length) {
    finishWorkout();
  } else {
    renderWorkout();
  }
}

// ══════════════════════════════════════════════════════════ CALENDAR ══

function renderCalendar() {
  const month = STATE.calendarMonth;
  const year = month.getFullYear();
  const mon  = month.getMonth();

  $('cal-month-label').textContent = month.toLocaleDateString('en-US', {
    month: 'long', year: 'numeric'
  }).toUpperCase();

  // Build date→logs map
  const logMap = {};
  STATE.workoutLogs.forEach(log => {
    if (!logMap[log.date]) logMap[log.date] = [];
    logMap[log.date].push(log);
  });

  // Build grid
  const firstDay = new Date(year, mon, 1).getDay();
  const daysInMonth = new Date(year, mon + 1, 0).getDate();
  const today = todayStr();

  let html = '';
  for (let i = 0; i < firstDay; i++) html += '<div class="cal-day"></div>';

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(mon + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const logs = logMap[dateStr] || [];
    const isToday = dateStr === today;
    const hasWorkout = logs.length > 0;
    const tc = hasWorkout ? typeClass(logs[0].type) : '';

    html += `<div class="cal-day${isToday ? ' today' : ''}${hasWorkout ? ` has-workout ${tc}` : ''}">
      ${d}
      ${hasWorkout ? `<div class="cal-dot ${tc}"></div>` : ''}
    </div>`;
  }
  $('cal-grid').innerHTML = html;

  // Month log list
  const monthLogs = STATE.workoutLogs.filter(log => {
    const d = new Date(log.date + 'T00:00:00');
    return d.getFullYear() === year && d.getMonth() === mon;
  }).reverse();

  if (monthLogs.length === 0) {
    $('cal-log-list').innerHTML = '<div class="empty-state">No workouts this month.</div>';
  } else {
    $('cal-log-list').innerHTML = monthLogs.map(log => {
      const day = new Date(log.date + 'T00:00:00').getDate();
      const tc = typeClass(log.type);
      const label = WORKOUT_LABELS[log.type] || log.type.toUpperCase();
      const dur = log.duration_mins ? fmtDuration(log.duration_mins) : '';
      return `<div class="cal-log-item ${tc}">
        <div class="cal-log-date">${day}</div>
        <div class="cal-log-name">${label}</div>
        ${dur ? `<div class="cal-log-dur">${dur}</div>` : ''}
      </div>`;
    }).join('');
  }
}

function calPrevMonth() {
  STATE.calendarMonth = new Date(
    STATE.calendarMonth.getFullYear(),
    STATE.calendarMonth.getMonth() - 1, 1
  );
  renderCalendar();
}

function calNextMonth() {
  STATE.calendarMonth = new Date(
    STATE.calendarMonth.getFullYear(),
    STATE.calendarMonth.getMonth() + 1, 1
  );
  renderCalendar();
}

// ══════════════════════════════════════════════════════════ FOOD LOG ══

async function renderFood() {
  if (!STATE.foodDate) STATE.foodDate = todayStr();

  $('food-date-label').textContent = fmtDateLabel(STATE.foodDate);

  const entries = await loadFoodLog(STATE.foodDate);
  renderFoodLog(entries);
  renderMacros(entries);

  // Clear search
  $('food-search-input').value = '';
  $('food-results').innerHTML = '';
  cancelAddFood();
}

function renderFoodLog(entries) {
  if (!entries.length) {
    $('food-log-list').innerHTML = '<div class="empty-state">No food logged yet.</div>';
    return;
  }
  $('food-log-list').innerHTML = entries.map(e => `
    <div class="food-log-item">
      <div class="food-log-item-name">${e.name}</div>
      <div class="food-log-item-detail">${e.grams}g</div>
      <div class="food-log-item-cal">${Math.round(e.calories)} kcal</div>
      <button class="btn-del-food" onclick="deleteFoodItem('${e.id}')">✕</button>
    </div>
  `).join('');
}

function renderMacros(entries) {
  const totalCal  = entries.reduce((s, e) => s + (e.calories || 0), 0);
  const totalProt = entries.reduce((s, e) => s + (e.protein  || 0), 0);
  const totalCarb = entries.reduce((s, e) => s + (e.carbs    || 0), 0);
  const totalFat  = entries.reduce((s, e) => s + (e.fat      || 0), 0);

  $('food-total-cal').textContent     = Math.round(totalCal).toLocaleString();
  $('food-total-protein').textContent = Math.round(totalProt);
  $('food-total-carbs').textContent   = Math.round(totalCarb);
  $('food-total-fat').textContent     = Math.round(totalFat);

  // Macro bar: protein=4kcal/g, carbs=4kcal/g, fat=9kcal/g
  const protCal = totalProt * 4;
  const carbCal = totalCarb * 4;
  const fatCal  = totalFat * 9;
  const total   = protCal + carbCal + fatCal || 1;

  $('macro-protein').style.width = `${(protCal / total * 100).toFixed(1)}%`;
  $('macro-carbs').style.width   = `${(carbCal / total * 100).toFixed(1)}%`;
  $('macro-fat').style.width     = `${(fatCal  / total * 100).toFixed(1)}%`;
}

function foodPrevDay() {
  const d = new Date(STATE.foodDate + 'T00:00:00');
  d.setDate(d.getDate() - 1);
  STATE.foodDate = d.toISOString().slice(0, 10);
  renderFood();
}

function foodNextDay() {
  const d = new Date(STATE.foodDate + 'T00:00:00');
  d.setDate(d.getDate() + 1);
  STATE.foodDate = d.toISOString().slice(0, 10);
  renderFood();
}

// ── Food search ──────────────────────────────────────────────────────────────

function onFoodSearchInput(val) {
  clearTimeout(STATE.foodSearchTimeout);
  $('food-results').innerHTML = '';
  cancelAddFood();

  if (val.trim().length < 2) return;

  $('food-results').innerHTML = '<div class="searching-label">Searching...</div>';

  STATE.foodSearchTimeout = setTimeout(async () => {
    try {
      const results = await searchFood(val.trim());
      renderFoodResults(results);
    } catch (e) {
      $('food-results').innerHTML = '<div class="searching-label">Search unavailable.</div>';
    }
  }, 400);
}

function renderFoodResults(results) {
  if (!results.length) {
    $('food-results').innerHTML = '<div class="searching-label">No results found.</div>';
    return;
  }
  $('food-results').innerHTML = results.map((r, i) => `
    <div class="food-result-item" onclick="selectFood(${i})">
      <div class="food-result-name">${r.name}</div>
      <div class="food-result-kcal">${r.kcal_per_100g} kcal/100g</div>
    </div>
  `).join('');

  // Store results on window for onclick access
  window._foodResults = results;
}

function selectFood(idx) {
  const product = window._foodResults[idx];
  STATE.selectedFood = product;

  $('food-results').innerHTML = '';
  $('add-form-name').textContent = product.name;
  $('add-grams-input').value = 100;
  updateAddPreview();
  $('food-add-form').style.display = 'block';
  $('add-grams-input').oninput = updateAddPreview;
}

function updateAddPreview() {
  const p = STATE.selectedFood;
  if (!p) return;
  const g = parseFloat($('add-grams-input').value) || 0;
  const cal  = ((p.kcal_per_100g  / 100) * g).toFixed(0);
  const prot = ((p.protein_per_100g / 100) * g).toFixed(1);
  const carb = ((p.carbs_per_100g   / 100) * g).toFixed(1);
  const fat  = ((p.fat_per_100g     / 100) * g).toFixed(1);
  $('add-form-preview').textContent = `${cal} kcal · P ${prot}g · C ${carb}g · F ${fat}g`;
}

async function confirmAddFood() {
  const p = STATE.selectedFood;
  if (!p) return;
  const g = parseFloat($('add-grams-input').value) || 0;
  if (g <= 0) return;

  const entry = {
    date:     STATE.foodDate,
    name:     p.name,
    grams:    g,
    calories: (p.kcal_per_100g    / 100) * g,
    protein:  (p.protein_per_100g / 100) * g,
    carbs:    (p.carbs_per_100g   / 100) * g,
    fat:      (p.fat_per_100g     / 100) * g,
  };

  try {
    await saveFoodEntry(entry);
    cancelAddFood();
    $('food-search-input').value = '';
    renderFood();
  } catch (e) {
    alert('Could not save food entry. Is the server running?');
  }
}

function cancelAddFood() {
  STATE.selectedFood = null;
  $('food-add-form').style.display = 'none';
  $('add-form-preview').textContent = '';
  window._foodResults = null;
}

async function deleteFoodItem(id) {
  try {
    await deleteFoodEntry(id, STATE.foodDate);
    renderFood();
  } catch (e) {
    alert('Could not delete entry.');
  }
}

// ══════════════════════════════════════════════════════════ SCHEDULE ══

const DAY_NAMES = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
const SCHEDULE_OPTIONS = [
  { value: 'rest',           label: '— Rest —' },
  { value: 'chest',          label: 'Chest' },
  { value: 'back',           label: 'Back' },
  { value: 'legs',           label: 'Legs' },
  { value: 'cardio_walking', label: 'Cardio — Walk' },
  { value: 'cardio_bag',     label: 'Cardio — Bag' },
];

function loadSchedule() {
  try {
    return JSON.parse(localStorage.getItem('workout_schedule') || '{}');
  } catch { return {}; }
}

function renderSchedule() {
  const schedule = loadSchedule();
  $('schedule-list').innerHTML = DAY_NAMES.map((day, i) => {
    const val = schedule[i] || 'rest';
    const opts = SCHEDULE_OPTIONS.map(o =>
      `<option value="${o.value}"${o.value === val ? ' selected' : ''}>${o.label}</option>`
    ).join('');
    return `<div class="schedule-row">
      <div class="schedule-day">${day}</div>
      <select class="schedule-select" id="sched-day-${i}">${opts}</select>
    </div>`;
  }).join('');
}

function saveSchedule() {
  const schedule = {};
  DAY_NAMES.forEach((_, i) => {
    schedule[i] = $(`sched-day-${i}`).value;
  });
  localStorage.setItem('workout_schedule', JSON.stringify(schedule));
  showScreen('home');
}

function getTodayScheduled() {
  const schedule = loadSchedule();
  const dayIdx = new Date().getDay();
  return schedule[dayIdx] || null;
}

function renderTodayBanner() {
  const type = getTodayScheduled();
  const banner = $('today-workout-banner');
  if (!type || type === 'rest') {
    banner.style.display = 'none';
    return;
  }
  $('today-workout-label').textContent = WORKOUT_LABELS[type] || type.toUpperCase();
  banner.style.display = 'flex';
  // Pre-select this workout when START is tapped
  banner.onclick = () => startWorkout(type);
}

// ══════════════════════════════════════════════════════════════ INIT ══

async function init() {
  STATE.foodDate = todayStr();
  STATE.calendarMonth = new Date();

  await loadExercises();
  await loadWorkoutLogs();
  showScreen('home');
}

document.addEventListener('DOMContentLoaded', init);
