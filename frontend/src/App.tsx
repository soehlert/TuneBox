import { Routes, Route, Link } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import ArtistList from "./components/ArtistList";
import ArtistAlbums from "./components/ArtistAlbums";
import TrackList from "./components/TrackList";
import theme from "./theme"; // Import the theme
import "./App.css";

function App() {
  return (
    <ThemeProvider theme={theme}> {/* Wrap your app with the ThemeProvider */}
      <div className="app-container">
        <Link to="/" className="app-title-link">
          <h1 className="app-title">Party Jukebox</h1>
        </Link>
        <Routes>
          <Route path="/" element={<ArtistList />} />
          <Route path="/artists/:artistId/albums" element={<ArtistAlbums />} />
          <Route path="/albums/:albumId/tracks" element={<TrackList />} />
        </Routes>
      </div>
    </ThemeProvider>
  );
}

export default App;
