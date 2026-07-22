import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Routes, Route, Link, useNavigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import ArtistList from "./components/ArtistList";
import ArtistAlbums from "./components/ArtistAlbums";
import TrackList from "./components/TrackList";
import MusicControls from "./components/MusicControls";
import Queue from "./components/Queue";
import theme from "./theme";
import TuneBoxLogo from "../public/TuneBox.svg";
import "./App.css";
import "./components/Queue.css";

const getApiUrl = (path: string) => {
  const isDev = window.location.port === "5173";
  const base = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;
  return `${base}${path}`;
};

interface GuestProfile {
  name: string;
  role: "member" | "guest";
}

interface ClientSession {
  client_id: string;
  name: string;
  role: string;
  is_display: boolean;
  connected_at: string;
}

const getClientId = () => {
  let cid = localStorage.getItem("tunebox_client_id");
  if (!cid) {
    cid = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).substring(2) + Date.now().toString(36);
    localStorage.setItem("tunebox_client_id", cid);
  }
  return cid;
};

const getWsUrl = () => {
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${host}/ws`;
};

// ─── Shared style helpers ─────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px",
  background: "#3a136b",
  color: "#fff",
  border: "1px solid rgba(255, 255, 255, 0.15)",
  borderRadius: "6px",
  fontSize: "14px",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: "14px",
  background: "#f5a623",
  color: "#1d083b",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer",
  fontWeight: "bold",
  fontSize: "15px",
  transition: "background 0.2s",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  color: "#ccc",
  fontSize: "13px",
  fontWeight: "bold",
  marginBottom: "8px",
};

// ─── Custom Confirm & Prompt Modals ──────────────────────────────────────────

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmModal({
  isOpen,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(29, 8, 59, 0.85)",
        backdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1200,
      }}
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        style={{
          background: "#2a0d52",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          borderRadius: "12px",
          padding: "28px 32px",
          width: "420px",
          maxWidth: "90vw",
          boxShadow: "0 20px 60px rgba(0, 0, 0, 0.6)",
        }}
      >
        <h3 style={{ margin: "0 0 12px 0", color: "#f5a623", fontSize: "18px" }}>{title}</h3>
        <p style={{ color: "#ccc", fontSize: "14px", margin: "0 0 24px 0", lineHeight: "1.4" }}>{message}</p>
        <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              padding: "10px 18px",
              background: "rgba(255, 255, 255, 0.08)",
              border: "1px solid rgba(255, 255, 255, 0.2)",
              color: "#fff",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "bold",
              fontSize: "14px",
            }}
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: "10px 18px",
              background: "#f5a623",
              border: "none",
              color: "#1d083b",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "bold",
              fontSize: "14px",
            }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

interface PromptModalProps {
  isOpen: boolean;
  title: string;
  message?: string;
  initialValue?: string;
  placeholder?: string;
  saveText?: string;
  cancelText?: string;
  onSave: (value: string) => void;
  onCancel: () => void;
}

function PromptModal({
  isOpen,
  title,
  message,
  initialValue = "",
  placeholder = "",
  saveText = "Save",
  cancelText = "Cancel",
  onSave,
  onCancel,
}: PromptModalProps) {
  const [val, setVal] = useState(initialValue);

  useEffect(() => {
    setVal(initialValue);
  }, [initialValue, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (val.trim()) {
      onSave(val.trim());
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(29, 8, 59, 0.85)",
        backdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1200,
      }}
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        style={{
          background: "#2a0d52",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          borderRadius: "12px",
          padding: "28px 32px",
          width: "420px",
          maxWidth: "90vw",
          boxShadow: "0 20px 60px rgba(0, 0, 0, 0.6)",
        }}
      >
        <h3 style={{ margin: "0 0 12px 0", color: "#f5a623", fontSize: "18px" }}>{title}</h3>
        {message && <p style={{ color: "#ccc", fontSize: "14px", margin: "0 0 16px 0" }}>{message}</p>}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <input
            type="text"
            value={val}
            placeholder={placeholder}
            onChange={(e) => setVal(e.target.value)}
            style={inputStyle}
            autoFocus
          />
          <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onCancel}
              style={{
                padding: "10px 18px",
                background: "rgba(255, 255, 255, 0.08)",
                border: "1px solid rgba(255, 255, 255, 0.2)",
                color: "#fff",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: "bold",
                fontSize: "14px",
              }}
            >
              {cancelText}
            </button>
            <button
              type="submit"
              style={{
                padding: "10px 18px",
                background: "#f5a623",
                border: "none",
                color: "#1d083b",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: "bold",
                fontSize: "14px",
              }}
            >
              {saveText}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Settings Modal ───────────────────────────────────────────────────────────

interface SettingsModalProps {
  adminToken: string;
  onClose: () => void;
  instanceName: string;
  setInstanceName: (val: string) => void;
}

function SettingsModal({ adminToken, onClose, instanceName, setInstanceName }: SettingsModalProps) {
  const [plexUsername, setPlexUsername] = useState("");
  const [localInstanceName, setLocalInstanceName] = useState(instanceName);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);
  const [servers, setServers] = useState<string[]>([]);
  const [selectedServer, setSelectedServer] = useState("");
  const [players, setPlayers] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [clients, setClients] = useState<ClientSession[]>([]);

  const handleRefreshResources = async () => {
    setRefreshing(true);
    setMsg("Refreshing devices...");
    try {
      const res = await axios.get(getApiUrl("/api/auth/resources?refresh=true"));
      setServers(res.data.servers ?? []);
      setPlayers(res.data.players ?? []);
      setMsg("✓ Devices refreshed!");
    } catch (err) {
      console.error("Failed to refresh resources:", err);
      setMsg("✗ Failed to refresh devices.");
    } finally {
      setRefreshing(false);
    }
  };

  const fetchClients = () => {
    axios
      .get(getApiUrl("/api/auth/clients"), {
        headers: { "x-admin-token": adminToken },
      })
      .then((res) => {
        setClients(res.data ?? []);
      })
      .catch(console.error);
  };

  useEffect(() => {
    axios
      .get(getApiUrl("/api/auth/settings"), {
        headers: { "x-admin-token": adminToken },
      })
      .then((res) => {
        setPlexUsername(res.data.plex_username ?? "");
        setSelectedServer(res.data.plex_server_name ?? "");
        setSelectedPlayer(res.data.client_name ?? "");
      })
      .catch(console.error);

    axios
      .get(getApiUrl("/api/auth/resources"))
      .then((res) => {
        setServers(res.data.servers ?? []);
        setPlayers(res.data.players ?? []);
      })
      .catch(console.error);
  }, [adminToken]);

  useEffect(() => {
    if (players.length > 0 && (!selectedPlayer || (selectedPlayer !== "disabled" && !players.includes(selectedPlayer)))) {
      setSelectedPlayer(players[0]);
    }
  }, [players, selectedPlayer]);

  useEffect(() => {
    fetchClients();
    const interval = setInterval(fetchClients, 3000);
    return () => clearInterval(interval);
  }, [adminToken]);

  const handleSetDisplay = async (clientId: string) => {
    try {
      await axios.post(
        getApiUrl(`/api/auth/clients/${clientId}/set-display`),
        {},
        { headers: { "x-admin-token": adminToken } }
      );
      fetchClients();
    } catch (err) {
      console.error("Failed to set display:", err);
    }
  };

  const handleUnsetDisplay = async (clientId: string) => {
    try {
      await axios.post(
        getApiUrl(`/api/auth/clients/${clientId}/unset-display`),
        {},
        { headers: { "x-admin-token": adminToken } }
      );
      fetchClients();
    } catch (err) {
      console.error("Failed to unset display:", err);
    }
  };

  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [renameState, setRenameState] = useState<{ isOpen: boolean; clientId: string; currentName: string }>({
    isOpen: false,
    clientId: "",
    currentName: "",
  });

  const handleOpenRename = (clientId: string, currentName: string) => {
    setRenameState({ isOpen: true, clientId, currentName });
  };

  const handleExecuteRename = async (newName: string) => {
    const clientId = renameState.clientId;
    setRenameState({ isOpen: false, clientId: "", currentName: "" });
    try {
      await axios.post(
        getApiUrl(`/api/auth/clients/${clientId}/rename`),
        { name: newName },
        { headers: { "x-admin-token": adminToken } }
      );
      fetchClients();
    } catch (err) {
      console.error("Failed to rename device:", err);
    }
  };

  const handleExecuteClearQueue = async () => {
    setConfirmClearOpen(false);
    try {
      await axios.post(
        getApiUrl("/api/music/clear-queue"),
        {},
        { headers: { "x-admin-token": adminToken } }
      );
      setMsg("✓ Playback queue cleared!");
    } catch (err) {
      console.error("Failed to clear queue:", err);
      setMsg("✗ Failed to clear queue.");
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      localStorage.setItem("tunebox_instance_name", localInstanceName);
      setInstanceName(localInstanceName);

      await axios.post(
        getApiUrl("/api/auth/settings"),
        { plex_username: plexUsername, client_name: selectedPlayer, plex_server_name: selectedServer },
        { headers: { "x-admin-token": adminToken } }
      );
      sessionStorage.clear();
      setMsg("✓ Settings saved! Switching server...");
      setTimeout(() => {
        window.location.href = window.location.origin + "/";
      }, 300);
    } catch {
      setMsg("✗ Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(29, 8, 59, 0.8)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#2a0d52",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          borderRadius: "12px",
          padding: "36px",
          width: "480px",
          maxWidth: "90vw",
          boxShadow: "0 20px 60px rgba(29, 8, 59, 0.5)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
          <h2 style={{ margin: 0, color: "#f5a623", fontSize: "20px" }}>⚙ Jukebox Settings</h2>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "rgba(255, 255, 255, 0.4)", fontSize: "22px", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
          <div>
            <label style={labelStyle}>Plex Username</label>
            <input
              type="text"
              value={plexUsername}
              onChange={(e) => setPlexUsername(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>TuneBox Instance Name</label>
            <input
              type="text"
              value={localInstanceName}
              onChange={(e) => setLocalInstanceName(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label style={labelStyle}>Plex Player (Playback Device)</label>
              <button
                type="button"
                onClick={handleRefreshResources}
                disabled={refreshing}
                style={{
                  background: "none",
                  border: "none",
                  color: "#ffc107",
                  cursor: "pointer",
                  fontSize: "12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "0 0 8px 0"
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>refresh</span>
                {refreshing ? "Refreshing..." : "Refresh"}
              </button>
            </div>
            {players.length > 0 ? (
              <select
                value={selectedPlayer}
                onChange={(e) => setSelectedPlayer(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="disabled">None (Released / Disconnected)</option>
                {players.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                placeholder="Enter player name manually (or 'disabled')"
                value={selectedPlayer}
                onChange={(e) => setSelectedPlayer(e.target.value)}
                style={inputStyle}
              />
            )}
          </div>
          <div>
            <label style={labelStyle}>Plex Media Server</label>
            {servers.length > 0 ? (
              <select
                value={selectedServer}
                onChange={(e) => setSelectedServer(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                {servers.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                placeholder="Enter server name manually"
                value={selectedServer}
                onChange={(e) => setSelectedServer(e.target.value)}
                style={inputStyle}
              />
            )}
          </div>

          {msg && (
            <div
              style={{
                padding: "10px",
                borderRadius: "6px",
                background: msg.startsWith("✓") ? "#1a3a1a" : "#3a1a1a",
                color: msg.startsWith("✓") ? "#5cdd5c" : "#ff6b6b",
                fontSize: "13px",
                textAlign: "center",
              }}
            >
              {msg}
            </div>
          )}

          <div style={{ display: "flex", gap: "12px", marginTop: "10px" }}>
            <button
              type="submit"
              disabled={saving}
              style={{ ...btnStyle, flex: 1 }}
              onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
              onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}
            >
              {saving ? "Saving..." : "Save Settings"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmClearOpen(true)}
              style={{
                background: "rgba(255, 107, 107, 0.15)",
                border: "1px solid #ff6b6b",
                color: "#ff6b6b",
                borderRadius: "8px",
                padding: "10px 16px",
                fontSize: "14px",
                fontWeight: "bold",
                cursor: "pointer",
                transition: "background-color 0.2s, color 0.2s",
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.backgroundColor = "#ff6b6b";
                e.currentTarget.style.color = "#fff";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.backgroundColor = "rgba(255, 107, 107, 0.15)";
                e.currentTarget.style.color = "#ff6b6b";
              }}
            >
              Clear Queue
            </button>
          </div>
        </form>

        <div style={{ marginTop: "24px", borderTop: "1px solid rgba(255, 255, 255, 0.15)", paddingTop: "20px" }}>
          <h3 style={{ margin: "0 0 12px 0", color: "#f5a623", fontSize: "16px" }}>💻 Connected Devices</h3>
          {clients.length === 0 ? (
            <p style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "13px", margin: 0 }}>No devices connected.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "200px", overflowY: "auto" }}>
              {/* Display screens at the top */}
              {clients.filter(c => c.is_display).map((c) => (
                <div
                  key={c.client_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: "rgba(92, 221, 92, 0.08)",
                    border: "1px solid rgba(92, 221, 92, 0.2)",
                    borderRadius: "6px",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                      {c.name} {c.client_id === getClientId() ? " (This Device)" : ""}
                      <span
                        className="material-symbols-outlined"
                        onClick={() => handleOpenRename(c.client_id, c.name)}
                        style={{ fontSize: "16px", cursor: "pointer", color: "var(--color-primary)", opacity: 0.7, transition: "opacity 0.2s" }}
                        onMouseOver={(e) => e.currentTarget.style.opacity = "1"}
                        onMouseOut={(e) => e.currentTarget.style.opacity = "0.7"}
                        title="Rename Device"
                      >
                        edit
                      </span>
                    </span>
                    <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "11px", textTransform: "capitalize" }}>
                      Role: {c.role} • Display Screen
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ color: "#5cdd5c", fontSize: "12px", fontWeight: "bold", marginRight: "8px" }}>
                      ✓ Display
                    </span>
                    <button
                      onClick={() => handleUnsetDisplay(c.client_id)}
                      style={{
                        background: "transparent",
                        border: "1px solid rgba(255, 107, 107, 0.4)",
                        color: "#ff6b6b",
                        borderRadius: "4px",
                        padding: "6px 10px",
                        fontSize: "11px",
                        fontWeight: "bold",
                        cursor: "pointer",
                        transition: "background-color 0.2s",
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(255, 107, 107, 0.1)";
                      }}
                      onMouseOut={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                      }}
                    >
                      Undisplay
                    </button>
                  </div>
                </div>
              ))}

              {/* Divider if displays and others both exist */}
              {clients.filter(c => c.is_display).length > 0 && clients.filter(c => !c.is_display).length > 0 && (
                <div style={{ height: "1px", background: "rgba(255, 255, 255, 0.15)", margin: "8px 0" }} />
              )}

              {/* Other instances */}
              {clients.filter(c => !c.is_display).map((c) => (
                <div
                  key={c.client_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: "#3a136b",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    borderRadius: "6px",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                      {c.name} {c.client_id === getClientId() ? " (This Device)" : ""}
                      <span
                        className="material-symbols-outlined"
                        onClick={() => handleOpenRename(c.client_id, c.name)}
                        style={{ fontSize: "16px", cursor: "pointer", color: "var(--color-primary)", opacity: 0.7, transition: "opacity 0.2s" }}
                        onMouseOver={(e) => e.currentTarget.style.opacity = "1"}
                        onMouseOut={(e) => e.currentTarget.style.opacity = "0.7"}
                        title="Rename Device"
                      >
                        edit
                      </span>
                    </span>
                    <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "11px", textTransform: "capitalize" }}>
                      Role: {c.role}
                    </span>
                  </div>
                  {c.client_id !== getClientId() && (
                    <button
                      onClick={() => handleSetDisplay(c.client_id)}
                      style={{
                        background: "#f5a623",
                        color: "#1d083b",
                        border: "none",
                        borderRadius: "4px",
                        padding: "6px 10px",
                        fontSize: "11px",
                        fontWeight: "bold",
                        cursor: "pointer",
                      }}
                      onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                      onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}
                    >
                      Make Display
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <ConfirmModal
          isOpen={confirmClearOpen}
          title="Clear Playback Queue?"
          message="Are you sure you want to clear all tracks from the playback queue? This action will immediately empty the queue for all connected party guests."
          confirmText="Clear Queue"
          cancelText="Cancel"
          onConfirm={handleExecuteClearQueue}
          onCancel={() => setConfirmClearOpen(false)}
        />

        <PromptModal
          isOpen={renameState.isOpen}
          title="Rename Device"
          message={`Enter a new display name for device "${renameState.currentName}":`}
          initialValue={renameState.currentName}
          saveText="Save Name"
          cancelText="Cancel"
          onSave={handleExecuteRename}
          onCancel={() => setRenameState({ isOpen: false, clientId: "", currentName: "" })}
        />
      </div>
    </div>
  );
}

// ─── Guest Registration Modal ─────────────────────────────────────────────────

interface GuestModalProps {
  onJoin: (profile: GuestProfile) => void;
  onClose?: () => void;
}

function GuestModal({ onJoin, onClose }: GuestModalProps) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");
    try {
      const res = await axios.get(getApiUrl(`/api/auth/verify-username?username=${encodeURIComponent(trimmed)}`));
      const profile: GuestProfile = { name: trimmed, role: res.data.role };
      localStorage.setItem("tunebox_guest", JSON.stringify(profile));
      onJoin(profile);
    } catch {
      setError("Could not verify username. Joining as guest.");
      const profile: GuestProfile = { name: trimmed, role: "guest" };
      localStorage.setItem("tunebox_guest", JSON.stringify(profile));
      onJoin(profile);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.85)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          position: "relative",
          background: "#1e1e1e",
          border: "1px solid #333",
          borderRadius: "16px",
          padding: "40px",
          width: "380px",
          maxWidth: "90vw",
          textAlign: "center",
          boxShadow: "0 20px 60px rgba(0,0,0,0.9)",
        }}
      >
        {onClose && (
          <button
            onClick={onClose}
            style={{
              position: "absolute",
              top: "16px",
              right: "16px",
              background: "none",
              border: "none",
              color: "rgba(255, 255, 255, 0.4)",
              fontSize: "20px",
              cursor: "pointer",
              transition: "color 0.2s"
            }}
            onMouseOver={(e) => e.currentTarget.style.color = "#fff"}
            onMouseOut={(e) => e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)"}
          >
            ✕
          </button>
        )}
        <div style={{ fontSize: "40px", marginBottom: "16px" }}>🎵</div>
        <h2 style={{ color: "#f5a623", margin: "0 0 8px 0", fontSize: "22px" }}>Welcome to TuneBox!</h2>
        <p style={{ color: "#888", fontSize: "14px", marginBottom: "28px", lineHeight: "1.5" }}>
          Enter your Plex username to get verified voting power, or any nickname to join as a guest.
        </p>

        <form onSubmit={handleJoin} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <input
            type="text"
            placeholder="Your name or Plex username"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ ...inputStyle, textAlign: "center", fontSize: "16px", padding: "12px" }}
            autoFocus
          />
          {error && <div style={{ color: "#aaa", fontSize: "12px" }}>{error}</div>}
          <button
            type="submit"
            disabled={loading || !name.trim()}
            style={{ ...btnStyle, opacity: !name.trim() ? 0.5 : 1, cursor: !name.trim() ? "not-allowed" : "pointer" }}
            onMouseOver={(e) => name.trim() && (e.currentTarget.style.background = "#d48b17")}
            onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}
          >
            {loading ? "Joining..." : "Join Jukebox"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── User Badge ───────────────────────────────────────────────────────────────

function UserBadge({ profile, onLeave, onEditName }: { profile: GuestProfile; onLeave: () => void; onEditName: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "6px 12px",
        background: "#1e1e1e",
        borderRadius: "20px",
        border: "1px solid #333",
        fontSize: "13px",
        color: "#ccc",
        flexShrink: 0,
        whiteSpace: "nowrap",
      }}
    >
      <div
        onClick={onEditName}
        style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}
        title="Click to edit name"
      >
        <span style={{ color: profile.role === "member" ? "#5cdd5c" : "#f5a623" }}>
          {profile.role === "member" ? "✓" : "◉"}
        </span>
        <span style={{ fontWeight: 600 }}>{profile.name}</span>
        {profile.role === "member" && (
          <span style={{ fontSize: "10px", background: "#1a3a1a", color: "#5cdd5c", padding: "2px 6px", borderRadius: "10px", fontWeight: "bold" }}>
            2× votes
          </span>
        )}
      </div>
      <span style={{ width: "1px", height: "12px", background: "rgba(255,255,255,0.15)" }}></span>
      <span
        className="material-symbols-outlined"
        onClick={onLeave}
        style={{
          fontSize: "15px",
          cursor: "pointer",
          color: "rgba(255, 255, 255, 0.4)",
          transition: "color 0.2s"
        }}
        onMouseOver={(e) => e.currentTarget.style.color = "#ff6b6b"}
        onMouseOut={(e) => e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)"}
        title="Leave Jukebox"
      >
        logout
      </span>
    </div>
  );
}

// ─── Name Editing Modal ───────────────────────────────────────────────────────

interface NameModalProps {
  currentName: string;
  onSave: (newName: string) => void;
  onClose: () => void;
}

function NameModal({ currentName, onSave, onClose }: NameModalProps) {
  const [name, setName] = useState(currentName);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setLoading(true);
    try {
      await onSave(trimmed);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(29, 8, 59, 0.8)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1100,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#2a0d52",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          borderRadius: "16px",
          padding: "36px",
          width: "360px",
          textAlign: "center",
          boxShadow: "0 20px 60px rgba(29, 8, 59, 0.5)",
        }}
      >
        <h3 style={{ color: "#f5a623", margin: "0 0 16px 0", fontSize: "20px" }}>Change Account Name</h3>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <input
            type="text"
            placeholder="Enter new name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ ...inputStyle, textAlign: "center", fontSize: "16px", padding: "12px" }}
            autoFocus
          />
          <div style={{ display: "flex", gap: "10px" }}>
            <button
              type="button"
              onClick={onClose}
              style={{ ...btnStyle, background: "rgba(255,255,255,0.05)", color: "#fff", flex: 1 }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              style={{ ...btnStyle, flex: 1 }}
            >
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);

  // Wizard states
  const [step, setStep] = useState<number>(1);
  const [pinCode, setPinCode] = useState<string>("");
  const [pinId, setPinId] = useState<number | null>(null);
  const [authUrl, setAuthUrl] = useState<string>("");

  // Input states
  const [plexUsername, setPlexUsername] = useState<string>(
    () => localStorage.getItem("tunebox_setup_plex_username") ?? ""
  );
  const [localUsername, setLocalUsername] = useState<string>(
    () => localStorage.getItem("tunebox_setup_local_username") ?? ""
  );

  // Resources
  const [servers, setServers] = useState<string[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [players, setPlayers] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<string>("");
  const [customPlayer, setCustomPlayer] = useState<string>("");
  const [isManualConfig, setIsManualConfig] = useState<boolean>(false);
  const [customServer, setCustomServer] = useState<string>("");
  const [isFetchingResources, setIsFetchingResources] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Instance name for this browser session (stored in localStorage)
  const [instanceName, setInstanceName] = useState<string>(
    () => localStorage.getItem("tunebox_instance_name") ?? "Jukebox Screen"
  );

  // Display / kiosk mode — designated by the admin; persists in localStorage
  const [isDisplay, setIsDisplay] = useState<boolean>(
    () => localStorage.getItem("tunebox_display") === "true"
  );

  // Admin / guest state — must be React state so changes trigger re-renders
  const [adminToken, setAdminToken] = useState<string>(
    () => localStorage.getItem("tunebox_admin_token") ?? ""
  );
  const isAdmin = Boolean(adminToken) && !isDisplay;
  const [showSettings, setShowSettings] = useState(false);
  const [isMobileQueueOpen, setIsMobileQueueOpen] = useState(false);
  const [showNameModal, setShowNameModal] = useState(false);
  const [dismissedGuestModal, setDismissedGuestModal] = useState(false);
  const [guestProfile, setGuestProfile] = useState<GuestProfile | null>(() => {
    const raw = localStorage.getItem("tunebox_guest");
    return raw ? (JSON.parse(raw) as GuestProfile) : null;
  });

  // Artist library / Search states
  const navigate = useNavigate();
  const location = useLocation();

  // ── ?wizard URL param: force wizard flow for setup-flow testing ──────────────
  // When the URL contains ?wizard, clear stored admin token and guest profile so
  // the setup wizard always runs. Only runs once on mount.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("wizard")) {
      localStorage.removeItem("tunebox_admin_token");
      localStorage.removeItem("tunebox_guest");
      setAdminToken("");
      setGuestProfile(null);
      // Strip ?wizard from URL without a reload so the app behaves normally after
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
    }
    if (params.has("reset_display")) {
      localStorage.removeItem("tunebox_display");
      setIsDisplay(false);
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
    }
  }, []);

  const [artists, setArtists] = useState<any[]>([]);
  const [loadingArtists, setLoadingArtists] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLetter, setSelectedLetter] = useState("");
  const [filteredArtists, setFilteredArtists] = useState<any[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [accessibleServers, setAccessibleServers] = useState<any[]>([]);
  const [selectedServerIds, setSelectedServerIds] = useState<string[]>([]);
  const [showServerMenu, setShowServerMenu] = useState(false);
  const [showServerModal, setShowServerModal] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Clear search query when clear_search parameter is present
  useEffect(() => {
    if (location.search.includes("clear_search=true")) {
      setSearchTerm("");
      setSelectedLetter("");
    }
  }, [location.search]);

  // Close dropdown on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowServerMenu(false);
        setShowServerModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch accessible Plex servers
  useEffect(() => {
    if (!isConfigured) return;
    axios
      .get(getApiUrl("/api/music/servers"))
      .then((res) => {
        if (Array.isArray(res.data)) {
          setAccessibleServers(res.data);
          const primaryIds = res.data.filter((s: any) => s.is_primary).map((s: any) => s.server_id);
          if (primaryIds.length > 0) {
            setSelectedServerIds(primaryIds);
          } else if (res.data.length > 0) {
            setSelectedServerIds([res.data[0].server_id]);
          }
        }
      })
      .catch((err) => console.error("Error fetching servers:", err));
  }, [isConfigured]);

  // Debouncing hook logic
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchTerm]);

  useEffect(() => {
    // Only fetch if configured
    if (!isConfigured) return;

    const fetchArtists = async () => {
      try {
        const serverParam = selectedServerIds.length > 0 ? `&server_ids=${selectedServerIds.join(",")}` : "";
        const searchURL = getApiUrl(`/api/music/unified-search?query=${encodeURIComponent(searchTerm)}${serverParam}`);
        const artistListURL = getApiUrl("/api/music/artists");
        const endpoint = debouncedSearchTerm ? searchURL : artistListURL;

        const response = await axios.get(endpoint);
        let data = response.data;

        if (debouncedSearchTerm) {
          setSearchResults(data);
        } else {
          // Only keep artists (exclude albums, tracks, etc.)
          data = data.filter((item: any) => item.name);

          // Sort the fetched data alphabetically by artist name
          const sortedArtists = data.sort((a: any, b: any) =>
            a.name && b.name ? a.name.localeCompare(b.name) : -1
          );

          setArtists(sortedArtists);
          setFilteredArtists(sortedArtists);
          setSearchResults([]);
        }
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setLoadingArtists(false);
      }
    };

    if (debouncedSearchTerm === "" || debouncedSearchTerm) {
      fetchArtists();
    } else {
      setLoadingArtists(false);
      setArtists([]);
    }
  }, [debouncedSearchTerm, isConfigured, selectedServerIds]);



  const handleAlphabetClick = (character: string) => {
    setSelectedLetter(character);
    setSearchTerm(""); // Clear search term so the full artist list is visible

    // Redirect to root if not on root
    if (location.pathname !== "/") {
      navigate("/");
    }

    // Preserve full artist list so user can scroll up and down continuously
    setFilteredArtists(artists);
  };

  // Manage client_control WebSocket connection
  useEffect(() => {
    // Only connect if the user has completed the wizard (admin), joined as guest, or is in display mode
    if (!isAdmin && !isDisplay && !guestProfile) {
      return;
    }

    const wsUrl = getWsUrl();
    const ws = new WebSocket(wsUrl);
    let pingInterval: number;
    let pongTimeout: number;

    const register = () => {
      if (ws.readyState === WebSocket.OPEN) {
        let name = "Unknown";
        let role = "guest";
        if (isAdmin) {
          name = `Admin (${instanceName})`;
          role = "admin";
        } else if (isDisplay) {
          name = localStorage.getItem("tunebox_display_name") || "Shared Display";
          role = "display";
        } else if (guestProfile) {
          name = guestProfile.name;
          role = guestProfile.role;
        }

        ws.send(
          JSON.stringify({
            type: "client_control",
            client_id: getClientId(),
            name,
            role,
            is_display: isDisplay,
          })
        );
      }
    };

    ws.onopen = () => {
      console.log("Client control WS opened");
      register();

      // Start ping heartbeat
      pingInterval = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "heartbeat", message: "ping" }));
          pongTimeout = window.setTimeout(() => {
            console.warn("Client control WS ping timeout, closing");
            ws.close();
          }, 4000);
        }
      }, 10000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "set_display_mode") {
          console.log("Received set_display_mode WS push!");
          localStorage.setItem("tunebox_display", "true");
          setIsDisplay(true);
          if (guestProfile) {
            localStorage.setItem("tunebox_display_name", guestProfile.name);
          }
        } else if (data.type === "unset_display_mode") {
          console.log("Received unset_display_mode WS push!");
          localStorage.removeItem("tunebox_display");
          setIsDisplay(false);
        } else if (data.message === "pong") {
          window.clearTimeout(pongTimeout);
        }
      } catch (err) {
        console.error("Error parsing WS message:", err);
      }
    };

    ws.onclose = () => {
      console.log("Client control WS closed");
      window.clearInterval(pingInterval);
      window.clearTimeout(pongTimeout);
    };

    return () => {
      ws.close();
    };
  }, [isAdmin, isDisplay, guestProfile, instanceName]);

  useEffect(() => {
    checkStatus();
    if (!isAuthenticated) {
      const interval = setInterval(checkStatus, 3000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated]);

  const checkStatus = async () => {
    try {
      const res = await axios.get(getApiUrl("/api/auth/status"));
      setIsAuthenticated(res.data.authenticated);
      setIsConfigured(res.data.is_configured);

      if (res.data.plex_username) setPlexUsername(res.data.plex_username);
      if (res.data.client_name) setLocalUsername(res.data.client_name);

      // Testing-mode bypass: backend returns admin_token in status when TESTING=true
      // and setup has been completed. Store it so admin mode activates immediately.
      if (res.data.admin_token && !adminToken) {
        localStorage.setItem("tunebox_admin_token", res.data.admin_token);
        setAdminToken(res.data.admin_token);
      }

      if (res.data.authenticated) {
        if (res.data.is_configured) {
          setStep(4);
        } else {
          setStep(3);
          fetchResources();
        }
      }
    } catch (err) {
      console.error("Status check failed:", err);
      setIsAuthenticated(false);
      setIsConfigured(false);
    }
  };

  const handleStartLinking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localUsername.trim() || !plexUsername.trim()) {
      alert("Please enter both Plex username and TuneBox Instance Name.");
      return;
    }
    try {
      localStorage.setItem("tunebox_setup_plex_username", plexUsername);
      localStorage.setItem("tunebox_setup_local_username", localUsername);
      const res = await axios.post(getApiUrl("/api/auth/pin"));
      setPinCode(res.data.code);
      setPinId(res.data.pin_id);
      setAuthUrl(res.data.url);
      setStep(2);
    } catch (err) {
      console.error("Failed to request PIN:", err);
    }
  };

  useEffect(() => {
    if (step === 2 && pinId !== null) {
      const timer = setInterval(async () => {
        try {
          const res = await axios.get(getApiUrl(`/api/auth/check?pin_id=${pinId}`));
          if (res.data.authenticated) {
            clearInterval(timer);
            setIsAuthenticated(true);
            setStep(3);
            fetchResources();
          }
        } catch (err) {
          console.error("Error checking PIN status:", err);
        }
      }, 3000);
      return () => clearInterval(timer);
    }
  }, [step, pinId]);

  const fetchResources = async () => {
    setIsFetchingResources(true);
    try {
      const res = await axios.get(getApiUrl("/api/auth/resources"));
      setServers(res.data.servers);
      if (res.data.servers.length > 0) setSelectedServer(res.data.servers[0]);

      const fetchedPlayers = res.data.players || [];
      setPlayers(fetchedPlayers);
      if (fetchedPlayers.length > 0) {
        setSelectedPlayer(fetchedPlayers[0]);
      } else {
        setSelectedPlayer(localUsername);
      }
    } catch (err) {
      console.error("Failed to fetch resources:", err);
      setIsManualConfig(true);
    } finally {
      setIsFetchingResources(false);
    }
  };

  const handleSaveConfiguration = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    const serverName = isManualConfig ? customServer : selectedServer;
    const playerClientName = isManualConfig ? customPlayer : selectedPlayer;
    if (!serverName) {
      alert("Please select or enter a Plex server name.");
      setIsSubmitting(false);
      return;
    }
    try {
      const res = await axios.post(getApiUrl("/api/auth/configure"), {
        plex_username: plexUsername,
        client_name: playerClientName || localUsername,
        plex_server_name: serverName,
      });
      // Store admin token and update state so gear icon appears immediately
      if (res.data.admin_token) {
        localStorage.setItem("tunebox_admin_token", res.data.admin_token);
        setAdminToken(res.data.admin_token);
      }
      localStorage.removeItem("tunebox_setup_plex_username");
      localStorage.removeItem("tunebox_setup_local_username");
      localStorage.setItem("tunebox_instance_name", localUsername);
      setInstanceName(localUsername);
      setIsConfigured(true);
      setStep(4);
    } catch (err) {
      console.error("Save config failed:", err);
      alert("Failed to save configuration settings.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGuestLeave = () => {
    localStorage.removeItem("tunebox_guest");
    setGuestProfile(null);
    setDismissedGuestModal(false);
  };

  const handleSaveNewName = async (newName: string) => {
    try {
      const res = await axios.get(getApiUrl(`/api/auth/verify-username?username=${encodeURIComponent(newName)}`));
      const profile: GuestProfile = { name: newName, role: res.data.role };
      localStorage.setItem("tunebox_guest", JSON.stringify(profile));
      setGuestProfile(profile);
    } catch {
      const profile: GuestProfile = { name: newName, role: "guest" };
      localStorage.setItem("tunebox_guest", JSON.stringify(profile));
      setGuestProfile(profile);
    }
  };

  // Plain base URL for QR — no query params so guests don't accidentally enter display mode
  const joinUrl = `${window.location.protocol}//${window.location.hostname}${window.location.port ? `:${window.location.port}` : ""}`;

  // ── Loading spinner ──────────────────────────────────────────────────────────
  if (isAuthenticated === null) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#121212", color: "white" }}>
        <h3>Loading TuneBox...</h3>
      </div>
    );
  }

  // ── Jukebox Dashboard (configured) ──────────────────────────────────────────
  if (isAuthenticated && isConfigured && step === 4) {
    return (
      <ThemeProvider theme={theme}>
        <div className="app-container">
          {/* Ambient background glows */}
          <div className="ambient-background">
            <div className="glow-circle glow-top-right"></div>
            <div className="glow-circle glow-bottom-left"></div>
          </div>

          {/* Top Navbar */}
          <div className="navbar">
            <Link
              to="/"
              className="app-title-link"
              onClick={() => {
                setSearchTerm("");
                setSelectedLetter("");
                window.scrollTo(0, 0);
                const mainEl = document.querySelector(".main-content");
                if (mainEl) mainEl.scrollTop = 0;
              }}
            >
              <img src={TuneBoxLogo} alt="TuneBox Logo" className="logo" />
            </Link>

            {/* Server Connection Indicator */}
            {isConfigured && (
              <div
                className="server-indicator-badge"
                onClick={() => setShowServerModal(true)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "4px 10px",
                  background: "rgba(255, 255, 255, 0.07)",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  borderRadius: "16px",
                  fontSize: "11px",
                  fontWeight: 600,
                  color: "rgba(255, 255, 255, 0.75)",
                  whiteSpace: "nowrap",
                  cursor: "pointer",
                }}
                title="Click to view connected Plex server name"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "14px", color: "#5cdd5c" }}>dns</span>
                <span className="server-name-text">
                  {accessibleServers.find((s) => s.is_primary)?.name || "Plex Server"}
                </span>
              </div>
            )}

            <div className="navbar-right">
              {/* Search Box in Navbar */}
              <div
                className="navbar-search-container"
                onClick={() => searchInputRef.current?.focus()}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "20px", color: "rgba(255,255,255,0.4)", cursor: "pointer", flexShrink: 0 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    searchInputRef.current?.focus();
                  }}
                >
                  search
                </span>
                <input
                  ref={searchInputRef}
                  type="text"
                  className="navbar-search-input"
                  placeholder="Search Jukebox..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setSelectedLetter("");
                    if (location.pathname !== "/") {
                      navigate("/");
                    }
                  }}
                />
                {accessibleServers.length > 1 && (
                  <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <button
                      type="button"
                      onClick={() => setShowServerMenu(!showServerMenu)}
                      style={{
                        background: "none",
                        border: "none",
                        color: selectedServerIds.length > 1 ? "#f5a623" : "rgba(255,255,255,0.4)",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        padding: "4px",
                        marginRight: "4px",
                        transition: "color 0.2s",
                      }}
                      title="Select servers to search"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>dns</span>
                    </button>
                    {showServerMenu && isMobile &&
                      createPortal(
                        <div className="server-dropdown-overlay" onClick={() => setShowServerMenu(false)}>
                          <div className="server-dropdown-menu" onClick={(e) => e.stopPropagation()}>
                            <div className="server-dropdown-header">
                              <span>SEARCH LIBRARIES</span>
                              <button
                                type="button"
                                className="server-dropdown-close-btn"
                                onClick={() => setShowServerMenu(false)}
                              >
                                ✕
                              </button>
                            </div>
                            {accessibleServers.map((s) => {
                              const isChecked = selectedServerIds.includes(s.server_id);
                              return (
                                <label key={s.server_id} className="server-dropdown-item">
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={() => {
                                      if (isChecked) {
                                        if (selectedServerIds.length > 1) {
                                          setSelectedServerIds(selectedServerIds.filter((id) => id !== s.server_id));
                                        }
                                      } else {
                                        setSelectedServerIds([...selectedServerIds, s.server_id]);
                                      }
                                    }}
                                  />
                                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {s.name} {s.is_primary ? "(Home)" : ""}
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>,
                        document.body
                      )
                    }
                    {showServerMenu && !isMobile && (
                      <div className="server-dropdown-menu" onClick={(e) => e.stopPropagation()}>
                        <div className="server-dropdown-header">
                          <span>SEARCH LIBRARIES</span>
                        </div>
                        {accessibleServers.map((s) => {
                          const isChecked = selectedServerIds.includes(s.server_id);
                          return (
                            <label key={s.server_id} className="server-dropdown-item">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => {
                                  if (isChecked) {
                                    if (selectedServerIds.length > 1) {
                                      setSelectedServerIds(selectedServerIds.filter((id) => id !== s.server_id));
                                    }
                                  } else {
                                    setSelectedServerIds([...selectedServerIds, s.server_id]);
                                  }
                                }}
                              />
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {s.name} {s.is_primary ? "(Home)" : ""}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Admin identity badge */}
              {isAdmin && (
                <div
                  onClick={() => setShowSettings(true)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    background: "rgba(245, 166, 35, 0.15)",
                    border: "1px solid rgba(245, 166, 35, 0.35)",
                    borderRadius: "20px",
                    fontSize: "12px",
                    fontWeight: "bold",
                    color: "#f5a623",
                    cursor: "pointer",
                    flexShrink: 0,
                    whiteSpace: "nowrap"
                  }}
                  title="Admin Session — Click to open Settings"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>admin_panel_settings</span>
                  <span>{instanceName ? `Admin (${instanceName})` : "Admin"}</span>
                </div>
              )}

              {/* Guest user badge (top-right, for guests who have joined) */}
              {!isAdmin && guestProfile && (
                <UserBadge
                  profile={guestProfile}
                  onLeave={handleGuestLeave}
                  onEditName={() => setShowNameModal(true)}
                />
              )}

              {/* Join Jukebox button if guest dismissed registration modal */}
              {!isAdmin && !isDisplay && !guestProfile && dismissedGuestModal && (
                <button
                  onClick={() => setDismissedGuestModal(false)}
                  style={{
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid rgba(255, 255, 255, 0.15)",
                    color: "white",
                    padding: "6px 14px",
                    borderRadius: "20px",
                    fontFamily: "var(--font-body)",
                    fontSize: "12px",
                    fontWeight: "bold",
                    cursor: "pointer",
                    transition: "all 0.2s",
                    flexShrink: 0,
                    whiteSpace: "nowrap"
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.borderColor = "var(--color-primary)";
                    e.currentTarget.style.color = "var(--color-primary)";
                    e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.08)";
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.15)";
                    e.currentTarget.style.color = "white";
                    e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.05)";
                  }}
                >
                  Join Jukebox
                </button>
              )}
            </div>
          </div>

          {/* Persistent Alphabet Fast-Scroll Sidebar on Left */}
          <aside className="left-sidebar">
            <div className="alphabet-filter">
              <button
                onClick={() => handleAlphabetClick("0-9")}
                className={selectedLetter === "0-9" ? "active" : ""}
              >
                #
              </button>
              {"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((letter) => (
                <button
                  key={letter}
                  onClick={() => handleAlphabetClick(letter)}
                  className={selectedLetter === letter ? "active" : ""}
                >
                  {letter}
                </button>
              ))}
            </div>
          </aside>

          {/* Main Grid Wrapper */}
          <div className="main-wrapper">
            {/* Subpage content */}
            <div className="main-content">
              <div className="header-gradient"></div>
              <Routes>
                <Route
                  path="/"
                  element={
                    <ArtistList
                      filteredArtists={filteredArtists}
                      loading={loadingArtists}
                      searchResults={searchResults}
                      isSearching={Boolean(debouncedSearchTerm)}
                      selectedLetter={selectedLetter}
                    />
                  }
                />
                <Route path="/artists/:artistId/albums" element={<ArtistAlbums />} />
                <Route path="/albums/:albumId/tracks" element={<TrackList />} />
              </Routes>
            </div>

            {/* Sidebar: Queue + QR Code (non-admin shared display) */}
            <div className="queue-container">
              <Queue />
              {isDisplay && (
                <div
                  className="glass-panel"
                  style={{
                    position: "absolute",
                    bottom: "16px",
                    left: "16px",
                    right: "16px",
                    padding: "20px",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "12px",
                    background: "rgba(22, 6, 45, 0.95)",
                    border: "1px solid var(--color-glass-border)",
                    boxShadow: "0 -8px 32px rgba(0,0,0,0.5)",
                    zIndex: 100,
                  }}
                >
                  <p style={{ color: "#aaa", fontSize: "12px", margin: 0, textAlign: "center", fontWeight: "bold", letterSpacing: "0.5px", textTransform: "uppercase" }}>
                    Scan to Join
                  </p>
                  <QRCodeSVG
                    value={joinUrl}
                    size={140}
                    bgColor="transparent"
                    fgColor="var(--color-primary)"
                    level="M"
                  />
                  <p style={{ color: "#888", fontSize: "11px", margin: 0, textAlign: "center", wordBreak: "break-all" }}>
                    {joinUrl}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Persistent Bottom Playback Bar */}
          <footer className="player-footer">
            <MusicControls
              instanceName={instanceName}
              onOpenMobileQueue={() => setIsMobileQueueOpen(!isMobileQueueOpen)}
            />
          </footer>

          {/* Mobile Queue Drawer Overlay */}
          {isMobileQueueOpen && (
            <div className="mobile-queue-overlay">
              <div className="mobile-queue-header">
                <h3 style={{ margin: 0, color: "#f5a623", fontSize: "18px" }}>Up Next (Queue)</h3>
                <button
                  onClick={() => setIsMobileQueueOpen(false)}
                  className="mobile-queue-close-btn"
                >
                  ✕
                </button>
              </div>
              <div className="mobile-queue-body">
                <Queue />
              </div>
            </div>
          )}

          {/* Settings Modal */}
          {showSettings && (
            <SettingsModal adminToken={adminToken} onClose={() => setShowSettings(false)} instanceName={instanceName} setInstanceName={setInstanceName} />
          )}

          {/* Guest Registration Modal — only for non-admin, non-display devices without a profile */}
          {!isAdmin && !isDisplay && !guestProfile && !dismissedGuestModal && (
            <GuestModal
              onJoin={(profile) => setGuestProfile(profile)}
              onClose={() => setDismissedGuestModal(true)}
            />
          )}

          {/* Name Editing Modal */}
          {showNameModal && (
            <NameModal
              currentName={guestProfile?.name || ""}
              onSave={handleSaveNewName}
              onClose={() => setShowNameModal(false)}
            />
          )}

          {/* Server Info Modal */}
          {showServerModal && (
            <div
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: "rgba(10, 3, 24, 0.75)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                zIndex: 2000,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "20px",
              }}
              onClick={() => setShowServerModal(false)}
            >
              <div
                style={{
                  background: "linear-gradient(135deg, #2a0d52 0%, #16062d 100%)",
                  border: "1px solid rgba(245, 166, 35, 0.4)",
                  borderRadius: "20px",
                  padding: "28px",
                  maxWidth: "360px",
                  width: "100%",
                  boxShadow: "0 20px 50px rgba(0,0,0,0.8)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "16px",
                  animation: "slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span className="material-symbols-outlined" style={{ fontSize: "28px", color: "#5cdd5c" }}>dns</span>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, fontFamily: "var(--font-title)", color: "#fff" }}>
                    Home Server
                  </div>
                </div>
                <div style={{ fontSize: "0.95rem", color: "rgba(255,255,255,0.8)", lineHeight: 1.5 }}>
                  Server from settings: <strong style={{ color: "#f5a623" }}>{accessibleServers.find((s) => s.is_primary)?.name || instanceName || "Plex Server"}</strong>
                </div>
                <button
                  type="button"
                  onClick={() => setShowServerModal(false)}
                  style={{
                    background: "var(--color-primary)",
                    color: "#0e0e0f",
                    fontWeight: 700,
                    border: "none",
                    borderRadius: "20px",
                    padding: "10px 20px",
                    cursor: "pointer",
                    alignSelf: "flex-end",
                    fontSize: "14px",
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </ThemeProvider>
    );
  }

  // ── Setup Wizard ─────────────────────────────────────────────────────────────
  return (
    <ThemeProvider theme={theme}>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "var(--color-bg)", color: "white", padding: "20px" }}>
        <div className="glass-panel" style={{ padding: "40px", borderRadius: "16px", maxWidth: "480px", width: "100%", textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,0.8)" }}>

          <img src={TuneBoxLogo} alt="TuneBox Logo" style={{ height: "45px", marginBottom: "25px" }} />

          {/* STEP 1: Profile Setup */}
          {step === 1 && (
            <form onSubmit={handleStartLinking} style={{ textAlign: "left" }}>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623", textAlign: "center" }}>First Setup Wizard</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px", lineHeight: "1.5", textAlign: "center" }}>
                Welcome! Let's get your details set up to link your Jukebox.
              </p>
              <div style={{ marginBottom: "20px" }}>
                <label style={labelStyle}>Plex Username</label>
                <input type="text" placeholder="e.g. plex_user" value={plexUsername} onChange={(e) => setPlexUsername(e.target.value)} style={inputStyle} required />
              </div>
              <div style={{ marginBottom: "25px" }}>
                <label style={labelStyle}>TuneBox Instance Name</label>
                <input type="text" placeholder="e.g. Steve's Jukebox" value={localUsername} onChange={(e) => setLocalUsername(e.target.value)} style={inputStyle} required />
              </div>
              <button type="submit" style={btnStyle}
                onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                Connect to Plex
              </button>
            </form>
          )}

          {/* STEP 2: Plex PIN Authorization */}
          {step === 2 && (
            <div>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623" }}>Plex PIN Authorization</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "25px" }}>
                Sign in to your Plex account and authorize this TuneBox client.
              </p>
              <div style={{ background: "#2a2a2a", padding: "20px", borderRadius: "8px", marginBottom: "25px", fontSize: "36px", letterSpacing: "4px", fontWeight: "bold", fontFamily: "monospace", color: "#fff", border: "1px dashed #555" }}>
                {pinCode || "Loading..."}
              </div>
              <p style={{ color: "#eee", fontSize: "14px", textAlign: "left", margin: "0 0 25px 0", lineHeight: "1.6" }}>
                1. Open <a href="https://plex.tv/link" target="_blank" rel="noopener noreferrer" style={{ color: "#f5a623", textDecoration: "underline" }}>plex.tv/link</a> in a web browser.<br />
                2. Sign in as <strong>{plexUsername}</strong> and enter the 4-character code above.
              </p>
              {authUrl && (
                <a href={authUrl} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", width: "100%", padding: "12px", background: "#f5a623", color: "#121212", borderRadius: "6px", textDecoration: "none", fontWeight: "bold", marginBottom: "15px", textAlign: "center" }}>
                  Go to Plex Link
                </a>
              )}
              <div style={{ color: "#777", fontSize: "12px", display: "flex", justifyContent: "center", alignItems: "center", gap: "8px" }}>
                <span className="spinner" style={{ display: "inline-block", width: "12px", height: "12px", border: "2px solid #555", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
                Waiting for Plex authorization...
              </div>
            </div>
          )}

          {/* STEP 3: Server Selection */}
          {step === 3 && (
            <form onSubmit={handleSaveConfiguration} style={{ textAlign: "left" }}>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623", textAlign: "center" }}>Select Plex Server</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "25px", textAlign: "center", lineHeight: "1.4" }}>
                Select the Plex Media Server containing your music library.
              </p>
              {isFetchingResources ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "30px 0" }}>
                  <span className="spinner" style={{ display: "inline-block", width: "30px", height: "30px", border: "3px solid #333", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite", marginBottom: "15px" }}></span>
                  <div style={{ color: "#aaa", fontSize: "13px" }}>Querying Plex Servers...</div>
                </div>
              ) : (
                <div>
                  {!isManualConfig ? (
                    <>
                      <div style={{ marginBottom: "20px" }}>
                        <label style={labelStyle}>Plex Media Server</label>
                        {servers.length > 0 ? (
                          <select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                            {servers.map((s) => <option key={s} value={s}>{s}</option>)}
                          </select>
                        ) : (
                          <div style={{ color: "#ff6b6b", fontSize: "13px", padding: "5px 0" }}>No Plex Media Servers found.</div>
                        )}
                      </div>
                      <div style={{ marginBottom: "20px" }}>
                        <label style={labelStyle}>Plex Player (Playback Device)</label>
                        {players.length > 0 ? (
                          <select value={selectedPlayer} onChange={(e) => setSelectedPlayer(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                            {players.map((p) => <option key={p} value={p}>{p}</option>)}
                          </select>
                        ) : (
                          <input type="text" placeholder="e.g. Living Room Plexamp" value={selectedPlayer} onChange={(e) => setSelectedPlayer(e.target.value)} style={inputStyle} required />
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div style={{ marginBottom: "20px" }}>
                        <label style={labelStyle}>Custom Plex Server Name</label>
                        <input type="text" placeholder="e.g. MyHomeServer" value={customServer} onChange={(e) => setCustomServer(e.target.value)} style={inputStyle} required />
                      </div>
                      <div style={{ marginBottom: "20px" }}>
                        <label style={labelStyle}>Custom Plex Player Name</label>
                        <input type="text" placeholder="e.g. Living Room Plexamp" value={customPlayer} onChange={(e) => setCustomPlayer(e.target.value)} style={inputStyle} required />
                      </div>
                    </>
                  )}
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "25px 0" }}>
                    <input type="checkbox" id="manual-toggle" checked={isManualConfig} onChange={(e) => setIsManualConfig(e.target.checked)} style={{ cursor: "pointer" }} />
                    <label htmlFor="manual-toggle" style={{ color: "#aaa", fontSize: "13px", cursor: "pointer", userSelect: "none" }}>Configure server manually</label>
                  </div>
                  <button type="submit" disabled={isSubmitting} style={btnStyle}
                    onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                    onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                    {isSubmitting ? "Saving Configuration..." : "Save & Finish Setup"}
                  </button>
                </div>
              )}
            </form>
          )}

          {/* STEP 4: Transition */}
          {step === 4 && (
            <div>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623" }}>Setup Completed!</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px" }}>Connecting to your Jukebox...</p>
              <div style={{ display: "flex", justifyContent: "center", padding: "20px 0" }}>
                <span className="spinner" style={{ display: "inline-block", width: "40px", height: "40px", border: "4px solid #333", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
              </div>
            </div>
          )}

        </div>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    </ThemeProvider>
  );
}

export default App;
