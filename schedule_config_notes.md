# Schedule Config Notes

**Generated:** 2026-04-03
**Source docs:** daily-schedule.md, menu.md

---

## Ambiguities Resolved

### 1. Pre-workout snack (not in daily-schedule.md sequence)
The daily schedule doesn't list a "pre-workout snack" as a separate item, but menu.md's calorie table shows Pre-exercise calories (232 on HIIT days = coffee + fruit, 132 on standard days = coffee only). I added a "Pre-workout snack" as order 1 on gym days to make the food tracking complete. On HIIT days it includes Coffee #1 + 1 fruit; on standard days it's Coffee #1 only.

### 2. Coffee #1 placement on rest days (Saturday/Sunday)
On rest days there's no gym, so no "pre-workout" coffee. The schedule shows "Coffee & Left hand coloring" appearing mid-morning. I marked this as Coffee #1 on rest days since there's no pre-workout context. Coffee #2 still appears later in the day.

### 3. NSDR sessions (not in daily-schedule.md) — CONFIRMED by Amy
The daily schedule document does NOT mention NSDR sessions. Amy confirmed placement: post prep vegetables + post laundry. Both locked. Updated in all day templates.

### 4. Snacks placement (not in daily-schedule.md sequence)
Snacks aren't listed as a separate item in the daily schedule. Menu.md says they're "post-lunch." I placed them as order N+1 after Lunch in each template. The snack structure differs between HIIT days (no fruit — it moved to pre-workout) and standard days (includes fruit).

### 5. Saturday: missing walk between Coffee #2 and Lunch
The Saturday schedule in daily-schedule.md goes: "Prep meals → Coffee #2 → Lunch" with no walk between Coffee #2 and Lunch. Every other day has a walk there. I preserved the source doc exactly (no walk inserted). This may be intentional since Saturday is a lighter day.

### 6. Estimated durations
The source docs don't specify durations for most items. I used reasonable estimates:
- Gym: 60 min
- Walk: 20 min (~1 mile)
- Prep Day morning routine: 30 min
- Clean kitchen: 15 min
- Zone cleaning (bathrooms, living room, etc.): 30 min
- Kitchen deep clean: 45 min
- Shower: 20 min
- Laundry: 15 min (start load, not full cycle)
- Prep meals: 60 min
- Coffee & coloring: 30 min
- Crochet: 30 min
- NSDR: 10 min
- Meals: 20-30 min
- Snacks: 15 min
- Grocery shopping: 60 min
- Pre-workout snack: 5 min

These are estimates and should be calibrated from actual usage data.

### 7. Food choice master lists
Menu.md specifies quantities (7 fruits/week, 6 unique snack vegetables, 9 unique veggie bowl vegetables) but doesn't name specific items. Shopping-lists.md uses numbered placeholders ("Snack fruit #1", "Veggie bowl veg #4", etc.) — actual items are chosen at the store. Master lists populated with common MIND-diet-aligned options. The pantry model handles what's actually stocked — Amy updates after each shopping trip (Mon/Fri). Kroger project (projects-grocery-price-lookup.md) has UPC data for 37+ products if specific item mapping is needed later.

### 8. Week number calculation
The spec says system starts 2026-03-16. I defined Week 1 as the first 7 days from start, then alternating. Formula: `week_number = ((floor(days_since_start / 7)) % 2 == 0) ? 1 : 2`. This means Mar 16-22 = Week 1, Mar 23-29 = Week 2, Mar 30 - Apr 5 = Week 1, etc.

---

## Items That Don't Fit Cleanly Into Categories

| Item | Assigned Category | Notes |
|------|------------------|-------|
| Coffee & Left hand coloring | `coffee` | Combines coffee ritual + creative activity. Could be split into `coffee` + `custom` if the app needs to track them separately. |
| Prep Day — Morning routine | `prep` | Vague — could include multiple sub-tasks. May need its own category or sub-items in the future. |
| Crochet | `custom` | Creative/leisure activity. No predefined category; using `custom`. |
| Left hand coloring | (bundled with coffee) | Not a separate item — always paired with Coffee #1. |
| Pre-workout snack | `meal` | Not a full meal, but uses `meal` category for food tracking consistency. Could warrant a `snack` or `pre-workout` category. |
| Snacks | `meal` | Same as above — post-lunch snacks grouped as one `meal` category item. Could warrant a `snack` or `pre-workout` category. |

---

## Brain Building — CONFIRMED by Amy, added to config
Brain building was added to the routine on 2026-03-27, after daily-schedule.md was last updated (2026-03-23). Amy confirmed it should be in the config. Placed after Crochet in every day template (creative morning block → brain building → next activity).