import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Typography } from "@mui/material"; // MUI components
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
}

function ArtistList({
  filteredArtists,
  loading,
}: ArtistListProps) {
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  const [visibleCount, setVisibleCount] = useState(48);
  const loaderRef = useRef<HTMLDivElement | null>(null);

  // Reset display count and scroll to top when list of filtered artists changes
  useEffect(() => {
    setVisibleCount(48);
    const mainContent = document.querySelector(".main-content");
    if (mainContent) {
      mainContent.scrollTop = 0;
    }
  }, [filteredArtists]);

  // Set up intersection observer to detect when user scrolls to bottom
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first.isIntersecting) {
          setVisibleCount((prev) => {
            if (prev < filteredArtists.length) {
              return Math.min(prev + 36, filteredArtists.length);
            }
            return prev;
          });
        }
      },
      { threshold: 0.1, rootMargin: "100px" }
    );

    const currentLoader = loaderRef.current;
    if (currentLoader) {
      observer.observe(currentLoader);
    }

    return () => {
      if (currentLoader) {
        observer.unobserve(currentLoader);
      }
    };
  }, [filteredArtists.length]);

  // Function to handle card click and navigate to artist's album page
  const handleArtistClick = (artistId: number) => {
    navigate(`/artists/${artistId}/albums`);
  };

  const currentArtists = filteredArtists.slice(0, visibleCount);

  return (
    <div className="artist-list-wrapper">
      <header className="page-header">
        <Typography variant="h1" className="gradient-text">Artists</Typography>
      </header>
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
                <img
                  src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                  alt={artist.name}
                  className="artist-photo"
                />
                <div className="artist-card-overlay">
                  <Typography className="artist-card-name">{artist.name}</Typography>
                </div>
              </Card>
            ))}
          </div>

          {/* Infinite Scroll Loader Target */}
          {visibleCount < filteredArtists.length && (
            <div ref={loaderRef} className="infinite-scroll-loader">
              <div className="spinner-glass">
                <span className="spinner-inner"></span>
              </div>
              <Typography className="loader-text">Loading more artists...</Typography>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ArtistList;

