import { createTheme } from "@mui/material/styles";

// Create theme with custom colors
const theme = createTheme({
  palette: {
    primary: {
      main: "#E59500", // Orange accent for primary buttons
    },
    secondary: {
      main: "#0077B6", // Blue for secondary buttons and highlights
    },
    background: {
      default: "#1d083b", // Deep dark purple background
      paper: "rgba(42, 13, 82, 0.4)", // Translucent dark purple paper
    },
    text: {
      primary: "#EEEEEE", // Light gray text color
      secondary: "#686D76", // Muted gray for secondary text
    },
  },
  typography: {
    fontFamily: "Inter, sans-serif",
    h1: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#EEEEEE",
    },
    h2: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#E59500",
    },
    h3: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#E59500",
    },
    h4: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#E59500",
    },
    h5: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#EEEEEE",
    },
    h6: {
      fontFamily: "Montserrat, sans-serif",
      fontWeight: 700,
      color: "#EEEEEE",
    },
    body1: {
      fontFamily: "Inter, sans-serif",
      color: "#EEEEEE",
    },
    body2: {
      fontFamily: "Inter, sans-serif",
      color: "#EEEEEE",
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          color: "#FFFFFF", // White text color for all cards
          boxShadow: "0 4px 16px rgba(0, 0, 0, 0.4)",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          color: "#FFFFFF",
        },
      },
    },
  },
});

export default theme;
