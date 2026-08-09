import { useState, useEffect, useRef, useCallback } from "react";
import { Routes, Route, Link, useNavigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import ArtistList from "./components/ArtistList";
import ArtistAlbums from "./components/ArtistAlbums";
import TrackList from "./components/TrackList";
import MusicControls from "./components/MusicControls";
import Queue from "./components/Queue";
import { BrowseTabs, AlbumsGridView, GenresGridView, DecadesGridView, ViewMode } from "./components/BrowseViews";
import theme from "./theme";
import TuneBoxLogo from "../public/TuneBox.svg";
import Stats from "./components/Stats";
import TuneBoxDialog from "./components/TuneBoxDialog";
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
  device_name?: string;
  user_agent?: string;
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
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
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
  onServerToggled?: () => void;
}

function SettingsModal({ adminToken, onClose, instanceName, setInstanceName, onServerToggled }: SettingsModalProps) {
  const [plexUsername, setPlexUsername] = useState("");
  const [localInstanceName, setLocalInstanceName] = useState(instanceName);
  const [selectedServer, setSelectedServer] = useState("");
  const [players, setPlayers] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [isFormDirty, setIsFormDirty] = useState(false);

  const handleAttemptClose = () => {
    if (isFormDirty) {
      setShowUnsavedDialog(true);
    } else {
      onClose();
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        handleAttemptClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [isFormDirty, onClose]);

  const [clients, setClients] = useState<ClientSession[]>([]);
  const [libraries, setLibraries] = useState<any[]>([]);
  const [playlists, setPlaylists] = useState<{ playlist_id: number; title: string }[]>([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState("");
  const [preseedCount, setPreseedCount] = useState<string>("10");
  const [seeding, setSeeding] = useState(false);
  const [sectionsOpen, setSectionsOpen] = useState({
    general: false,
    queue: false,
    devices: false,
    guests: false,
  });

  const [autoplayEnabled, setAutoplayEnabled] = useState(false);

  useEffect(() => {
    if (msg) {
      const timer = setTimeout(() => {
        setMsg("");
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [msg]);

  useEffect(() => {
    axios
      .get(getApiUrl("/api/music/playlists"), {
        headers: { "x-admin-token": adminToken },
      })
      .then((res) => {
        setPlaylists(res.data ?? []);
        if (res.data && res.data.length > 0) {
          setSelectedPlaylistId(String(res.data[0].playlist_id));
        }
      })
      .catch((err) => console.error("Failed to load playlists:", err));

    axios
      .get(getApiUrl("/api/music/autoplay"))
      .then((res) => {
        setAutoplayEnabled(res.data.autoplay_enabled ?? false);
      })
      .catch((err) => console.error("Failed to load autoplay status:", err));
  }, [adminToken]);

  const handleSeedJukebox = async () => {
    if (!selectedPlaylistId) return;
    setSeeding(true);
    setMsg("Preseeding TuneBox...");
    const parsedCount = Math.max(1, parseInt(preseedCount, 10) || 10);
    try {
      const res = await axios.post(
        getApiUrl(`/api/music/playlists/${selectedPlaylistId}/seed?count=${parsedCount}`),
        {},
        { headers: { "x-admin-token": adminToken } }
      );
      setMsg(`✓ ${res.data.message || "TuneBox preseeded successfully!"}`);
    } catch (err) {
      console.error("Failed to preseed TuneBox:", err);
      setMsg("✗ Failed to preseed TuneBox.");
    } finally {
      setSeeding(false);
    }
  };

  const handleToggleAutoplay = async (enabled: boolean) => {
    try {
      const res = await axios.post(
        getApiUrl("/api/music/autoplay"),
        { enabled },
        { headers: { "x-admin-token": adminToken } }
      );
      setAutoplayEnabled(res.data.autoplay_enabled ?? false);
      setMsg(`✓ Autoplay is now ${enabled ? "enabled" : "disabled"}!`);
    } catch (err) {
      console.error("Failed to toggle autoplay:", err);
      setMsg("✗ Failed to toggle autoplay.");
    }
  };

  const handleRefreshResources = async () => {
    setRefreshing(true);
    setMsg("Refreshing devices...");
    try {
      const res = await axios.get(getApiUrl("/api/auth/resources?refresh=true"));
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
        if (res.data.plex_username) {
          setPlexUsername(res.data.plex_username);
          localStorage.setItem("tunebox_admin_name", res.data.plex_username);
        }
        setSelectedServer(res.data.plex_server_name ?? "");
        setSelectedPlayer(res.data.client_name ?? "");
        if (res.data.instance_name) setInstanceName(res.data.instance_name);
        setIsFormDirty(false);
      })
      .catch(console.error);

    axios
      .get(getApiUrl("/api/auth/resources"))
      .then((res) => {
        setPlayers(res.data.players ?? []);
      })
      .catch(console.error);

    axios
      .get(getApiUrl("/api/auth/libraries"))
      .then((res) => {
        setLibraries(res.data ?? []);
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
  const [confirmStopOpen, setConfirmStopOpen] = useState(false);
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
      if (clientId === getClientId() && adminToken) {
        localStorage.setItem("tunebox_admin_name", newName);
      }
      fetchClients();
    } catch (err) {
      console.error("Failed to rename user:", err);
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
      setMsg("✓ Upcoming queue cleared!");
    } catch (err) {
      console.error("Failed to clear queue:", err);
      setMsg("✗ Failed to clear upcoming queue.");
    }
  };

  const handleExecuteStopQueue = async () => {
    setConfirmStopOpen(false);
    try {
      await fetch(getApiUrl("/api/music/stop-queue"), {
        method: "POST",
        headers: { "x-admin-token": adminToken },
      });
      setMsg("✓ Playback stopped & full queue cleared!");
    } catch (err) {
      console.error("Error stopping queue:", err);
      setMsg("✗ Failed to clear full queue.");
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
        {
          plex_username: plexUsername,
          client_name: selectedPlayer,
          plex_server_name: selectedServer,
          instance_name: localInstanceName,
        },
        { headers: { "x-admin-token": adminToken } }
      );

      const enabledIds = libraries.filter((l) => l.enabled).map((l) => l.server_id);
      await axios.post(
        getApiUrl("/api/auth/libraries"),
        { enabled_server_ids: enabledIds },
        { headers: { "x-admin-token": adminToken } }
      );

      setIsFormDirty(false);
      setMsg("✓ Settings saved!");
      onServerToggled?.();
    } catch {
      setMsg("✗ Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const getToastStyles = () => {
    if (!msg) return {};
    if (msg.startsWith("✓")) {
      return {
        background: "rgba(46, 204, 113, 0.15)",
        border: "1px solid rgba(46, 204, 113, 0.4)",
        color: "#2ecc71",
      };
    }
    if (msg.startsWith("✗") || msg.toLowerCase().includes("fail") || msg.toLowerCase().includes("error")) {
      return {
        background: "rgba(231, 76, 60, 0.15)",
        border: "1px solid rgba(231, 76, 60, 0.4)",
        color: "#ff4d4d",
      };
    }
    return {
      background: "rgba(51, 118, 173, 0.15)",
      border: "1px solid #3375A8",
      color: "#3375A8",
    };
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        background: "rgba(14, 14, 15, 0.75)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10000,
        padding: "16px",
        boxSizing: "border-box",
      }}
      onClick={handleAttemptClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#141416",
          border: "1px solid rgba(255, 255, 255, 0.12)",
          borderRadius: "16px",
          padding: "20px 24px",
          width: "calc(100% - 32px)",
          maxWidth: "480px",
          maxHeight: "calc(100dvh - 32px)",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 12px 32px rgba(0, 0, 0, 0.6)",
          boxSizing: "border-box",
          color: "#fff",
        }}
      >
        {/* Sticky Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
          <h2 style={{ margin: 0, color: "#f5a623", fontSize: "19px", display: "flex", alignItems: "center", gap: "8px", whiteSpace: "nowrap" }}>
            <span className="material-symbols-outlined">settings</span> TuneBox Settings
          </h2>

          {selectedServer && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                padding: "3px 9px",
                background: "rgba(255, 255, 255, 0.07)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                borderRadius: "14px",
                fontSize: "11px",
                fontWeight: 600,
                color: "rgba(255, 255, 255, 0.75)",
                whiteSpace: "nowrap",
                maxWidth: "160px",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={`Connected Plex Server: ${selectedServer}`}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "14px", color: "#5cdd5c", flexShrink: 0 }}>dns</span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{selectedServer}</span>
            </div>
          )}

          <button
            onClick={handleAttemptClose}
            style={{ background: "none", border: "none", color: "rgba(255, 255, 255, 0.4)", fontSize: "22px", cursor: "pointer", padding: "0 4px" }}
          >
            ✕
          </button>
        </div>

        {/* Sticky Alert Message Banner - High Contrast Translucent Fill */}
        {msg && (
          <div
            style={{
              padding: "12px",
              borderRadius: "8px",
              fontSize: "14px",
              fontWeight: "bold",
              textAlign: "center",
              marginBottom: "16px",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
              ...getToastStyles(),
            }}
          >
            {msg}
          </div>
        )}
        {/* Scrollable Accordion Body */}
        <div className="hide-scrollbar" style={{ overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: "16px", scrollbarWidth: "none", msOverflowStyle: "none" }}>

          <Link
            to="/stats"
            onClick={onClose}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              background: "rgba(51, 118, 173, 0.15)",
              border: "1px solid #3375A8",
              color: "#3375A8",
              padding: "12px",
              borderRadius: "8px",
              fontWeight: "bold",
              textDecoration: "none",
              fontSize: "14px",
              transition: "background-color 0.2s",
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.backgroundColor = "rgba(51, 118, 173, 0.25)";
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.backgroundColor = "rgba(51, 118, 173, 0.15)";
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>leaderboard</span>
            View TuneBox Stats & Leaderboard 🏆
          </Link>

          {/* Section 1: General Settings */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div
              onClick={() => {
                setSectionsOpen(prev => ({
                  general: !prev.general,
                  queue: false,
                  devices: false,
                  guests: false,
                }));
              }}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                cursor: "pointer",
                padding: "12px 14px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "8px",
                userSelect: "none",
              }}
            >
              <span style={{ color: "#f5a623", fontSize: "14px", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px" }}>
                ⚙️ General Settings
              </span>
              <span style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: "11px" }}>
                {sectionsOpen.general ? "▲" : "▼"}
              </span>
            </div>

            {sectionsOpen.general && (
              <form id="settings-form" onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "14px", padding: "4px 8px 12px 8px" }}>
                <div>
                  <label style={labelStyle}>Authenticated Plex Account</label>
                  <div style={{ ...inputStyle, background: "rgba(255, 255, 255, 0.05)", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#f5a623", fontWeight: "bold" }}>
                    {plexUsername || "Connected via Plex"}
                  </div>
                </div>
                <div>
                  <label style={labelStyle}>TuneBox Instance Name</label>
                  <input
                    type="text"
                    value={localInstanceName}
                    onChange={(e) => { setLocalInstanceName(e.target.value); setIsFormDirty(true); }}
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
                      onChange={(e) => { setSelectedPlayer(e.target.value); setIsFormDirty(true); }}
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
                      onChange={(e) => { setSelectedPlayer(e.target.value); setIsFormDirty(true); }}
                      style={inputStyle}
                    />
                  )}
                </div>
                <div>
                  <label style={labelStyle}>Plex Media Servers (Unified Catalog)</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", background: "rgba(255, 255, 255, 0.03)", padding: "10px 12px", borderRadius: "8px", border: "1px solid rgba(255, 255, 255, 0.08)" }}>
                    {libraries.length === 0 ? (
                      <span style={{ color: "rgba(255, 255, 255, 0.5)", fontSize: "13px" }}>No servers found.</span>
                    ) : (
                      libraries.map((lib) => (
                        <label key={lib.server_id || lib.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px", color: "#fff", fontSize: "13px", cursor: "pointer", userSelect: "none", width: "100%" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <input
                              type="checkbox"
                              checked={lib.enabled}
                              onChange={(e) => {
                                const updatedEnabled = e.target.checked;
                                const nextLibs = libraries.map((l) => l.server_id === lib.server_id ? { ...l, enabled: updatedEnabled } : l);
                                setLibraries(nextLibs);
                                setIsFormDirty(true);
                              }}
                            />
                            <span>{lib.name} {lib.is_primary ? "(Home Server)" : ""}</span>
                          </div>
                          <span
                            style={{
                              fontSize: "10px",
                              fontWeight: "bold",
                              padding: "2px 8px",
                              borderRadius: "12px",
                              background: !lib.enabled
                                ? "rgba(255, 255, 255, 0.08)"
                                : lib.status === "connected"
                                ? "rgba(46, 204, 113, 0.15)"
                                : lib.status === "failed"
                                ? "rgba(231, 76, 60, 0.15)"
                                : "rgba(52, 152, 219, 0.15)",
                              border: !lib.enabled
                                ? "1px solid rgba(255, 255, 255, 0.2)"
                                : lib.status === "connected"
                                ? "1px solid rgba(46, 204, 113, 0.4)"
                                : lib.status === "failed"
                                ? "1px solid rgba(231, 76, 60, 0.4)"
                                : "1px solid rgba(52, 152, 219, 0.4)",
                              color: !lib.enabled
                                ? "#aaa"
                                : lib.status === "connected"
                                ? "#2ecc71"
                                : lib.status === "failed"
                                ? "#e74c3c"
                                : "#3498db",
                            }}
                            title={!lib.enabled ? "Not connected (Unchecked)" : lib.status === "failed" ? lib.error || "Connection failed" : lib.status === "connected" ? "Successfully connected to server" : "Connecting to server..."}
                          >
                            {!lib.enabled ? "⚪ Not Connected" : lib.status === "connected" ? "🟢 Connected" : lib.status === "failed" ? "🔴 Failed" : "🔵 Connecting"}
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              </form>
            )}
          </div>

          {/* Section 2: Queue Management */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div
              onClick={() => setSectionsOpen(prev => ({ general: false, queue: !prev.queue, devices: false, guests: false }))}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                cursor: "pointer",
                padding: "12px 14px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "8px",
                userSelect: "none",
              }}
            >
              <span style={{ color: "#f5a623", fontSize: "14px", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px" }}>
                🎵 Queue Management
              </span>
              <span style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: "11px" }}>
                {sectionsOpen.queue ? "▲" : "▼"}
              </span>
            </div>

            {sectionsOpen.queue && (
              <div style={{ display: "flex", flexDirection: "column", gap: "14px", padding: "4px 8px 12px 8px" }}>
                {/* Playlist Selection & Seeding */}
                <div>
                  <label style={labelStyle}>Seed Playlist to Queue</label>
                  <div style={{ display: "flex", gap: "8px", marginTop: "4px", alignItems: "center" }}>
                    <select
                      value={selectedPlaylistId}
                      onChange={(e) => setSelectedPlaylistId(e.target.value)}
                      style={{ ...inputStyle, flex: 2, cursor: "pointer" }}
                    >
                      <option value="">Select a playlist...</option>
                      {playlists.map((pl) => (
                        <option key={pl.playlist_id} value={pl.playlist_id}>
                          {pl.title}
                        </option>
                      ))}
                    </select>
                    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                      <span style={{ fontSize: "11px", color: "rgba(255, 255, 255, 0.6)", whiteSpace: "nowrap" }}>Count:</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        value={preseedCount}
                        onChange={(e) => setPreseedCount(e.target.value)}
                        style={{ ...inputStyle, width: "55px", padding: "6px 8px", textAlign: "center" }}
                        title="Number of tracks to preseed"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleSeedJukebox}
                      disabled={seeding || !selectedPlaylistId}
                      style={{
                        background: "#3375A8",
                        color: "white",
                        border: "none",
                        borderRadius: "6px",
                        padding: "0 16px",
                        height: "36px",
                        fontWeight: "bold",
                        fontSize: "13px",
                        cursor: seeding || !selectedPlaylistId ? "not-allowed" : "pointer",
                        opacity: seeding || !selectedPlaylistId ? 0.5 : 1,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {seeding ? "Preseeding..." : "Preseed Queue"}
                    </button>
                  </div>
                  <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "11px", display: "block", marginTop: "4px" }}>
                    Shuffles and preseeds playlist tracks into the queue. Guest selections automatically take priority.
                  </span>
                </div>

                {/* Smart Autoplay toggle */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.03)", padding: "12px", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.05)" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px", paddingRight: "16px" }}>
                    <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px" }}>
                      📻 Smart Autoplay Mode
                    </span>
                    <span style={{ color: "rgba(255, 255, 255, 0.5)", fontSize: "11px", lineHeight: "1.4" }}>
                      Keep music playing based on recent vibe when queue falls to 5 or fewer tracks. Guest tracks automatically leapfrog fallback tracks.
                    </span>
                  </div>
                  <div
                    onClick={() => handleToggleAutoplay(!autoplayEnabled)}
                    style={{
                      width: "50px",
                      height: "26px",
                      backgroundColor: autoplayEnabled ? "var(--color-primary)" : "rgba(255, 255, 255, 0.2)",
                      borderRadius: "13px",
                      position: "relative",
                      cursor: "pointer",
                      flexShrink: 0,
                      transition: "background-color 0.2s",
                    }}
                  >
                    <div style={{
                      width: "20px",
                      height: "20px",
                      backgroundColor: "#0e0e0f",
                      borderRadius: "50%",
                      position: "absolute",
                      top: "3px",
                      left: autoplayEnabled ? "27px" : "3px",
                      transition: "left 0.2s",
                    }} />
                  </div>
                </div>

                {/* Queue Control Buttons */}
                <div>
                  <label style={{ ...labelStyle, fontSize: "13px", color: "rgba(255, 255, 255, 0.6)", display: "block", marginBottom: "8px" }}>⚠️ Admin Controls</label>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                    <button
                      type="button"
                      onClick={() => setConfirmClearOpen(true)}
                      title="Clears all upcoming songs in the queue while preserving the currently playing track"
                      style={{
                        width: "100%",
                        background: "rgba(245, 166, 35, 0.15)",
                        border: "1px solid rgba(245, 166, 35, 0.4)",
                        color: "#f5a623",
                        borderRadius: "8px",
                        padding: "12px 14px",
                        fontSize: "13px",
                        fontWeight: "bold",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "6px",
                        transition: "all 0.2s ease-in-out",
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(245, 166, 35, 0.25)";
                        e.currentTarget.style.borderColor = "#f5a623";
                      }}
                      onMouseOut={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(245, 166, 35, 0.15)";
                        e.currentTarget.style.borderColor = "rgba(245, 166, 35, 0.4)";
                      }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>playlist_remove</span>
                      Clear Upcoming Queue
                    </button>

                    <button
                      type="button"
                      onClick={() => setConfirmStopOpen(true)}
                      title="Stops player immediately and clears the entire queue including the current song"
                      style={{
                        width: "100%",
                        background: "#ff4d4d",
                        border: "none",
                        color: "#ffffff",
                        borderRadius: "8px",
                        padding: "12px 14px",
                        fontSize: "13px",
                        fontWeight: "bold",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "6px",
                        boxShadow: "0 4px 12px rgba(255, 77, 77, 0.25)",
                        transition: "all 0.2s ease-in-out",
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.backgroundColor = "#e04343";
                      }}
                      onMouseOut={(e) => {
                        e.currentTarget.style.backgroundColor = "#ff4d4d";
                      }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>stop_circle</span>
                      Clear Full Queue
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Section 3: Connected Devices & Kiosks */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div
              onClick={() => setSectionsOpen(prev => ({ general: false, queue: false, devices: !prev.devices, guests: false }))}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                cursor: "pointer",
                padding: "12px 14px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "8px",
                userSelect: "none",
              }}
            >
              <span style={{ color: "#f5a623", fontSize: "14px", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px" }}>
                🖥️ Connected Devices & Kiosks
                <span className="kiosk-help-container">
                  <span
                    className="material-symbols-outlined"
                    onClick={(e) => e.stopPropagation()}
                    style={{ fontSize: "16px", color: "#3375A8", cursor: "help" }}
                    title="TEST"                  >
                    help_outline
                  </span>
                  <span className="kiosk-help-popover">
                    Turning a connected device into a Kiosk converts it into a shared, central party display screen: displays a prominent QR code for guests to scan and join instantly.
                  </span>
                </span>
              </span>
              <span style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: "11px" }}>
                {sectionsOpen.devices ? "▲" : "▼"}
              </span>
            </div>

            {sectionsOpen.devices && (
              <div style={{ padding: "4px 8px 12px 8px" }}>
                {clients.length === 0 ? (
                  <p style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "13px", margin: 0 }}>No connected devices.</p>
                ) : (
                  <div className="hide-scrollbar" style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "200px", overflowY: "auto", scrollbarWidth: "none", msOverflowStyle: "none" }}>
                    {clients.map((c) => (
                      <div
                        key={c.client_id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "8px 12px",
                          background: c.is_display ? "rgba(92, 221, 92, 0.08)" : "#3a136b",
                          border: c.is_display ? "1px solid rgba(92, 221, 92, 0.2)" : "1px solid rgba(255, 255, 255, 0.05)",
                          borderRadius: "6px",
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                          <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold" }}>
                            {c.device_name || c.name}
                          </span>
                          <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "11px" }}>
                            {c.is_display ? "Kiosk Display Screen" : `Device Session (${c.role})`}
                          </span>
                        </div>
                        {c.is_display ? (
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ color: "#5cdd5c", fontSize: "12px", fontWeight: "bold", marginRight: "4px" }}>
                              ✓ Kiosk Mode
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
                              title="Return device to standard view"
                            >
                              Remove Kiosk
                            </button>
                          </div>
                        ) : (
                          c.client_id !== getClientId() && (
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
                              title="Set as Party Kiosk Display"
                            >
                              Make Kiosk
                            </button>
                          )
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section 4: Active Party Guests */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "12px" }}>
            <div
              onClick={() => setSectionsOpen(prev => ({ general: false, queue: false, devices: false, guests: !prev.guests }))}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                cursor: "pointer",
                padding: "12px 14px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "8px",
                userSelect: "none",
              }}
            >
              <span style={{ color: "#f5a623", fontSize: "14px", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px" }}>
                👥 Active Party Guests
              </span>
              <span style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: "11px" }}>
                {sectionsOpen.guests ? "▲" : "▼"}
              </span>
            </div>

            {sectionsOpen.guests && (
              <div style={{ padding: "4px 8px 12px 8px" }}>
                {clients.length === 0 ? (
                  <p style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "13px", margin: 0 }}>No active party guests.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "200px", overflowY: "auto" }}>
                    {clients.map((c) => (
                      <div
                        key={c.client_id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "8px 12px",
                          background: "rgba(255, 255, 255, 0.03)",
                          border: "1px solid rgba(255, 255, 255, 0.06)",
                          borderRadius: "6px",
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                          <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                            {c.name}
                            <span
                              className="material-symbols-outlined"
                              onClick={() => handleOpenRename(c.client_id, c.name)}
                              style={{ fontSize: "16px", cursor: "pointer", color: "var(--color-primary)", opacity: 0.7, transition: "opacity 0.2s" }}
                              onMouseOver={(e) => e.currentTarget.style.opacity = "1"}
                              onMouseOut={(e) => e.currentTarget.style.opacity = "0.7"}
                              title="Edit Username"
                            >
                              edit
                            </span>
                          </span>
                          <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "11px", textTransform: "capitalize" }}>
                            Role: {c.role} {c.is_display ? "• Display Screen" : ""}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sticky Save Button Row at Bottom */}
        <div style={{ display: "flex", gap: "12px", marginTop: "16px", paddingTop: "12px", borderTop: "1px solid rgba(255, 255, 255, 0.1)" }}>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            style={{
              flex: 1,
              background: "#f5a623",
              color: "#141416",
              border: "none",
              padding: "12px",
              borderRadius: "8px",
              fontWeight: "bold",
              fontSize: "15px",
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.7 : 1,
              transition: "background-color 0.2s",
            }}
            onMouseOver={(e) => {
              if (!saving) e.currentTarget.style.backgroundColor = "#d48b17";
            }}
            onMouseOut={(e) => {
              if (!saving) e.currentTarget.style.backgroundColor = "#f5a623";
            }}
          >
            {saving ? "Saving Settings..." : "Save Settings"}
          </button>
        </div>

        <TuneBoxDialog
          open={showUnsavedDialog}
          type="confirm"
          icon="warning"
          title="Unsaved Changes"
          message="You have unsaved setting changes. Would you like to save your changes before closing?"
          confirmText="Save Settings"
          cancelText="Discard"
          thirdText="Keep Editing"
          onConfirm={() => {
            setShowUnsavedDialog(false);
            const form = document.getElementById("settings-form") as HTMLFormElement;
            if (form) form.requestSubmit();
          }}
          onThird={() => {
            setShowUnsavedDialog(false);
            onClose();
          }}
          onCancel={() => setShowUnsavedDialog(false)}
        />
        <ConfirmModal
          isOpen={confirmClearOpen}
          title="Clear Upcoming Queue?"
          message="Are you sure you want to clear upcoming tracks from the queue? The currently playing song will remain active."
          confirmText="Clear Upcoming"
          cancelText="Cancel"
          onConfirm={handleExecuteClearQueue}
          onCancel={() => setConfirmClearOpen(false)}
        />
        <ConfirmModal
          isOpen={confirmStopOpen}
          title="Clear Full Queue & Stop Music?"
          message="Are you sure you want to stop playback and clear the full queue? This will immediately halt playback and wipe the active song as well as all upcoming tracks."
          confirmText="Clear Full Queue"
          cancelText="Cancel"
          onConfirm={handleExecuteStopQueue}
          onCancel={() => setConfirmStopOpen(false)}
        />        <PromptModal
          isOpen={renameState.isOpen}
          title="Change Username"
          message={`Enter a new username for "${renameState.currentName}":`}
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
          Enter a nickname to join the session.
        </p>

        <form onSubmit={handleJoin} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <input
            type="text"
            placeholder="Your Nickname"
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
            {loading ? "Joining..." : "Join TuneBox"}
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
        gap: "6px",
        padding: "6px 12px",
        background: "rgba(51, 118, 173, 0.15)",
        border: "1px solid #3375A8",
        borderRadius: "20px",
        fontSize: "12px",
        fontWeight: "bold",
        color: "#3375A8",
        flexShrink: 0,
        whiteSpace: "nowrap",
      }}
    >
      <div
        onClick={onEditName}
        style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
        title="Click to edit username"
      >
        <span className="material-symbols-outlined" style={{ fontSize: "15px", color: "#3375A8" }}>person</span>
        <span>{profile.name}</span>
      </div>
      <span style={{ width: "1px", height: "12px", background: "rgba(51, 118, 173, 0.3)" }}></span>
      <span
        className="material-symbols-outlined"
        onClick={onLeave}
        style={{
          fontSize: "15px",
          cursor: "pointer",
          color: "#3375A8",
          transition: "color 0.2s"
        }}
        onMouseOver={(e) => e.currentTarget.style.color = "#ff6b6b"}
        onMouseOut={(e) => e.currentTarget.style.color = "#3375A8"}
        title="Leave Session"
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
    () => localStorage.getItem("tunebox_instance_name") ?? "TuneBox Screen"
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
  const [appDialog, setAppDialog] = useState<{ open: boolean; title?: string; message: string }>({
    open: false,
    message: "",
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

  const [viewMode, setViewMode] = useState<ViewMode>("artists");
  const [artists, setArtists] = useState<any[]>([]);
  const [loadingArtists, setLoadingArtists] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLetter, setSelectedLetter] = useState("");
  const [filteredArtists, setFilteredArtists] = useState<any[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [accessibleServers, setAccessibleServers] = useState<any[]>([]);
  const [showServerModal, setShowServerModal] = useState(false);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [indexingStatus, setIndexingStatus] = useState<{ isIndexing: boolean; isInitial: boolean; serverName: string; message?: string | null; isError?: boolean } | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Clear search query when clear_search parameter is present
  useEffect(() => {
    if (location.search.includes("clear_search=true")) {
      setSearchTerm("");
      setSelectedLetter("");
    }
  }, [location.search]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowServerModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch accessible Plex servers & active indexing status
  useEffect(() => {
    if (!isConfigured) return;
    axios
      .get(getApiUrl("/api/music/servers"))
      .then((res) => {
        if (Array.isArray(res.data)) {
          setAccessibleServers(res.data);
        }
      })
      .catch((err) => console.error("Error fetching servers:", err));

    axios
      .get(getApiUrl("/api/music/indexing-status"))
      .then((res) => {
        if (res.data && res.data.is_indexing) {
          setIndexingStatus({
            isIndexing: Boolean(res.data.is_indexing),
            isInitial: Boolean(res.data.is_initial),
            serverName: res.data.server_name || "Plex",
            message: res.data.message || null,
            isError: Boolean(res.data.is_error),
          });
        }
      })
      .catch((err) => console.error("Error fetching indexing status:", err));
  }, [isConfigured]);

  // Auto-refresh artist list dynamically while library indexing is active in background
  useEffect(() => {
    if (!isConfigured || !indexingStatus?.isIndexing || debouncedSearchTerm) return;

    const interval = setInterval(() => {
      const artistListURL = getApiUrl("/api/music/artists");
      axios
        .get(artistListURL)
        .then((res) => {
          if (Array.isArray(res.data)) {
            const sortedArtists = res.data
              .filter((item: any) => item.name)
              .sort((a: any, b: any) => (a.name && b.name ? a.name.localeCompare(b.name) : -1));
            setArtists(sortedArtists);
            setFilteredArtists(sortedArtists);
          }
        })
        .catch(() => {});
    }, 2500);

    return () => clearInterval(interval);
  }, [isConfigured, indexingStatus?.isIndexing, debouncedSearchTerm]);

  // Debouncing hook logic
  useEffect(() => {
    if (searchTerm) {
      setLoadingArtists(true);
    }
    const handler = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchTerm]);

  const refreshLibraryData = useCallback(async () => {
    window.dispatchEvent(new CustomEvent("tunebox_refresh_albums"));
    if (!isConfigured) return;
    setLoadingArtists(true);
    try {
      const searchURL = getApiUrl(`/api/music/unified-search?query=${encodeURIComponent(debouncedSearchTerm)}`);
      const artistListURL = getApiUrl("/api/music/artists");
      const endpoint = debouncedSearchTerm ? searchURL : artistListURL;

      const response = await axios.get(endpoint);
      let data = response.data;

      if (debouncedSearchTerm) {
        setSearchResults(data);
      } else {
        data = data.filter((item: any) => item.name);
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
  }, [isConfigured, debouncedSearchTerm]);

  useEffect(() => {
    if (debouncedSearchTerm === "" || debouncedSearchTerm) {
      refreshLibraryData();
    } else {
      setLoadingArtists(false);
      setArtists([]);
    }
  }, [debouncedSearchTerm, isConfigured, viewMode, refreshLibraryData]);



  const [scrollTargetLetter, setScrollTargetLetter] = useState<{ letter: string; timestamp: number } | null>(null);

  const handleAlphabetClick = (e: React.MouseEvent<HTMLButtonElement>, character: string) => {
    (e.currentTarget as HTMLElement).blur();
    setSelectedLetter(character);
    setScrollTargetLetter({ letter: character, timestamp: Date.now() });
    setSearchTerm("");

    if (location.pathname !== "/") {
      navigate("/");
    }

    setFilteredArtists(artists);
  };

  const handleScrollLetterChange = useCallback((letter: string) => {
    setSelectedLetter(letter);
  }, []);

  // Manage client_control WebSocket connection
  useEffect(() => {
    // Only connect if the user has completed the wizard (admin), joined as guest, or is in display mode
    if (!isAdmin && !isDisplay && !guestProfile) {
      return;
    }

    let ws: WebSocket | null = null;
    let pingInterval: number;
    let pongTimeout: number;
    let reconnectTimeout: number;
    let isDisposed = false;

    const connectWs = () => {
      if (isDisposed) return;
      const wsUrl = getWsUrl();
      ws = new WebSocket(wsUrl);

      const register = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          let name = "Unknown";
          let role = "guest";
          if (isAdmin) {
            name = localStorage.getItem("tunebox_admin_name") || "Admin";
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

        pingInterval = window.setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "heartbeat", message: "ping" }));
            pongTimeout = window.setTimeout(() => {
              console.warn("Client control WS ping timeout, closing");
              ws?.close();
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
          } else if (data.type === "server_settings_updated") {
            console.log("Received server_settings_updated WS push. Re-fetching library content...");
            refreshLibraryData();
            setIndexingStatus(null);
          } else if (data.type === "indexing_status") {
            console.log("Received indexing_status WS push:", data);
            window.dispatchEvent(new CustomEvent("tunebox_refresh_albums"));
            const isInd = Boolean(data.is_indexing);
            const isInit = Boolean(data.is_initial);
            const sName = data.server_name || "Plex";
            const msg = data.message || null;
            const isErr = Boolean(data.is_error);
            setIndexingStatus({
              isIndexing: isInd,
              isInitial: isInit,
              serverName: sName,
              message: msg,
              isError: isErr,
            });
            if (!isInd) {
              setTimeout(() => setIndexingStatus(null), isErr ? 6000 : 3000);
            }
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
        if (!isDisposed) {
          reconnectTimeout = window.setTimeout(connectWs, 3000);
        }
      };
    };

    connectWs();

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          console.log("Tab became visible, reconnecting client_control WS...");
          connectWs();
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      isDisposed = true;
      document.removeEventListener("visibilitychange", handleVisibility);
      window.clearInterval(pingInterval);
      window.clearTimeout(pongTimeout);
      window.clearTimeout(reconnectTimeout);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
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
      if (res.data.instance_name) {
        setInstanceName(res.data.instance_name);
        localStorage.setItem("tunebox_instance_name", res.data.instance_name);
      }
      if (res.data.client_name) {
        setLocalUsername(res.data.client_name);
      }

      if (res.data.authenticated) {
        if (res.data.is_configured) {
          setStep(4);
        } else {
          setStep(3);
          fetchResources();
        }
      } else if (step === 4) {
        setStep(1);
      }
    } catch (err) {
      console.error("Status check failed:", err);
      setIsAuthenticated(false);
      setIsConfigured(false);
      if (step === 4) {
        setStep(1);
      }
    }
  };

  const handleStartLinking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localUsername.trim() || !plexUsername.trim()) {
      setAppDialog({
        open: true,
        title: "Setup Warning",
        message: "Please enter both Plex username and TuneBox Instance Name.",
      });
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
      setAppDialog({
        open: true,
        title: "Setup Warning",
        message: "Please select or enter a Plex server name.",
      });
      setIsSubmitting(false);
      return;
    }
    try {
      const res = await axios.post(getApiUrl("/api/auth/configure"), {
        plex_username: plexUsername,
        client_name: playerClientName || localUsername,
        plex_server_name: serverName,
        instance_name: localUsername,
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
      setAppDialog({
        open: true,
        title: "Setup Error",
        message: "Failed to save configuration settings.",
      });
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

  // ── TuneBox Dashboard (configured) ──────────────────────────────────────────
  if (isAuthenticated && isConfigured && step === 4) {
    const isDev = window.location.port === "5173";
    const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

    const isStatsOpen = location.pathname === "/stats";

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
                  placeholder="Search TuneBox..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setSelectedLetter("");
                    if (location.pathname !== "/") {
                      navigate("/");
                    }
                  }}
                />
              </div>

              {/* Admin identity badge */}
              {isAdmin && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    background: "rgba(51, 118, 173, 0.15)",
                    border: "1px solid #3375A8",
                    borderRadius: "20px",
                    fontSize: "12px",
                    fontWeight: "bold",
                    color: "#3375A8",
                    flexShrink: 0,
                    whiteSpace: "nowrap"
                  }}
                >
                  <div
                    onClick={() => setShowSettings(true)}
                    style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
                    title="Admin Session — Click to open Settings"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>admin_panel_settings</span>
                    <span>{localStorage.getItem("tunebox_admin_name") || "Admin"}</span>
                  </div>
                  <span style={{ width: "1px", height: "12px", background: "rgba(51, 118, 173, 0.3)" }}></span>
                  <span
                    className="material-symbols-outlined"
                    onClick={() => {
                      localStorage.removeItem("tunebox_admin_token");
                      localStorage.removeItem("tunebox_admin_name");
                      window.location.reload();
                    }}
                    style={{
                      fontSize: "15px",
                      cursor: "pointer",
                      color: "#3375A8",
                      transition: "color 0.2s"
                    }}
                    onMouseOver={(e) => (e.currentTarget.style.color = "#ff6b6b")}
                    onMouseOut={(e) => (e.currentTarget.style.color = "#3375A8")}
                    title="Log out Admin Session"
                  >
                    logout
                  </span>
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

              {/* Join TuneBox button if guest dismissed registration modal */}
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
                  Join TuneBox
                </button>
              )}
            </div>
          </div>

          {/* Persistent Alphabet Fast-Scroll Sidebar on Left (Artists & Albums View) */}
          {(location.pathname === "/" || location.pathname === "/artists") && (viewMode === "artists" || viewMode === "albums") && (
            <aside className="left-sidebar">
              <div className="alphabet-filter">
                <button
                  onClick={(e) => handleAlphabetClick(e, "0-9")}
                  className={selectedLetter === "0-9" ? "active" : ""}
                >
                  #
                </button>
                {"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((letter) => (
                  <button
                    key={letter}
                    onClick={(e) => handleAlphabetClick(e, letter)}
                    className={selectedLetter === letter ? "active" : ""}
                  >
                    {letter}
                  </button>
                ))}
              </div>
            </aside>
          )}

          {/* Main Grid Wrapper */}
          <div className="main-wrapper">
            {/* Subpage content */}
            <div className={`main-content ${(location.pathname === "/" || location.pathname === "/artists") && viewMode !== "artists" && viewMode !== "albums" ? "no-sidebar" : ""}`}>
              {indexingStatus && (
                <div
                  style={{
                    background: indexingStatus.isError
                      ? "linear-gradient(90deg, #d32f2f 0%, #b71c1c 100%)"
                      : "linear-gradient(90deg, #1e3c72 0%, #2a5298 100%)",
                    borderBottom: indexingStatus.isError
                      ? "1px solid rgba(255, 100, 100, 0.4)"
                      : "1px solid rgba(100, 200, 255, 0.4)",
                    color: "#ffffff",
                    padding: "12px 20px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "12px",
                    fontSize: "14px",
                    fontWeight: 600,
                    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
                    borderRadius: "8px",
                    marginBottom: "16px",
                    zIndex: 10,
                  }}
                >
                  <span className={`material-symbols-outlined ${indexingStatus.isIndexing ? "spin-animation" : ""}`} style={{ fontSize: "20px", color: indexingStatus.isError ? "#ffcdd2" : "#64c8ff" }}>
                    {indexingStatus.isIndexing ? "sync" : indexingStatus.isError ? "warning" : "check_circle"}
                  </span>
                  <span>
                    {indexingStatus.message
                      ? indexingStatus.message
                      : <>Indexing server <strong>{indexingStatus.serverName}</strong>...</>}
                  </span>
                </div>
              )}
              <div className="header-gradient"></div>
              {(location.pathname === "/" || location.pathname === "/artists") && (
                <BrowseTabs currentMode={viewMode} onModeChange={setViewMode} />
              )}
              <Routes>
                <Route
                  path="/"
                  element={
                    Boolean(debouncedSearchTerm) ? (
                      <ArtistList
                        filteredArtists={filteredArtists}
                        loading={loadingArtists}
                        searchResults={searchResults}
                        isSearching={true}
                        selectedLetter={selectedLetter}
                        scrollTargetLetter={scrollTargetLetter}
                        onSelectLetter={handleScrollLetterChange}
                      />
                    ) : viewMode === "albums" ? (
                      <AlbumsGridView apiBase={getApiUrl("")} selectedLetter={selectedLetter} scrollTargetLetter={scrollTargetLetter} onSelectLetter={handleScrollLetterChange} />
                    ) : viewMode === "genres" ? (
                      <GenresGridView apiBase={getApiUrl("")} />
                    ) : viewMode === "decades" ? (
                      <DecadesGridView apiBase={getApiUrl("")} />
                    ) : (
                      <ArtistList
                        filteredArtists={filteredArtists}
                        loading={loadingArtists}
                        searchResults={searchResults}
                        isSearching={false}
                        selectedLetter={selectedLetter}
                        scrollTargetLetter={scrollTargetLetter}
                        onSelectLetter={handleScrollLetterChange}
                      />
                    )
                  }
                />
                <Route
                  path="/artists"
                  element={
                    Boolean(debouncedSearchTerm) ? (
                      <ArtistList
                        filteredArtists={filteredArtists}
                        loading={loadingArtists}
                        searchResults={searchResults}
                        isSearching={true}
                        selectedLetter={selectedLetter}
                        scrollTargetLetter={scrollTargetLetter}
                        onSelectLetter={handleScrollLetterChange}
                      />
                    ) : viewMode === "albums" ? (
                      <AlbumsGridView apiBase={getApiUrl("")} selectedLetter={selectedLetter} scrollTargetLetter={scrollTargetLetter} onSelectLetter={handleScrollLetterChange} />
                    ) : viewMode === "genres" ? (
                      <GenresGridView apiBase={getApiUrl("")} />
                    ) : viewMode === "decades" ? (
                      <DecadesGridView apiBase={getApiUrl("")} />
                    ) : (
                      <ArtistList
                        filteredArtists={filteredArtists}
                        loading={loadingArtists}
                        searchResults={searchResults}
                        isSearching={false}
                        selectedLetter={selectedLetter}
                        scrollTargetLetter={scrollTargetLetter}
                        onSelectLetter={handleScrollLetterChange}
                      />
                    )
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
              onOpenServerModal={() => setShowServerModal(true)}
              primaryServerName={accessibleServers.find((s) => s.is_primary)?.name || (accessibleServers.length > 0 ? accessibleServers[0].name : "Plex Server")}
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
            <SettingsModal
              adminToken={adminToken}
              onClose={() => setShowSettings(false)}
              instanceName={instanceName}
              setInstanceName={setInstanceName}
              onServerToggled={() => {
                refreshLibraryData();
              }}
            />
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

          {isStatsOpen && <Stats apiBase={apiBase} />}
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
                Welcome! Let's get your details set up your Tukebox.
              </p>
              <div style={{ marginBottom: "25px" }}>
                <label style={labelStyle}>TuneBox Instance Name</label>
                <input type="text" placeholder="e.g. Living Room Jukebox" value={localUsername} onChange={(e) => setLocalUsername(e.target.value)} style={inputStyle} required />
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
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px" }}>Connecting to your TuneBox</p>
              <div style={{ display: "flex", justifyContent: "center", padding: "20px 0" }}>
                <span className="spinner" style={{ display: "inline-block", width: "40px", height: "40px", border: "4px solid #333", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
              </div>
              <div style={{ marginTop: "20px" }}>
                <button
                  type="button"
                  onClick={() => {
                    localStorage.clear();
                    setStep(1);
                    setIsAuthenticated(false);
                    setIsConfigured(false);
                  }}
                  style={{
                    background: "transparent",
                    border: "1px solid rgba(255, 255, 255, 0.2)",
                    color: "#aaa",
                    fontSize: "12px",
                    padding: "8px 16px",
                    borderRadius: "20px",
                    cursor: "pointer",
                  }}
                >
                  Stuck? Restart Setup Wizard
                </button>
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

      <TuneBoxDialog
        open={appDialog.open}
        title={appDialog.title}
        message={appDialog.message}
        onConfirm={() => setAppDialog((prev) => ({ ...prev, open: false }))}
      />
    </ThemeProvider>
  );
}

export default App;
