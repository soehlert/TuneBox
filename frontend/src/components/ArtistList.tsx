import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Grid, Card, CardContent, Typography, TextField } from "@mui/material"; // MUI components
import Pagination from "./Pagination";
import Queue from "./Queue";
import MusicControls from "./MusicControls";

import "../App.css";
import "./ArtistList.css";

interface Artist {
  artist_id: number;
  name: string;
}

function ArtistList() {
  const [artists, setArtists] = useState<Artist[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [artistsPerPage] = useState(24);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const fetchArtists = async () => {
      try {
        const endpoint = searchTerm
          ? `http://localhost:8000/api/music/search?query=${encodeURIComponent(searchTerm)}`
          : "http://localhost:8000/api/music/artists";

        const response = await axios.get(endpoint);
        let data = response.data;

        if (searchTerm) {
          data = data.filter((item: any) => item.type === "artist");
        }

        const sortedArtists = data.sort((a: Artist, b: Artist) =>
          a.name ? a.name.localeCompare(b.name || "") : -1
        );

        setArtists(sortedArtists);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchArtists();
  }, [searchTerm]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);

  const indexOfLastArtist = currentPage * artistsPerPage;
  const indexOfFirstArtist = indexOfLastArtist - artistsPerPage;
  const currentArtists = artists.slice(indexOfFirstArtist, indexOfLastArtist);

  const paginate = (pageNumber: number) => setCurrentPage(pageNumber);

  return (
    <div className="app-container">
      <MusicControls />
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
          <>
            <Grid container spacing={2}>
              {currentArtists.map((artist) => (
                <Grid item xs={12} sm={6} md={4} key={artist.artist_id}>
                  <Card
                    className="artist-card"
                    onClick={() => navigate(`/artists/${artist.artist_id}/albums`)}
                    style={{ cursor: "pointer" }}
                  >
                    <CardContent>
                      <Typography variant="h6">{artist.name}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>

            <Pagination
              className="pagination"  // Pass className here for custom styles
              currentPage={currentPage}
              totalPages={Math.ceil(artists.length / artistsPerPage)}
              paginate={paginate}
            />
          </>
        )}
      </div>

      {/* Ensure Queue is placed on the right */}
      <Queue />
    </div>
  );
}

export default ArtistList;
