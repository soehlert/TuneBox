import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, Typography, TextField } from "@mui/material"; // MUI components
import Pagination from "./Pagination";
import "../App.css";
import "./ArtistList.css";

// Utility for debouncing
const useDebounce = (value: string, delay: number) => {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

interface Artist {
  artist_id: number;
  name: string;
  thumb?: string;
}

function ArtistList() {
  const [artists, setArtists] = useState<Artist[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [artistsPerPage] = useState(24);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filteredArtists, setFilteredArtists] = useState<Artist[]>([]);

  // Using the debounced search term
  const debouncedSearchTerm = useDebounce(searchTerm, 300);
  const navigate = useNavigate();

// Fetch artists and filter them based on the search term
useEffect(() => {
  const fetchArtists = async () => {
    try {
      const endpoint = debouncedSearchTerm
        ? `http://localhost:8000/api/music/search?query=${encodeURIComponent(searchTerm)}`
        : "http://localhost:8000/api/music/artists";

      const response = await axios.get(endpoint);
      let data = response.data;

      // Only keep artists (exclude albums, tracks, etc.)
      data = data.filter((item: any) => item.name);

      // Sort the fetched data alphabetically by artist name
      const sortedArtists = data.sort((a: Artist, b: Artist) =>
        a.name && b.name ? a.name.localeCompare(b.name) : -1
      );

      setArtists(sortedArtists);
      setFilteredArtists(sortedArtists);
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setLoading(false);
    }
  };
  if (debouncedSearchTerm == "" || debouncedSearchTerm) {
      fetchArtists();
    } else {
      setLoading(false);
      setArtists([]); // Clear artists if no search term
    }
  }, [debouncedSearchTerm]);

// Reset pagination whenever search term changes
useEffect(() => {
  setCurrentPage(1);
}, [filteredArtists]);


  // Handle clicking a letter on the alphabet filter
  const handleAlphabetClick = (letter: string) => {
    const filtered = artists.filter(artist =>
      artist.name[0].toUpperCase() === letter.toUpperCase() // Filter artists by first letter
    );

    setFilteredArtists(filtered);
    setCurrentPage(1); // Reset pagination to first page

    // Scroll to the first matching artist
    if (filtered.length > 0) {
      const firstArtistElement = document.getElementById(`artist-${filtered[0].artist_id}`);
      if (firstArtistElement) {
        firstArtistElement.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  };

  // Function to handle card click and navigate to artist's album page
  const handleArtistClick = (artistId: number) => {
    // Assuming the album page URL pattern is "/albums/:artistId"
    navigate(`/artists/${artistId}/albums`);
  };

  const indexOfLastArtist = currentPage * artistsPerPage;
  const indexOfFirstArtist = indexOfLastArtist - artistsPerPage;
  const currentArtists = filteredArtists.slice(indexOfFirstArtist, indexOfLastArtist);

  const paginate = (pageNumber: number) => setCurrentPage(pageNumber);

  return (
    <div className="app-container">
      <div className="content-container">
        <TextField
          label="Search Artists"
          variant="outlined"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          fullWidth
          margin="normal"
        />

        {loading ? (
          <Typography variant="h6">Loading...</Typography>
        ) : (
          <div className="artist-list-container">
            {/* Alphabet filter */}
            <div className="alphabet-filter">
              {"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((letter) => (
                <button
                  key={letter}
                  onClick={() => handleAlphabetClick(letter)}  // Update the filtered artists and scroll
                  className={searchTerm === letter ? "active" : ""}
                >
                  {letter}
                </button>
              ))}
            </div>

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
                    {artist.thumb && (
                      <img
                        src={artist.thumb}
                        alt={artist.name}
                        className="artist-photo"
                      />
                    )}
                    <Typography variant="h6">
                      {artist.name}
                    </Typography>
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
