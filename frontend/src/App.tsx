import { useState, useEffect } from "react";
import { Routes, Route, Link } from "react-router-dom";
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
import "./components/Pagination.css";

const getApiUrl = (path: string) => {
  const isDev = window.location.port === "5173";
  const base = isDev ? "http://localhost:8000" : window.location.origin;
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
  const host = isDev ? "localhost:8000" : window.location.host;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${host}/ws`;
};

// ─── Shared style helpers ─────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px",
  background: "#2a2a2a",
  color: "#fff",
  border: "1px solid #444",
  borderRadius: "6px",
  fontSize: "14px",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: "14px",
  background: "#f5a623",
  color: "#121212",
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

// ─── Settings Modal ───────────────────────────────────────────────────────────

interface SettingsModalProps {
  adminToken: string;
  onClose: () => void;
}

function SettingsModal({ adminToken, onClose }: SettingsModalProps) {
  const [plexUsername, setPlexUsername] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [servers, setServers] = useState<string[]>([]);
  const [selectedServer, setSelectedServer] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [clients, setClients] = useState<ClientSession[]>([]);

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
        setInstanceName(res.data.client_name ?? "");
        setSelectedServer(res.data.plex_server_name ?? "");
      })
      .catch(console.error);

    axios
      .get(getApiUrl("/api/auth/resources"))
      .then((res) => {
        setServers(res.data.servers ?? []);
      })
      .catch(console.error);
  }, [adminToken]);

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

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      await axios.post(
        getApiUrl("/api/auth/settings"),
        { plex_username: plexUsername, client_name: instanceName, plex_server_name: selectedServer },
        { headers: { "x-admin-token": adminToken } }
      );
      setMsg("✓ Settings saved!");
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
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#1e1e1e",
          border: "1px solid #333",
          borderRadius: "12px",
          padding: "36px",
          width: "480px",
          maxWidth: "90vw",
          boxShadow: "0 20px 60px rgba(0,0,0,0.8)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
          <h2 style={{ margin: 0, color: "#f5a623", fontSize: "20px" }}>⚙ Jukebox Settings</h2>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "#777", fontSize: "22px", cursor: "pointer" }}
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
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              style={inputStyle}
            />
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

          <button
            type="submit"
            disabled={saving}
            style={btnStyle}
            onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
            onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </form>

        <div style={{ marginTop: "24px", borderTop: "1px solid #333", paddingTop: "20px" }}>
          <h3 style={{ margin: "0 0 12px 0", color: "#f5a623", fontSize: "16px" }}>💻 Connected Devices</h3>
          {clients.filter(c => c.client_id !== getClientId()).length === 0 ? (
            <p style={{ color: "#777", fontSize: "13px", margin: 0 }}>No other devices connected.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "150px", overflowY: "auto" }}>
              {clients.filter(c => c.client_id !== getClientId()).map((c) => (
                <div
                  key={c.client_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: "#2a2a2a",
                    borderRadius: "6px",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <span style={{ color: "#fff", fontSize: "14px", fontWeight: "bold" }}>
                      {c.name}
                    </span>
                    <span style={{ color: "#888", fontSize: "11px", textTransform: "capitalize" }}>
                      Role: {c.role} {c.is_display && "• Display"}
                    </span>
                  </div>
                  {c.is_display ? (
                    <span style={{ color: "#5cdd5c", fontSize: "12px", fontWeight: "bold" }}>
                      ✓ Display
                    </span>
                  ) : (
                    <button
                      onClick={() => handleSetDisplay(c.client_id)}
                      style={{
                        background: "#f5a623",
                        color: "#121212",
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
      </div>
    </div>
  );
}

// ─── Guest Registration Modal ─────────────────────────────────────────────────

interface GuestModalProps {
  onJoin: (profile: GuestProfile) => void;
}

function GuestModal({ onJoin }: GuestModalProps) {
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

function UserBadge({ profile, onLeave }: { profile: GuestProfile; onLeave: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "6px 12px",
        background: "#1e1e1e",
        borderRadius: "20px",
        border: "1px solid #333",
        cursor: "pointer",
        fontSize: "13px",
        color: "#ccc",
      }}
      title="Click to leave"
      onClick={onLeave}
    >
      <span style={{ color: profile.role === "member" ? "#5cdd5c" : "#f5a623" }}>
        {profile.role === "member" ? "✓" : "◉"}
      </span>
      <span>{profile.name}</span>
      {profile.role === "member" && (
        <span style={{ fontSize: "10px", background: "#1a3a1a", color: "#5cdd5c", padding: "2px 6px", borderRadius: "10px", fontWeight: "bold" }}>
          2× votes
        </span>
      )}
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
  const [plexUsername, setPlexUsername] = useState<string>("");
  const [localUsername, setLocalUsername] = useState<string>("");

  // Resources
  const [servers, setServers] = useState<string[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [isManualConfig, setIsManualConfig] = useState<boolean>(false);
  const [customServer, setCustomServer] = useState<string>("");
  const [isFetchingResources, setIsFetchingResources] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Admin / guest state — must be React state so changes trigger re-renders
  const [adminToken, setAdminToken] = useState<string>(
    () => localStorage.getItem("tunebox_admin_token") ?? ""
  );
  const isAdmin = Boolean(adminToken);
  const [showSettings, setShowSettings] = useState(false);
  const [guestProfile, setGuestProfile] = useState<GuestProfile | null>(() => {
    const raw = localStorage.getItem("tunebox_guest");
    return raw ? (JSON.parse(raw) as GuestProfile) : null;
  });

  // Display / kiosk mode — designated by the admin; persists in localStorage
  const [isDisplay, setIsDisplay] = useState<boolean>(
    () => localStorage.getItem("tunebox_display") === "true"
  );

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
          name = `Admin (${localUsername || "Owner"})`;
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
  }, [isAdmin, isDisplay, guestProfile, localUsername]);

  useEffect(() => {
    checkStatus();
  }, []);

  const checkStatus = async () => {
    try {
      const res = await axios.get(getApiUrl("/api/auth/status"));
      setIsAuthenticated(res.data.authenticated);
      setIsConfigured(res.data.is_configured);

      if (res.data.plex_username) setPlexUsername(res.data.plex_username);
      if (res.data.client_name) setLocalUsername(res.data.client_name);

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
    if (!serverName) {
      alert("Please select or enter a Plex server name.");
      setIsSubmitting(false);
      return;
    }
    try {
      const res = await axios.post(getApiUrl("/api/auth/configure"), {
        plex_username: plexUsername,
        client_name: localUsername,
        plex_server_name: serverName,
      });
      // Store admin token and update state so gear icon appears immediately
      if (res.data.admin_token) {
        localStorage.setItem("tunebox_admin_token", res.data.admin_token);
        setAdminToken(res.data.admin_token);
      }
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
          {/* Navbar */}
          <div className="navbar">
            <Link to="/" className="app-title-link">
              <img src={TuneBoxLogo} alt="TuneBox Logo" className="logo" />
            </Link>
            <div className="music-controls-container">
              <MusicControls />
            </div>
            {/* User badge (top-right, for guests who have joined) */}
            {!isAdmin && guestProfile && (
              <div style={{ marginLeft: "auto", paddingRight: "16px" }}>
                <UserBadge profile={guestProfile} onLeave={handleGuestLeave} />
              </div>
            )}
          </div>

          {/* Main content area */}
          <div className="main-content">
            <div className="artist-grid-container">
              <Routes>
                <Route path="/" element={<ArtistList />} />
                <Route path="/artists/:artistId/albums" element={<ArtistAlbums />} />
                <Route path="/albums/:albumId/tracks" element={<TrackList />} />
              </Routes>
            </div>

            {/* Sidebar: Queue + QR Code (non-admin shared display) */}
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <Queue />
              {isDisplay && (
                <div
                  style={{
                    background: "#1e1e1e",
                    border: "1px solid #2a2a2a",
                    borderRadius: "12px",
                    padding: "20px",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "12px",
                  }}
                >
                  <p style={{ color: "#aaa", fontSize: "12px", margin: 0, textAlign: "center", fontWeight: "bold", letterSpacing: "0.5px", textTransform: "uppercase" }}>
                    Scan to Join
                  </p>
                  <QRCodeSVG
                    value={joinUrl}
                    size={140}
                    bgColor="#1e1e1e"
                    fgColor="#f5a623"
                    level="M"
                  />
                  <p style={{ color: "#555", fontSize: "11px", margin: 0, textAlign: "center" }}>
                    {joinUrl}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Admin Settings Gear — bottom-left, admin-only */}
          {isAdmin && (
            <button
              onClick={() => setShowSettings(true)}
              style={{
                position: "fixed",
                bottom: "24px",
                left: "24px",
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "#2a2a2a",
                border: "1px solid #444",
                color: "#f5a623",
                fontSize: "22px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 4px 16px rgba(0,0,0,0.6)",
                transition: "background 0.2s, transform 0.2s",
                zIndex: 100,
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = "#383838";
                e.currentTarget.style.transform = "scale(1.1)";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = "#2a2a2a";
                e.currentTarget.style.transform = "scale(1)";
              }}
              title="Settings"
            >
              ⚙
            </button>
          )}

          {/* Settings Modal */}
          {showSettings && isAdmin && (
            <SettingsModal adminToken={adminToken} onClose={() => setShowSettings(false)} />
          )}

          {/* Guest Registration Modal — only for non-admin, non-display devices without a profile */}
          {!isAdmin && !isDisplay && !guestProfile && (
            <GuestModal onJoin={(profile) => setGuestProfile(profile)} />
          )}
        </div>
      </ThemeProvider>
    );
  }

  // ── Setup Wizard ─────────────────────────────────────────────────────────────
  return (
    <ThemeProvider theme={theme}>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#121212", color: "white", padding: "20px" }}>
        <div style={{ background: "#1e1e1e", padding: "40px", borderRadius: "12px", maxWidth: "480px", width: "100%", textAlign: "center", border: "1px solid #333", boxShadow: "0 8px 30px rgba(0,0,0,0.5)" }}>

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
                  ) : (
                    <div style={{ marginBottom: "20px" }}>
                      <label style={labelStyle}>Custom Plex Server Name</label>
                      <input type="text" placeholder="e.g. MyHomeServer" value={customServer} onChange={(e) => setCustomServer(e.target.value)} style={inputStyle} required />
                    </div>
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
