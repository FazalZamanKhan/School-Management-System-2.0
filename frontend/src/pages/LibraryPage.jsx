import { useState, useEffect, useCallback } from "react";
import { BookMarked, Search, BookCopy, RotateCcw, Plus, Pencil, Trash2, X } from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState } from "./ui";
import { formatDate, formatCurrency } from "./format";
import { apiFetch, jsonHeaders } from "../api";
import { useToast } from "../toast";

const BOOKS_URL = "/api/library/books/";
const ISSUES_URL = "/api/library/issues/";
const CAMPUSES_URL = "/api/schools/campuses/";

const copyStatusClass = (status) =>
  ({ available: "active", issued: "info", lost: "warn", damaged: "inactive" })[status] || "info";

const BOOK_CATEGORY_CHOICES = [
  { value: "fiction", label: "Fiction" },
  { value: "non_fiction", label: "Non-Fiction" },
  { value: "textbook", label: "Textbook" },
  { value: "reference", label: "Reference" },
  { value: "science", label: "Science" },
  { value: "math", label: "Mathematics" },
  { value: "literature", label: "Literature" },
  { value: "history", label: "History" },
  { value: "geography", label: "Geography" },
  { value: "other", label: "Other" },
];

const EMPTY_BOOK_FORM = {
  title: "",
  campus: "",
  author: "",
  isbn: "",
  publisher: "",
  publication_year: "",
  category: "other",
  description: "",
  total_copies: 1,
};

