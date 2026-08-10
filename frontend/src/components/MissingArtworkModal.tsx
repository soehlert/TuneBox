import React, { useState, useEffect } from "react";
import axios from "axios";
import { getApiUrl } from "../utils";
import "./MissingArtworkModal.css";

interface MissingArtworkModalProps {
  type: "artist" | "album";
  onClose: () => void;
  onRefreshed?: () => void;
}

interface MissingItem {
  id: number;
  title: string;
  subtitle: string;
}

export const MissingArtworkModal: React.FC<MissingArtworkModalProps> = ({
  type,
  onClose,
  onRefreshed,
}) => {
  const [items, setItems] = useState<MissingItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);

  const fetchItems = (query: string = "") => {
    setLoading(true);
    axios
      .get(getApiUrl(`/api/stats/missing-artwork?type=${type}&query=${encodeURIComponent(query)}`))
      .then((res) => {
        setItems(res.data.items || []);
      })
      .catch((err) => console.error("Failed to load missing artwork items:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchItems(searchQuery);
  }, [type, searchQuery]);

  const handleCopy = (id: number, textToCopy: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(textToCopy);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const handleRefetch = (id: number) => {
    setSyncingId(id);
    axios
      .post(getApiUrl("/api/stats/refetch-artwork"), { type, id })
      .then((res) => {
        if (res.data.success) {
          fetchItems(searchQuery);
          if (onRefreshed) {
            onRefreshed();
          }
        } else {
          alert("Artwork re-sync completed, but no new image URL was found on Plex server.");
        }
      })
      .catch((err) => {
        console.error("Failed to re-sync artwork from Plex:", err);
        alert("Failed to connect to primary Plex server to re-sync artwork.");
      })
      .finally(() => setSyncingId(null));
  };

  const titleText = type === "artist" ? "Missing Artist Artwork" : "Missing Album Artwork";

  return (
    <div className="missing-art-modal-overlay" onClick={onClose}>
      <div className="missing-art-modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="missing-art-modal-header">
          <h3 className="missing-art-modal-title">
            <span>🖼️</span> {titleText} ({items.length})
          </h3>
          <button className="missing-art-modal-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="missing-art-modal-search">
          <input
            type="text"
            className="missing-art-modal-search-input"
            placeholder={`Filter missing ${type}s by name...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="missing-art-modal-list">
          {loading ? (
            <p style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "13px", margin: 0, textAlign: "center", padding: "20px" }}>
              Loading missing items...
            </p>
          ) : items.length === 0 ? (
            <p style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "13px", margin: 0, textAlign: "center", padding: "20px" }}>
              {searchQuery ? "No matching items found." : `All ${type}s on your primary server have artwork! 🎉`}
            </p>
          ) : (
            items.map((item) => (
              <div key={item.id} className="missing-art-modal-item">
                <div className="missing-art-modal-item-info">
                  <span className="missing-art-modal-item-title">{item.title}</span>
                  {item.subtitle && <span className="missing-art-modal-item-subtitle">{item.subtitle}</span>}
                </div>
                <div className="missing-art-modal-item-actions">
                  <button
                    className="missing-art-btn"
                    onClick={() => handleCopy(item.id, item.subtitle ? `${item.title} ${item.subtitle}` : item.title)}
                    title="Copy name to clipboard for Plex search"
                  >
                    {copiedId === item.id ? "✓ Copied" : "Copy Name"}
                  </button>
                  <button
                    className="missing-art-btn missing-art-btn-primary"
                    onClick={() => handleRefetch(item.id)}
                    disabled={syncingId === item.id}
                    title="Re-sync thumbnail URL from Plex"
                  >
                    {syncingId === item.id ? "Syncing..." : "Re-Sync"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
