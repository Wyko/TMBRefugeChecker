/** @file TMB Refuge Checker — frontend logic */

// ── State ──────────────────────────────────────────────
let allRefuges = [];      // [{id, name, order, km_from_start}, ...]
let groups = [];           // [[{id, name}, ...], ...]
let draggedRefugeIds = []; // IDs being dragged (single or cluster)
let clusterRadiusKm = 7;   // adjustable grouping radius

// ── DOM refs ───────────────────────────────────────────
const refugeList   = document.getElementById("refuge-list");
const refugeCount  = document.getElementById("refuge-count");
const groupsEl     = document.getElementById("groups");
const addGroupBtn  = document.getElementById("add-group-btn");
const checkBtn     = document.getElementById("check-btn");
const datePreset   = document.getElementById("date-preset");
const customDates  = document.getElementById("custom-dates");
const startDateEl  = document.getElementById("start-date");
const endDateEl    = document.getElementById("end-date");
const minPlacesEl  = document.getElementById("min-places");
const dailyKmEl    = document.getElementById("daily-km");
const resultsStatus = document.getElementById("results-status");
const resultsHead  = document.getElementById("results-head");
const resultsBody  = document.getElementById("results-body");
const saveBtn      = document.getElementById("save-btn");
const loadBtn      = document.getElementById("load-btn");
const refreshBtn   = document.getElementById("refresh-btn");

// ── Init ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    setDefaultDates();
    datePreset.addEventListener("change", onPresetChange);
    addGroupBtn.addEventListener("click", () => { addGroup(); updateCheckBtn(); });

    // Allow dropping refuges onto the "Add Night" button
    addGroupBtn.addEventListener("dragover", (e) => { e.preventDefault(); addGroupBtn.classList.add("drag-over"); });
    addGroupBtn.addEventListener("dragleave", () => addGroupBtn.classList.remove("drag-over"));
    addGroupBtn.addEventListener("drop", (e) => {
        e.preventDefault();
        addGroupBtn.classList.remove("drag-over");
        if (draggedRefugeIds.length > 0) {
            addGroupWithRefuges(draggedRefugeIds);
        }
    });

    // Allow dropping refuges onto empty area of the groups panel
    groupsEl.addEventListener("dragover", (e) => { e.preventDefault(); });
    groupsEl.addEventListener("drop", (e) => {
        // Only handle drops on the panel itself, not on a group box
        if (e.target === groupsEl && draggedRefugeIds.length > 0) {
            e.preventDefault();
            addGroupWithRefuges(draggedRefugeIds);
        }
    });
    checkBtn.addEventListener("click", onCheck);
    saveBtn.addEventListener("click", onSave);
    loadBtn.addEventListener("click", onLoad);
    refreshBtn.addEventListener("click", onRefresh);
    dailyKmEl.addEventListener("input", renderRefuges);
    document.getElementById("refuge-filter").addEventListener("input", renderRefuges);
    const clusterSlider = document.getElementById("cluster-radius");
    const clusterValue  = document.getElementById("cluster-radius-value");
    clusterSlider.addEventListener("input", () => {
        clusterRadiusKm = parseInt(clusterSlider.value, 10);
        clusterValue.textContent = clusterRadiusKm;
        renderRefuges();
    });

    refugeList.innerHTML = '<div class="loading">Loading refuges…</div>';
    try {
        const res = await fetch("/api/refuges");
        allRefuges = await res.json();
        refugeCount.textContent = `(${allRefuges.length})`;
        renderRefuges();
    } catch {
        refugeList.innerHTML = '<div class="loading error">Failed to load refuges.</div>';
    }
});

// ── Date helpers ───────────────────────────────────────
function setDefaultDates() {
    const today = new Date();
    startDateEl.value = fmtDate(today);
    const end = new Date(today);
    end.setMonth(end.getMonth() + 3);
    endDateEl.value = fmtDate(end);
}

function fmtDate(d) {
    return d.toISOString().slice(0, 10);
}

function getDateRange() {
    const preset = datePreset.value;
    if (preset === "3months") {
        const s = new Date();
        const e = new Date(); e.setMonth(e.getMonth() + 3);
        return [fmtDate(s), fmtDate(e)];
    }
    if (preset === "summer") {
        return ["2026-06-01", "2026-09-30"];
    }
    return [startDateEl.value, endDateEl.value];
}

