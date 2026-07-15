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
  const [pinCode, setPinCode] = useState<string>("");
  const [pinId, setPinId] = useState<number | null>(null);
  const [authUrl, setAuthUrl] = useState<string>("");

  useEffect(() => {
    checkStatus();
  }, []);

  const checkStatus = async () => {
    try {
      const res = await axios.get(getApiUrl("/api/auth/status"));
      setIsAuthenticated(res.data.authenticated);
      if (!res.data.authenticated) {
        requestPin();
      }
    } catch (err) {
      console.error("Status check failed, falling back to unauthenticated:", err);
      setIsAuthenticated(false);
      requestPin();
    }
  };

  const requestPin = async () => {
    try {
      const res = await axios.post(getApiUrl("/api/auth/pin"));
      setPinCode(res.data.code);
      setPinId(res.data.pin_id);
      setAuthUrl(res.data.url);
    } catch (err) {
      console.error("Failed to request PIN code:", err);
    }
  };

  useEffect(() => {
    if (isAuthenticated === false && pinId !== null) {
      const timer = setInterval(async () => {
        try {
          const res = await axios.get(getApiUrl(`/api/auth/check?pin_id=${pinId}`));
          if (res.data.authenticated) {
            clearInterval(timer);
            setIsAuthenticated(true);
          }
        } catch (err) {
          console.error("Error checking PIN status:", err);
        }
      }, 3000);
      return () => clearInterval(timer);
    }
  }, [isAuthenticated, pinId]);

  const handleSimulateClaim = async () => {
    try {
      await axios.post(getApiUrl("/api/auth/mock-claim"));
    } catch (err) {
      console.error("Simulation claim failed:", err);
    }
  };

  if (isAuthenticated === null) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#121212", color: "white" }}>
        <h3>Loading TuneBox...</h3>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <ThemeProvider theme={theme}>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#121212", color: "white", padding: "20px" }}>
          <div style={{ background: "#1e1e1e", padding: "40px", borderRadius: "12px", maxWidth: "450px", width: "100%", textAlign: "center", border: "1px solid #333", boxShadow: "0 8px 30px rgba(0,0,0,0.5)" }}>
            <h2 style={{ margin: "0 0 10px 0", color: "#f5a623" }}>Link Plex Account</h2>
            <p style={{ color: "#aaa", fontSize: "14px", marginBottom: "30px" }}>
              To start using TuneBox Jukebox, connect your Plex account.
            </p>
            
            <div style={{ background: "#2a2a2a", padding: "20px", borderRadius: "8px", marginBottom: "25px", fontSize: "36px", letterSpacing: "4px", fontWeight: "bold", fontFamily: "monospace", color: "#fff", border: "1px dashed #555" }}>
              {pinCode || "Loading..."}
            </div>

            <p style={{ color: "#eee", fontSize: "15px", textAlign: "left", margin: "0 0 20px 0", lineHeight: "1.6" }}>
              1. Open <a href="https://plex.tv/link" target="_blank" rel="noopener noreferrer" style={{ color: "#f5a623", textDecoration: "underline" }}>plex.tv/link</a> in a web browser.<br />
              2. Sign in and enter the 4-character code above.
            </p>

            {authUrl && (
              <a href={authUrl} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", width: "100%", padding: "12px", background: "#f5a623", color: "#121212", borderRadius: "6px", textDecoration: "none", fontWeight: "bold", marginBottom: "15px", textAlign: "center", transition: "background 0.2s" }}
                 onMouseOver={(e) => (e.currentTarget.style.background = "#d48b17")}
                 onMouseOut={(e) => (e.currentTarget.style.background = "#f5a623")}>
                Go to Plex Link
              </a>
            )}

            {pinCode === "MOCK" && (
              <button onClick={handleSimulateClaim} style={{ width: "100%", padding: "12px", background: "#333", color: "#f5a623", border: "1px solid #f5a623", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", marginBottom: "15px" }}>
                Simulate Link (Testing)
              </button>
            )}

            <div style={{ color: "#777", fontSize: "12px", display: "flex", justifyContent: "center", alignItems: "center", gap: "8px" }}>
              <span className="spinner" style={{ display: "inline-block", width: "12px", height: "12px", border: "2px solid #555", borderTopColor: "#f5a623", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
              Waiting for Plex authorization...
            </div>
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

        {/* Main content area with artist grid and queue */}
        <div className="main-content">
          <div className="artist-grid-container">
            <Routes>
              <Route path="/" element={<ArtistList />} />
              <Route path="/artists/:artistId/albums" element={<ArtistAlbums />} />
              <Route path="/albums/:albumId/tracks" element={<TrackList />} />
            </Routes>
          </div>

          {/* Queue section (sticky on the right side) */}
          <Queue />
        </div>
      </div>
    </ThemeProvider>
  );
}

export default App;

