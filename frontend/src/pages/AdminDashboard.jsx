import { useState, useEffect } from "react";
import { fetchCourses, addCourse, deleteCourse, updateCourse, fetchPolicy, updatePolicy } from "../services/api";
import "./AdminDashboard.css";

// ─── Pagination ──────────────────────────────────────────────────────────────

const PAGE_SIZE = 10;

function Pagination({ total, page, onPage }) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (totalPages === 1) return null;

  const pages = [];
  const delta = 2;
  const left = Math.max(1, page - delta);
  const right = Math.min(totalPages, page + delta);

  if (left > 1) { pages.push(1); if (left > 2) pages.push("…"); }
  for (let i = left; i <= right; i++) pages.push(i);
  if (right < totalPages) { if (right < totalPages - 1) pages.push("…"); pages.push(totalPages); }

  return (
    <div className="admin-pagination">
      <button className="admin-page-btn" disabled={page === 1} onClick={() => onPage(page - 1)}>‹</button>
      {pages.map((p, i) =>
        p === "…"
          ? <span key={`ellipsis-${i}`} className="admin-page-ellipsis">…</span>
          : <button key={p} className={`admin-page-btn${page === p ? " admin-page-btn--active" : ""}`} onClick={() => onPage(p)}>{p}</button>
      )}
      <button className="admin-page-btn" disabled={page === totalPages} onClick={() => onPage(page + 1)}>›</button>
      <span className="admin-page-info">{total} total</span>
    </div>
  );
}

// ─── Courses Tab ────────────────────────────────────────────────────────────