function onPresetChange() {
    customDates.style.display = datePreset.value === "custom" ? "flex" : "none";
}

// ── Refuge rendering ───────────────────────────────────

/** Return the set of refuge IDs already used in any night group. */
function usedRefugeIds() {
    const ids = new Set();
    for (const g of groups) for (const r of g) ids.add(r.id);
    return ids;
}

/** Find refuges within the current grouping radius of the given refuge. */
function clusterAround(refuge, available) {
    if (refuge.km_from_start == null || clusterRadiusKm <= 0) return [refuge];
    return available.filter(r =>
        r.km_from_start != null &&
        Math.abs(r.km_from_start - refuge.km_from_start) <= clusterRadiusKm
    );
}

/** Compute the set of refuge IDs to highlight as best next stop. */
function suggestedNextIds() {
    const dailyKm = parseFloat(dailyKmEl.value) || 15;
    const used = usedRefugeIds();

    // Find the last group (highest index) that has refuges with km data
    let lastKm = null;
    for (let i = groups.length - 1; i >= 0; i--) {
        for (const r of groups[i]) {
            const full = allRefuges.find(a => a.id === r.id);
            if (full && full.km_from_start != null) {
                if (lastKm === null || full.km_from_start > lastKm)
                    lastKm = full.km_from_start;
            }
        }
        if (lastKm !== null) break;
    }
    if (lastKm === null) return new Set();

    const targetKm = lastKm + dailyKm;
    const available = allRefuges.filter(r => !used.has(r.id) && r.km_from_start != null);
    if (available.length === 0) return new Set();

    // Find the refuge closest to the target distance
    let bestDist = Infinity;
    for (const r of available) {
        const d = Math.abs(r.km_from_start - targetKm);
        if (d < bestDist) bestDist = d;
    }
    // Include all refuges within CLUSTER_RADIUS_KM of the best match
    const bestRefuges = available.filter(r =>
        Math.abs(r.km_from_start - targetKm) <= bestDist + clusterRadiusKm
    );
    return new Set(bestRefuges.map(r => r.id));
}

function renderRefuges() {
    refugeList.innerHTML = "";
    const used = usedRefugeIds();
    const suggested = suggestedNextIds();
    const filterText = (document.getElementById("refuge-filter").value || "").toLowerCase();

    // Sort by km_from_start (nulls last), then by order, then by name
    const sorted = [...allRefuges].sort((a, b) => {
        const aKm = a.km_from_start ?? Infinity;
        const bKm = b.km_from_start ?? Infinity;
        if (aKm !== bKm) return aKm - bKm;
        const aOrd = a.order ?? Infinity;
        const bOrd = b.order ?? Infinity;
        if (aOrd !== bOrd) return aOrd - bOrd;
        return a.name.localeCompare(b.name);
    });

    const available = sorted.filter(r => !used.has(r.id));
    refugeCount.textContent = `(${available.length}/${allRefuges.length})`;

    const filtered = filterText
        ? sorted.filter(r => r.name.toLowerCase().includes(filterText))
        : sorted;

    for (let i = 0; i < filtered.length; i++) {
        const r = filtered[i];
        const isUsed = used.has(r.id);

        // Distance badge between consecutive refuges
        if (i > 0 && filtered[i - 1].km_from_start != null && r.km_from_start != null) {
            const dist = (r.km_from_start - filtered[i - 1].km_from_start).toFixed(1);
            const badge = document.createElement("div");
            badge.className = "distance-badge";
            badge.textContent = `↓ ${dist} km`;
            refugeList.appendChild(badge);
        }

        const card = document.createElement("div");
        let cls = "refuge-card";
        if (isUsed) cls += " refuge-used";
        else if (suggested.has(r.id)) cls += " refuge-suggested";
        card.className = cls;
        card.draggable = !isUsed;
        card.dataset.id = r.id;

        const nameSpan = document.createElement("span");
        nameSpan.textContent = r.name;
        card.appendChild(nameSpan);

        const rightSide = document.createElement("span");
        rightSide.style.display = "flex";
        rightSide.style.alignItems = "center";
        rightSide.style.gap = ".3rem";

        if (!isUsed) {
            // Cluster drag button (only for available refuges)
            const cluster = clusterAround(r, available);
            if (cluster.length > 1) {
                const clusterBtn = document.createElement("button");
                clusterBtn.className = "cluster-btn";
                clusterBtn.title = `Drag all ${cluster.length} nearby refuges as a group (within ${clusterRadiusKm} km of each other)`;
                clusterBtn.textContent = `+${cluster.length - 1}`;
                clusterBtn.draggable = true;
                clusterBtn.addEventListener("dragstart", (e) => {
                    e.stopPropagation();
                    draggedRefugeIds = cluster.map(c => c.id);
                    card.classList.add("dragging");
                    e.dataTransfer.effectAllowed = "copy";
                });
                clusterBtn.addEventListener("dragend", () => {
                    card.classList.remove("dragging");
                    draggedRefugeIds = [];
                });
                rightSide.appendChild(clusterBtn);
            }
        }

        if (r.km_from_start != null) {
            const kmSpan = document.createElement("span");
            kmSpan.className = "refuge-km";
            kmSpan.textContent = `km ${r.km_from_start}`;
            rightSide.appendChild(kmSpan);
        }

        card.appendChild(rightSide);

        if (!isUsed) {
            card.addEventListener("dragstart", (e) => {
                draggedRefugeIds = [r.id];
                card.classList.add("dragging");
                e.dataTransfer.effectAllowed = "copy";
            });
            card.addEventListener("dragend", () => {
                card.classList.remove("dragging");
                draggedRefugeIds = [];
            });
        }
        refugeList.appendChild(card);
    }
}

