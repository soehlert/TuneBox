import { useState, useEffect } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import axios from "axios";
import ArtistList from "./components/ArtistList";
import ArtistAlbums from "./components/ArtistAlbums";
import TrackList from "./components/TrackList";
import MusicControls from "./components/MusicControls";
import Queue from "./components/Queue";
import theme from "./theme";
import TuneBoxLogo from '../public/TuneBox.svg';
import "./App.css";
import "./components/Queue.css";
import "./components/Pagination.css";

const getApiUrl = (path: string) => {
  const isDev = window.location.port === "5173";
  const base = isDev ? "http://localhost:8000" : window.location.origin;
  return `${base}${path}`;
};

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);

  // Wizard States
  const [step, setStep] = useState<number>(1);
  const [pinCode, setPinCode] = useState<string>("");
  const [pinId, setPinId] = useState<number | null>(null);
  const [authUrl, setAuthUrl] = useState<string>("");

  // Input States
  const [plexUsername, setPlexUsername] = useState<string>("");
  const [localUsername, setLocalUsername] = useState<string>(""); // TuneBox Instance Name

  // Discovered Resources
  const [servers, setServers] = useState<string[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [isManualConfig, setIsManualConfig] = useState<boolean>(false);
  const [customServer, setCustomServer] = useState<string>("");
  const [isFetchingResources, setIsFetchingResources] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

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
      await axios.post(getApiUrl("/api/auth/configure"), {
        plex_username: plexUsername,
        client_name: localUsername,
        plex_server_name: serverName
      });
      setIsConfigured(true);
      setStep(4);
    } catch (err) {
      console.error("Save config failed:", err);
      alert("Failed to save configuration settings.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isAuthenticated === null) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#121212", color: "white" }}>
        <h3>Loading TuneBox...</h3>
      </div>
    );
  }

  // If authenticated and configured, show Jukebox player
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
            <Queue />
          </div>
        </div>
      </ThemeProvider>
    );
  }

  // Otherwise, render Wizard Screen
  return (
    <ThemeProvider theme={theme}>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#121212", color: "white", padding: "20px" }}>
        <div style={{ background: "#1e1e1e", padding: "40px", borderRadius: "12px", maxWidth: "480px", width: "100%", textAlign: "center", border: "1px solid #333", boxShadow: "0 8px 30px rgba(0,0,0,0.5)" }}>

          <img src={TuneBoxLogo} alt="TuneBox Logo" style={{ height: "45px", marginBottom: "25px" }} />

          {/* STEP 1: PROFILE SETUP */}
          {step === 1 && (
            <form onSubmit={handleStartLinking} style={{ textAlign: "left" }}>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623", textAlign: "center" }}>First Setup Wizard</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px", lineHeight: "1.5", textAlign: "center" }}>
                Welcome! Let's get your details set up to link your Jukebox.
              </p>

              {/* User inputs */}
              <div style={{ marginBottom: "20px" }}>
                <label style={{ display: "block", color: "#ccc", fontSize: "13px", fontWeight: "bold", marginBottom: "8px" }}>Plex Username</label>
                <input type="text" placeholder="e.g. plex_user" value={plexUsername} onChange={(e) => setPlexUsername(e.target.value)} style={{ width: "100%", padding: "10px", background: "#2a2a2a", color: "#fff", border: "1px solid #444", borderRadius: "6px", fontSize: "14px", boxSizing: "border-box" }} required />
              </div>

              <div style={{ marginBottom: "25px" }}>
                <label style={{ display: "block", color: "#ccc", fontSize: "13px", fontWeight: "bold", marginBottom: "8px" }}>TuneBox Instance Name</label>
                <input type="text" placeholder="e.g. Steve's Jukebox" value={localUsername} onChange={(e) => setLocalUsername(e.target.value)} style={{ width: "100%", padding: "10px", background: "#2a2a2a", color: "#fff", border: "1px solid #444", borderRadius: "6px", fontSize: "14px", boxSizing: "border-box" }} required />
              </div>

              <button type="submit" style={{ width: "100%", padding: "14px", background: "#f5a623", color: "#121212", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "15px", marginTop: "15px", transition: "background 0.2s" }}
                onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                Connect to Plex
              </button>
            </form>
          )}

          {/* STEP 2: LINK PLEX ACCOUNT */}
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
                2. Sign in as **{plexUsername}** and enter the 4-character code above.
              </p>

              {authUrl && (
                <a href={authUrl} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", width: "100%", padding: "12px", background: "#f5a623", color: "#121212", borderRadius: "6px", textDecoration: "none", fontWeight: "bold", marginBottom: "15px", textAlign: "center", transition: "background 0.2s" }}
                   onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                   onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                  Go to Plex Link
                </a>
              )}

              <div style={{ color: "#777", fontSize: "12px", display: "flex", justifyContent: "center", alignItems: "center", gap: "8px" }}>
                <span className="spinner" style={{ display: "inline-block", width: "12px", height: "12px", border: "2px solid #555", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
                Waiting for Plex authorization...
              </div>
            </div>
          )}

          {/* STEP 3: SERVER SELECTION */}
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
                      <label style={{ display: "block", color: "#ccc", fontSize: "13px", fontWeight: "bold", marginBottom: "8px" }}>Plex Media Server</label>
                      {servers.length > 0 ? (
                        <select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)} style={{ width: "100%", padding: "10px", background: "#2a2a2a", color: "#fff", border: "1px solid #444", borderRadius: "6px", fontSize: "14px" }}>
                          {servers.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      ) : (
                        <div style={{ color: "#ff6b6b", fontSize: "13px", padding: "5px 0" }}>No Plex Media Servers found.</div>
                      )}
                    </div>
                  ) : (
                    <div style={{ marginBottom: "20px" }}>
                      <label style={{ display: "block", color: "#ccc", fontSize: "13px", fontWeight: "bold", marginBottom: "8px" }}>Custom Plex Server Name</label>
                      <input type="text" placeholder="e.g. MyHomeServer" value={customServer} onChange={(e) => setCustomServer(e.target.value)} style={{ width: "100%", padding: "10px", background: "#2a2a2a", color: "#fff", border: "1px solid #444", borderRadius: "6px", fontSize: "14px", boxSizing: "border-box" }} required />
                    </div>
                  )}

                  {/* Manual config override toggle */}
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "25px 0 25px 0" }}>
                    <input type="checkbox" id="manual-toggle" checked={isManualConfig} onChange={(e) => setIsManualConfig(e.target.checked)} style={{ cursor: "pointer" }} />
                    <label htmlFor="manual-toggle" style={{ color: "#aaa", fontSize: "13px", cursor: "pointer", userSelect: "none" }}>Configure server manually</label>
                  </div>

                  <button type="submit" disabled={isSubmitting} style={{ width: "100%", padding: "14px", background: "#f5a623", color: "#121212", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "15px", transition: "background 0.2s" }}
                    onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                    onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                    {isSubmitting ? "Saving Configuration..." : "Save & Finish Setup"}
                  </button>
                </div>
              )}
            </form>
          )}

          {/* STEP 4: DONE STATE (TRANSITIONING) */}
          {step === 4 && (
            <div>
              <h2 style={{ margin: "0 0 10px 0", color: "#f5a623" }}>Setup Completed!</h2>
              <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px" }}>
                Connecting to your Jukebox...
              </p>
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
