import { useEffect, useMemo, useState } from "react";
import { getKnowledgeBase } from "../api";
import { BookIcon } from "../icons";
import "./KnowledgeBase.css";

export default function KnowledgeBase() {
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");

  useEffect(() => {
    getKnowledgeBase()
      .then(setDocs)
      .catch((err) => setError(err.message || "Could not load the knowledge base."));
  }, []);

  const categories = useMemo(() => {
    if (!docs) return [];
    return Array.from(new Set(docs.map((d) => d.category))).sort();
  }, [docs]);

  const filtered = useMemo(() => {
    if (!docs) return [];
    const q = search.trim().toLowerCase();
    return docs.filter((d) => {
      const matchesCategory = category === "all" || d.category === category;
      const matchesSearch = !q || d.document_title.toLowerCase().includes(q);
      return matchesCategory && matchesSearch;
    });
  }, [docs, search, category]);

  return (
    <div className="panel kb-panel">
      <div className="kb-header">
        <div className="kb-icon"><BookIcon width={20} height={20} /></div>
        <div>
          <h1>Knowledge Base</h1>
          <p>Documents JIRVA retrieves evidence from.</p>
        </div>
      </div>

      {error && <div className="form-error">{error}</div>}

      {!docs && !error && <p>Loading...</p>}

      {docs && (
        <>
          <div className="kb-controls">
            <input
              type="text"
              placeholder="Search by document title..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="kb-search"
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="kb-filter"
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <p className="kb-count">
            {filtered.length} of {docs.length} document{docs.length === 1 ? "" : "s"}
          </p>

          <table className="kb-table">
            <thead>
              <tr>
                <th>Document Title</th>
                <th>Category</th>
                <th>Source Type</th>
                <th>Chunks</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.document_id}>
                  <td>
                    <a href={d.source_url} target="_blank" rel="noreferrer">
                      {d.document_title}
                    </a>
                  </td>
                  <td>{d.category}</td>
                  <td>{d.source_type}</td>
                  <td>{d.chunk_count ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 && <p className="kb-empty">No documents match your search.</p>}
        </>
      )}
    </div>
  );
}