// ── Group management ───────────────────────────────────
function addGroup() {
    groups.push([]);
    renderGroups();
}

function addGroupWithRefuges(refugeIds) {
    groups.push([]);
    const newIdx = groups.length - 1;
    addMultipleRefugesToGroup(newIdx, refugeIds);
}

function removeGroup(idx) {
    groups.splice(idx, 1);
    renderGroups();
    renderRefuges();
    updateCheckBtn();
}

function addRefugeToGroup(groupIdx, refugeId) {
    const refuge = allRefuges.find(r => r.id === refugeId);
    if (!refuge) return;
    // Prevent duplicates within the same group
    if (groups[groupIdx].some(r => r.id === refugeId)) return;
    groups[groupIdx].push({ id: refuge.id, name: refuge.name });
    renderGroups();
    renderRefuges();
    updateCheckBtn();
}

function addMultipleRefugesToGroup(groupIdx, refugeIds) {
    for (const id of refugeIds) {
        const refuge = allRefuges.find(r => r.id === id);
        if (!refuge) continue;
        if (groups[groupIdx].some(r => r.id === id)) continue;
        groups[groupIdx].push({ id: refuge.id, name: refuge.name });
    }
    renderGroups();
    renderRefuges();
    updateCheckBtn();
}

function removeRefugeFromGroup(groupIdx, refugeId) {
    groups[groupIdx] = groups[groupIdx].filter(r => r.id !== refugeId);
    renderGroups();
    renderRefuges();
    updateCheckBtn();
}

function renderGroups() {
    groupsEl.innerHTML = "";
    groups.forEach((group, gIdx) => {
        const box = document.createElement("div");
        box.className = "group-box";

        // Header
        const header = document.createElement("div");
        header.className = "group-header";
        const title = document.createElement("span");
        title.textContent = `Night ${gIdx + 1}`;
        const removeBtn = document.createElement("button");
        removeBtn.textContent = "Remove";
        removeBtn.addEventListener("click", () => removeGroup(gIdx));
        header.append(title, removeBtn);
        box.appendChild(header);

        // Items
        const items = document.createElement("div");
        items.className = "group-items";
        if (group.length === 0) {
            const placeholder = document.createElement("div");
            placeholder.className = "group-placeholder";
            placeholder.textContent = "Empty — own reservation (drag refuges here or leave empty to skip)";
            items.appendChild(placeholder);
        }
        for (const r of group) {
            const el = document.createElement("div");
            el.className = "group-refuge";
            el.innerHTML = `<span>${r.name}</span>`;
            const rm = document.createElement("button");
            rm.className = "remove-refuge";
            rm.textContent = "✕";
            rm.addEventListener("click", () => removeRefugeFromGroup(gIdx, r.id));
            el.appendChild(rm);
            items.appendChild(el);
        }
        box.appendChild(items);

        // Drop zone
        box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drag-over"); });
        box.addEventListener("dragleave", () => box.classList.remove("drag-over"));
        box.addEventListener("drop", (e) => {
            e.preventDefault();
            box.classList.remove("drag-over");
            if (draggedRefugeIds.length > 0) {
                addMultipleRefugesToGroup(gIdx, draggedRefugeIds);
            }
        });

        groupsEl.appendChild(box);
    });
}

