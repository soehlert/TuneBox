import { useNavigate } from "react-router-dom";
import { Card, CardContent, Typography } from "@mui/material"; // MUI components
import Pagination from "./Pagination";
import "../App.css";
import "./ArtistList.css";

interface Artist {
  artist_id: number;
  name: string;
  thumb?: string;
}

interface ArtistListProps {
  filteredArtists: Artist[];
  loading: boolean;
  currentPage: number;
  setCurrentPage: (page: number) => void;
  artistsPerPage: number;
}

function ArtistList({
  filteredArtists,
  loading,
  currentPage,
  setCurrentPage,
  artistsPerPage,
}: ArtistListProps) {
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? "http://localhost:8000" : window.location.origin;

  // Function to handle card click and navigate to artist's album page
  const handleArtistClick = (artistId: number) => {
    navigate(`/artists/${artistId}/albums`);
  };

  const indexOfLastArtist = currentPage * artistsPerPage;
  const indexOfFirstArtist = indexOfLastArtist - artistsPerPage;
  const currentArtists = filteredArtists.slice(indexOfFirstArtist, indexOfLastArtist);

  const paginate = (pageNumber: number) => setCurrentPage(pageNumber);

  return (
    <div className="app-container" style={{ minHeight: "auto", padding: 0 }}>
      <div className="content-container" style={{ padding: 0, width: "100%" }}>
        {loading ? (
          <Typography variant="h6">Loading...</Typography>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px", width: "100%" }}>
            {/* Artist grid */}
            <div className="artist-grid">
              {currentArtists.map((artist) => (
                <Card
                  className="artist-card"
                  key={artist.artist_id}
                  id={`artist-${artist.artist_id}`}
                  onClick={() => handleArtistClick(artist.artist_id)}
                >
                  <CardContent>
                    <img
                      src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                      alt={artist.name}
                      className="artist-photo"
                    />
                    <Typography variant="h6">{artist.name}</Typography>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Pagination */}
            <Pagination
              className="pagination"
              currentPage={currentPage}
              totalPages={Math.ceil(filteredArtists.length / artistsPerPage)}
              paginate={paginate}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default ArtistList;