function CoursesTab() {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterCredits, setFilterCredits] = useState("");
  const [filterLab, setFilterLab] = useState("");
  const [page, setPage] = useState(1);
  const [editingCourse, setEditingCourse] = useState(null);
  const [editForm, setEditForm] = useState(null);

  const resetFilters = () => { setSearch(""); setFilterDept(""); setFilterCredits(""); setFilterLab(""); setPage(1); };
  const goPage = (p) => { setPage(p); };

  const emptyForm = {
    courseCode: "",
    displayName: "",
    credits: "",
    labRequired: false,
    requiredTopics: "",
    requiredOutcomes: "",
    department: "",
    departmentCustom: "",
    prerequisites: "",
    description: "",
  };
  const [form, setForm] = useState(emptyForm);

  useEffect(() => {
    fetchCourses()
      .then(setCourses)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const startEdit = (c) => {
    setEditingCourse(c);
    setEditForm({
      displayName: c.displayName || "",
      department: c.department || "",
      departmentCustom: "",
      credits: String(c.credits || ""),
      labRequired: c.labRequired || false,
      prerequisites: c.prerequisites || "",
      description: c.description || "",
      requiredTopics: (c.requiredTopics || []).join(", "),
      requiredOutcomes: (c.requiredOutcomes || []).join(", "),
    });
    setShowForm(false);
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const dept = (editForm.department === "__other__" ? editForm.departmentCustom : editForm.department).trim() || "";
      const updated = await updateCourse(editingCourse.courseId, {
        displayName: editForm.displayName.trim(),
        department: dept,
        credits: parseInt(editForm.credits, 10) || 0,
        labRequired: editForm.labRequired,
        prerequisites: editForm.prerequisites.trim() || null,
        description: editForm.description.trim() || null,
        requiredTopics: editForm.requiredTopics.split(",").map((t) => t.trim()).filter(Boolean),
        requiredOutcomes: editForm.requiredOutcomes.split(",").map((o) => o.trim()).filter(Boolean),
      });
      setCourses((prev) => prev.map((c) => c.courseId === editingCourse.courseId ? updated : c));
      setEditingCourse(null);
      setEditForm(null);
      setSuccessMsg(`Course ${updated.courseCode} updated.`);
      setTimeout(() => setSuccessMsg(""), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (c) => {
    if (!window.confirm(`Delete course ${c.courseCode} — ${c.displayName}? This cannot be undone.`)) return;
    try {
      await deleteCourse(c.courseId);
      setCourses((prev) => prev.filter((x) => x.courseId !== c.courseId));
      setSuccessMsg(`Course ${c.courseCode} deleted.`);
      setTimeout(() => setSuccessMsg(""), 4000);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        courseCode: form.courseCode.trim(),
        displayName: form.displayName.trim(),
        credits: parseInt(form.credits, 10) || 0,
        labRequired: form.labRequired,
        requiredTopics: form.requiredTopics.split(",").map((t) => t.trim()).filter(Boolean),
        requiredOutcomes: form.requiredOutcomes.split(",").map((o) => o.trim()).filter(Boolean),
        department: (form.department === "__other__" ? form.departmentCustom : form.department).trim() || "",
        prerequisites: form.prerequisites.trim() || null,
        description: form.description.trim() || null,
      };
      const created = await addCourse(payload);
      setCourses((prev) => [...prev, created]);
      setForm(emptyForm);
      setShowForm(false);
      setSuccessMsg(`Course ${created.courseCode || payload.courseCode} added.`);
      setTimeout(() => setSuccessMsg(""), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="admin-loading">Loading courses...</p>;

  return (
    <div className="admin-tab-content">
      <div className="admin-tab-header">
        <h2>Courses</h2>
        <button className="admin-btn admin-btn--primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ Add Course"}
        </button>
      </div>

      {error && <p className="admin-error">{error}</p>}
      {successMsg && <p className="admin-success">{successMsg}</p>}

      {editingCourse && editForm && (
        <form className="admin-form" onSubmit={handleEdit}>
          <h3 className="admin-form-title">Edit Course — <code>{editingCourse.courseCode}</code></h3>
          <div className="admin-form-grid">
            <div className="admin-field">
              <label>Display Name *</label>
              <input required value={editForm.displayName}
                onChange={(e) => setEditForm({ ...editForm, displayName: e.target.value })} />
            </div>
            <div className="admin-field">
              <label>Credits *</label>
              <input required type="number" min="1" max="10" value={editForm.credits}
                onChange={(e) => setEditForm({ ...editForm, credits: e.target.value })} />
            </div>
            <div className="admin-field">
              <label>Department *</label>
              {editForm.department === "__other__" ? (
                <input required autoFocus placeholder="Enter department name"
                  value={editForm.departmentCustom || ""}
                  onChange={(e) => setEditForm({ ...editForm, departmentCustom: e.target.value })}
                  onBlur={(e) => { if (!e.target.value.trim()) setEditForm({ ...editForm, department: "", departmentCustom: "" }); }}
                />
              ) : (
                <select required value={editForm.department}
                  onChange={(e) => setEditForm({ ...editForm, department: e.target.value, departmentCustom: "" })}>
                  <option value="">Select department...</option>
                  {[...new Set(courses.map((c) => c.department).filter(Boolean))].sort().map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                  <option value="__other__">+ Add new department</option>
                </select>
              )}
            </div>
            <div className="admin-field admin-field--full">
              <label>Prerequisites <span className="admin-hint">(optional)</span></label>
              <input placeholder="e.g. CPSC-1110" value={editForm.prerequisites}
                onChange={(e) => setEditForm({ ...editForm, prerequisites: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Description <span className="admin-hint">(optional)</span></label>
              <input placeholder="Short course description..." value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Required Topics <span className="admin-hint">(comma-separated)</span></label>
              <textarea value={editForm.requiredTopics}
                onChange={(e) => setEditForm({ ...editForm, requiredTopics: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Required Outcomes <span className="admin-hint">(comma-separated)</span></label>
              <textarea value={editForm.requiredOutcomes}
                onChange={(e) => setEditForm({ ...editForm, requiredOutcomes: e.target.value })} />
            </div>
            <div className="admin-field admin-field--checkbox">
              <label>
                <input type="checkbox" checked={editForm.labRequired}
                  onChange={(e) => setEditForm({ ...editForm, labRequired: e.target.checked })} />
                Lab Required
              </label>
            </div>
          </div>
          <div className="admin-form-actions">
            <button className="admin-btn admin-btn--primary" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </button>
            <button className="admin-btn" type="button" onClick={() => { setEditingCourse(null); setEditForm(null); }}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {!showForm && !editingCourse && <div className="admin-filters">
        <input
          className="admin-filter-input"
          type="text"
          placeholder="Search code or name..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
        <select
          className="admin-filter-select"
          value={filterDept}
          onChange={(e) => { setFilterDept(e.target.value); setPage(1); }}
        >
          <option value="">All Departments</option>
          {[...new Set(courses.map((c) => c.department).filter(Boolean))].sort().map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <select
          className="admin-filter-select"
          value={filterCredits}
          onChange={(e) => { setFilterCredits(e.target.value); setPage(1); }}
        >
          <option value="">Any Credits</option>
          {[...new Set(courses.map((c) => c.credits).filter((v) => v != null))].sort((a, b) => a - b).map((cr) => (
            <option key={cr} value={cr}>{cr} cr</option>
          ))}
        </select>
        <select
          className="admin-filter-select"
          value={filterLab}
          onChange={(e) => { setFilterLab(e.target.value); setPage(1); }}
        >
          <option value="">Lab: Any</option>
          <option value="yes">Lab: Required</option>
          <option value="no">Lab: Not Required</option>
        </select>
        {(search || filterDept || filterCredits || filterLab) && (
          <button className="admin-filter-clear" onClick={resetFilters}>Clear</button>
        )}
      </div>}

      {showForm && (
        <form className="admin-form" onSubmit={handleAdd}>
          <h3 className="admin-form-title">New Course</h3>
          <div className="admin-form-grid">
            <div className="admin-field">
              <label>Course Code *</label>
              <input required placeholder="e.g. CPSC-2150" value={form.courseCode}
                onChange={(e) => setForm({ ...form, courseCode: e.target.value })} />
            </div>
            <div className="admin-field">
              <label>Display Name *</label>
              <input required placeholder="e.g. Data Structures" value={form.displayName}
                onChange={(e) => setForm({ ...form, displayName: e.target.value })} />
            </div>
            <div className="admin-field">
              <label>Credits *</label>
              <input required type="number" min="1" max="10" placeholder="3" value={form.credits}
                onChange={(e) => setForm({ ...form, credits: e.target.value })} />
            </div>
            <div className="admin-field">
              <label>Department *</label>
              {form.department === "__other__" ? (
                <input
                  required
                  autoFocus
                  placeholder="Enter department name"
                  value={form.departmentCustom || ""}
                  onChange={(e) => setForm({ ...form, departmentCustom: e.target.value })}
                  onBlur={(e) => {
                    if (!e.target.value.trim()) setForm({ ...form, department: "", departmentCustom: "" });
                  }}
                />
              ) : (
                <select
                  required
                  value={form.department}
                  onChange={(e) => setForm({ ...form, department: e.target.value, departmentCustom: "" })}
                >
                  <option value="">Select department...</option>
                  {[...new Set(courses.map((c) => c.department).filter(Boolean))].sort().map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                  <option value="__other__">+ Add new department</option>
                </select>
              )}
            </div>
            <div className="admin-field admin-field--full">
              <label>Prerequisites <span className="admin-hint">(optional)</span></label>
              <input placeholder="e.g. CPSC-1110" value={form.prerequisites}
                onChange={(e) => setForm({ ...form, prerequisites: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Description <span className="admin-hint">(optional)</span></label>
              <input placeholder="Short course description..." value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Required Topics <span className="admin-hint">(comma-separated)</span></label>
              <textarea placeholder="arrays, linked lists, trees, sorting..." value={form.requiredTopics}
                onChange={(e) => setForm({ ...form, requiredTopics: e.target.value })} />
            </div>
            <div className="admin-field admin-field--full">
              <label>Required Outcomes <span className="admin-hint">(comma-separated)</span></label>
              <textarea placeholder="Implement common data structures, Analyze time complexity..." value={form.requiredOutcomes}
                onChange={(e) => setForm({ ...form, requiredOutcomes: e.target.value })} />
            </div>
            <div className="admin-field admin-field--checkbox">
              <label>
                <input type="checkbox" checked={form.labRequired}
                  onChange={(e) => setForm({ ...form, labRequired: e.target.checked })} />
                Lab Required
              </label>
            </div>
          </div>
          <button className="admin-btn admin-btn--primary" type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save Course"}
          </button>
        </form>
      )}

      {!showForm && !editingCourse && (() => {
        const filtered = courses.filter((c) => {
          const q = search.toLowerCase();
          if (q && !(c.courseCode || "").toLowerCase().includes(q) && !(c.displayName || "").toLowerCase().includes(q)) return false;
          if (filterDept && c.department !== filterDept) return false;
          if (filterCredits && String(c.credits) !== filterCredits) return false;
          if (filterLab === "yes" && !c.labRequired) return false;
          if (filterLab === "no" && c.labRequired) return false;
          return true;
        });
        const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
        if (courses.length === 0) return <p className="admin-empty">No courses yet. Add the first one.</p>;
        if (filtered.length === 0) return <p className="admin-empty">No courses match the current filters.</p>;
        return (
          <>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Credits</th>
                  <th>Lab</th>
                  <th>Topics</th>
                  <th>Department</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {paged.map((c, i) => (
                  <tr key={c.courseId || i}>
                    <td><code>{c.courseCode}</code></td>
                    <td>{c.displayName}</td>
                    <td>{c.credits}</td>
                    <td>{c.labRequired ? "Yes" : "No"}</td>
                    <td className="admin-topics-cell">
                      {(c.requiredTopics || []).slice(0, 3).join(", ")}
                      {(c.requiredTopics || []).length > 3 && ` +${c.requiredTopics.length - 3} more`}
                    </td>
                    <td>{c.department || "—"}</td>
                    <td className="admin-row-actions">
                      <button className="admin-btn-inline admin-btn-inline--edit" onClick={() => startEdit(c)}>Edit</button>
                      <button className="admin-btn-inline admin-btn-inline--delete" onClick={() => handleDelete(c)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination total={filtered.length} page={page} onPage={goPage} />
          </>
        );
      })()}
    </div>
  );
}

// ─── Policy Tab ─────────────────────────────────────────────────────────────

const DEFAULT_POLICY = {
  approveThreshold: 90,
  bridgeThreshold: 80,
  needsInfoThreshold: 70,
  requireLabParity: true,
  requireCreditsKnown: true,
  requireTopicsOrOutcomes: true,
  minGrade: "",
  minContactHours: 0,
  maxCourseAgeYears: 0,
  mustIncludeTopics: "",
};

function PolicyTab() {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState("");

  useEffect(() => {
    fetchPolicy()
      .then((data) => setPolicy({
        ...DEFAULT_POLICY,
        ...data,
        mustIncludeTopics: Array.isArray(data.mustIncludeTopics)
          ? data.mustIncludeTopics.join(", ")
          : (data.mustIncludeTopics || ""),
        minGrade: data.minGrade || "",
      }))
      .catch(() => setPolicy({ ...DEFAULT_POLICY }))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...policy,
        minGrade: policy.minGrade.trim() || null,
        minContactHours: parseInt(policy.minContactHours, 10) || 0,
        maxCourseAgeYears: parseInt(policy.maxCourseAgeYears, 10) || 0,
        mustIncludeTopics: policy.mustIncludeTopics
          .split(",").map((t) => t.trim()).filter(Boolean),
      };
      await updatePolicy(payload);
      setSuccessMsg("Policy saved successfully.");
      setTimeout(() => setSuccessMsg(""), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="admin-loading">Loading policy...</p>;

  const set = (key, val) => setPolicy((prev) => ({ ...prev, [key]: val }));

  return (
    <div className="admin-tab-content">
      <div className="admin-tab-header">
        <h2>Decision Policy</h2>
      </div>

      {error && <p className="admin-error">{error}</p>}
      {successMsg && <p className="admin-success">{successMsg}</p>}

      <form className="admin-form" onSubmit={handleSave}>

        <h3 className="admin-section-heading">Decision Thresholds (0–100)</h3>
        <p className="admin-section-desc">Score bands that determine the AI recommendation: Approve → Approve with Bridge → Needs Info → Deny.</p>
        <div className="admin-form-grid">
          <div className="admin-field">
            <label>Approve Threshold</label>
            <input type="number" min="0" max="100" value={policy.approveThreshold}
              onChange={(e) => set("approveThreshold", Number(e.target.value))} />
            <span className="admin-hint">Score ≥ this → APPROVE</span>
          </div>
          <div className="admin-field">
            <label>Bridge Threshold</label>
            <input type="number" min="0" max="100" value={policy.bridgeThreshold}
              onChange={(e) => set("bridgeThreshold", Number(e.target.value))} />
            <span className="admin-hint">Score ≥ this and &lt; Approve → APPROVE WITH BRIDGE</span>
          </div>
          <div className="admin-field">
            <label>Needs Info Threshold</label>
            <input type="number" min="0" max="100" value={policy.needsInfoThreshold}
              onChange={(e) => set("needsInfoThreshold", Number(e.target.value))} />
            <span className="admin-hint">Score ≥ this and &lt; Bridge → NEEDS MORE INFO. Below → DENY</span>
          </div>
        </div>

        <h3 className="admin-section-heading">Behavior Toggles</h3>
        <p className="admin-section-desc">When enabled, these force NEEDS MORE INFO or add a bridge requirement if evidence is missing.</p>
        <div className="admin-toggles">
          <label className="admin-toggle-row">
            <input type="checkbox" checked={policy.requireLabParity}
              onChange={(e) => set("requireLabParity", e.target.checked)} />
            <span><strong>Require Lab Parity</strong> — Source must show a lab component if the target requires one.</span>
          </label>
          <label className="admin-toggle-row">
            <input type="checkbox" checked={policy.requireCreditsKnown}
              onChange={(e) => set("requireCreditsKnown", e.target.checked)} />
            <span><strong>Require Credits Known</strong> — Missing source credits forces NEEDS MORE INFO.</span>
          </label>
          <label className="admin-toggle-row">
            <input type="checkbox" checked={policy.requireTopicsOrOutcomes}
              onChange={(e) => set("requireTopicsOrOutcomes", e.target.checked)} />
            <span><strong>Require Topics or Outcomes</strong> — If both are unknown, forces NEEDS MORE INFO.</span>
          </label>
        </div>

        <h3 className="admin-section-heading">Optional Hard Rules</h3>
        <p className="admin-section-desc">These act as veto conditions. Leave blank or 0 to disable.</p>
        <div className="admin-form-grid">
          <div className="admin-field">
            <label>Minimum Grade</label>
            <input type="text" placeholder="e.g. C (blank = off)" value={policy.minGrade}
              onChange={(e) => set("minGrade", e.target.value)} />
            <span className="admin-hint">Requires transcript data.</span>
          </div>
          <div className="admin-field">
            <label>Min Contact Hours</label>
            <input type="number" min="0" placeholder="0 = off" value={policy.minContactHours}
              onChange={(e) => set("minContactHours", e.target.value)} />
            <span className="admin-hint">Lecture + lab hours combined.</span>
          </div>
          <div className="admin-field">
            <label>Max Course Age (years)</label>
            <input type="number" min="0" placeholder="0 = off" value={policy.maxCourseAgeYears}
              onChange={(e) => set("maxCourseAgeYears", e.target.value)} />
            <span className="admin-hint">Requires transcript data.</span>
          </div>
          <div className="admin-field admin-field--full">
            <label>Must Include Topics <span className="admin-hint">(comma-separated, blank = off)</span></label>
            <input type="text" placeholder="e.g. ethics, capstone" value={policy.mustIncludeTopics}
              onChange={(e) => set("mustIncludeTopics", e.target.value)} />
          </div>
        </div>

        <button className="admin-btn admin-btn--primary" type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save Policy"}
        </button>
      </form>
    </div>
  );
}

// ─── Prerequisites Tab ──────────────────────────────────────────────────────

function PrerequisitesTab() {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [filterHasPrereq, setFilterHasPrereq] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [page, setPage] = useState(1);

  const resetFilters = () => { setSearch(""); setFilterDept(""); setFilterHasPrereq(""); setPage(1); };

  useEffect(() => {
    fetchCourses()
      .then(setCourses)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="admin-loading">Loading courses...</p>;

  return (
    <div className="admin-tab-content">
      <div className="admin-tab-header">
        <h2>Prerequisites</h2>
      </div>
      <p className="admin-section-desc">
        Prerequisites are set per course when adding a course.
      </p>

      {error && <p className="admin-error">{error}</p>}

      <div className="admin-filters">
        <input
          className="admin-filter-input"
          type="text"
          placeholder="Search code, name, or prerequisite..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
        <select
          className="admin-filter-select"
          value={filterDept}
          onChange={(e) => { setFilterDept(e.target.value); setPage(1); }}
        >
          <option value="">All Departments</option>
          {[...new Set(courses.map((c) => c.department).filter(Boolean))].sort().map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <select
          className="admin-filter-select"
          value={filterHasPrereq}
          onChange={(e) => { setFilterHasPrereq(e.target.value); setPage(1); }}
        >
          <option value="">Any Prerequisites</option>
          <option value="yes">Has Prerequisites</option>
          <option value="no">No Prerequisites</option>
        </select>
        {(search || filterDept || filterHasPrereq) && (
          <button className="admin-filter-clear" onClick={resetFilters}>Clear</button>
        )}
      </div>

      {(() => {
        const filtered = courses.filter((c) => {
          const q = search.toLowerCase();
          if (q && !(c.courseCode || "").toLowerCase().includes(q)
            && !(c.displayName || "").toLowerCase().includes(q)
            && !(c.prerequisites || "").toLowerCase().includes(q)) return false;
          if (filterDept && c.department !== filterDept) return false;
          if (filterHasPrereq === "yes" && !c.prerequisites) return false;
          if (filterHasPrereq === "no" && c.prerequisites) return false;
          return true;
        });
        const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
        if (courses.length === 0) return <p className="admin-empty">No courses added yet. Add courses from the Courses tab first.</p>;
        if (filtered.length === 0) return <p className="admin-empty">No courses match the current filters.</p>;
        return (
          <>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Course Code</th>
                  <th>Display Name</th>
                  <th>Credits</th>
                  <th>Prerequisites</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((c, i) => (
                  <tr key={c.courseId || i}>
                    <td><code>{c.courseCode}</code></td>
                    <td>{c.displayName}</td>
                    <td>{c.credits}</td>
                    <td>{c.prerequisites || <span style={{ color: "var(--color-text-muted)" }}>None</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination total={filtered.length} page={page} onPage={setPage} />
          </>
        );
      })()}
    </div>
  );
}

// ─── Admin Dashboard ────────────────────────────────────────────────────────

const TABS = ["Courses", "Policy", "Prerequisites"];

export default function AdminDashboard() {
  const [activeTab, setActiveTab] = useState("Courses");

  return (
    <div className="admin-dashboard">
      <h1>Admin Dashboard</h1>

      <div className="admin-tab-bar">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`admin-tab-btn${activeTab === tab ? " admin-tab-btn--active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Courses" && <CoursesTab />}
      {activeTab === "Policy" && <PolicyTab />}
      {activeTab === "Prerequisites" && <PrerequisitesTab />}
    </div>
  );
}