export default function LibraryPage() {
  const toast = useToast();
  const [tab, setTab] = useState("books");
  const [books, setBooks] = useState(null);
  const [issues, setIssues] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [message, setMessage] = useState("");
  const [returning, setReturning] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_BOOK_FORM);
  const [campuses, setCampuses] = useState([]);

  const [copiesBook, setCopiesBook] = useState(null);
  const [copiesError, setCopiesError] = useState("");
  const [copySaving, setCopySaving] = useState(false);

  const loadCampuses = useCallback(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadCampuses();
  }, [loadCampuses]);

  const loadBooks = () => {
    setLoading(true);
    setError("");

    const params = new URLSearchParams();

    if (search.trim()) {
      params.append("q", search.trim());
    }

    if (category) {
      params.append("category", category);
    }

    fetch(`${BOOKS_URL}?${params.toString()}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(detail?.detail || detail?.message || `Unable to load books (${response.status}).`);
        }
        return response.json();
      })
      .then((data) => {
        setBooks(data.results || data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  const loadIssues = () => {
    setLoading(true);
    setError("");

    fetch(ISSUES_URL, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(detail?.detail || detail?.message || `Unable to load book issues (${response.status}).`);
        }
        return response.json();
      })
      .then((data) => {
        setIssues(data.results || data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  const switchTab = (next) => {
    setTab(next);
    setMessage("");

    if (next === "books" && books === null) {
      loadBooks();
    } else if (next === "issues" && issues === null) {
      loadIssues();
    }
  };

  const handleReturn = async (issueId) => {
    setReturning(issueId);
    setMessage("");

    try {
      await apiFetch(
        `${ISSUES_URL}${issueId}/return/`,
        { method: "POST", headers: jsonHeaders() },
        "Could not return the book."
      );

      setMessage("Book returned successfully.");
      toast.success("Book returned successfully.");
      setIssues(null);
      loadIssues();
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setReturning(null);
    }
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setForm(EMPTY_BOOK_FORM);
  };

  const openAddBook = () => {
    setEditing(null);
    setForm(EMPTY_BOOK_FORM);
    setShowForm(true);
  };

  const openEditBook = (book) => {
    setEditing(book);
    setForm({
      title: book.title || "",
      campus: book.campus ?? "",
      author: book.author || "",
      isbn: book.isbn || "",
      publisher: book.publisher || "",
      publication_year: book.publication_year ?? "",
      category: book.category || "other",
      description: book.description || "",
      total_copies: book.total_copies ?? 1,
    });
    setShowForm(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      title: form.title,
      campus: form.campus || null,
      author: form.author,
      isbn: form.isbn,
      publisher: form.publisher,
      publication_year: form.publication_year ? Number(form.publication_year) : null,
      category: form.category,
      description: form.description,
      total_copies: Number(form.total_copies) || 1,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BOOKS_URL}${editing.id}/` : BOOKS_URL;

      await apiFetch(url, {
        method: isEditing ? "PATCH" : "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      }, `Unable to ${isEditing ? "update" : "create"} book.`);

      closeForm();
      setMessage(isEditing ? "Book updated successfully." : "Book created successfully.");
      toast.success(isEditing ? "Book updated successfully." : "Book created successfully.");
      loadBooks();
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteBook = async (book) => {
    if (!window.confirm(`Delete book "${book.title}"? This cannot be undone.`)) return;

    setError("");

    try {
      await apiFetch(`${BOOKS_URL}${book.id}/`, {
        method: "DELETE",
        headers: jsonHeaders(),
      }, "Unable to delete book.");

      setMessage("Book deleted successfully.");
      toast.success(`"${book.title}" deleted.`);
      loadBooks();
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    }
  };

  const openCopies = (book) => {
    setCopiesError("");
    setCopiesBook(book);
  };

  const refreshCopiesBook = () => {
    if (!copiesBook) return;
    apiFetch(`${BOOKS_URL}${copiesBook.id}/`)
      .then((data) => setCopiesBook((current) => (current ? { ...data } : current)))
      .catch(() => {});
  };

  const closeCopies = () => {
    setCopiesBook(null);
    setCopySaving(false);
    setCopiesError("");
  };

  const addCopy = async () => {
    if (!copiesBook) return;
    setCopySaving(true);
    setCopiesError("");

    try {
      await apiFetch(
        `${BOOKS_URL}${copiesBook.id}/copies/`,
        {
          method: "POST",
          headers: jsonHeaders(),
          body: JSON.stringify({ book: copiesBook.id }),
        },
        "Unable to add a copy."
      );
      loadBooks();
      refreshCopiesBook();
      toast.success("Copy added.");
    } catch (err) {
      setCopiesError(err.message);
      toast.error(err.message);
    } finally {
      setCopySaving(false);
    }
  };

  const deleteCopy = async (copy) => {
    if (!copiesBook) return;
    if (!window.confirm(`Delete copy "${copy.barcode || copy.id}"? This cannot be undone.`)) return;

    setCopiesError("");

    try {
      await apiFetch(
        `${BOOKS_URL}${copiesBook.id}/copies/${copy.id}/`,
        { method: "DELETE", headers: jsonHeaders() },
        "Unable to delete the copy."
      );
      loadBooks();
      refreshCopiesBook();
      toast.success(`Copy ${copy.barcode || copy.id} deleted.`);
    } catch (err) {
      setCopiesError(err.message);
      toast.error(err.message);
    }
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Library"
        title="Library"
        subtitle="Manage the school library catalog and book issues."
        action={
          <button type="button" className="primary-button" onClick={openAddBook}>
            <Plus size={15} /> Add Book
          </button>
        }
      />

      {message && (
        <div className="state-card success">
          <strong>{message}</strong>
        </div>
      )}

      <div className="tabs">
        <button
          className={`tab-button ${tab === "books" ? "active" : ""}`}
          onClick={() => switchTab("books")}
        >
          Books
        </button>

        <button
          className={`tab-button ${tab === "issues" ? "active" : ""}`}
          onClick={() => switchTab("issues")}
        >
          Issues
        </button>
      </div>

      {tab === "books" && (
        <div className="panel">
          <PanelHeader
            title="Book Catalog"
            subtitle="books found"
            count={books ? books.length : null}
          />

          <div className="filter-row">
            <div className="filter-search">
              <Search size={18} />

              <input
                type="text"
                placeholder="Search by title, author, or ISBN..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>

            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All categories</option>
              {BOOK_CATEGORY_CHOICES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>

            <button type="button" className="primary-button" onClick={loadBooks}>
              Search
            </button>
          </div>

          <StateArea loading={loading} error={error} onRetry={loadBooks}>
            {!books || books.length === 0 ? (
              <EmptyState
                icon={BookMarked}
                title="No books found"
                message="Add books in the admin panel or adjust your filters."
              />
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>TITLE</th>
                      <th>AUTHOR</th>
                      <th>ISBN</th>
                      <th>CATEGORY</th>
                      <th>COPIES</th>
                      <th>AVAILABLE</th>
                      <th>ISSUED</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>

                  <tbody>
                    {books.map((book) => (
                      <tr key={book.id}>
                        <td>
                          <strong>{book.title}</strong>
                        </td>

                        <td>{book.author || "\u2014"}</td>

                        <td>{book.isbn || "\u2014"}</td>

                        <td>{book.category_display || "\u2014"}</td>

                        <td>{book.total_copies ?? 0}</td>

                        <td>
                          <span className="status-badge active">
                            {book.available_copies ?? 0}
                          </span>
                        </td>

                        <td>{book.issued_copies ?? 0}</td>

                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openEditBook(book)}
                          >
                            <Pencil size={13} />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openCopies(book)}
                          >
                            <BookCopy size={13} />
                            Copies
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => handleDeleteBook(book)}
                          >
                            <Trash2 size={13} />
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </StateArea>
        </div>
      )}

      {tab === "issues" && (
        <div className="panel">
          <PanelHeader
            title="Book Issues"
            subtitle="issue records"
            count={issues ? issues.length : null}
          />

          <StateArea loading={loading} error={error} onRetry={loadIssues}>
            {!issues || issues.length === 0 ? (
              <EmptyState
                icon={BookCopy}
                title="No issues recorded"
                message="Issue records will appear here once books are lent out."
              />
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>BOOK</th>
                      <th>BARCODE</th>
                      <th>BORROWER</th>
                      <th>ISSUE DATE</th>
                      <th>DUE DATE</th>
                      <th>RETURN DATE</th>
                      <th>FINE</th>
                      <th>STATUS</th>
                      <th>ACTION</th>
                    </tr>
                  </thead>

                  <tbody>
                    {issues.map((issue) => (
                      <tr key={issue.id}>
                        <td>
                          <strong>{issue.book_title}</strong>
                        </td>

                        <td>{issue.barcode || "\u2014"}</td>

                        <td>{issue.borrower || "\u2014"}</td>

                        <td>{formatDate(issue.issue_date)}</td>

                        <td>{formatDate(issue.due_date)}</td>

                        <td>{formatDate(issue.return_date)}</td>

                        <td>{formatCurrency(issue.fine)}</td>

                        <td>
                          <span className={`status-badge ${issue.status === "returned" ? "inactive" : "warn"}`}>
                            {issue.status ? issue.status.charAt(0).toUpperCase() + issue.status.slice(1) : "\u2014"}
                          </span>
                        </td>

                        <td>
                          {issue.status !== "returned" ? (
                            <button
                              type="button"
                              className="table-action"
                              disabled={returning === issue.id}
                              onClick={() => handleReturn(issue.id)}
                            >
                              <RotateCcw size={14} />
                              {returning === issue.id ? "Returning..." : "Return"}
                            </button>
                          ) : (
                            <span className="muted">{"\u2014"}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </StateArea>
        </div>
      )}

      {showForm && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={editing ? "Edit Book" : "Add Book"}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeForm();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editing ? "Edit Book" : "Add Book"}</h3>
                <p>{editing ? "Update the book details." : "Add a new book to the catalog."}</p>
              </div>
              <button className="modal-close" aria-label="Close" onClick={closeForm} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="form-section">
                <h4>Book Details</h4>
                <div className="form-grid">
                  <label className="form-span">
                    Title
                    <input name="title" value={form.title} onChange={handleChange} required />
                  </label>

                  <label>
                    Campus
                    <select name="campus" value={form.campus} onChange={handleChange}>
                      <option value="">No campus</option>
                      {campuses.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Author
                    <input name="author" value={form.author} onChange={handleChange} />
                  </label>

                  <label>
                    ISBN
                    <input name="isbn" value={form.isbn} onChange={handleChange} />
                  </label>

                  <label>
                    Publisher
                    <input name="publisher" value={form.publisher} onChange={handleChange} />
                  </label>

                  <label>
                    Publication Year
                    <input
                      type="number"
                      name="publication_year"
                      value={form.publication_year}
                      onChange={handleChange}
                      min="1000"
                      max="2099"
                    />
                  </label>

                  <label>
                    Category
                    <select name="category" value={form.category} onChange={handleChange}>
                      {BOOK_CATEGORY_CHOICES.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Total Copies
                    <input
                      type="number"
                      name="total_copies"
                      value={form.total_copies}
                      onChange={handleChange}
                      min="1"
                      required
                    />
                  </label>

                  <label className="form-span">
                    Description
                    <textarea name="description" value={form.description} onChange={handleChange} rows="3" />
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={closeForm} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <Plus size={17} />
                  {saving ? "Saving..." : editing ? "Save Changes" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {copiesBook && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={`Copies — ${copiesBook.title}`}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeCopies();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>Copies — {copiesBook.title}</h3>
                <p>Manage the individual physical copies of this book.</p>
              </div>
              <button className="modal-close" aria-label="Close" onClick={closeCopies}>
                <X size={18} />
              </button>
            </div>

            {copiesError && <div className="state-card error">{copiesError}</div>}

            <div className="form-section">
              <div className="filter-row" style={{ marginBottom: 12 }}>
                <button
                  type="button"
                  className="primary-button"
                  disabled={copySaving}
                  onClick={addCopy}
                >
                  <Plus size={15} />
                  {copySaving ? "Adding..." : "Add Copy"}
                </button>
              </div>

              {(copiesBook.copies || []).length === 0 ? (
                <p className="muted">No copies exist for this book yet.</p>
              ) : (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>BARCODE</th>
                        <th>STATUS</th>
                        <th>ADDED</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(copiesBook.copies || []).map((copy) => (
                        <tr key={copy.id}>
                          <td><code>{copy.barcode || "—"}</code></td>
                          <td>
                            <span className={`status-badge ${copyStatusClass(copy.status)}`}>
                              {copy.status || "available"}
                            </span>
                          </td>
                          <td>{formatDate(copy.created_at)}</td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <button
                              type="button"
                              className="table-action danger"
                              onClick={() => deleteCopy(copy)}
                            >
                              <Trash2 size={13} />
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