function updateCheckBtn() {
    const hasGroups = groups.length > 0 && groups.some(g => g.length > 0);
    checkBtn.disabled = !hasGroups;
}

// ── Availability check ────────────────────────────────
async function onCheck() {
    if (groups.length === 0 || !groups.some(g => g.length > 0)) return;

    const [startDate, endDate] = getDateRange();
    const minPlaces = parseInt(minPlacesEl.value) || 1;

    checkBtn.disabled = true;
    resultsStatus.innerHTML = '<span class="spinner"></span> Checking availability&hellip;';
    resultsHead.innerHTML = "";
    resultsBody.innerHTML = "";

    try {
        const res = await fetch("/api/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                groups: groups.map(g => g.map(r => r.id)),
                start_date: startDate,
                end_date: endDate,
                min_places: minPlaces,
            }),
        });

        if (!res.ok) {
            resultsStatus.textContent = `Error: ${res.status} ${res.statusText}`;
            return;
        }

        const data = await res.json();
        renderResults(data.results, groups);
    } catch (err) {
        resultsStatus.textContent = `Request failed: ${err.message}`;
    } finally {
        updateCheckBtn();
    }
}

/** Store the last rendered results so the detail view can go back. */
let lastResults = null;
let lastGroupsUsed = null;

function renderResults(results, groupsUsed) {
    lastResults = results;
    lastGroupsUsed = groupsUsed;

    if (results.length === 0) {
        resultsStatus.textContent = "No viable starting dates found.";
        return;
    }

    resultsStatus.textContent = `${results.length} viable starting date${results.length > 1 ? "s" : ""} found.`;

    // Header row
    const headerRow = document.createElement("tr");
    const thDate = document.createElement("th");
    thDate.textContent = "Start Date";
    headerRow.appendChild(thDate);
    for (let i = 0; i < groupsUsed.length; i++) {
        const th = document.createElement("th");
        th.textContent = `Night ${i + 1}`;
        headerRow.appendChild(th);
    }
    resultsHead.appendChild(headerRow);

    // Data rows
    for (const itinerary of results) {
        const row = document.createElement("tr");
        row.className = "result-row";
        row.addEventListener("click", () => showItineraryDetail(itinerary));

        const tdStart = document.createElement("td");
        tdStart.textContent = formatDisplayDate(itinerary.start_date);
        row.appendChild(tdStart);

        for (const night of itinerary.nights) {
            const td = document.createElement("td");
            if (night.skipped) {
                td.textContent = "Own reservation";
                td.className = "night-skipped";
            } else {
                td.textContent = `${night.refuge_name} (${night.places})`;
            }
            row.appendChild(td);
        }

        resultsBody.appendChild(row);
    }
}

const BOOKING_BASE = "https://www.montourdumontblanc.com";

