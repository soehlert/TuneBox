import { Routes, Route, Link } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import ArtistList from "./components/ArtistList";
import ArtistAlbums from "./components/ArtistAlbums";
import TrackList from "./components/TrackList";
import MusicControls from "./components/MusicControls";
import Queue from "./components/Queue";
import theme from "./theme";
import TuneBoxLogo from './assets/TuneBox.svg';
import "./App.css";
import "./components/Queue.css";
import "./components/Pagination.css";

function App() {
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