/** Show a detailed itinerary view replacing the results table. */
function showItineraryDetail(itinerary) {
    resultsHead.innerHTML = "";
    resultsBody.innerHTML = "";
    resultsStatus.innerHTML = "";

    const wrap = document.getElementById("results-table-wrap");
    const detail = document.createElement("div");
    detail.className = "itinerary-detail";

    // Back button
    const backBtn = document.createElement("button");
    backBtn.className = "detail-back-btn";
    backBtn.textContent = "\u2190 Back to all dates";
    backBtn.addEventListener("click", () => {
        detail.remove();
        renderResults(lastResults, lastGroupsUsed);
    });
    detail.appendChild(backBtn);

    // Title
    const title = document.createElement("h3");
    title.className = "detail-title";
    title.textContent = `Itinerary starting ${formatDisplayDate(itinerary.start_date)}`;
    detail.appendChild(title);

    // Night cards
    for (let i = 0; i < itinerary.nights.length; i++) {
        const night = itinerary.nights[i];
        const card = document.createElement("div");
        card.className = night.skipped ? "detail-card detail-card-skipped" : "detail-card";

        const header = document.createElement("div");
        header.className = "detail-card-header";
        header.innerHTML = `<span class="detail-night-label">Night ${i + 1}</span>`
            + `<span class="detail-date">${formatDisplayDate(night.date)}</span>`;
        card.appendChild(header);

        const body = document.createElement("div");
        body.className = "detail-card-body";

        if (night.skipped) {
            const nameEl = document.createElement("div");
            nameEl.className = "detail-refuge-name";
            nameEl.textContent = "Own reservation";
            body.appendChild(nameEl);

            const noteEl = document.createElement("div");
            noteEl.className = "detail-places";
            noteEl.textContent = "Not checked — you have your own booking";
            body.appendChild(noteEl);
        } else {
            const nameEl = document.createElement("div");
            nameEl.className = "detail-refuge-name";
            nameEl.textContent = night.refuge_name;
            body.appendChild(nameEl);

            const placesEl = document.createElement("div");
            placesEl.className = "detail-places";
            placesEl.textContent = `${night.places} place${night.places !== 1 ? "s" : ""} available`;
            body.appendChild(placesEl);

            if (night.reservation_url) {
                const link = document.createElement("a");
                link.className = "detail-book-link";
                link.href = BOOKING_BASE + night.reservation_url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = "Reserve \u2192";
                body.appendChild(link);
            }
        }

        card.appendChild(body);
        detail.appendChild(card);
    }

    wrap.appendChild(detail);
}

function formatDisplayDate(isoStr) {
    const d = new Date(isoStr + "T00:00:00");
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

// ── Save / Load / Refresh ──────────────────────────────
async function onSave() {
    const settings = {
        datePreset: datePreset.value,
        startDate: startDateEl.value,
        endDate: endDateEl.value,
        minPlaces: minPlacesEl.value,
        dailyKm: dailyKmEl.value,
        clusterRadius: clusterRadiusKm,
    };
    try {
        const res = await fetch("/api/selections/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ groups, settings }),
        });
        if (res.ok) {
            saveBtn.textContent = "Saved \u2713";
            setTimeout(() => { saveBtn.textContent = "Save"; }, 1500);
        }
    } catch (err) {
        alert("Failed to save: " + err.message);
    }
}

async function onLoad() {
    try {
        const res = await fetch("/api/selections/load");
        if (!res.ok) return;
        const data = await res.json();
        if (!data.groups || data.groups.length === 0) {
            alert("No saved selections found.");
            return;
        }
        groups = data.groups;
        if (data.settings) {
            const s = data.settings;
            if (s.datePreset) { datePreset.value = s.datePreset; onPresetChange(); }
            if (s.startDate) startDateEl.value = s.startDate;
            if (s.endDate) endDateEl.value = s.endDate;
            if (s.minPlaces) minPlacesEl.value = s.minPlaces;
            if (s.dailyKm) dailyKmEl.value = s.dailyKm;
            if (s.clusterRadius != null) {
                clusterRadiusKm = s.clusterRadius;
                document.getElementById("cluster-radius").value = clusterRadiusKm;
                document.getElementById("cluster-radius-value").textContent = clusterRadiusKm;
            }
        }
        renderGroups();
        renderRefuges();
        updateCheckBtn();
        loadBtn.textContent = "Loaded \u2713";
        setTimeout(() => { loadBtn.textContent = "Load"; }, 1500);
    } catch (err) {
        alert("Failed to load: " + err.message);
    }
}

async function onRefresh() {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing\u2026";
    try {
        await fetch("/api/refresh", { method: "POST" });
        // Re-fetch refuges with fresh data
        const res = await fetch("/api/refuges");
        allRefuges = await res.json();
        refugeCount.textContent = `(${allRefuges.length})`;
        renderRefuges();
        refreshBtn.textContent = "Done \u2713";
        setTimeout(() => { refreshBtn.innerHTML = "Refresh &#x21bb;"; }, 1500);
    } catch (err) {
        refreshBtn.textContent = "Failed";
        setTimeout(() => { refreshBtn.innerHTML = "Refresh &#x21bb;"; }, 2000);
    } finally {
        refreshBtn.disabled = false;
    }
}
